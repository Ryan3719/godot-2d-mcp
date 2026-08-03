@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const TypePolicy := preload("res://addons/godot_2d_mcp/utils/type_policy.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_PROPERTIES_PER_REQUEST := 64
const MAX_PROPERTY_RESULTS := 512
const PROTECTED_PROPERTIES := {
	"owner": true,
	"scene_file_path": true,
	"script": true,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_properties(params: Dictionary) -> Dictionary:
	var resolved := _resolve_node(params, false)
	if resolved.has("_error"):
		return resolved
	var node: Node = resolved["node"]
	var scene_root: Node = resolved["scene_root"]
	var fields: Array = params.get("fields", [])
	var requested: Dictionary = {}
	for field_value in fields:
		requested[str(field_value)] = true

	var properties: Array[Dictionary] = []
	var found: Dictionary = {}
	var truncated := false
	for property_info_value in node.get_property_list():
		var property_info: Dictionary = property_info_value
		var property_name := str(property_info.get("name", ""))
		if property_name.is_empty():
			continue
		if not requested.is_empty() and not requested.has(property_name):
			continue
		var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
		if not _is_public_property(usage):
			continue
		if properties.size() >= MAX_PROPERTY_RESULTS:
			truncated = true
			break
		found[property_name] = true
		properties.append(_serialize_property(node, property_info))

	var missing_fields: Array[String] = []
	for field_value in fields:
		var field_name := str(field_value)
		if not found.has(field_name):
			missing_fields.append(field_name)

	return {
		"path": ScenePath.from_node(node, scene_root),
		"type": node.get_class(),
		"properties": properties,
		"count": properties.size(),
		"missing_fields": missing_fields,
		"truncated": truncated,
	}


func create_node(params: Dictionary) -> Dictionary:
	var guarded := MutationGuard.require_scene(params)
	if guarded.has("_error"):
		return guarded
	var scene_root: Node = guarded["scene_root"]
	var type_name := str(params.get("type", "")).strip_edges()
	if type_name.is_empty():
		return Errors.make("MISSING_PARAMETER", "type is required")
	if not TypePolicy.is_supported_node_class(StringName(type_name)):
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"Node type is not allowed by the 2D policy: %s" % type_name,
			false,
			"Use class_search to select a supported 2D node type."
		)

	var parent_path := str(params.get("parent_path", ""))
	var parent := ScenePath.resolve(parent_path, scene_root)
	if parent == null:
		return Errors.make(
			"NODE_NOT_FOUND",
			"Parent node not found: %s" % parent_path,
			false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if not TypePolicy.is_supported_node_class(parent.get_class()):
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"Parent node is outside the supported 2D policy: %s" % parent.get_class()
		)
	var parent_editability := _require_locally_owned(parent, scene_root, "create children under")
	if parent_editability != null:
		return parent_editability

	var requested_name := str(params.get("name", "")).strip_edges()
	if requested_name.is_empty():
		requested_name = type_name
	if requested_name.length() > 256 or requested_name.validate_node_name() != requested_name:
		return Errors.make("INVALID_NODE_NAME", "Invalid node name: %s" % requested_name)
	for sibling in parent.get_children(false):
		if String(sibling.name) == requested_name:
			return Errors.make(
				"NODE_NAME_CONFLICT",
				"Parent already has a child named '%s'" % requested_name,
				false,
				"Choose a unique sibling name."
			)

	var created_object := ClassDB.instantiate(StringName(type_name))
	if not created_object is Node:
		if created_object != null:
			created_object.free()
		return Errors.make("INSTANTIATION_FAILED", "Failed to instantiate node type: %s" % type_name)
	var created_node: Node = created_object
	created_node.name = requested_name

	_undo_redo.create_action(
		"Godot 2D MCP: Create %s" % requested_name,
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_method(parent, "add_child", created_node, true)
	_undo_redo.add_do_method(created_node, "set_owner", scene_root)
	_undo_redo.add_do_reference(created_node)
	_undo_redo.add_undo_method(parent, "remove_child", created_node)
	_undo_redo.commit_action()

	return {
		"path": ScenePath.from_node(created_node, scene_root),
		"parent_path": ScenePath.from_node(parent, scene_root),
		"name": String(created_node.name),
		"type": created_node.get_class(),
		"undoable": true,
		"_scene_mutated": true,
	}


func set_properties(params: Dictionary) -> Dictionary:
	var resolved := _resolve_node(params)
	if resolved.has("_error"):
		return resolved
	var node: Node = resolved["node"]
	var scene_root: Node = resolved["scene_root"]
	var editability := _require_locally_owned(node, scene_root, "update")
	if editability != null:
		return editability
	var requested = params.get("properties", {})
	if not requested is Dictionary or requested.is_empty():
		return Errors.make("MISSING_PARAMETER", "properties must be a non-empty object")
	if requested.size() > MAX_PROPERTIES_PER_REQUEST:
		return Errors.make(
			"REQUEST_LIMIT_EXCEEDED",
			"A single update can contain at most %d properties" % MAX_PROPERTIES_PER_REQUEST
		)

	var property_info_by_name: Dictionary = {}
	for property_info_value in node.get_property_list():
		var property_info: Dictionary = property_info_value
		property_info_by_name[str(property_info.get("name", ""))] = property_info

	var changes: Array[Dictionary] = []
	var unchanged: Array[String] = []
	for property_name_value in requested:
		var property_name := str(property_name_value)
		if not property_info_by_name.has(property_name):
			return Errors.make(
				"PROPERTY_NOT_FOUND",
				"Property '%s' does not exist on %s" % [property_name, node.get_class()],
				false,
				"Call node_get_properties to inspect writable properties.",
				{"property": property_name, "node_type": node.get_class()}
			)
		var property_info: Dictionary = property_info_by_name[property_name]
		var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
		if not _is_writable_property(property_name, usage):
			return Errors.make(
				"PROPERTY_NOT_WRITABLE",
				"Property '%s' is not writable through this tool" % property_name,
				false,
				"Use a public editable property returned by node_get_properties.",
				{"property": property_name}
			)
		var old_value = node.get(property_name)
		var decoded := VariantCodec.decode(requested[property_name_value], property_info, old_value)
		if decoded.has("_error"):
			decoded["_error"]["details"]["property"] = property_name
			return decoded
		var new_value = decoded["value"]
		if old_value == new_value:
			unchanged.append(property_name)
			continue
		changes.append(
			{
				"name": property_name,
				"old_value": old_value,
				"new_value": new_value,
			}
		)

	if changes.is_empty():
		return {
			"path": ScenePath.from_node(node, scene_root),
			"updated": {},
			"unchanged": unchanged,
			"undoable": false,
		}

	_undo_redo.create_action(
		"Godot 2D MCP: Update %s" % node.name,
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	for change in changes:
		_undo_redo.add_do_property(node, change["name"], change["new_value"])
		_undo_redo.add_undo_property(node, change["name"], change["old_value"])
	_undo_redo.commit_action()

	var updated := {}
	for change in changes:
		updated[change["name"]] = VariantCodec.serialize(node.get(change["name"]))
	return {
		"path": ScenePath.from_node(node, scene_root),
		"updated": updated,
		"unchanged": unchanged,
		"undoable": true,
		"_scene_mutated": true,
	}


func delete_node(params: Dictionary) -> Dictionary:
	var resolved := _resolve_node(params)
	if resolved.has("_error"):
		return resolved
	var node: Node = resolved["node"]
	var scene_root: Node = resolved["scene_root"]
	if node == scene_root:
		return Errors.make("SCENE_ROOT_PROTECTED", "The edited scene root cannot be deleted")
	var editability := _require_locally_owned(node, scene_root, "delete")
	if editability != null:
		return editability

	var parent := node.get_parent()
	var child_index := node.get_index(false)
	var owner_records := _capture_owners(node)
	var original_path := ScenePath.from_node(node, scene_root)
	_undo_redo.create_action(
		"Godot 2D MCP: Delete %s" % node.name,
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_method(parent, "remove_child", node)
	_undo_redo.add_undo_method(parent, "add_child", node, true)
	_undo_redo.add_undo_method(parent, "move_child", node, child_index)
	for record in owner_records:
		_undo_redo.add_undo_method(record["node"], "set_owner", record["owner"])
	_undo_redo.add_undo_reference(node)
	_undo_redo.commit_action()

	return {
		"path": original_path,
		"deleted": true,
		"undoable": true,
		"_scene_mutated": true,
	}


func _capture_owners(root: Node) -> Array[Dictionary]:
	var records: Array[Dictionary] = []
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		records.append({"node": node, "owner": node.owner})
		var children := node.get_children(false)
		for index in range(children.size() - 1, -1, -1):
			stack.append(children[index])
	return records


func _resolve_node(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var guarded := MutationGuard.require_scene(params, require_writable)
	if guarded.has("_error"):
		return guarded
	var scene_root: Node = guarded["scene_root"]
	var requested_path := str(params.get("path", ""))
	if requested_path.is_empty():
		return Errors.make("MISSING_PARAMETER", "path is required")
	var node := ScenePath.resolve(requested_path, scene_root)
	if node == null:
		return Errors.make(
			"NODE_NOT_FOUND",
			"Node not found: %s" % requested_path,
			false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if not TypePolicy.is_supported_node_class(node.get_class()):
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"Node is outside the supported 2D policy: %s" % node.get_class()
		)
	return {"node": node, "scene_root": scene_root}


func _serialize_property(node: Node, property_info: Dictionary) -> Dictionary:
	var property_name := str(property_info.get("name", ""))
	var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
	return {
		"name": property_name,
		"type": type_string(int(property_info.get("type", TYPE_NIL))),
		"class_name": str(property_info.get("class_name", "")),
		"hint": int(property_info.get("hint", PROPERTY_HINT_NONE)),
		"hint_string": str(property_info.get("hint_string", "")),
		"read_only": not _is_writable_property(property_name, usage),
		"value": VariantCodec.serialize(node.get(property_name)),
	}


func _is_public_property(usage: int) -> bool:
	return bool(usage & PROPERTY_USAGE_EDITOR) or bool(usage & PROPERTY_USAGE_STORAGE)


func _is_writable_property(property_name: String, usage: int) -> bool:
	return (
		_is_public_property(usage)
		and not bool(usage & PROPERTY_USAGE_READ_ONLY)
		and not PROTECTED_PROPERTIES.has(property_name)
	)


func _require_locally_owned(node: Node, scene_root: Node, operation: String) -> Variant:
	if node == scene_root or node.owner == scene_root:
		return null
	return Errors.make(
		"PACKED_SCENE_BOUNDARY",
		"Cannot %s node '%s' because it belongs to an instanced scene" % [operation, node.name],
		false,
		"Edit the source PackedScene or target its locally owned instance root."
	)

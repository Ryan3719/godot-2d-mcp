@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const NodePathMigration := preload("res://addons/godot_2d_mcp/utils/node_path_migration.gd")
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
	var script_result := _load_supported_node_script(
		str(params.get("script_path", "")).strip_edges(), StringName(type_name)
	)
	if script_result.has("_error"):
		return script_result
	var script: Script = script_result["script"]

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
	if script != null:
		_undo_redo.add_do_property(created_node, "script", script)
		_undo_redo.add_undo_property(created_node, "script", null)
	_undo_redo.add_do_reference(created_node)
	_undo_redo.add_undo_method(parent, "remove_child", created_node)
	_undo_redo.commit_action()

	return {
		"path": ScenePath.from_node(created_node, scene_root),
		"parent_path": ScenePath.from_node(parent, scene_root),
		"name": String(created_node.name),
		"type": created_node.get_class(),
		"script": _serialize_script(created_node.get_script()),
		"undoable": true,
		"_scene_mutated": true,
	}


func bind_script(params: Dictionary) -> Dictionary:
	var resolved := _resolve_node(params)
	if resolved.has("_error"):
		return resolved
	var node: Node = resolved["node"]
	var scene_root: Node = resolved["scene_root"]
	var editability := _require_locally_owned(node, scene_root, "bind a script to")
	if editability != null:
		return editability
	var script_result := _load_supported_node_script(
		str(params.get("script_path", "")).strip_edges(), node.get_class()
	)
	if script_result.has("_error"):
		return script_result
	var replacement: Script = script_result["script"]
	var current: Script = node.get_script()
	if current == replacement:
		return {
			"path": ScenePath.from_node(node, scene_root),
			"script": _serialize_script(current),
			"changed": false,
			"undoable": false,
		}
	if current != null and not bool(params.get("replace_existing", false)):
		return Errors.make(
			"SCRIPT_ALREADY_ATTACHED",
			"Node '%s' already has a script attached" % node.name,
			false,
			"Set replace_existing to true after inspecting the current script, or call node_script_clear."
		)
	_undo_redo.create_action(
		"Godot 2D MCP: Bind script to %s" % node.name,
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_property(node, "script", replacement)
	_undo_redo.add_undo_property(node, "script", current)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(node, scene_root),
		"script": _serialize_script(node.get_script()),
		"previous_script": _serialize_script(current),
		"changed": true,
		"undoable": true,
		"_scene_mutated": true,
	}


func clear_script(params: Dictionary) -> Dictionary:
	var resolved := _resolve_node(params)
	if resolved.has("_error"):
		return resolved
	var node: Node = resolved["node"]
	var scene_root: Node = resolved["scene_root"]
	var editability := _require_locally_owned(node, scene_root, "clear the script from")
	if editability != null:
		return editability
	var current: Script = node.get_script()
	if current == null:
		return {
			"path": ScenePath.from_node(node, scene_root),
			"cleared": false,
			"undoable": false,
		}
	_undo_redo.create_action(
		"Godot 2D MCP: Clear script from %s" % node.name,
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_property(node, "script", null)
	_undo_redo.add_undo_property(node, "script", current)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(node, scene_root),
		"previous_script": _serialize_script(current),
		"cleared": true,
		"undoable": true,
		"_scene_mutated": true,
	}


func instance_packed_scene(params: Dictionary) -> Dictionary:
	var guarded := MutationGuard.require_scene(params)
	if guarded.has("_error"):
		return guarded
	var scene_root: Node = guarded["scene_root"]
	var scene_path := str(params.get("scene_path", "")).strip_edges()
	var loaded := _load_supported_packed_scene(scene_path)
	if loaded.has("_error"):
		return loaded
	var instance: Node = loaded["instance"]

	var parent_path := str(params.get("parent_path", ""))
	var parent := ScenePath.resolve(parent_path, scene_root)
	if parent == null:
		instance.free()
		return Errors.make(
			"NODE_NOT_FOUND",
			"Parent node not found: %s" % parent_path,
			false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if not TypePolicy.is_supported_node_class(parent.get_class()):
		instance.free()
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"Parent node is outside the supported 2D policy: %s" % parent.get_class()
		)
	var parent_editability := _require_locally_owned(parent, scene_root, "instance scenes under")
	if parent_editability != null:
		instance.free()
		return parent_editability

	var requested_name := str(params.get("name", "")).strip_edges()
	if requested_name.is_empty():
		requested_name = String(instance.name)
	var name_error := _validate_node_name(requested_name)
	if name_error != null:
		instance.free()
		return name_error
	if _has_sibling_name(parent, requested_name, null):
		instance.free()
		return _name_conflict_error(requested_name)
	instance.name = requested_name
	var subtree_node_count := _collect_subtree(instance).size()

	_undo_redo.create_action(
		"Godot 2D MCP: Instance %s" % requested_name,
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_method(parent, "add_child", instance, true)
	# Only the instance root belongs to this scene; child owners preserve the PackedScene boundary.
	_undo_redo.add_do_method(instance, "set_owner", scene_root)
	_undo_redo.add_do_reference(instance)
	_undo_redo.add_undo_method(parent, "remove_child", instance)
	_undo_redo.commit_action()

	return {
		"path": ScenePath.from_node(instance, scene_root),
		"parent_path": ScenePath.from_node(parent, scene_root),
		"name": String(instance.name),
		"type": instance.get_class(),
		"scene_path": scene_path,
		"subtree_node_count": subtree_node_count,
		"undoable": true,
		"_scene_mutated": true,
	}


func get_packed_scene_instance(params: Dictionary) -> Dictionary:
	var resolved := _resolve_node(params, false)
	if resolved.has("_error"):
		return resolved
	var node: Node = resolved["node"]
	var scene_root: Node = resolved["scene_root"]
	var instance_result := _require_packed_scene_instance_root(node, scene_root)
	if instance_result.has("_error"):
		return instance_result
	return _serialize_packed_scene_instance(instance_result["instance"], scene_root)


func enable_packed_scene_editable_children(params: Dictionary) -> Dictionary:
	var resolved := _resolve_node(params)
	if resolved.has("_error"):
		return resolved
	var node: Node = resolved["node"]
	var scene_root: Node = resolved["scene_root"]
	var instance_result := _require_packed_scene_instance_root(node, scene_root)
	if instance_result.has("_error"):
		return instance_result
	var instance: Node = instance_result["instance"]
	var parent_editability := _require_editable_instance_parent(instance, scene_root)
	if parent_editability != null:
		return parent_editability
	var was_editable := scene_root.is_editable_instance(instance)
	var was_placeholder := instance.get_scene_instance_load_placeholder()
	if was_editable and not was_placeholder:
		var unchanged := _serialize_packed_scene_instance(instance, scene_root)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged

	_undo_redo.create_action(
		"Godot 2D MCP: Enable Editable Children for %s" % instance.name,
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_method(scene_root, "set_editable_instance", instance, true)
	_undo_redo.add_undo_method(scene_root, "set_editable_instance", instance, was_editable)
	if was_placeholder:
		_undo_redo.add_do_method(instance, "set_scene_instance_load_placeholder", false)
		_undo_redo.add_undo_method(instance, "set_scene_instance_load_placeholder", true)
	_undo_redo.commit_action()

	var result := _serialize_packed_scene_instance(instance, scene_root)
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_properties(params: Dictionary) -> Dictionary:
	var resolved := _resolve_node(params)
	if resolved.has("_error"):
		return resolved
	var node: Node = resolved["node"]
	var scene_root: Node = resolved["scene_root"]
	var editability := _require_property_editable(node, scene_root, "update")
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
	var subtree_check := _require_supported_subtree(node, "delete")
	if subtree_check != null:
		return subtree_check
	var deletion_check := NodePathMigration.validate_removal(scene_root, node)
	if deletion_check.has("_error"):
		return deletion_check

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


func rename_node(params: Dictionary) -> Dictionary:
	var resolved := _resolve_node(params)
	if resolved.has("_error"):
		return resolved
	var node: Node = resolved["node"]
	var scene_root: Node = resolved["scene_root"]
	if node == scene_root:
		return Errors.make(
			"SCENE_ROOT_PROTECTED",
			"The edited scene root cannot be renamed because it anchors scene paths"
		)
	var editability := _require_locally_owned(node, scene_root, "rename")
	if editability != null:
		return editability
	var is_packed_scene_instance := _is_packed_scene_instance_root(node, scene_root)
	var subtree_check: Variant = (
		_require_supported_subtree(node, "rename")
		if is_packed_scene_instance
		else _require_local_subtree(node, scene_root, "rename")
	)
	if subtree_check != null:
		return subtree_check

	var new_name := str(params.get("name", "")).strip_edges()
	var name_error := _validate_node_name(new_name)
	if name_error != null:
		return name_error
	var old_name := String(node.name)
	var old_path := ScenePath.from_node(node, scene_root)
	if old_name == new_name:
		return {
			"path": old_path,
			"old_path": old_path,
			"name": new_name,
			"unchanged": true,
			"undoable": false,
		}
	var parent := node.get_parent()
	if _has_sibling_name(parent, new_name, node):
		return _name_conflict_error(new_name)

	var migration := NodePathMigration.plan(
		scene_root, node, parent, new_name, not is_packed_scene_instance
	)
	if migration.has("_error"):
		return migration
	_undo_redo.create_action(
		"Godot 2D MCP: Rename %s to %s" % [old_name, new_name],
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_method(node, "set_name", new_name)
	_add_do_migration(migration)
	_add_undo_migration(migration)
	_undo_redo.add_undo_method(node, "set_name", old_name)
	_undo_redo.commit_action()

	return {
		"path": ScenePath.from_node(node, scene_root),
		"old_path": old_path,
		"name": String(node.name),
		"migrated_node_paths": migration["property_records"].size(),
		"migrated_animation_tracks": migration["track_records"].size(),
		"undoable": true,
		"_scene_mutated": true,
	}


func duplicate_node(params: Dictionary) -> Dictionary:
	var resolved := _resolve_node(params)
	if resolved.has("_error"):
		return resolved
	var node: Node = resolved["node"]
	var scene_root: Node = resolved["scene_root"]
	if node == scene_root:
		return Errors.make("SCENE_ROOT_PROTECTED", "The edited scene root cannot be duplicated")
	var editability := _require_locally_owned(node, scene_root, "duplicate")
	if editability != null:
		return editability
	var is_packed_scene_instance := _is_packed_scene_instance_root(node, scene_root)
	var subtree_check: Variant = (
		_require_supported_subtree(node, "duplicate")
		if is_packed_scene_instance
		else _require_local_subtree(node, scene_root, "duplicate")
	)
	if subtree_check != null:
		return subtree_check

	var parent := node.get_parent()
	var requested_name := str(params.get("name", "")).strip_edges()
	if not requested_name.is_empty():
		var name_error := _validate_node_name(requested_name)
		if name_error != null:
			return name_error
		if _has_sibling_name(parent, requested_name, node):
			return _name_conflict_error(requested_name)

	var duplicate := node.duplicate()
	if duplicate == null:
		return Errors.make("DUPLICATION_FAILED", "Godot failed to duplicate node: %s" % node.name)
	if duplicate.get_script() != node.get_script():
		duplicate.free()
		return Errors.make(
			"DUPLICATION_SCRIPT_INIT_FAILED",
			"The node script could not be duplicated safely",
			false,
			"Use a script with a parameterless _init or create a new node explicitly."
		)
	if is_packed_scene_instance and duplicate.scene_file_path != node.scene_file_path:
		duplicate.free()
		return Errors.make(
			"DUPLICATION_INSTANCE_BOUNDARY_LOST",
			"Godot did not preserve the PackedScene source while duplicating '%s'" % node.name,
			false,
			"Duplicate the instance root again after reopening the scene."
		)
	if not requested_name.is_empty():
		duplicate.name = requested_name
	var duplicated_nodes := _collect_subtree(duplicate)
	var local_owner_paths := _collect_local_owner_paths(node, scene_root)
	var duplicate_owner_nodes := _resolve_duplicate_owner_nodes(duplicate, local_owner_paths)
	if duplicate_owner_nodes.has("_error"):
		duplicate.free()
		return duplicate_owner_nodes
	_undo_redo.create_action(
		"Godot 2D MCP: Duplicate %s" % node.name,
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_method(parent, "add_child", duplicate, true)
	if is_packed_scene_instance:
		# Preserve the external instance boundary while retaining local override descendants.
		for duplicate_owner_node in duplicate_owner_nodes["nodes"]:
			_undo_redo.add_do_method(duplicate_owner_node, "set_owner", scene_root)
	else:
		for duplicated_node in duplicated_nodes:
			_undo_redo.add_do_method(duplicated_node, "set_owner", scene_root)
	_undo_redo.add_do_reference(duplicate)
	_undo_redo.add_undo_method(parent, "remove_child", duplicate)
	_undo_redo.commit_action()

	return {
		"path": ScenePath.from_node(duplicate, scene_root),
		"source_path": ScenePath.from_node(node, scene_root),
		"name": String(duplicate.name),
		"type": duplicate.get_class(),
		"copied_node_count": duplicated_nodes.size(),
		"packed_scene_instance": is_packed_scene_instance,
		"scene_path": duplicate.scene_file_path if is_packed_scene_instance else "",
		"undoable": true,
		"_scene_mutated": true,
	}


func reparent_node(params: Dictionary) -> Dictionary:
	var resolved := _resolve_node(params)
	if resolved.has("_error"):
		return resolved
	var node: Node = resolved["node"]
	var scene_root: Node = resolved["scene_root"]
	if node == scene_root:
		return Errors.make("SCENE_ROOT_PROTECTED", "The edited scene root cannot be reparented")
	var editability := _require_locally_owned(node, scene_root, "reparent")
	if editability != null:
		return editability
	var is_packed_scene_instance := _is_packed_scene_instance_root(node, scene_root)
	var subtree_check: Variant = (
		_require_supported_subtree(node, "reparent")
		if is_packed_scene_instance
		else _require_local_subtree(node, scene_root, "reparent")
	)
	if subtree_check != null:
		return subtree_check

	var new_parent_path := str(params.get("new_parent_path", ""))
	if new_parent_path.is_empty():
		return Errors.make("MISSING_PARAMETER", "new_parent_path is required")
	var new_parent := ScenePath.resolve(new_parent_path, scene_root)
	if new_parent == null:
		return Errors.make(
			"NODE_NOT_FOUND",
			"New parent node not found: %s" % new_parent_path,
			false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if not TypePolicy.is_supported_node_class(new_parent.get_class()):
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"New parent is outside the supported 2D policy: %s" % new_parent.get_class()
		)
	var parent_editability := _require_locally_owned(new_parent, scene_root, "reparent under")
	if parent_editability != null:
		return parent_editability
	if node == new_parent or node.is_ancestor_of(new_parent):
		return Errors.make("NODE_CYCLE", "A node cannot be reparented below itself or its descendant")

	var old_parent := node.get_parent()
	if old_parent == new_parent:
		return Errors.make(
			"PARENT_UNCHANGED",
			"Node already belongs to the requested parent",
			false,
			"Use node_move to change sibling order."
		)
	if _has_sibling_name(new_parent, String(node.name), node):
		return _name_conflict_error(String(node.name))
	var requested_index := int(params.get("index", -1))
	if requested_index < -1 or requested_index > new_parent.get_child_count(false):
		return Errors.make(
			"INDEX_OUT_OF_RANGE",
			"index must be between -1 and %d" % new_parent.get_child_count(false)
		)

	var migration := NodePathMigration.plan(
		scene_root, node, new_parent, String(node.name), not is_packed_scene_instance
	)
	if migration.has("_error"):
		return migration
	var old_path := ScenePath.from_node(node, scene_root)
	var old_index := node.get_index(false)
	var owner_records := _capture_owners(node)
	var keep_global_transform := bool(params.get("keep_global_transform", true))
	var node_2d: Node2D = node if node is Node2D else null
	var control: Control = node if node is Control else null
	var old_transform := Transform2D.IDENTITY
	var old_global_transform := Transform2D.IDENTITY
	var old_position := Vector2.ZERO
	var old_global_position := Vector2.ZERO
	if keep_global_transform:
		if node_2d != null:
			old_transform = node_2d.transform
			old_global_transform = node_2d.global_transform
		elif control != null:
			old_position = control.position
			old_global_position = control.global_position
	_undo_redo.create_action(
		"Godot 2D MCP: Reparent %s" % node.name,
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_method(old_parent, "remove_child", node)
	_undo_redo.add_do_method(new_parent, "add_child", node, true)
	if requested_index >= 0:
		_undo_redo.add_do_method(new_parent, "move_child", node, requested_index)
	for record in owner_records:
		_undo_redo.add_do_method(record["node"], "set_owner", record["owner"])
	if keep_global_transform:
		if node_2d != null:
			_undo_redo.add_do_method(node_2d, "set_global_transform", old_global_transform)
		elif control != null:
			_undo_redo.add_do_method(control, "set_global_position", old_global_position)
	_add_do_migration(migration)
	_undo_redo.add_undo_method(new_parent, "remove_child", node)
	_undo_redo.add_undo_method(old_parent, "add_child", node, true)
	_undo_redo.add_undo_method(old_parent, "move_child", node, old_index)
	for record in owner_records:
		_undo_redo.add_undo_method(record["node"], "set_owner", record["owner"])
	if keep_global_transform:
		if node_2d != null:
			_undo_redo.add_undo_method(node_2d, "set_transform", old_transform)
		elif control != null:
			_undo_redo.add_undo_method(control, "set_position", old_position)
	_add_undo_migration(migration)
	_undo_redo.commit_action()

	return {
		"path": ScenePath.from_node(node, scene_root),
		"old_path": old_path,
		"old_parent_path": ScenePath.from_node(old_parent, scene_root),
		"new_parent_path": ScenePath.from_node(new_parent, scene_root),
		"index": node.get_index(false),
		"kept_global_transform": keep_global_transform,
		"packed_scene_instance": is_packed_scene_instance,
		"migrated_node_paths": migration["property_records"].size(),
		"migrated_animation_tracks": migration["track_records"].size(),
		"undoable": true,
		"_scene_mutated": true,
	}


func move_node(params: Dictionary) -> Dictionary:
	var resolved := _resolve_node(params)
	if resolved.has("_error"):
		return resolved
	var node: Node = resolved["node"]
	var scene_root: Node = resolved["scene_root"]
	if node == scene_root:
		return Errors.make("SCENE_ROOT_PROTECTED", "The edited scene root cannot be reordered")
	var editability := _require_locally_owned(node, scene_root, "reorder")
	if editability != null:
		return editability
	if not params.has("index"):
		return Errors.make("MISSING_PARAMETER", "index is required")
	var new_index := int(params["index"])
	var parent := node.get_parent()
	var old_index := node.get_index(false)
	var child_count := parent.get_child_count(false)
	if new_index < 0 or new_index >= child_count:
		return Errors.make(
			"INDEX_OUT_OF_RANGE", "index must be between 0 and %d" % (child_count - 1)
		)
	if new_index == old_index:
		return {
			"path": ScenePath.from_node(node, scene_root),
			"index": new_index,
			"unchanged": true,
			"undoable": false,
		}
	_undo_redo.create_action(
		"Godot 2D MCP: Move %s" % node.name,
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_method(parent, "move_child", node, new_index)
	_undo_redo.add_undo_method(parent, "move_child", node, old_index)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(node, scene_root),
		"old_index": old_index,
		"index": new_index,
		"undoable": true,
		"_scene_mutated": true,
	}


func _add_do_migration(migration: Dictionary) -> void:
	for record in migration["property_records"]:
		_undo_redo.add_do_property(record["object"], record["property"], record["new_path"])
	for record in migration["track_records"]:
		_undo_redo.add_do_method(
			record["animation"], "track_set_path", record["track_index"], record["new_path"]
		)


func _add_undo_migration(migration: Dictionary) -> void:
	for record in migration["property_records"]:
		_undo_redo.add_undo_property(record["object"], record["property"], record["old_path"])
	for record in migration["track_records"]:
		_undo_redo.add_undo_method(
			record["animation"], "track_set_path", record["track_index"], record["old_path"]
		)


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


func _collect_subtree(root: Node) -> Array[Node]:
	var nodes: Array[Node] = []
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		nodes.append(node)
		var children := node.get_children(false)
		for index in range(children.size() - 1, -1, -1):
			stack.append(children[index])
	return nodes


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


func _load_supported_node_script(script_path: String, node_type: StringName) -> Dictionary:
	if script_path.is_empty():
		return {"script": null}
	if (
		script_path.length() > 4096
		or not script_path.begins_with("res://")
		or script_path.contains("/../")
		or script_path.ends_with("/..")
		or script_path.contains("\\")
	):
		return Errors.make(
			"INVALID_SCRIPT_PATH",
			"script_path must be a bounded project-local res:// path",
			false,
			"Pass an existing script path such as res://scripts/player.gd."
		)
	if not ResourceLoader.exists(script_path):
		return Errors.make(
			"SCRIPT_NOT_FOUND",
			"Script path does not exist: %s" % script_path,
			false,
			"Pass an existing project-local Script resource."
		)
	var resource := ResourceLoader.load(script_path)
	if not resource is Script:
		return Errors.make(
			"SCRIPT_TYPE_MISMATCH",
			"script_path does not load a Script resource: %s" % script_path,
			false,
			"Pass a project-local GDScript, C# script, or another Script resource."
		)
	var script := resource as Script
	if script.is_tool():
		return Errors.make(
			"TOOL_SCRIPT_NOT_SUPPORTED",
			"Refusing to attach editor-running @tool script: %s" % script_path,
			false,
			"Attach non-tool gameplay scripts through MCP; attach @tool scripts manually in Godot."
		)
	var base_type := script.get_instance_base_type()
	if base_type.is_empty() or not ClassDB.class_exists(base_type):
		return Errors.make(
			"SCRIPT_BASE_TYPE_UNAVAILABLE",
			"Script does not expose a valid native node base type: %s" % script_path,
			false,
			"Fix script parse errors and make it extend a built-in supported 2D or UI node type."
		)
	if not TypePolicy.is_supported_node_class(base_type):
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"Script '%s' extends unsupported node type %s" % [script_path, base_type],
			false,
			"Use scripts that extend supported 2D or UI node types."
		)
	if node_type != base_type and not ClassDB.is_parent_class(node_type, base_type):
		return Errors.make(
			"SCRIPT_BASE_TYPE_MISMATCH",
			"Script base type %s cannot be attached to %s" % [base_type, node_type],
			false,
			"Create or target a node whose native type inherits the script base type."
		)
	return {"script": script}


func _serialize_script(script: Script) -> Dictionary:
	if script == null:
		return {}
	return {
		"resource_path": script.resource_path,
		"base_type": String(script.get_instance_base_type()),
		"global_name": String(script.get_global_name()),
		"is_tool": script.is_tool(),
	}


func _serialize_property(node: Node, property_info: Dictionary) -> Dictionary:
	var property_name := str(property_info.get("name", ""))
	var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
	var value = node.get(property_name)
	var serialized := {
		"name": property_name,
		"type": type_string(int(property_info.get("type", TYPE_NIL))),
		"class_name": str(property_info.get("class_name", "")),
		"hint": int(property_info.get("hint", PROPERTY_HINT_NONE)),
		"hint_string": str(property_info.get("hint_string", "")),
		"read_only": not _is_writable_property(property_name, usage),
		"value": VariantCodec.serialize(value),
	}
	var container_type := VariantCodec.describe_container(value)
	if container_type != null:
		serialized["container_type"] = container_type
	return serialized


func _is_public_property(usage: int) -> bool:
	return bool(usage & PROPERTY_USAGE_EDITOR) or bool(usage & PROPERTY_USAGE_STORAGE)


func _is_writable_property(property_name: String, usage: int) -> bool:
	return (
		_is_public_property(usage)
		and not bool(usage & PROPERTY_USAGE_READ_ONLY)
		and not PROTECTED_PROPERTIES.has(property_name)
	)


func _require_property_editable(node: Node, scene_root: Node, operation: String) -> Variant:
	if node == scene_root or node.owner == scene_root:
		return null
	if node.owner != null and scene_root.is_editable_instance(node.owner):
		return null
	var instance_path := ""
	if node.owner != null and scene_root.is_ancestor_of(node.owner):
		instance_path = ScenePath.from_node(node.owner, scene_root)
	return Errors.make(
		"PACKED_SCENE_EDITABLE_CHILDREN_REQUIRED",
		"Cannot %s node '%s' because its PackedScene owner is not editable" % [operation, node.name],
		false,
		"Call packed_scene_instance_editable_children_enable for '%s' before editing its descendants."
		% instance_path,
		{"instance_path": instance_path}
	)


func _require_packed_scene_instance_root(node: Node, scene_root: Node) -> Dictionary:
	if not _is_packed_scene_instance_root(node, scene_root):
		return Errors.make(
			"PACKED_SCENE_INSTANCE_REQUIRED",
			"Node '%s' is not an instanced PackedScene root" % node.name,
			false,
			"Pass the root path returned by node_instance_scene or scene_get_hierarchy."
		)
	return {"instance": node}


func _require_editable_instance_parent(instance: Node, scene_root: Node) -> Variant:
	if instance.owner == scene_root:
		return null
	if instance.owner != null and scene_root.is_editable_instance(instance.owner):
		return null
	var owner_path := ""
	if instance.owner != null and scene_root.is_ancestor_of(instance.owner):
		owner_path = ScenePath.from_node(instance.owner, scene_root)
	return Errors.make(
		"PACKED_SCENE_EDITABLE_CHILDREN_REQUIRED",
		"Enable the parent PackedScene before enabling nested instance '%s'" % instance.name,
		false,
		"Call packed_scene_instance_editable_children_enable for '%s' first." % owner_path,
		{"instance_path": owner_path}
	)


func _is_packed_scene_instance_root(node: Node, scene_root: Node) -> bool:
	return node != scene_root and not node.scene_file_path.is_empty()


func _serialize_packed_scene_instance(instance: Node, scene_root: Node) -> Dictionary:
	var subtree_node_count := 0
	var local_override_node_count := 0
	for descendant in _collect_subtree(instance):
		subtree_node_count += 1
		if descendant != instance and descendant.owner == scene_root:
			local_override_node_count += 1
	return {
		"path": ScenePath.from_node(instance, scene_root),
		"type": instance.get_class(),
		"scene_path": instance.scene_file_path,
		"editable_children": scene_root.is_editable_instance(instance),
		"load_as_placeholder": instance.get_scene_instance_load_placeholder(),
		"subtree_node_count": subtree_node_count,
		"local_override_node_count": local_override_node_count,
	}


func _collect_local_owner_paths(root: Node, scene_root: Node) -> Array[String]:
	var paths: Array[String] = []
	for descendant in _collect_subtree(root):
		if descendant != root and descendant.owner != scene_root:
			continue
		paths.append("" if descendant == root else String(root.get_path_to(descendant)))
	return paths


func _resolve_duplicate_owner_nodes(duplicate: Node, local_owner_paths: Array[String]) -> Dictionary:
	var nodes: Array[Node] = []
	for path in local_owner_paths:
		var duplicate_node := duplicate if path.is_empty() else duplicate.get_node_or_null(NodePath(path))
		if duplicate_node == null:
			return Errors.make(
				"DUPLICATION_OVERRIDE_LOST",
				"Godot did not preserve local override node '%s' while duplicating the PackedScene" % path,
				false,
				"Duplicate the instance again after reopening the scene."
			)
		nodes.append(duplicate_node)
	return {"nodes": nodes}


func _require_locally_owned(node: Node, scene_root: Node, operation: String) -> Variant:
	if node == scene_root or node.owner == scene_root:
		return null
	return Errors.make(
		"PACKED_SCENE_BOUNDARY",
		"Cannot %s node '%s' because it belongs to an instanced scene" % [operation, node.name],
		false,
		"Edit the source PackedScene or target its locally owned instance root."
	)


func _require_local_subtree(node: Node, scene_root: Node, operation: String) -> Variant:
	for descendant in _collect_subtree(node):
		if not TypePolicy.is_supported_node_class(descendant.get_class()):
			return Errors.make(
				"UNSUPPORTED_2D_TYPE",
				"Cannot %s '%s' because its subtree contains unsupported node type %s"
				% [operation, node.name, descendant.get_class()],
				false,
				"Use this tool only with a subtree made entirely of supported 2D nodes."
			)
		if descendant != scene_root and descendant.owner != scene_root:
			return Errors.make(
				"PACKED_SCENE_BOUNDARY",
				"Cannot %s '%s' because its subtree contains an instanced scene" % [operation, node.name],
				false,
				"Edit the source PackedScene or operate on a fully local subtree."
			)
	return null


func _require_supported_subtree(node: Node, operation: String) -> Variant:
	for descendant in _collect_subtree(node):
		if TypePolicy.is_supported_node_class(descendant.get_class()):
			continue
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"Cannot %s '%s' because its subtree contains unsupported node type %s"
			% [operation, node.name, descendant.get_class()],
			false,
			"Use this tool only with a subtree made entirely of supported 2D nodes."
		)
	return null


func _validate_node_name(value: String) -> Variant:
	if value.is_empty():
		return Errors.make("MISSING_PARAMETER", "name is required")
	if value.length() > 256 or value.validate_node_name() != value:
		return Errors.make("INVALID_NODE_NAME", "Invalid node name: %s" % value)
	return null


func _has_sibling_name(parent: Node, name: String, ignored_node: Node) -> bool:
	for sibling in parent.get_children(false):
		if sibling != ignored_node and String(sibling.name) == name:
			return true
	return false


func _name_conflict_error(name: String) -> Dictionary:
	return Errors.make(
		"NODE_NAME_CONFLICT",
		"Parent already has a child named '%s'" % name,
		false,
		"Choose a unique sibling name."
	)


func _load_supported_packed_scene(scene_path: String) -> Dictionary:
	if (
		scene_path.is_empty()
		or scene_path.length() > 4096
		or not scene_path.begins_with("res://")
		or scene_path.contains("/../")
		or scene_path.ends_with("/..")
	):
		return Errors.make(
			"INVALID_PACKED_SCENE_PATH",
			"scene_path must be a bounded project-local res:// path",
			false,
			"Pass an existing 2D PackedScene path such as res://scenes/player.tscn."
		)
	if not ResourceLoader.exists(scene_path):
		return Errors.make(
			"PACKED_SCENE_NOT_FOUND",
			"PackedScene path does not exist: %s" % scene_path,
			false,
			"Use an existing PackedScene under the current project."
		)
	var resource := ResourceLoader.load(scene_path)
	if not resource is PackedScene:
		return Errors.make(
			"PACKED_SCENE_TYPE_MISMATCH",
			"scene_path does not load a PackedScene: %s" % scene_path,
			false,
			"Pass a .tscn or .scn resource with a supported 2D root node."
		)
	var instance := (resource as PackedScene).instantiate()
	if instance == null:
		return Errors.make("PACKED_SCENE_INSTANTIATION_FAILED", "Godot could not instance: %s" % scene_path)
	for descendant in _collect_subtree(instance):
		if TypePolicy.is_supported_node_class(descendant.get_class()):
			continue
		var unsupported_type := descendant.get_class()
		instance.free()
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"PackedScene '%s' contains unsupported node type %s" % [
				scene_path, unsupported_type
			],
			false,
			"Instance PackedScenes whose complete subtree uses supported 2D and UI node types."
		)
	return {"instance": instance}

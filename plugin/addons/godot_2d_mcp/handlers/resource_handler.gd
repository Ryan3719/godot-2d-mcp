@tool
extends RefCounted

const EditorState := preload("res://addons/godot_2d_mcp/utils/editor_state.gd")
const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const TypePolicy := preload("res://addons/godot_2d_mcp/utils/type_policy.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_FIELDS := 64
const MAX_PROPERTIES := 64
const MAX_PROPERTY_RESULTS := 512
const MAX_PATH_LENGTH := 4096
const MAX_TYPE_NAME_LENGTH := 256
const MAX_RESOURCE_HISTORIES := 128
const PROTECTED_PROPERTIES := {
	"resource_path": true,
	"resource_local_to_scene": true,
	"resource_name": true,
	"resource_scene_unique_id": true,
	"script": true,
}

var _resource_histories := {}


func _init(_undo_redo: EditorUndoRedoManager) -> void:
	pass


func get_resource(params: Dictionary) -> Dictionary:
	var resolved := _load_resource(params, false, false)
	if resolved.has("_error"):
		return resolved
	var fields_result := _parse_fields(params.get("fields", []))
	if fields_result.has("_error"):
		return fields_result
	return _resource_response(resolved["resource"], fields_result["fields"])


func create_resource(params: Dictionary) -> Dictionary:
	var writable := _require_editor_writable()
	if writable.has("_error"):
		return writable
	var type_name := str(params.get("type", "")).strip_edges()
	if type_name.is_empty() or type_name.length() > MAX_TYPE_NAME_LENGTH:
		return Errors.make(
			"INVALID_RESOURCE_TYPE",
			"type must contain between 1 and %d characters" % MAX_TYPE_NAME_LENGTH
		)
	if not TypePolicy.is_resource_management_class(StringName(type_name)):
		return Errors.make(
			"UNSUPPORTED_2D_RESOURCE",
			"Resource type is not available through the generic 2D resource workflow: %s" % type_name,
			false,
			"Use class_2d_describe to inspect audited resources, or the matching specialized tool."
		)
	if not ClassDB.can_instantiate(StringName(type_name)):
		return Errors.make(
			"RESOURCE_NOT_INSTANTIABLE",
			"Godot cannot instantiate resource type: %s" % type_name,
			false,
			"Choose a concrete audited Resource class."
		)
	var path_result := _parse_resource_path(params.get("resource_path", ""), true)
	if path_result.has("_error"):
		return path_result
	var resource_path: String = path_result["resource_path"]
	if ResourceLoader.exists(resource_path) or FileAccess.file_exists(resource_path):
		return Errors.make(
			"RESOURCE_PATH_EXISTS",
			"A project resource already exists at: %s" % resource_path,
			false,
			"Use resource_set_properties for an existing resource or choose a new .tres/.res path."
		)
	var directory_result := _ensure_resource_parent_directory(resource_path)
	if directory_result.has("_error"):
		return directory_result
	var created: Object = ClassDB.instantiate(StringName(type_name))
	if not created is Resource:
		return Errors.make(
			"RESOURCE_CREATION_FAILED",
			"Godot did not create a Resource instance for type: %s" % type_name
		)
	var resource := created as Resource
	var change_result := _collect_property_changes(resource, params.get("properties", {}), true)
	if change_result.has("_error"):
		return change_result
	for change_value in change_result["changes"]:
		var change: Dictionary = change_value
		resource.set(change["name"], change["new_value"])
	var save_error := ResourceSaver.save(resource, resource_path)
	if save_error != OK:
		return Errors.make(
			"RESOURCE_SAVE_FAILED",
			"Godot could not create resource '%s': %s" % [resource_path, error_string(save_error)],
			false,
			"Check the parent directory, file permissions, and resource property values.",
			{"error": save_error, "error_name": error_string(save_error)}
		)
	var result := _resource_response(resource, [])
	result["created"] = true
	result["saved"] = true
	result["undoable"] = false
	result["updated"] = _serialize_changes(resource, change_result["changes"])
	return result


func set_resource_properties(params: Dictionary) -> Dictionary:
	var resolved := _load_resource(params, true, true)
	if resolved.has("_error"):
		return resolved
	var resource: Resource = resolved["resource"]
	var change_result := _collect_property_changes(resource, params.get("properties", null), false)
	if change_result.has("_error"):
		return change_result
	var changes: Array = change_result["changes"]
	var unchanged: Array = change_result["unchanged"]
	if changes.is_empty():
		return {
			"resource_path": resource.resource_path,
			"resource_type": resource.get_class(),
			"updated": {},
			"unchanged": unchanged,
			"saved": false,
			"undoable": false,
		}
	var history_result := _ensure_resource_history(resource)
	if history_result.has("_error"):
		return history_result
	var history: UndoRedo = history_result["history"]
	history.create_action("Godot 2D MCP: Update %s" % resource.resource_path, UndoRedo.MERGE_DISABLE)
	for change_value in changes:
		var change: Dictionary = change_value
		history.add_do_property(resource, change["name"], change["new_value"])
		history.add_undo_property(resource, change["name"], change["old_value"])
	history.commit_action()
	return {
		"resource_path": resource.resource_path,
		"resource_type": resource.get_class(),
		"updated": _serialize_changes(resource, changes),
		"unchanged": unchanged,
		"saved": false,
		"undoable": true,
	}


func save_resource(params: Dictionary) -> Dictionary:
	var resolved := _load_resource(params, true, true)
	if resolved.has("_error"):
		return resolved
	var resource: Resource = resolved["resource"]
	var save_error := ResourceSaver.save(resource, resource.resource_path)
	if save_error != OK:
		return Errors.make(
			"RESOURCE_SAVE_FAILED",
			"Godot could not save resource '%s': %s" % [resource.resource_path, error_string(save_error)],
			false,
			"Check the file permissions, resource dependencies, and project import state.",
			{"error": save_error, "error_name": error_string(save_error)}
		)
	return {
		"resource_path": resource.resource_path,
		"resource_type": resource.get_class(),
		"saved": true,
		"undoable": false,
	}


func undo_resource(params: Dictionary) -> Dictionary:
	var resolved := _load_resource(params, true, true)
	if resolved.has("_error"):
		return resolved
	return _apply_resource_history(resolved["resource"], false)


func redo_resource(params: Dictionary) -> Dictionary:
	var resolved := _load_resource(params, true, true)
	if resolved.has("_error"):
		return resolved
	return _apply_resource_history(resolved["resource"], true)


func _load_resource(params: Dictionary, require_writable: bool, require_editable: bool) -> Dictionary:
	if require_writable:
		var writable := _require_editor_writable()
		if writable.has("_error"):
			return writable
	var path_result := _parse_resource_path(params.get("resource_path", ""), require_editable)
	if path_result.has("_error"):
		return path_result
	var resource_path: String = path_result["resource_path"]
	if not ResourceLoader.exists(resource_path):
		return Errors.make(
			"RESOURCE_NOT_FOUND",
			"Project resource does not exist: %s" % resource_path,
			false,
			"Create a resource first or use an existing res:// path."
		)
	var resource := ResourceLoader.load(resource_path)
	if resource == null or not resource is Resource:
		return Errors.make("RESOURCE_LOAD_FAILED", "Godot could not load resource: %s" % resource_path)
	if not TypePolicy.is_resource_management_class(resource.get_class()):
		return Errors.make(
			"UNSUPPORTED_2D_RESOURCE",
			"Resource type is not available through the generic 2D resource workflow: %s" % resource.get_class(),
			false,
			"Use the matching specialized resource tool for this type."
		)
	return {"resource": resource as Resource}


func _parse_resource_path(raw_value: Variant, require_editable: bool) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_RESOURCE_PATH", "resource_path must be a project-local res:// path")
	var resource_path: String = raw_value.strip_edges()
	if (
		resource_path.is_empty()
		or resource_path.length() > MAX_PATH_LENGTH
		or not resource_path.begins_with("res://")
		or resource_path.contains("/../")
		or resource_path.ends_with("/..")
		or resource_path.contains("::")
	):
		return Errors.make("INVALID_RESOURCE_PATH", "resource_path must stay inside res://")
	if require_editable and not _is_editable_resource_path(resource_path):
		return Errors.make(
			"RESOURCE_NOT_EDITABLE",
			"Only standalone .tres and .res resources can be modified by this workflow: %s" % resource_path,
			false,
			"Use a specialized tool for imported assets, or save a standalone resource as .tres/.res."
		)
	return {"resource_path": resource_path}


func _is_editable_resource_path(resource_path: String) -> bool:
	var lowercase_path := resource_path.to_lower()
	return lowercase_path.ends_with(".tres") or lowercase_path.ends_with(".res")


func _ensure_resource_parent_directory(resource_path: String) -> Dictionary:
	var directory_path := ProjectSettings.globalize_path(resource_path.get_base_dir())
	if DirAccess.dir_exists_absolute(directory_path):
		return {}
	var create_error := DirAccess.make_dir_recursive_absolute(directory_path)
	if create_error == OK:
		return {}
	return Errors.make(
		"RESOURCE_DIRECTORY_CREATE_FAILED",
		"Godot could not create the parent directory for '%s': %s" % [
			resource_path, error_string(create_error)
		],
		false,
		"Check project directory permissions and use a writable res:// path.",
		{"error": create_error, "error_name": error_string(create_error)}
	)


func _parse_fields(raw_value: Variant) -> Dictionary:
	if not raw_value is Array or raw_value.size() > MAX_FIELDS:
		return Errors.make("INVALID_RESOURCE_FIELDS", "fields must contain at most %d property names" % MAX_FIELDS)
	var fields: Array[String] = []
	var seen := {}
	for value in raw_value:
		if not value is String:
			return Errors.make("INVALID_RESOURCE_FIELDS", "fields must only contain property names")
		var field: String = value.strip_edges()
		if field.is_empty() or field.length() > MAX_TYPE_NAME_LENGTH or seen.has(field):
			return Errors.make("INVALID_RESOURCE_FIELDS", "fields must contain unique non-empty property names")
		seen[field] = true
		fields.append(field)
	return {"fields": fields}


func _collect_property_changes(resource: Resource, raw_properties: Variant, allow_empty: bool) -> Dictionary:
	if not raw_properties is Dictionary or (not allow_empty and raw_properties.is_empty()):
		return Errors.make("INVALID_RESOURCE_PROPERTIES", "properties must be a non-empty object")
	if raw_properties.size() > MAX_PROPERTIES:
		return Errors.make(
			"REQUEST_LIMIT_EXCEEDED",
			"A single resource update can contain at most %d properties" % MAX_PROPERTIES
		)
	var property_info_by_name := {}
	for property_info_value in resource.get_property_list():
		var property_info: Dictionary = property_info_value
		property_info_by_name[str(property_info.get("name", ""))] = property_info
	var changes: Array[Dictionary] = []
	var unchanged: Array[String] = []
	for property_name_value in raw_properties:
		if not property_name_value is String:
			return Errors.make("INVALID_RESOURCE_PROPERTIES", "property names must be strings")
		var property_name: String = property_name_value
		if not property_info_by_name.has(property_name):
			return Errors.make(
				"PROPERTY_NOT_FOUND",
				"Property '%s' does not exist on %s" % [property_name, resource.get_class()],
				false,
				"Call resource_get to inspect writable properties.",
				{"property": property_name, "resource_type": resource.get_class()}
			)
		var property_info: Dictionary = property_info_by_name[property_name]
		if not _is_writable_property(property_name, int(property_info.get("usage", PROPERTY_USAGE_NONE))):
			return Errors.make(
				"PROPERTY_NOT_WRITABLE",
				"Property '%s' is not writable through this tool" % property_name,
				false,
				"Use a writable property returned by resource_get.",
				{"property": property_name}
			)
		var old_value = resource.get(property_name)
		var decoded := VariantCodec.decode(raw_properties[property_name_value], property_info, old_value)
		if decoded.has("_error"):
			decoded["_error"]["details"]["property"] = property_name
			return decoded
		var new_value = decoded["value"]
		if old_value == new_value:
			unchanged.append(property_name)
			continue
		changes.append({"name": property_name, "old_value": old_value, "new_value": new_value})
	return {"changes": changes, "unchanged": unchanged}


func _resource_response(resource: Resource, fields: Array[String]) -> Dictionary:
	var requested := {}
	for field in fields:
		requested[field] = true
	var properties: Array[Dictionary] = []
	var found := {}
	var truncated := false
	for property_info_value in resource.get_property_list():
		var property_info: Dictionary = property_info_value
		var property_name := str(property_info.get("name", ""))
		if property_name.is_empty() or (not requested.is_empty() and not requested.has(property_name)):
			continue
		var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
		if not _is_public_property(usage):
			continue
		if properties.size() >= MAX_PROPERTY_RESULTS:
			truncated = true
			break
		found[property_name] = true
		properties.append(_serialize_property(resource, property_info))
	var missing_fields: Array[String] = []
	for field in fields:
		if not found.has(field):
			missing_fields.append(field)
	return {
		"resource_path": resource.resource_path,
		"resource_type": resource.get_class(),
		"resource_name": resource.resource_name,
		"properties": properties,
		"count": properties.size(),
		"missing_fields": missing_fields,
		"truncated": truncated,
	}


func _serialize_property(resource: Resource, property_info: Dictionary) -> Dictionary:
	var property_name := str(property_info.get("name", ""))
	var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
	var value = resource.get(property_name)
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


func _serialize_changes(resource: Resource, changes: Array) -> Dictionary:
	var output := {}
	for change_value in changes:
		var change: Dictionary = change_value
		output[change["name"]] = VariantCodec.serialize(resource.get(change["name"]))
	return output


func _apply_resource_history(resource: Resource, redo: bool) -> Dictionary:
	var history: UndoRedo = _existing_resource_history(resource)
	if history == null:
		return {
			"resource_path": resource.resource_path,
			"resource_type": resource.get_class(),
			"changed": false,
			"action": "",
			"has_undo": false,
			"has_redo": false,
		}
	var can_apply: bool = history.has_redo() if redo else history.has_undo()
	if not can_apply:
		return {
			"resource_path": resource.resource_path,
			"resource_type": resource.get_class(),
			"changed": false,
			"action": "",
			"has_undo": history.has_undo(),
			"has_redo": history.has_redo(),
		}
	var action_name: String = (
		history.get_action_name(history.get_current_action() + 1)
		if redo
		else history.get_current_action_name()
	)
	var changed: bool = history.redo() if redo else history.undo()
	return {
		"resource_path": resource.resource_path,
		"resource_type": resource.get_class(),
		"changed": changed,
		"action": action_name,
		"has_undo": history.has_undo(),
		"has_redo": history.has_redo(),
	}


func _ensure_resource_history(resource: Resource) -> Dictionary:
	var resource_path := resource.resource_path
	if _resource_histories.has(resource_path):
		return {"history": _resource_histories[resource_path] as UndoRedo}
	if _resource_histories.size() >= MAX_RESOURCE_HISTORIES:
		return Errors.make(
			"RESOURCE_HISTORY_LIMIT_EXCEEDED",
			"The plugin retains undo history for at most %d external resources" % MAX_RESOURCE_HISTORIES,
			false,
			"Save work, restart the plugin to clear old resource histories, then retry."
		)
	var history := UndoRedo.new()
	_resource_histories[resource_path] = history
	return {"history": history}


func _existing_resource_history(resource: Resource) -> UndoRedo:
	if not _resource_histories.has(resource.resource_path):
		return null
	return _resource_histories[resource.resource_path] as UndoRedo


func _is_public_property(usage: int) -> bool:
	return bool(usage & PROPERTY_USAGE_EDITOR) or bool(usage & PROPERTY_USAGE_STORAGE)


func _is_writable_property(property_name: String, usage: int) -> bool:
	return (
		_is_public_property(usage)
		and not bool(usage & PROPERTY_USAGE_READ_ONLY)
		and not PROTECTED_PROPERTIES.has(property_name)
	)


func _require_editor_writable() -> Dictionary:
	var readiness := EditorState.readiness()
	if readiness == "ready":
		return {}
	return Errors.make(
		"EDITOR_NOT_WRITABLE",
		"The editor is not writable while its state is '%s'" % readiness,
		readiness == "importing",
		"Wait for imports to finish and stop the running scene before editing resources.",
		{"readiness": readiness}
	)

@tool
extends RefCounted

const EditorState := preload("res://addons/godot_2d_mcp/utils/editor_state.gd")
const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const InputEventCodec := preload("res://addons/godot_2d_mcp/utils/input_event_codec.gd")

const MAX_EVENTS := 64
const MAX_SERIALIZED_EVENTS := 128
const MAX_PATH_LENGTH := 4096
const MAX_SHORTCUT_HISTORIES := 128
const ACTION_LABEL_PREFIX := "Godot 2D MCP: Shortcut"

var _shortcut_histories := {}


func _init(_undo_redo: EditorUndoRedoManager) -> void:
	pass


func get_shortcut(params: Dictionary) -> Dictionary:
	var resolved := _load_shortcut(params, false)
	if resolved.has("_error"):
		return resolved
	return _shortcut_response(resolved["shortcut"])


func create_shortcut(params: Dictionary) -> Dictionary:
	var writable := _require_editor_writable()
	if writable.has("_error"):
		return writable
	var path_result := _parse_resource_path(params.get("resource_path", ""))
	if path_result.has("_error"):
		return path_result
	var resource_path: String = path_result["resource_path"]
	if ResourceLoader.exists(resource_path) or FileAccess.file_exists(resource_path):
		return Errors.make(
			"SHORTCUT_PATH_EXISTS",
			"A project resource already exists at: %s" % resource_path,
			false,
			"Choose an unused standalone .tres or .res path."
		)
	var events_result := _parse_events(params.get("events", null), false)
	if events_result.has("_error"):
		return events_result
	var directory_result := _ensure_resource_parent_directory(resource_path)
	if directory_result.has("_error"):
		return directory_result
	var shortcut := Shortcut.new()
	shortcut.events = events_result["events"]
	var save_error := ResourceSaver.save(shortcut, resource_path)
	if save_error != OK:
		return _save_error(resource_path, save_error, "create")
	var response := _shortcut_response(shortcut)
	response["created"] = true
	response["saved"] = true
	response["undoable"] = false
	return response


func set_shortcut(params: Dictionary) -> Dictionary:
	var resolved := _load_shortcut(params, true)
	if resolved.has("_error"):
		return resolved
	var events_result := _parse_events(params.get("events", null), true)
	if events_result.has("_error"):
		return events_result
	var shortcut: Shortcut = resolved["shortcut"]
	var next_events: Array = events_result["events"]
	var previous_events: Array = shortcut.events.duplicate()
	if _events_match(previous_events, next_events):
		var unchanged := _shortcut_response(shortcut)
		unchanged["saved"] = false
		unchanged["undoable"] = false
		unchanged["unchanged"] = true
		return unchanged
	var history_result := _ensure_shortcut_history(shortcut)
	if history_result.has("_error"):
		return history_result
	var history: UndoRedo = history_result["history"]
	history.create_action("%s: Update %s" % [ACTION_LABEL_PREFIX, shortcut.resource_path], UndoRedo.MERGE_DISABLE)
	history.add_do_method(_apply_events.bind(shortcut, next_events))
	history.add_undo_method(_apply_events.bind(shortcut, previous_events))
	history.commit_action()
	var response := _shortcut_response(shortcut)
	response["saved"] = false
	response["undoable"] = true
	response["updated"] = true
	return response


func save_shortcut(params: Dictionary) -> Dictionary:
	var resolved := _load_shortcut(params, true)
	if resolved.has("_error"):
		return resolved
	var shortcut: Shortcut = resolved["shortcut"]
	var save_error := ResourceSaver.save(shortcut, shortcut.resource_path)
	if save_error != OK:
		return _save_error(shortcut.resource_path, save_error, "save")
	return {
		"resource_path": shortcut.resource_path,
		"resource_type": shortcut.get_class(),
		"saved": true,
		"undoable": false,
	}


func undo_shortcut(params: Dictionary) -> Dictionary:
	var resolved := _load_shortcut(params, true)
	if resolved.has("_error"):
		return resolved
	return _apply_shortcut_history(resolved["shortcut"], false)


func redo_shortcut(params: Dictionary) -> Dictionary:
	var resolved := _load_shortcut(params, true)
	if resolved.has("_error"):
		return resolved
	return _apply_shortcut_history(resolved["shortcut"], true)


func _load_shortcut(params: Dictionary, require_writable: bool) -> Dictionary:
	if require_writable:
		var writable := _require_editor_writable()
		if writable.has("_error"):
			return writable
	var path_result := _parse_resource_path(params.get("resource_path", ""))
	if path_result.has("_error"):
		return path_result
	var resource_path: String = path_result["resource_path"]
	if not ResourceLoader.exists(resource_path):
		return Errors.make(
			"SHORTCUT_NOT_FOUND",
			"Standalone Shortcut resource does not exist: %s" % resource_path,
			false,
			"Create a Shortcut first or use an existing standalone res:// resource path."
		)
	var resource := ResourceLoader.load(resource_path)
	if resource == null or not resource is Shortcut:
		return Errors.make(
			"SHORTCUT_RESOURCE_TYPE",
			"Project resource is not a Shortcut: %s" % resource_path,
			false,
			"Use a standalone .tres or .res resource whose root type is Shortcut."
		)
	var shortcut := resource as Shortcut
	if shortcut.get_script() != null:
		return Errors.make(
			"SHORTCUT_SCRIPTED_RESOURCE",
			"Scripted Shortcut resources are not editable through this workflow: %s" % resource_path,
			false,
			"Use a native Shortcut resource without an attached script."
		)
	return {"shortcut": shortcut}


func _parse_resource_path(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_SHORTCUT_PATH", "resource_path must be a standalone project-local res:// path")
	var resource_path: String = raw_value.strip_edges()
	if (
		resource_path.is_empty()
		or resource_path.length() > MAX_PATH_LENGTH
		or not resource_path.begins_with("res://")
		or resource_path.contains("/../")
		or resource_path.ends_with("/..")
		or resource_path.contains("::")
		or not (resource_path.to_lower().ends_with(".tres") or resource_path.to_lower().ends_with(".res"))
	):
		return Errors.make(
			"INVALID_SHORTCUT_PATH",
			"resource_path must be a standalone res:// .tres or .res resource"
		)
	return {"resource_path": resource_path}


func _parse_events(raw_events: Variant, allow_empty: bool) -> Dictionary:
	var parsed := InputEventCodec.parse_events(raw_events, MAX_EVENTS, "INVALID_SHORTCUT_EVENTS", "events")
	if parsed.has("_error"):
		return parsed
	if not allow_empty and (parsed["events"] as Array).is_empty():
		return Errors.make(
			"SHORTCUT_EVENTS_REQUIRED",
			"events must contain at least one supported InputEvent when creating a Shortcut"
		)
	return parsed


func _shortcut_response(shortcut: Shortcut) -> Dictionary:
	var events: Array[Dictionary] = []
	var raw_events: Array = shortcut.events
	var truncated := false
	for raw_event in raw_events:
		if events.size() >= MAX_SERIALIZED_EVENTS:
			truncated = true
			break
		events.append(InputEventCodec.serialize_event(raw_event))
	return {
		"resource_path": shortcut.resource_path,
		"resource_type": shortcut.get_class(),
		"events": events,
		"event_count": raw_events.size(),
		"events_truncated": truncated,
		"has_valid_event": shortcut.has_valid_event(),
		"text": shortcut.get_as_text(),
		"supported_event_types": InputEventCodec.supported_event_types(),
	}


func _apply_events(shortcut: Shortcut, events: Array) -> void:
	shortcut.events = events


func _events_match(left: Array, right: Array) -> bool:
	if left.size() != right.size():
		return false
	for index in left.size():
		if not left[index] is InputEvent or not right[index] is InputEvent:
			return false
		if not (left[index] as InputEvent).is_match(right[index] as InputEvent):
			return false
	return true


func _apply_shortcut_history(shortcut: Shortcut, redo: bool) -> Dictionary:
	var history := _existing_shortcut_history(shortcut)
	if history == null:
		return _history_response(shortcut, false, "", false, false)
	var can_apply: bool = history.has_redo() if redo else history.has_undo()
	if not can_apply:
		return _history_response(shortcut, false, "", history.has_undo(), history.has_redo())
	var action_name: String = (
		history.get_action_name(history.get_current_action() + 1)
		if redo
		else history.get_current_action_name()
	)
	var changed: bool = history.redo() if redo else history.undo()
	return _history_response(shortcut, changed, action_name, history.has_undo(), history.has_redo())


func _history_response(
	shortcut: Shortcut,
	changed: bool,
	action_name: String,
	has_undo: bool,
	has_redo: bool
) -> Dictionary:
	return {
		"resource_path": shortcut.resource_path,
		"resource_type": shortcut.get_class(),
		"changed": changed,
		"action": action_name,
		"has_undo": has_undo,
		"has_redo": has_redo,
	}


func _ensure_shortcut_history(shortcut: Shortcut) -> Dictionary:
	var resource_path := shortcut.resource_path
	if _shortcut_histories.has(resource_path):
		return {"history": _shortcut_histories[resource_path] as UndoRedo}
	if _shortcut_histories.size() >= MAX_SHORTCUT_HISTORIES:
		return Errors.make(
			"SHORTCUT_HISTORY_LIMIT_EXCEEDED",
			"The plugin retains undo history for at most %d Shortcut resources" % MAX_SHORTCUT_HISTORIES,
			false,
			"Save work, restart the plugin to clear old Shortcut histories, then retry."
		)
	var history := UndoRedo.new()
	_shortcut_histories[resource_path] = history
	return {"history": history}


func _existing_shortcut_history(shortcut: Shortcut) -> UndoRedo:
	if not _shortcut_histories.has(shortcut.resource_path):
		return null
	return _shortcut_histories[shortcut.resource_path] as UndoRedo


func _ensure_resource_parent_directory(resource_path: String) -> Dictionary:
	var directory_path := ProjectSettings.globalize_path(resource_path.get_base_dir())
	if DirAccess.dir_exists_absolute(directory_path):
		return {}
	var create_error := DirAccess.make_dir_recursive_absolute(directory_path)
	if create_error == OK:
		return {}
	return Errors.make(
		"SHORTCUT_DIRECTORY_CREATE_FAILED",
		"Godot could not create the parent directory for '%s': %s" % [
			resource_path, error_string(create_error)
		],
		false,
		"Check project directory permissions and use a writable res:// path.",
		{"error": create_error, "error_name": error_string(create_error)}
	)


func _save_error(resource_path: String, save_error: Error, operation: String) -> Dictionary:
	return Errors.make(
		"SHORTCUT_SAVE_FAILED",
		"Godot could not %s Shortcut '%s': %s" % [operation, resource_path, error_string(save_error)],
		false,
		"Check the parent directory, file permissions, and resource state.",
		{"error": save_error, "error_name": error_string(save_error)}
	)


func _require_editor_writable() -> Dictionary:
	var readiness := EditorState.readiness()
	if readiness == "ready":
		return {}
	return Errors.make(
		"EDITOR_NOT_WRITABLE",
		"The editor is not writable while its state is '%s'" % readiness,
		readiness == "importing",
		"Wait for imports to finish and stop the running scene before editing Shortcut resources.",
		{"readiness": readiness}
	)

@tool
extends RefCounted

const EditorState := preload("res://addons/godot_2d_mcp/utils/editor_state.gd")
const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")

const MAX_ACTIONS_PER_PAGE := 500
const MAX_EVENTS_PER_ACTION := 64
const MAX_SERIALIZED_EVENTS_PER_ACTION := 128
const MAX_ACTION_NAME_LENGTH := 128
const INPUT_ACTION_PREFIX := "input/"
const ACTION_LABEL_PREFIX := "Godot 2D MCP: Input Map"
const SUPPORTED_EVENT_TYPES := {
	"key": true,
	"mouse_button": true,
	"joypad_button": true,
	"joypad_motion": true,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_input_map(params: Dictionary) -> Dictionary:
	var query := str(params.get("query", "")).strip_edges().to_lower()
	var offset := maxi(0, int(params.get("offset", 0)))
	var limit := clampi(int(params.get("limit", 100)), 1, MAX_ACTIONS_PER_PAGE)
	var actions := _action_descriptors(query)
	var start := mini(offset, actions.size())
	var end := mini(start + limit, actions.size())
	var page: Array[Dictionary] = []
	if start < actions.size():
		page.assign(actions.slice(start, end))
	return {
		"actions": page,
		"total": actions.size(),
		"offset": start,
		"limit": limit,
		"has_more": end < actions.size(),
		"supported_event_types": SUPPORTED_EVENT_TYPES.keys(),
	}


func upsert_action(params: Dictionary) -> Dictionary:
	var writable := _require_project_writable()
	if writable != null:
		return writable
	var action_name_result := _parse_action_name(params.get("action", ""))
	if action_name_result.has("_error"):
		return action_name_result
	var action_name: String = action_name_result["action"]
	var property_name := _property_name(action_name)
	if _is_builtin_action(action_name):
		return Errors.make(
			"INPUT_ACTION_BUILTIN",
			"Built-in input action '%s' cannot be modified through MCP" % action_name,
			false,
			"Create a project-specific action instead of changing Godot's ui_* defaults."
		)
	var events_result := _parse_events(params.get("events", null))
	if events_result.has("_error"):
		return events_result
	var existed := ProjectSettings.has_setting(property_name)
	var replace_existing = params.get("replace_existing", false)
	if not replace_existing is bool:
		return Errors.make("INVALID_INPUT_ACTION", "replace_existing must be a boolean")
	if existed and not replace_existing:
		return Errors.make(
			"INPUT_ACTION_REPLACE_CONFIRMATION_REQUIRED",
			"Input action '%s' already exists" % action_name,
			false,
			"Read input_map_get, then resend the complete events list with replace_existing: true."
		)
	var previous_config: Dictionary = {}
	if existed:
		var existing_config = ProjectSettings.get_setting(property_name)
		if not existing_config is Dictionary or not existing_config.has("events"):
			return Errors.make(
				"INPUT_ACTION_INVALID",
				"Project setting '%s' is not a valid Input Map action" % property_name,
				false,
				"Repair the project setting in Godot before replacing it through MCP."
			)
		previous_config = (existing_config as Dictionary).duplicate(true)
	var deadzone_result := _parse_deadzone(params.get("deadzone", null), previous_config)
	if deadzone_result.has("_error"):
		return deadzone_result
	var next_config: Dictionary = {
		"deadzone": deadzone_result["deadzone"],
		"events": events_result["events"],
	}
	_commit_action_state(
		action_name,
		next_config,
		true,
		previous_config,
		existed,
		"%s: Upsert %s" % [ACTION_LABEL_PREFIX, action_name]
	)
	return {
		"action": _serialize_action(action_name, next_config, false),
		"created": not existed,
		"replaced": existed,
		"undoable": true,
		"project_saved": true,
	}


func delete_action(params: Dictionary) -> Dictionary:
	var writable := _require_project_writable()
	if writable != null:
		return writable
	var confirm = params.get("confirm", false)
	if not confirm is bool:
		return Errors.make("INVALID_INPUT_ACTION", "confirm must be a boolean")
	if not confirm:
		return Errors.make(
			"INPUT_ACTION_DELETE_CONFIRMATION_REQUIRED",
			"Deleting an Input Map action requires confirm: true",
			false,
			"Read input_map_get first, then resend with confirm: true."
		)
	var action_name_result := _parse_action_name(params.get("action", ""))
	if action_name_result.has("_error"):
		return action_name_result
	var action_name: String = action_name_result["action"]
	var property_name := _property_name(action_name)
	if not ProjectSettings.has_setting(property_name):
		return Errors.make(
			"INPUT_ACTION_NOT_FOUND",
			"Input action '%s' does not exist" % action_name,
			false,
			"Call input_map_get to inspect project-defined input actions."
		)
	if _is_builtin_action(action_name):
		return Errors.make(
			"INPUT_ACTION_BUILTIN",
			"Built-in input action '%s' cannot be deleted through MCP" % action_name,
			false,
			"Create and use a project-specific action instead."
		)
	var existing_config = ProjectSettings.get_setting(property_name)
	if not existing_config is Dictionary or not existing_config.has("events"):
		return Errors.make(
			"INPUT_ACTION_INVALID",
			"Project setting '%s' is not a valid Input Map action" % property_name
		)
	_commit_action_state(
		action_name,
		{},
		false,
		(existing_config as Dictionary).duplicate(true),
		true,
		"%s: Delete %s" % [ACTION_LABEL_PREFIX, action_name]
	)
	return {
		"action": action_name,
		"deleted": true,
		"undoable": true,
		"project_saved": true,
	}


func undo(params: Dictionary) -> Dictionary:
	var writable := _require_project_writable()
	if writable != null:
		return writable
	var history := _global_history()
	if history == null or not history.has_undo():
		return _history_response(history, false, "")
	var action_name := history.get_current_action_name()
	if not action_name.begins_with(ACTION_LABEL_PREFIX):
		return Errors.make(
			"INPUT_MAP_HISTORY_NOT_AVAILABLE",
			"The latest project-wide undo action was not created by Input Map tools",
			false,
			"Undo that action in Godot or call input_map_undo immediately after an Input Map change."
		)
	return _history_response(history, history.undo(), action_name)


func redo(params: Dictionary) -> Dictionary:
	var writable := _require_project_writable()
	if writable != null:
		return writable
	var history := _global_history()
	if history == null or not history.has_redo():
		return _history_response(history, false, "")
	var action_name := history.get_action_name(history.get_current_action() + 1)
	if not action_name.begins_with(ACTION_LABEL_PREFIX):
		return Errors.make(
			"INPUT_MAP_HISTORY_NOT_AVAILABLE",
			"The next project-wide redo action was not created by Input Map tools",
			false,
			"Redo that action in Godot or call input_map_redo immediately after input_map_undo."
		)
	return _history_response(history, history.redo(), action_name)


func _action_descriptors(query: String) -> Array[Dictionary]:
	var actions: Array[Dictionary] = []
	for property_info_value in ProjectSettings.get_property_list():
		var property_info: Dictionary = property_info_value
		var property_name := str(property_info.get("name", ""))
		if not property_name.begins_with(INPUT_ACTION_PREFIX):
			continue
		var action_name := property_name.trim_prefix(INPUT_ACTION_PREFIX)
		if not query.is_empty() and not action_name.to_lower().contains(query):
			continue
		var raw_config = ProjectSettings.get_setting(property_name)
		if not raw_config is Dictionary or not raw_config.has("events"):
			continue
		actions.append(
			_serialize_action(
				action_name,
				raw_config as Dictionary,
				_is_builtin_action(action_name)
			)
		)
	actions.sort_custom(
		func(left: Dictionary, right: Dictionary) -> bool: return left["action"] < right["action"]
	)
	return actions


func _serialize_action(action_name: String, config: Dictionary, builtin: bool) -> Dictionary:
	var events: Array[Dictionary] = []
	var events_truncated := false
	var raw_events = config.get("events", [])
	if raw_events is Array:
		for raw_event in raw_events:
			if events.size() >= MAX_SERIALIZED_EVENTS_PER_ACTION:
				events_truncated = true
				break
			events.append(_serialize_event(raw_event))
	return {
		"action": action_name,
		"deadzone": _safe_deadzone(config.get("deadzone", 0.2)),
		"events": events,
		"event_count": raw_events.size() if raw_events is Array else 0,
		"events_truncated": events_truncated,
		"builtin": builtin,
		"editable": not builtin,
		"active": InputMap.has_action(StringName(action_name)),
	}


func _serialize_event(raw_event: Variant) -> Dictionary:
	if not raw_event is InputEvent:
		return {"type": "unsupported", "supported": false, "class": type_string(typeof(raw_event))}
	var event: InputEvent = raw_event
	var descriptor := {
		"type": "unsupported",
		"supported": false,
		"class": event.get_class(),
		"device": event.get_device(),
		"text": event.as_text(),
	}
	if event is InputEventKey:
		var key_event := event as InputEventKey
		descriptor.merge(_serialize_modifier_event(key_event), true)
		descriptor.merge(
			{
				"type": "key",
				"supported": _is_serializable_key(key_event),
				"keycode": int(key_event.keycode),
				"physical_keycode": int(key_event.physical_keycode),
				"key_label": int(key_event.key_label),
				"unicode": key_event.unicode,
				"location": int(key_event.location),
			},
			true
		)
	elif event is InputEventMouseButton:
		var mouse_event := event as InputEventMouseButton
		descriptor.merge(_serialize_modifier_event(mouse_event), true)
		descriptor.merge(
			{
				"type": "mouse_button",
				"supported": int(mouse_event.button_index) >= 1 and int(mouse_event.button_index) <= 9,
				"button": int(mouse_event.button_index),
			},
			true
		)
	elif event is InputEventJoypadButton:
		var joypad_button := event as InputEventJoypadButton
		descriptor.merge(
			{
				"type": "joypad_button",
				"supported": int(joypad_button.button_index) >= 0 and int(joypad_button.button_index) < 128,
				"button": int(joypad_button.button_index),
			},
			true
		)
	elif event is InputEventJoypadMotion:
		var joypad_motion := event as InputEventJoypadMotion
		descriptor.merge(
			{
				"type": "joypad_motion",
				"supported": int(joypad_motion.axis) >= 0 and int(joypad_motion.axis) < 10
					and not is_zero_approx(joypad_motion.axis_value),
				"axis": int(joypad_motion.axis),
				"axis_value": _safe_number(joypad_motion.axis_value),
			},
			true
		)
	return descriptor


func _serialize_modifier_event(event: InputEventWithModifiers) -> Dictionary:
	return {
		"shift": event.is_shift_pressed(),
		"alt": event.is_alt_pressed(),
		"ctrl": event.is_ctrl_pressed(),
		"meta": event.is_meta_pressed(),
		"command_or_control_autoremap": event.is_command_or_control_autoremap(),
	}


func _is_serializable_key(event: InputEventKey) -> bool:
	var fields := 0
	for value in [event.keycode, event.physical_keycode, event.key_label, event.unicode]:
		if int(value) != 0:
			fields += 1
	return fields == 1


func _parse_events(value: Variant) -> Dictionary:
	if not value is Array or value.size() > MAX_EVENTS_PER_ACTION:
		return Errors.make(
			"INVALID_INPUT_EVENTS",
			"events must be an array with at most %d entries" % MAX_EVENTS_PER_ACTION
		)
	var events: Array[InputEvent] = []
	for index in value.size():
		var decoded := _decode_event(value[index])
		if decoded.has("_error"):
			return decoded.merged({"details": {"index": index}}, true)
		events.append(decoded["event"])
	return {"events": events}


func _decode_event(value: Variant) -> Dictionary:
	if not value is Dictionary:
		return Errors.make("INVALID_INPUT_EVENT", "Each event must be an object")
	var event: Dictionary = value
	match str(event.get("type", "")).strip_edges().to_lower():
		"key":
			return _decode_key_event(event)
		"mouse_button":
			return _decode_mouse_button_event(event)
		"joypad_button":
			return _decode_joypad_button_event(event)
		"joypad_motion":
			return _decode_joypad_motion_event(event)
	return Errors.make(
		"INVALID_INPUT_EVENT_TYPE",
		"event type must be key, mouse_button, joypad_button, or joypad_motion"
	)


func _decode_key_event(event: Dictionary) -> Dictionary:
	var allowed := {
		"type": true, "keycode": true, "physical_keycode": true, "key_label": true, "unicode": true,
		"location": true, "device": true, "shift": true, "alt": true, "ctrl": true, "meta": true,
		"command_or_control_autoremap": true,
	}
	var unknown := _unknown_fields(event, allowed)
	if not unknown.is_empty():
		return Errors.make("INVALID_INPUT_EVENT", "key event contains unsupported fields: %s" % ", ".join(unknown))
	var key_fields := ["keycode", "physical_keycode", "key_label", "unicode"]
	var supplied: Array[String] = []
	for field in key_fields:
		if event.has(field):
			supplied.append(field)
	if supplied.size() != 1:
		return Errors.make(
			"INVALID_INPUT_EVENT",
			"key event requires exactly one of keycode, physical_keycode, key_label, or unicode"
		)
	var key_value_result := _parse_non_negative_int(event[supplied[0]], supplied[0], 0x7FFFFFFF)
	if key_value_result.has("_error"):
		return key_value_result
	if int(key_value_result["value"]) == 0:
		return Errors.make("INVALID_INPUT_EVENT", "%s must not be zero" % supplied[0])
	var modifier_result := _parse_modifiers(event)
	if modifier_result.has("_error"):
		return modifier_result
	var device_result := _parse_device(event.get("device", -1))
	if device_result.has("_error"):
		return device_result
	var location_result := _parse_non_negative_int(event.get("location", 0), "location", 2)
	if location_result.has("_error"):
		return location_result
	var key_event := InputEventKey.new()
	key_event.set(supplied[0], int(key_value_result["value"]))
	key_event.location = int(location_result["value"])
	key_event.device = int(device_result["device"])
	_apply_modifiers(key_event, modifier_result)
	return {"event": key_event}


func _decode_mouse_button_event(event: Dictionary) -> Dictionary:
	var allowed := {
		"type": true, "button": true, "device": true, "shift": true, "alt": true, "ctrl": true,
		"meta": true, "command_or_control_autoremap": true,
	}
	var unknown := _unknown_fields(event, allowed)
	if not unknown.is_empty():
		return Errors.make("INVALID_INPUT_EVENT", "mouse_button event contains unsupported fields: %s" % ", ".join(unknown))
	var button_result := _parse_non_negative_int(event.get("button", null), "button", 9)
	if button_result.has("_error"):
		return button_result
	if int(button_result["value"]) < 1:
		return Errors.make("INVALID_INPUT_EVENT", "button must be between 1 and 9")
	var modifier_result := _parse_modifiers(event)
	if modifier_result.has("_error"):
		return modifier_result
	var device_result := _parse_device(event.get("device", -1))
	if device_result.has("_error"):
		return device_result
	var mouse_event := InputEventMouseButton.new()
	mouse_event.button_index = int(button_result["value"])
	mouse_event.device = int(device_result["device"])
	_apply_modifiers(mouse_event, modifier_result)
	return {"event": mouse_event}


func _decode_joypad_button_event(event: Dictionary) -> Dictionary:
	var allowed := {"type": true, "button": true, "device": true}
	var unknown := _unknown_fields(event, allowed)
	if not unknown.is_empty():
		return Errors.make("INVALID_INPUT_EVENT", "joypad_button event contains unsupported fields: %s" % ", ".join(unknown))
	var button_result := _parse_non_negative_int(event.get("button", null), "button", 127)
	if button_result.has("_error"):
		return button_result
	var device_result := _parse_device(event.get("device", -1))
	if device_result.has("_error"):
		return device_result
	var joypad_event := InputEventJoypadButton.new()
	joypad_event.button_index = int(button_result["value"])
	joypad_event.device = int(device_result["device"])
	return {"event": joypad_event}


func _decode_joypad_motion_event(event: Dictionary) -> Dictionary:
	var allowed := {"type": true, "axis": true, "axis_value": true, "device": true}
	var unknown := _unknown_fields(event, allowed)
	if not unknown.is_empty():
		return Errors.make("INVALID_INPUT_EVENT", "joypad_motion event contains unsupported fields: %s" % ", ".join(unknown))
	var axis_result := _parse_non_negative_int(event.get("axis", null), "axis", 9)
	if axis_result.has("_error"):
		return axis_result
	var axis_value = event.get("axis_value", null)
	if not _is_finite_number(axis_value) or absf(float(axis_value)) > 1.0 or is_zero_approx(float(axis_value)):
		return Errors.make("INVALID_INPUT_EVENT", "axis_value must be a non-zero finite number between -1 and 1")
	var device_result := _parse_device(event.get("device", -1))
	if device_result.has("_error"):
		return device_result
	var joypad_event := InputEventJoypadMotion.new()
	joypad_event.axis = int(axis_result["value"])
	joypad_event.axis_value = float(axis_value)
	joypad_event.device = int(device_result["device"])
	return {"event": joypad_event}


func _parse_modifiers(event: Dictionary) -> Dictionary:
	var result := {
		"shift": false,
		"alt": false,
		"ctrl": false,
		"meta": false,
		"command_or_control_autoremap": false,
	}
	for name in result.keys():
		if event.has(name):
			if not event[name] is bool:
				return Errors.make("INVALID_INPUT_EVENT", "%s must be a boolean" % name)
			result[name] = event[name]
	if bool(result["command_or_control_autoremap"]) and (bool(result["ctrl"]) or bool(result["meta"])):
		return Errors.make(
			"INVALID_INPUT_EVENT",
			"command_or_control_autoremap cannot be combined with ctrl or meta"
		)
	return result


func _apply_modifiers(event: InputEventWithModifiers, modifiers: Dictionary) -> void:
	event.shift_pressed = bool(modifiers["shift"])
	event.alt_pressed = bool(modifiers["alt"])
	if bool(modifiers["command_or_control_autoremap"]):
		event.command_or_control_autoremap = true
	else:
		event.ctrl_pressed = bool(modifiers["ctrl"])
		event.meta_pressed = bool(modifiers["meta"])


func _parse_deadzone(value: Variant, existing_config: Dictionary) -> Dictionary:
	if value == null:
		return {"deadzone": _safe_deadzone(existing_config.get("deadzone", 0.2))}
	if not _is_finite_number(value) or float(value) < 0.0 or float(value) > 1.0:
		return Errors.make("INVALID_INPUT_DEADZONE", "deadzone must be a finite number between 0 and 1")
	return {"deadzone": float(value)}


func _parse_action_name(value: Variant) -> Dictionary:
	if not value is String:
		return Errors.make("INVALID_INPUT_ACTION", "action must be a string")
	var action_name := (value as String).strip_edges()
	if action_name.is_empty() or action_name.length() > MAX_ACTION_NAME_LENGTH:
		return Errors.make(
			"INVALID_INPUT_ACTION",
			"action must contain between 1 and %d characters" % MAX_ACTION_NAME_LENGTH
		)
	for character in action_name:
		if character.unicode_at(0) < 32:
			return Errors.make("INVALID_INPUT_ACTION", "action must not contain control characters")
	return {"action": action_name}


func _parse_non_negative_int(value: Variant, label: String, maximum: int) -> Dictionary:
	if not _is_integral_number(value) or int(value) < 0 or int(value) > maximum:
		return Errors.make("INVALID_INPUT_EVENT", "%s must be an integer between 0 and %d" % [label, maximum])
	return {"value": int(value)}


func _parse_device(value: Variant) -> Dictionary:
	if not _is_integral_number(value) or int(value) < -1 or int(value) > 0x7FFFFFFF:
		return Errors.make("INVALID_INPUT_EVENT", "device must be an integer between -1 and 2147483647")
	return {"device": int(value)}


func _unknown_fields(event: Dictionary, allowed: Dictionary) -> Array[String]:
	var unknown: Array[String] = []
	for raw_name in event:
		var name := str(raw_name)
		if not allowed.has(name):
			unknown.append(name)
	unknown.sort()
	return unknown


func _commit_action_state(
	action_name: String,
	next_config: Dictionary,
	next_exists: bool,
	previous_config: Dictionary,
	previous_exists: bool,
	action_label: String
) -> void:
	_undo_redo.create_action(action_label, UndoRedo.MERGE_DISABLE, null, false, false)
	_undo_redo.add_do_method(self, "_apply_action_state", action_name, next_config, next_exists)
	_undo_redo.add_undo_method(self, "_apply_action_state", action_name, previous_config, previous_exists)
	_undo_redo.commit_action()


func _apply_action_state(action_name: String, config: Dictionary, exists: bool) -> void:
	var property_name := _property_name(action_name)
	if exists:
		ProjectSettings.set_setting(property_name, config)
	elif ProjectSettings.has_setting(property_name):
		ProjectSettings.clear(property_name)
	InputMap.load_from_project_settings()
	var save_error := ProjectSettings.save()
	if save_error != OK:
		push_error("Godot 2D MCP could not save Input Map settings: %s" % error_string(save_error))


func _global_history() -> UndoRedo:
	return _undo_redo.get_history_undo_redo(EditorUndoRedoManager.GLOBAL_HISTORY)


func _history_response(history: UndoRedo, changed: bool, action_name: String) -> Dictionary:
	return {
		"changed": changed,
		"action": action_name,
		"has_undo": history != null and history.has_undo(),
		"has_redo": history != null and history.has_redo(),
		"version": history.get_version() if history != null else 0,
		"project_saved": changed,
	}


func _property_name(action_name: String) -> String:
	return "%s%s" % [INPUT_ACTION_PREFIX, action_name]


func _is_builtin_action(action_name: String) -> bool:
	return action_name.begins_with("ui_")


func _require_project_writable() -> Variant:
	var readiness := EditorState.readiness()
	if readiness == "importing" or readiness == "playing":
		return Errors.make(
			"EDITOR_NOT_WRITABLE",
			"The editor cannot change Input Map settings while its state is '%s'" % readiness,
			readiness == "importing",
			"Wait for imports to finish and stop the running scene before changing Input Map settings.",
			{"readiness": readiness}
		)
	return null


func _safe_deadzone(value: Variant) -> float:
	return float(value) if _is_finite_number(value) and float(value) >= 0.0 and float(value) <= 1.0 else 0.2


func _safe_number(value: float) -> Variant:
	return value if is_finite(value) else null


func _is_finite_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


func _is_integral_number(value: Variant) -> bool:
	return _is_finite_number(value) and is_equal_approx(float(value), round(float(value)))

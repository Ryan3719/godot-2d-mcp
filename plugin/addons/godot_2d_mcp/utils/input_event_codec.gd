@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")

const SUPPORTED_EVENT_TYPES := {
	"key": true,
	"mouse_button": true,
	"joypad_button": true,
	"joypad_motion": true,
}


static func supported_event_types() -> Array:
	return SUPPORTED_EVENT_TYPES.keys()


static func serialize_event(raw_event: Variant) -> Dictionary:
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


static func parse_events(value: Variant, maximum: int, error_code: String, label: String) -> Dictionary:
	if not value is Array or value.size() > maximum:
		return Errors.make(error_code, "%s must be an array with at most %d entries" % [label, maximum])
	var events: Array[InputEvent] = []
	for index in value.size():
		var decoded := _decode_event(value[index])
		if decoded.has("_error"):
			return decoded.merged({"details": {"index": index}}, true)
		events.append(decoded["event"])
	return {"events": events}


static func _decode_event(value: Variant) -> Dictionary:
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


static func _decode_key_event(event: Dictionary) -> Dictionary:
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


static func _decode_mouse_button_event(event: Dictionary) -> Dictionary:
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


static func _decode_joypad_button_event(event: Dictionary) -> Dictionary:
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


static func _decode_joypad_motion_event(event: Dictionary) -> Dictionary:
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


static func _serialize_modifier_event(event: InputEventWithModifiers) -> Dictionary:
	return {
		"shift": event.is_shift_pressed(),
		"alt": event.is_alt_pressed(),
		"ctrl": event.is_ctrl_pressed(),
		"meta": event.is_meta_pressed(),
		"command_or_control_autoremap": event.is_command_or_control_autoremap(),
	}


static func _is_serializable_key(event: InputEventKey) -> bool:
	var fields := 0
	for value in [event.keycode, event.physical_keycode, event.key_label, event.unicode]:
		if int(value) != 0:
			fields += 1
	return fields == 1


static func _parse_modifiers(event: Dictionary) -> Dictionary:
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


static func _apply_modifiers(event: InputEventWithModifiers, modifiers: Dictionary) -> void:
	event.shift_pressed = bool(modifiers["shift"])
	event.alt_pressed = bool(modifiers["alt"])
	if bool(modifiers["command_or_control_autoremap"]):
		event.command_or_control_autoremap = true
	else:
		event.ctrl_pressed = bool(modifiers["ctrl"])
		event.meta_pressed = bool(modifiers["meta"])


static func _parse_non_negative_int(value: Variant, label: String, maximum: int) -> Dictionary:
	if not _is_integral_number(value) or int(value) < 0 or int(value) > maximum:
		return Errors.make("INVALID_INPUT_EVENT", "%s must be an integer between 0 and %d" % [label, maximum])
	return {"value": int(value)}


static func _parse_device(value: Variant) -> Dictionary:
	if not _is_integral_number(value) or int(value) < -1 or int(value) > 0x7FFFFFFF:
		return Errors.make("INVALID_INPUT_EVENT", "device must be an integer between -1 and 2147483647")
	return {"device": int(value)}


static func _unknown_fields(event: Dictionary, allowed: Dictionary) -> Array[String]:
	var unknown: Array[String] = []
	for raw_name in event:
		var name := str(raw_name)
		if not allowed.has(name):
			unknown.append(name)
	unknown.sort()
	return unknown


static func _safe_number(value: float) -> Variant:
	return value if is_finite(value) else null


static func _is_finite_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


static func _is_integral_number(value: Variant) -> bool:
	return _is_finite_number(value) and is_equal_approx(float(value), round(float(value)))

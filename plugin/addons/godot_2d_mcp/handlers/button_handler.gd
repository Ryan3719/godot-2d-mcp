@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")

const MAX_PROPERTIES := 32
const MAX_TEXT_LENGTH := 4096
const MAX_LANGUAGE_LENGTH := 128
const MAX_PATH_LENGTH := 4096

const BASE_PROPERTIES := [
	"disabled", "toggle_mode", "button_pressed", "action_mode", "button_mask",
	"keep_pressed_outside", "shortcut_feedback", "shortcut_in_tooltip", "button_group_path",
	"shortcut_path",
]
const BUTTON_PROPERTIES := [
	"text", "icon_path", "flat", "alignment", "text_overrun_behavior", "autowrap_mode",
	"autowrap_trim_flags", "clip_text", "icon_alignment", "vertical_icon_alignment", "expand_icon",
	"text_direction", "language",
]
const TEXTURE_BUTTON_PROPERTIES := [
	"texture_normal_path", "texture_pressed_path", "texture_hover_path", "texture_disabled_path",
	"texture_focused_path", "click_mask_path", "ignore_texture_size", "stretch_mode", "flip_h", "flip_v",
]
const PROPERTY_ORDER := [
	"disabled", "toggle_mode", "button_group", "button_pressed", "action_mode", "button_mask",
	"keep_pressed_outside", "shortcut_feedback", "shortcut_in_tooltip", "shortcut", "text", "icon", "flat",
	"alignment", "text_overrun_behavior", "autowrap_mode", "autowrap_trim_flags", "clip_text",
	"icon_alignment", "vertical_icon_alignment", "expand_icon", "text_direction", "language",
	"texture_normal", "texture_pressed", "texture_hover", "texture_disabled", "texture_focused",
	"texture_click_mask", "ignore_texture_size", "stretch_mode", "flip_h", "flip_v",
]
const RESOURCE_PROPERTIES := {
	"button_group": true,
	"shortcut": true,
	"icon": true,
	"texture_normal": true,
	"texture_pressed": true,
	"texture_hover": true,
	"texture_disabled": true,
	"texture_focused": true,
	"texture_click_mask": true,
}
const ACTION_MODES := {"press": 0, "release": 1}
const BUTTON_MASKS := {"left": 1, "right": 2, "middle": 4}
const HORIZONTAL_ALIGNMENTS := {"left": 0, "center": 1, "right": 2}
const VERTICAL_ALIGNMENTS := {"top": 0, "center": 1, "bottom": 2}
const TEXT_OVERRUN_BEHAVIORS := {
	"no_trimming": 0,
	"trim_characters": 1,
	"trim_words": 2,
	"ellipsis": 3,
	"word_ellipsis": 4,
	"ellipsis_force": 5,
	"word_ellipsis_force": 6,
}
const AUTOWRAP_MODES := {"off": 0, "arbitrary": 1, "word": 2, "smart_word": 3}
const AUTOWRAP_TRIM_FLAGS := {"trim_start": 64, "trim_end": 128}
const TEXT_DIRECTIONS := {"auto": 0, "ltr": 1, "rtl": 2, "inherited": 3}
const TEXTURE_STRETCH_MODES := {
	"scale": 0,
	"tile": 1,
	"keep": 2,
	"keep_centered": 3,
	"keep_aspect": 4,
	"keep_aspect_centered": 5,
	"keep_aspect_covered": 6,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_button_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_button(params, false)
	if resolved.has("_error"):
		return resolved
	return _button_response(resolved["button"], resolved["scene_root"])


func set_button_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_button(params)
	if resolved.has("_error"):
		return resolved
	var button: BaseButton = resolved["button"]
	var parsed := _parse_updates(params, button)
	if parsed.has("_error"):
		return parsed
	var changed := _changed_properties(button, parsed["updates"])
	if changed.is_empty():
		var unchanged := _button_response(button, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_updates(button, resolved["scene_root"], changed, "Update %s %s" % [button.get_class(), button.name])
	var result := _button_response(button, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_button(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var guarded := MutationGuard.require_scene(params, require_writable)
	if guarded.has("_error"):
		return guarded
	var scene_root: Node = guarded["scene_root"]
	var path := str(params.get("path", "")).strip_edges()
	if path.is_empty():
		return Errors.make("MISSING_PARAMETER", "path is required")
	var node := ScenePath.resolve(path, scene_root)
	if node == null:
		return Errors.make(
			"NODE_NOT_FOUND",
			"Node not found: %s" % path,
			false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if not node is BaseButton:
		return Errors.make(
			"BASE_BUTTON_REQUIRED",
			"Node '%s' is %s, not a BaseButton" % [node.name, node.get_class()],
			false,
			"Target a Button, TextureButton, LinkButton, CheckButton, OptionButton, or MenuButton."
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit button '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned button."
		)
	return {"button": node as BaseButton, "scene_root": scene_root}


func _parse_updates(params: Dictionary, button: BaseButton) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > MAX_PROPERTIES:
		return _invalid_configuration(
			"properties must be a non-empty object containing at most %d entries" % MAX_PROPERTIES
		)
	var allowed := _supported_properties(button)
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String or not allowed.has(raw_name):
			return Errors.make(
				"UNSUPPORTED_BUTTON_PROPERTY",
				"Unsupported %s property: %s" % [button.get_class(), str(raw_name)],
				false,
				"Call button_2d_get to inspect supported_properties for this node type."
			)
		var value_result := _parse_property_value(raw_name, raw_properties[raw_name])
		if value_result.has("_error"):
			return value_result
		updates[value_result["property_name"]] = value_result["value"]
	var validation := _validate_configuration(button, updates)
	if validation.has("_error"):
		return validation
	return {"updates": updates}


func _parse_property_value(name: String, raw_value: Variant) -> Dictionary:
	match name:
		"disabled", "toggle_mode", "button_pressed", "keep_pressed_outside", "shortcut_feedback", \
		"shortcut_in_tooltip", "flat", "clip_text", "expand_icon", "ignore_texture_size", "flip_h", "flip_v":
			return _parse_bool(raw_value, name)
		"action_mode":
			return _parse_enum(raw_value, name, ACTION_MODES)
		"button_mask":
			return _parse_button_mask(raw_value)
		"button_group_path":
			return _load_optional_resource(raw_value, "ButtonGroup", name, "button_group")
		"shortcut_path":
			return _load_optional_resource(raw_value, "Shortcut", name, "shortcut")
		"text":
			return _parse_string(raw_value, name, MAX_TEXT_LENGTH)
		"icon_path":
			return _load_optional_resource(raw_value, "Texture2D", name, "icon")
		"alignment", "icon_alignment":
			return _parse_enum(raw_value, name, HORIZONTAL_ALIGNMENTS)
		"vertical_icon_alignment":
			return _parse_enum(raw_value, name, VERTICAL_ALIGNMENTS)
		"text_overrun_behavior":
			return _parse_enum(raw_value, name, TEXT_OVERRUN_BEHAVIORS)
		"autowrap_mode":
			return _parse_enum(raw_value, name, AUTOWRAP_MODES)
		"autowrap_trim_flags":
			return _parse_autowrap_trim_flags(raw_value)
		"text_direction":
			return _parse_enum(raw_value, name, TEXT_DIRECTIONS)
		"language":
			return _parse_string(raw_value, name, MAX_LANGUAGE_LENGTH)
		"texture_normal_path":
			return _load_optional_resource(raw_value, "Texture2D", name, "texture_normal")
		"texture_pressed_path":
			return _load_optional_resource(raw_value, "Texture2D", name, "texture_pressed")
		"texture_hover_path":
			return _load_optional_resource(raw_value, "Texture2D", name, "texture_hover")
		"texture_disabled_path":
			return _load_optional_resource(raw_value, "Texture2D", name, "texture_disabled")
		"texture_focused_path":
			return _load_optional_resource(raw_value, "Texture2D", name, "texture_focused")
		"click_mask_path":
			return _load_optional_resource(raw_value, "BitMap", name, "texture_click_mask")
		"stretch_mode":
			return _parse_enum(raw_value, name, TEXTURE_STRETCH_MODES)
	return _invalid_configuration("Unsupported button property: %s" % name)


func _validate_configuration(button: BaseButton, updates: Dictionary) -> Dictionary:
	var toggle_mode := bool(updates.get("toggle_mode", button.is_toggle_mode()))
	var pressed := bool(updates.get("button_pressed", button.is_pressed()))
	if pressed and not toggle_mode:
		return _invalid_configuration("button_pressed requires toggle_mode to be true")
	return {}


func _parse_bool(raw_value: Variant, property_name: String) -> Dictionary:
	if not raw_value is bool:
		return _invalid_configuration("%s must be a boolean" % property_name)
	return {"property_name": property_name, "value": raw_value}


func _parse_string(raw_value: Variant, property_name: String, maximum_length: int) -> Dictionary:
	if not raw_value is String or raw_value.length() > maximum_length:
		return _invalid_configuration("%s must be a string up to %d characters" % [property_name, maximum_length])
	return {"property_name": property_name, "value": raw_value}


func _parse_enum(raw_value: Variant, property_name: String, values: Dictionary) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must be one of: %s" % [property_name, _enum_options(values)])
	var name: String = raw_value.strip_edges().to_lower()
	if not values.has(name):
		return _invalid_configuration("%s must be one of: %s" % [property_name, _enum_options(values)])
	return {"property_name": property_name, "value": values[name]}


func _parse_button_mask(raw_value: Variant) -> Dictionary:
	if not raw_value is Array or raw_value.size() > BUTTON_MASKS.size():
		return _invalid_configuration("button_mask must contain unique left, right, or middle button names")
	var mask := 0
	var seen := {}
	for raw_name in raw_value:
		if not raw_name is String:
			return _invalid_configuration("button_mask must contain unique left, right, or middle button names")
		var name: String = raw_name.strip_edges().to_lower()
		if not BUTTON_MASKS.has(name) or seen.has(name):
			return _invalid_configuration("button_mask must contain unique left, right, or middle button names")
		seen[name] = true
		mask |= int(BUTTON_MASKS[name])
	return {"property_name": "button_mask", "value": mask}


func _parse_autowrap_trim_flags(raw_value: Variant) -> Dictionary:
	if not raw_value is Array or raw_value.size() > AUTOWRAP_TRIM_FLAGS.size():
		return _invalid_configuration("autowrap_trim_flags must contain unique trim_start or trim_end names")
	var flags := 0
	var seen := {}
	for raw_name in raw_value:
		if not raw_name is String:
			return _invalid_configuration("autowrap_trim_flags must contain unique trim_start or trim_end names")
		var name: String = raw_name.strip_edges().to_lower()
		if not AUTOWRAP_TRIM_FLAGS.has(name) or seen.has(name):
			return _invalid_configuration("autowrap_trim_flags must contain unique trim_start or trim_end names")
		seen[name] = true
		flags |= int(AUTOWRAP_TRIM_FLAGS[name])
	return {"property_name": "autowrap_trim_flags", "value": flags}


func _load_optional_resource(
	raw_value: Variant, expected_type: String, input_name: String, property_name: String
) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must be a res:// string or an empty string" % input_name)
	var resource_path: String = raw_value.strip_edges()
	if resource_path.is_empty():
		return {"property_name": property_name, "value": null}
	if resource_path.length() > MAX_PATH_LENGTH or not resource_path.begins_with("res://") \
		or resource_path.contains("/../") or resource_path.ends_with("/.."):
		return _invalid_configuration("%s must remain inside the project res:// directory" % input_name)
	if not ResourceLoader.exists(resource_path):
		return Errors.make("RESOURCE_NOT_FOUND", "Resource does not exist: %s" % resource_path)
	var resource := ResourceLoader.load(resource_path)
	if resource == null or not resource.is_class(expected_type):
		return Errors.make(
			"RESOURCE_TYPE_MISMATCH",
			"%s must load %s" % [input_name, expected_type],
			false,
			"Use an existing project-local %s resource." % expected_type
		)
	return {"property_name": property_name, "value": resource}


func _changed_properties(button: BaseButton, updates: Dictionary) -> Dictionary:
	var changed := {}
	for property_name_value in PROPERTY_ORDER:
		var property_name := str(property_name_value)
		if updates.has(property_name) and button.get(property_name) != updates[property_name]:
			changed[property_name] = updates[property_name]
	return changed


func _commit_updates(button: BaseButton, scene_root: Node, updates: Dictionary, action_label: String) -> void:
	_undo_redo.create_action("Godot 2D MCP: %s" % action_label, UndoRedo.MERGE_DISABLE, scene_root, true)
	for property_name_value in PROPERTY_ORDER:
		var property_name := str(property_name_value)
		if not updates.has(property_name):
			continue
		var old_value = button.get(property_name)
		var new_value = updates[property_name]
		_undo_redo.add_do_property(button, property_name, new_value)
		if RESOURCE_PROPERTIES.has(property_name) and new_value is Resource:
			_undo_redo.add_do_reference(new_value)
		_undo_redo.add_undo_property(button, property_name, old_value)
		if RESOURCE_PROPERTIES.has(property_name) and old_value is Resource:
			_undo_redo.add_undo_reference(old_value)
	_undo_redo.commit_action()


func _button_response(button: BaseButton, scene_root: Node) -> Dictionary:
	var configuration := {
		"disabled": button.is_disabled(),
		"toggle_mode": button.is_toggle_mode(),
		"button_pressed": button.is_pressed(),
		"action_mode": _enum_name(int(button.get_action_mode()), ACTION_MODES),
		"button_mask": _serialize_button_mask(int(button.get_button_mask())),
		"keep_pressed_outside": button.is_keep_pressed_outside(),
		"shortcut_feedback": button.is_shortcut_feedback(),
		"shortcut_in_tooltip": button.is_shortcut_in_tooltip_enabled(),
		"button_group": _resource_descriptor(button.get_button_group()),
		"shortcut": _resource_descriptor(button.get_shortcut()),
		"draw_mode": _draw_mode_name(int(button.get_draw_mode())),
	}
	if button is Button:
		configuration["button"] = _serialize_text_button(button as Button)
	if button is TextureButton:
		configuration["texture_button"] = _serialize_texture_button(button as TextureButton)
	return {
		"path": ScenePath.from_node(button, scene_root),
		"type": button.get_class(),
		"configuration": configuration,
		"supported_properties": _supported_properties(button),
	}


func _serialize_text_button(button: Button) -> Dictionary:
	return {
		"text": button.get_text(),
		"icon": _resource_descriptor(button.get_button_icon()),
		"flat": button.is_flat(),
		"alignment": _enum_name(int(button.get_text_alignment()), HORIZONTAL_ALIGNMENTS),
		"text_overrun_behavior": _enum_name(
			int(button.get_text_overrun_behavior()), TEXT_OVERRUN_BEHAVIORS
		),
		"autowrap_mode": _enum_name(int(button.get_autowrap_mode()), AUTOWRAP_MODES),
		"autowrap_trim_flags": _serialize_autowrap_trim_flags(int(button.get_autowrap_trim_flags())),
		"clip_text": button.get_clip_text(),
		"icon_alignment": _enum_name(int(button.get_icon_alignment()), HORIZONTAL_ALIGNMENTS),
		"vertical_icon_alignment": _enum_name(
			int(button.get_vertical_icon_alignment()), VERTICAL_ALIGNMENTS
		),
		"expand_icon": button.is_expand_icon(),
		"text_direction": _enum_name(int(button.get_text_direction()), TEXT_DIRECTIONS),
		"language": button.get_language(),
	}


func _serialize_texture_button(button: TextureButton) -> Dictionary:
	return {
		"texture_normal": _resource_descriptor(button.get_texture_normal()),
		"texture_pressed": _resource_descriptor(button.get_texture_pressed()),
		"texture_hover": _resource_descriptor(button.get_texture_hover()),
		"texture_disabled": _resource_descriptor(button.get_texture_disabled()),
		"texture_focused": _resource_descriptor(button.get_texture_focused()),
		"click_mask": _resource_descriptor(button.get_click_mask()),
		"ignore_texture_size": button.get_ignore_texture_size(),
		"stretch_mode": _enum_name(int(button.get_stretch_mode()), TEXTURE_STRETCH_MODES),
		"flip_h": button.is_flipped_h(),
		"flip_v": button.is_flipped_v(),
	}


func _resource_descriptor(resource: Resource) -> Dictionary:
	if resource == null:
		return {"assigned": false, "origin": "none", "resource_path": "", "resource_type": ""}
	return {
		"assigned": true,
		"origin": "external" if not resource.resource_path.is_empty() else "embedded",
		"resource_path": resource.resource_path,
		"resource_type": resource.get_class(),
	}


func _supported_properties(button: BaseButton) -> Array:
	var properties: Array = BASE_PROPERTIES.duplicate()
	if button is Button:
		properties.append_array(BUTTON_PROPERTIES)
	if button is TextureButton:
		properties.append_array(TEXTURE_BUTTON_PROPERTIES)
	return properties


func _serialize_button_mask(mask: int) -> Array[String]:
	var names: Array[String] = []
	for name_value in ["left", "right", "middle"]:
		var name: String = name_value
		if mask & int(BUTTON_MASKS[name]):
			names.append(name)
	return names


func _serialize_autowrap_trim_flags(flags: int) -> Array[String]:
	var names: Array[String] = []
	for name_value in ["trim_start", "trim_end"]:
		var name: String = name_value
		if flags & int(AUTOWRAP_TRIM_FLAGS[name]):
			names.append(name)
	return names


func _draw_mode_name(draw_mode: int) -> String:
	match draw_mode:
		0:
			return "normal"
		1:
			return "pressed"
		2:
			return "hover"
		3:
			return "disabled"
		4:
			return "hover_pressed"
	return "unknown"


func _enum_name(value: int, values: Dictionary) -> String:
	for name in values:
		if int(values[name]) == value:
			return str(name)
	return "unknown"


func _enum_options(values: Dictionary) -> String:
	var names: Array[String] = []
	for name in values:
		names.append(str(name))
	names.sort()
	return ", ".join(names)


func _invalid_configuration(message: String) -> Dictionary:
	return Errors.make("INVALID_BUTTON_CONFIGURATION", message)

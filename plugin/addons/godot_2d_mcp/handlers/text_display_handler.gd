@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")

const MAX_PROPERTIES := 40
const MAX_TEXT_LENGTH := 65_536
const MAX_LANGUAGE_LENGTH := 128
const MAX_PATH_LENGTH := 4096
const MAX_TAB_STOPS := 32
const MAX_TAB_STOP := 100_000.0
const MAX_PROGRESS_DELAY := 10_000
const LABEL_PROPERTIES := [
	"text", "label_settings_path", "horizontal_alignment", "vertical_alignment", "autowrap_mode",
	"autowrap_trim_flags", "justification_flags", "paragraph_separator", "clip_text",
	"text_overrun_behavior", "ellipsis_char", "uppercase", "tab_stops", "lines_skipped",
	"max_lines_visible", "visible_characters", "visible_characters_behavior", "visible_ratio",
	"text_direction", "language",
]
const LABEL_STATE_ORDER := [
	"label_settings", "text", "horizontal_alignment", "vertical_alignment", "autowrap_mode",
	"autowrap_trim_flags", "justification_flags", "paragraph_separator", "clip_text",
	"text_overrun_behavior", "ellipsis_char", "uppercase", "tab_stops", "lines_skipped",
	"max_lines_visible", "visible_characters_behavior", "visible_characters", "visible_ratio",
	"text_direction", "language",
]
const RICH_TEXT_LABEL_PROPERTIES := [
	"bbcode_enabled", "text", "fit_content", "scroll_active", "scroll_following",
	"scroll_following_visible_characters", "autowrap_mode", "autowrap_trim_flags", "tab_size",
	"context_menu_enabled", "shortcut_keys_enabled", "horizontal_alignment", "vertical_alignment",
	"justification_flags", "tab_stops", "meta_underlined", "hint_underlined", "threaded",
	"progress_bar_delay", "selection_enabled", "deselect_on_focus_loss_enabled",
	"drag_and_drop_selection_enabled", "visible_characters", "visible_characters_behavior",
	"visible_ratio", "text_direction", "language",
]
const RICH_TEXT_LABEL_STATE_ORDER := RICH_TEXT_LABEL_PROPERTIES
const BOOLEAN_PROPERTIES := {
	"bbcode_enabled": true,
	"fit_content": true,
	"scroll_active": true,
	"scroll_following": true,
	"scroll_following_visible_characters": true,
	"context_menu_enabled": true,
	"shortcut_keys_enabled": true,
	"meta_underlined": true,
	"hint_underlined": true,
	"threaded": true,
	"selection_enabled": true,
	"deselect_on_focus_loss_enabled": true,
	"drag_and_drop_selection_enabled": true,
	"clip_text": true,
	"uppercase": true,
}
const ENUMS := {
	"horizontal_alignment": {"left": 0, "center": 1, "right": 2, "fill": 3},
	"vertical_alignment": {"top": 0, "center": 1, "bottom": 2, "fill": 3},
	"autowrap_mode": {"off": 0, "arbitrary": 1, "word": 2, "smart_word": 3},
	"text_overrun_behavior": {
		"no_trimming": 0, "trim_characters": 1, "trim_words": 2, "ellipsis": 3,
		"word_ellipsis": 4, "ellipsis_force": 5, "word_ellipsis_force": 6,
	},
	"visible_characters_behavior": {
		"before_shaping": 0, "after_shaping": 1, "glyphs_auto": 2, "glyphs_ltr": 3,
		"glyphs_rtl": 4,
	},
	"text_direction": {"auto": 0, "ltr": 1, "rtl": 2, "inherited": 3},
}
const AUTOWRAP_TRIM_FLAGS := {"trim_start": 64, "trim_end": 128}
const JUSTIFICATION_FLAGS := {
	"kashida": 1,
	"word_bound": 2,
	"after_last_tab": 8,
	"skip_last_line": 32,
	"skip_last_line_with_visible_characters": 64,
	"do_not_skip_single_line": 128,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_text_display_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_text_display(params, false)
	if resolved.has("_error"):
		return resolved
	return _response(resolved["control"], resolved["scene_root"])


func set_text_display_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_text_display(params)
	if resolved.has("_error"):
		return resolved
	var control: Control = resolved["control"]
	var parsed := _parse_updates(params, control)
	if parsed.has("_error"):
		return parsed
	var old_state := _state(control)
	var next_state := old_state.duplicate(true)
	for property_name in parsed["updates"]:
		next_state[property_name] = parsed["updates"][property_name]
	if _states_equal(old_state, next_state):
		var unchanged := _response(control, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Update %s %s" % [control.get_class(), control.name],
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	if control is Label:
		var next_settings: Resource = next_state["label_settings"]
		var old_settings: Resource = old_state["label_settings"]
		if next_settings != null:
			_undo_redo.add_do_reference(next_settings)
		if old_settings != null:
			_undo_redo.add_undo_reference(old_settings)
	_undo_redo.add_do_method(self, "_apply_state", control, next_state)
	_undo_redo.add_undo_method(self, "_apply_state", control, old_state)
	_undo_redo.commit_action()
	var result := _response(control, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_text_display(params: Dictionary, require_writable: bool = true) -> Dictionary:
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
	if not (node is Label or node is RichTextLabel):
		return Errors.make(
			"TEXT_DISPLAY_2D_REQUIRED",
			"Node '%s' is %s, not a Label or RichTextLabel" % [node.name, node.get_class()],
			false,
			"Target a Label or RichTextLabel."
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit text display '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned text display control."
		)
	return {"control": node as Control, "scene_root": scene_root}


func _parse_updates(params: Dictionary, control: Control) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > MAX_PROPERTIES:
		return _invalid_configuration(
			"properties must be a non-empty object containing at most %d entries" % MAX_PROPERTIES
		)
	var allowed := _supported_properties(control)
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String or not allowed.has(raw_name):
			return Errors.make(
				"UNSUPPORTED_TEXT_DISPLAY_PROPERTY",
				"Unsupported %s property: %s" % [control.get_class(), str(raw_name)],
				false,
				"Call text_display_2d_get to inspect supported_properties for this node type."
			)
		var property_name: String = raw_name
		var parsed := _parse_property(property_name, raw_properties[property_name])
		if parsed.has("_error"):
			return parsed
		updates[parsed["property_name"]] = parsed["value"]
	return {"updates": updates}


func _parse_property(property_name: String, raw_value: Variant) -> Dictionary:
	if BOOLEAN_PROPERTIES.has(property_name):
		if not raw_value is bool:
			return _invalid_configuration("%s must be a boolean" % property_name)
		return {"property_name": property_name, "value": raw_value}
	if ENUMS.has(property_name):
		var enum_result := _parse_enum(property_name, raw_value, ENUMS[property_name])
		if enum_result.has("_error"):
			return enum_result
		enum_result["property_name"] = property_name
		return enum_result
	if property_name == "label_settings_path":
		return _load_label_settings(raw_value)
	if property_name in ["autowrap_trim_flags", "justification_flags"]:
		var flags := AUTOWRAP_TRIM_FLAGS if property_name == "autowrap_trim_flags" else JUSTIFICATION_FLAGS
		var flags_result := _parse_flags(property_name, raw_value, flags)
		if flags_result.has("_error"):
			return flags_result
		flags_result["property_name"] = property_name
		return flags_result
	if property_name == "tab_stops":
		var tab_stops := _parse_tab_stops(raw_value)
		if tab_stops.has("_error"):
			return tab_stops
		tab_stops["property_name"] = property_name
		return tab_stops
	if property_name in ["text", "paragraph_separator", "language", "ellipsis_char"]:
		return _parse_string(property_name, raw_value)
	if property_name in ["lines_skipped", "max_lines_visible", "visible_characters", "tab_size", "progress_bar_delay"]:
		return _parse_integer_property(property_name, raw_value)
	if property_name == "visible_ratio":
		if not (raw_value is int or raw_value is float) or not is_finite(float(raw_value)) \
			or float(raw_value) < 0.0 or float(raw_value) > 1.0:
			return _invalid_configuration("visible_ratio must be a finite number between 0 and 1")
		return {"property_name": property_name, "value": float(raw_value)}
	return _invalid_configuration("Unsupported text display property: %s" % property_name)


func _parse_enum(property_name: String, raw_value: Variant, values: Dictionary) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must be one of: %s" % [property_name, _enum_options(values)])
	var name: String = raw_value.strip_edges().to_lower()
	if not values.has(name):
		return _invalid_configuration("%s must be one of: %s" % [property_name, _enum_options(values)])
	return {"value": values[name]}


func _parse_flags(property_name: String, raw_value: Variant, flags: Dictionary) -> Dictionary:
	if not raw_value is Array or raw_value.size() > flags.size():
		return _invalid_configuration("%s must contain unique supported names" % property_name)
	var value := 0
	var seen := {}
	for raw_name in raw_value:
		if not raw_name is String:
			return _invalid_configuration("%s must contain unique supported names" % property_name)
		var name: String = raw_name.strip_edges().to_lower()
		if not flags.has(name) or seen.has(name):
			return _invalid_configuration("%s must contain unique supported names" % property_name)
		seen[name] = true
		value |= int(flags[name])
	return {"value": value}


func _parse_tab_stops(raw_value: Variant) -> Dictionary:
	if not raw_value is Array or raw_value.size() > MAX_TAB_STOPS:
		return _invalid_configuration("tab_stops must contain at most %d values" % MAX_TAB_STOPS)
	var values := PackedFloat32Array()
	var previous := -1.0
	for raw_entry in raw_value:
		if not (raw_entry is int or raw_entry is float) or not is_finite(float(raw_entry)) \
			or float(raw_entry) < 0.0 or float(raw_entry) > MAX_TAB_STOP \
			or float(raw_entry) <= previous:
			return _invalid_configuration(
				"tab_stops must be strictly increasing finite numbers from 0 to %s" % MAX_TAB_STOP
			)
		var value := float(raw_entry)
		values.append(value)
		previous = value
	return {"value": values}


func _parse_string(property_name: String, raw_value: Variant) -> Dictionary:
	var maximum := MAX_TEXT_LENGTH
	if property_name == "language":
		maximum = MAX_LANGUAGE_LENGTH
	if property_name == "paragraph_separator":
		maximum = 128
	if not raw_value is String or raw_value.length() > maximum:
		return _invalid_configuration(
			"%s must be a string up to %d characters" % [property_name, maximum]
		)
	if property_name == "ellipsis_char" and raw_value.length() != 1:
		return _invalid_configuration("ellipsis_char must contain exactly one character")
	return {"property_name": property_name, "value": raw_value}


func _parse_integer_property(property_name: String, raw_value: Variant) -> Dictionary:
	var minimum := 0
	var maximum := 128_000
	match property_name:
		"lines_skipped":
			maximum = 999
		"max_lines_visible":
			minimum = -1
			maximum = 999
		"visible_characters":
			minimum = -1
		"tab_size":
			maximum = 24
		"progress_bar_delay":
			maximum = MAX_PROGRESS_DELAY
	if not (raw_value is int or raw_value is float) or not is_finite(float(raw_value)) \
		or float(raw_value) != floorf(float(raw_value)):
		return _invalid_configuration(
			"%s must be an integer between %d and %d" % [property_name, minimum, maximum]
		)
	var value := int(raw_value)
	if value < minimum or value > maximum:
		return _invalid_configuration(
			"%s must be an integer between %d and %d" % [property_name, minimum, maximum]
		)
	return {"property_name": property_name, "value": value}


func _load_label_settings(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("label_settings_path must be a res:// string or an empty string")
	var path: String = raw_value.strip_edges()
	if path.is_empty():
		return {"property_name": "label_settings", "value": null}
	if path.length() > MAX_PATH_LENGTH or not path.begins_with("res://") \
		or path.contains("/../") or path.ends_with("/.."):
		return _invalid_configuration("label_settings_path must remain inside the project res:// directory")
	if not ResourceLoader.exists(path):
		return Errors.make("RESOURCE_NOT_FOUND", "Resource does not exist: %s" % path)
	var resource := ResourceLoader.load(path)
	if resource == null or not resource.is_class("LabelSettings"):
		return Errors.make(
			"RESOURCE_TYPE_MISMATCH",
			"label_settings_path must load LabelSettings",
			false,
			"Use an existing project-local LabelSettings resource."
		)
	return {"property_name": "label_settings", "value": resource}


func _state(control: Control) -> Dictionary:
	var state := {}
	for property_name_value in _state_order(control):
		var property_name: String = property_name_value
		state[property_name] = control.get(property_name)
	return state


func _apply_state(control: Control, state: Dictionary) -> void:
	for property_name_value in _state_order(control):
		var property_name: String = property_name_value
		if state.has(property_name):
			control.set(property_name, state[property_name])


func _response(control: Control, scene_root: Node) -> Dictionary:
	var state := _state(control)
	var configuration := {}
	for property_name in state:
		var value = state[property_name]
		if property_name == "label_settings":
			configuration[property_name] = _resource_descriptor(value as Resource)
		elif ENUMS.has(property_name):
			configuration[property_name] = _enum_name(int(value), ENUMS[property_name])
		elif property_name == "autowrap_trim_flags":
			configuration[property_name] = _serialize_flags(int(value), AUTOWRAP_TRIM_FLAGS)
		elif property_name == "justification_flags":
			configuration[property_name] = _serialize_flags(int(value), JUSTIFICATION_FLAGS)
		elif property_name == "tab_stops":
			configuration[property_name] = Array(value)
		else:
			configuration[property_name] = value
	return {
		"path": ScenePath.from_node(control, scene_root),
		"type": control.get_class(),
		"configuration": configuration,
		"supported_properties": _supported_properties(control),
	}


func _supported_properties(control: Control) -> Array:
	return LABEL_PROPERTIES.duplicate() if control is Label else RICH_TEXT_LABEL_PROPERTIES.duplicate()


func _state_order(control: Control) -> Array:
	return LABEL_STATE_ORDER if control is Label else RICH_TEXT_LABEL_STATE_ORDER


func _states_equal(left: Dictionary, right: Dictionary) -> bool:
	if left.size() != right.size():
		return false
	for property_name in left:
		if not right.has(property_name) or left[property_name] != right[property_name]:
			return false
	return true


func _resource_descriptor(resource: Resource) -> Dictionary:
	if resource == null:
		return {"assigned": false, "origin": "none", "resource_path": "", "resource_type": ""}
	return {
		"assigned": true,
		"origin": "external" if not resource.resource_path.is_empty() else "embedded",
		"resource_path": resource.resource_path,
		"resource_type": resource.get_class(),
	}


func _serialize_flags(value: int, flags: Dictionary) -> Array[String]:
	var names: Array[String] = []
	for name_value in flags:
		var name: String = name_value
		if value & int(flags[name]):
			names.append(name)
	names.sort()
	return names


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
	return Errors.make("INVALID_TEXT_DISPLAY_CONFIGURATION", message)

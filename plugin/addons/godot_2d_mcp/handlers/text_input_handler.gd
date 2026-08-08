@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")

const MAX_PROPERTIES := 64
const MAX_TEXT_LENGTH := 65_536
const MAX_LANGUAGE_LENGTH := 128
const MAX_LIST_ITEMS := 128
const MAX_LIST_TEXT_LENGTH := 256
const MAX_PAIRS := 64
const MAX_PAIR_TEXT_LENGTH := 128

const LINE_EDIT_PROPERTIES := [
	"max_length", "text", "placeholder_text", "alignment", "editable",
	"keep_editing_on_text_submit", "expand_to_text_length", "context_menu_enabled",
	"emoji_menu_enabled", "backspace_deletes_composite_character_enabled", "clear_button_enabled",
	"shortcut_keys_enabled", "middle_mouse_paste_enabled", "selecting_enabled",
	"deselect_on_focus_loss_enabled", "drag_and_drop_selection_enabled", "flat",
	"draw_control_chars", "select_all_on_focus", "virtual_keyboard_enabled",
	"virtual_keyboard_show_on_focus", "virtual_keyboard_type", "caret_blink",
	"caret_blink_interval", "caret_force_displayed", "caret_mid_grapheme", "secret",
	"secret_character", "text_direction", "language",
]
const TEXT_EDIT_PROPERTIES := [
	"text", "placeholder_text", "editable", "context_menu_enabled", "emoji_menu_enabled",
	"backspace_deletes_composite_character_enabled", "shortcut_keys_enabled", "selecting_enabled",
	"deselect_on_focus_loss_enabled", "drag_and_drop_selection_enabled", "middle_mouse_paste_enabled",
	"empty_selection_clipboard_enabled", "wrap_mode", "autowrap_mode", "indent_wrapped_lines",
	"tab_input_mode", "virtual_keyboard_enabled", "virtual_keyboard_show_on_focus", "scroll_smooth",
	"scroll_v_scroll_speed", "scroll_past_end_of_file", "scroll_fit_content_height",
	"scroll_fit_content_width", "minimap_draw", "minimap_width", "caret_type", "caret_blink",
	"caret_blink_interval", "caret_draw_when_editable_disabled", "caret_move_on_right_click",
	"caret_mid_grapheme", "caret_multiple", "use_default_word_separators",
	"use_custom_word_separators", "custom_word_separators", "highlight_all_occurrences",
	"highlight_current_line", "draw_control_chars", "draw_tabs", "draw_spaces", "text_direction",
	"language",
]
const CODE_EDIT_PROPERTIES := [
	"symbol_lookup_on_click", "symbol_tooltip_on_hover", "line_folding", "line_length_guidelines",
	"gutters_draw_breakpoints_gutter", "gutters_draw_bookmarks", "gutters_draw_executing_lines",
	"gutters_draw_line_numbers", "gutters_zero_pad_line_numbers", "gutters_line_numbers_min_digits",
	"gutters_draw_fold_gutter", "code_completion_enabled", "code_completion_prefixes", "indent_size",
	"indent_use_spaces", "indent_automatic", "indent_automatic_prefixes",
	"auto_brace_completion_enabled", "auto_brace_completion_highlight_matching",
	"auto_brace_completion_pairs",
]
const LINE_EDIT_ORDER := LINE_EDIT_PROPERTIES
const TEXT_EDIT_ORDER := TEXT_EDIT_PROPERTIES
const CODE_EDIT_ORDER := TEXT_EDIT_PROPERTIES + CODE_EDIT_PROPERTIES
const BOOLEAN_PROPERTIES := {
	"editable": true,
	"keep_editing_on_text_submit": true,
	"expand_to_text_length": true,
	"context_menu_enabled": true,
	"emoji_menu_enabled": true,
	"backspace_deletes_composite_character_enabled": true,
	"clear_button_enabled": true,
	"shortcut_keys_enabled": true,
	"middle_mouse_paste_enabled": true,
	"selecting_enabled": true,
	"deselect_on_focus_loss_enabled": true,
	"drag_and_drop_selection_enabled": true,
	"flat": true,
	"draw_control_chars": true,
	"select_all_on_focus": true,
	"virtual_keyboard_enabled": true,
	"virtual_keyboard_show_on_focus": true,
	"caret_blink": true,
	"caret_force_displayed": true,
	"caret_mid_grapheme": true,
	"secret": true,
	"empty_selection_clipboard_enabled": true,
	"indent_wrapped_lines": true,
	"tab_input_mode": true,
	"scroll_smooth": true,
	"scroll_past_end_of_file": true,
	"scroll_fit_content_height": true,
	"scroll_fit_content_width": true,
	"minimap_draw": true,
	"caret_draw_when_editable_disabled": true,
	"caret_move_on_right_click": true,
	"caret_multiple": true,
	"use_default_word_separators": true,
	"use_custom_word_separators": true,
	"highlight_all_occurrences": true,
	"highlight_current_line": true,
	"draw_tabs": true,
	"draw_spaces": true,
	"symbol_lookup_on_click": true,
	"symbol_tooltip_on_hover": true,
	"line_folding": true,
	"gutters_draw_breakpoints_gutter": true,
	"gutters_draw_bookmarks": true,
	"gutters_draw_executing_lines": true,
	"gutters_draw_line_numbers": true,
	"gutters_zero_pad_line_numbers": true,
	"gutters_draw_fold_gutter": true,
	"code_completion_enabled": true,
	"indent_use_spaces": true,
	"indent_automatic": true,
	"auto_brace_completion_enabled": true,
	"auto_brace_completion_highlight_matching": true,
}
const ENUMS := {
	"alignment": {"left": 0, "center": 1, "right": 2, "fill": 3},
	"virtual_keyboard_type": {
		"default": 0, "multiline": 1, "number": 2, "decimal": 3, "phone": 4,
		"email": 5, "password": 6, "url": 7,
	},
	"text_direction": {"auto": 0, "ltr": 1, "rtl": 2, "inherited": 3},
	"wrap_mode": {"none": 0, "boundary": 1},
	"autowrap_mode": {"off": 0, "arbitrary": 1, "word": 2, "smart_word": 3},
	"caret_type": {"line": 0, "block": 1},
}
const INTEGER_LIMITS := {
	"max_length": {"minimum": 0, "maximum": 1_000_000},
	"minimap_width": {"minimum": 1, "maximum": 4096},
	"gutters_line_numbers_min_digits": {"minimum": 1, "maximum": 5},
	"indent_size": {"minimum": 1, "maximum": 64},
}
const NUMBER_LIMITS := {
	"caret_blink_interval": {"minimum": 0.1, "maximum": 10.0},
	"scroll_v_scroll_speed": {"minimum": 0.0, "maximum": 100_000.0},
}
const STRING_PROPERTIES := {
	"text": MAX_TEXT_LENGTH,
	"placeholder_text": MAX_TEXT_LENGTH,
	"language": MAX_LANGUAGE_LENGTH,
	"secret_character": 1,
	"custom_word_separators": MAX_TEXT_LENGTH,
}
const STRING_LIST_PROPERTIES := {"line_length_guidelines": false, "code_completion_prefixes": true, "indent_automatic_prefixes": true}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_text_input_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_text_input(params, false)
	if resolved.has("_error"):
		return resolved
	return _text_input_response(resolved["control"], resolved["scene_root"])


func set_text_input_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_text_input(params)
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
		var unchanged := _text_input_response(control, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Update %s %s" % [control.get_class(), control.name],
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	_undo_redo.add_do_method(self, "_apply_state", control, next_state)
	_undo_redo.add_undo_method(self, "_apply_state", control, old_state)
	_undo_redo.commit_action()
	var result := _text_input_response(control, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_text_input(params: Dictionary, require_writable: bool = true) -> Dictionary:
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
	if not (node is LineEdit or node is TextEdit):
		return Errors.make(
			"TEXT_INPUT_2D_REQUIRED",
			"Node '%s' is %s, not a LineEdit, TextEdit, or CodeEdit" % [node.name, node.get_class()],
			false,
			"Target a LineEdit, TextEdit, or CodeEdit."
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit text input '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned text input control."
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
		if not raw_name is String or raw_name not in allowed:
			return Errors.make(
				"UNSUPPORTED_TEXT_INPUT_PROPERTY",
				"Unsupported %s property: %s" % [control.get_class(), str(raw_name)],
				false,
				"Call text_input_2d_get to inspect supported_properties for this node type."
			)
		var property_name: String = raw_name
		var parsed := _parse_property(property_name, raw_properties[property_name])
		if parsed.has("_error"):
			return parsed
		updates[property_name] = parsed["value"]
	return {"updates": updates}


func _parse_property(property_name: String, raw_value: Variant) -> Dictionary:
	if BOOLEAN_PROPERTIES.has(property_name):
		if not raw_value is bool:
			return _invalid_configuration("%s must be a boolean" % property_name)
		return {"value": raw_value}
	if ENUMS.has(property_name):
		return _parse_enum(property_name, raw_value, ENUMS[property_name])
	if STRING_PROPERTIES.has(property_name):
		var maximum := int(STRING_PROPERTIES[property_name])
		if not raw_value is String or raw_value.length() > maximum:
			return _invalid_configuration(
				"%s must be a string up to %d characters" % [property_name, maximum]
			)
		if property_name == "secret_character" and raw_value.length() != 1:
			return _invalid_configuration("secret_character must contain exactly one character")
		return {"value": raw_value}
	if INTEGER_LIMITS.has(property_name):
		var limits: Dictionary = INTEGER_LIMITS[property_name]
		return _parse_integer(property_name, raw_value, int(limits["minimum"]), int(limits["maximum"]))
	if NUMBER_LIMITS.has(property_name):
		var number_limits: Dictionary = NUMBER_LIMITS[property_name]
		return _parse_number(
			property_name,
			raw_value,
			float(number_limits["minimum"]),
			float(number_limits["maximum"])
		)
	if STRING_LIST_PROPERTIES.has(property_name):
		return _parse_list(property_name, raw_value, bool(STRING_LIST_PROPERTIES[property_name]))
	if property_name == "auto_brace_completion_pairs":
		return _parse_pairs(raw_value)
	return _invalid_configuration("Unsupported text input property: %s" % property_name)


func _parse_enum(property_name: String, raw_value: Variant, values: Dictionary) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must be one of: %s" % [property_name, _enum_options(values)])
	var name: String = raw_value.strip_edges().to_lower()
	if not values.has(name):
		return _invalid_configuration("%s must be one of: %s" % [property_name, _enum_options(values)])
	return {"value": values[name]}


func _parse_integer(property_name: String, raw_value: Variant, minimum: int, maximum: int) -> Dictionary:
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
	return {"value": value}


func _parse_number(property_name: String, raw_value: Variant, minimum: float, maximum: float) -> Dictionary:
	if not (raw_value is int or raw_value is float) or not is_finite(float(raw_value)):
		return _invalid_configuration("%s must be a finite number" % property_name)
	var value := float(raw_value)
	if value < minimum or value > maximum:
		return _invalid_configuration(
			"%s must be between %s and %s" % [property_name, minimum, maximum]
		)
	return {"value": value}


func _parse_list(property_name: String, raw_value: Variant, strings: bool) -> Dictionary:
	if not raw_value is Array or raw_value.size() > MAX_LIST_ITEMS:
		return _invalid_configuration(
			"%s must contain at most %d entries" % [property_name, MAX_LIST_ITEMS]
		)
	if strings:
		var result := PackedStringArray()
		for entry in raw_value:
			if not entry is String or entry.length() > MAX_LIST_TEXT_LENGTH:
				return _invalid_configuration(
					"%s entries must be strings up to %d characters" % [property_name, MAX_LIST_TEXT_LENGTH]
				)
			result.append(entry)
		return {"value": result}
	var numbers := PackedInt32Array()
	var seen := {}
	for entry in raw_value:
		var parsed := _parse_integer(property_name, entry, 1, 100_000)
		if parsed.has("_error"):
			return parsed
		var value: int = parsed["value"]
		if seen.has(value):
			return _invalid_configuration("%s entries must be unique" % property_name)
		seen[value] = true
		numbers.append(value)
	return {"value": numbers}


func _parse_pairs(raw_value: Variant) -> Dictionary:
	if not raw_value is Dictionary or raw_value.size() > MAX_PAIRS:
		return _invalid_configuration("auto_brace_completion_pairs must contain at most %d entries" % MAX_PAIRS)
	var pairs := {}
	for raw_key in raw_value:
		var raw_value_entry = raw_value[raw_key]
		if not raw_key is String or not raw_value_entry is String or raw_key.is_empty() \
			or raw_value_entry.is_empty() or raw_key.length() > MAX_PAIR_TEXT_LENGTH \
			or raw_value_entry.length() > MAX_PAIR_TEXT_LENGTH:
			return _invalid_configuration(
				"auto_brace_completion_pairs keys and values must be non-empty strings up to %d characters" % MAX_PAIR_TEXT_LENGTH
			)
		pairs[raw_key] = raw_value_entry
	return {"value": pairs}


func _state(control: Control) -> Dictionary:
	var state := {}
	for property_name_value in _property_order(control):
		var property_name: String = property_name_value
		state[property_name] = control.get(property_name)
	return state


func _apply_state(control: Control, state: Dictionary) -> void:
	for property_name_value in _property_order(control):
		var property_name: String = property_name_value
		if state.has(property_name):
			control.set(property_name, state[property_name])


func _text_input_response(control: Control, scene_root: Node) -> Dictionary:
	var state := _state(control)
	var configuration := {}
	for property_name in state:
		var value = state[property_name]
		if ENUMS.has(property_name):
			configuration[property_name] = _enum_name(int(value), ENUMS[property_name])
		elif property_name in ["line_length_guidelines", "code_completion_prefixes", "indent_automatic_prefixes"]:
			configuration[property_name] = Array(value)
		elif property_name == "auto_brace_completion_pairs":
			configuration[property_name] = (value as Dictionary).duplicate(true)
		else:
			configuration[property_name] = value
	return {
		"path": ScenePath.from_node(control, scene_root),
		"type": control.get_class(),
		"configuration": configuration,
		"supported_properties": _supported_properties(control),
	}


func _supported_properties(control: Control) -> Array:
	return _property_order(control).duplicate()


func _property_order(control: Control) -> Array:
	if control is LineEdit:
		return LINE_EDIT_ORDER
	if control is CodeEdit:
		return CODE_EDIT_ORDER
	return TEXT_EDIT_ORDER


func _states_equal(left: Dictionary, right: Dictionary) -> bool:
	if left.size() != right.size():
		return false
	for property_name in left:
		if not right.has(property_name) or left[property_name] != right[property_name]:
			return false
	return true


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
	return Errors.make("INVALID_TEXT_INPUT_CONFIGURATION", message)

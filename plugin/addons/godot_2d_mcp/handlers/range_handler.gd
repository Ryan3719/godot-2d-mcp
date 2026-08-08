@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")

const MAX_PROPERTIES := 20
const MAX_ABSOLUTE_VALUE := 1_000_000_000.0
const MAX_TEXT_LENGTH := 256
const BASE_PROPERTIES := [
	"min_value", "max_value", "value", "step", "page", "allow_greater", "allow_lesser",
	"exp_edit", "rounded",
]
const PROGRESS_BAR_PROPERTIES := [
	"fill_mode", "indeterminate", "show_percentage", "editor_preview_indeterminate",
]
const SLIDER_PROPERTIES := [
	"editable", "scrollable", "tick_count", "ticks_on_borders", "ticks_position",
]
const SCROLL_BAR_PROPERTIES := ["custom_step"]
const SPIN_BOX_PROPERTIES := [
	"alignment", "custom_arrow_round", "custom_arrow_step", "editable", "prefix", "suffix",
	"select_all_on_focus", "update_on_text_changed",
]
const PROGRESS_BAR_FILL_MODES := {
	"begin_to_end": 0,
	"end_to_begin": 1,
	"top_to_bottom": 2,
	"bottom_to_top": 3,
}
const SLIDER_TICK_POSITIONS := {
	"bottom_right": 0,
	"top_left": 1,
	"both": 2,
	"center": 3,
}
const SPIN_BOX_ALIGNMENTS := {"left": 0, "center": 1, "right": 2, "fill": 3}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_range_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_range(params, false)
	if resolved.has("_error"):
		return resolved
	return _range_response(resolved["range"], resolved["scene_root"])


func set_range_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_range(params)
	if resolved.has("_error"):
		return resolved
	var range: Range = resolved["range"]
	var parsed := _parse_updates(params, range)
	if parsed.has("_error"):
		return parsed
	var old_state := _range_state(range)
	var next_state := old_state.duplicate(true)
	for property_name in parsed["updates"]:
		next_state[property_name] = parsed["updates"][property_name]
	var validation := _validate_state(next_state)
	if validation.has("_error"):
		return validation
	if _states_equal(old_state, next_state):
		var unchanged := _range_response(range, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Update %s %s" % [range.get_class(), range.name],
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	_undo_redo.add_do_method(self, "_apply_range_state", range, next_state)
	_undo_redo.add_undo_method(self, "_apply_range_state", range, old_state)
	_undo_redo.commit_action()
	var result := _range_response(range, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_range(params: Dictionary, require_writable: bool = true) -> Dictionary:
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
	if not node is Range:
		return Errors.make(
			"RANGE_2D_REQUIRED",
			"Node '%s' is %s, not a Range control" % [node.name, node.get_class()],
			false,
			"Target a ProgressBar, HSlider, VSlider, HScrollBar, VScrollBar, or SpinBox."
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit range control '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned range control."
		)
	return {"range": node as Range, "scene_root": scene_root}


func _parse_updates(params: Dictionary, range: Range) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > MAX_PROPERTIES:
		return _invalid_configuration(
			"properties must be a non-empty object containing at most %d entries" % MAX_PROPERTIES
		)
	var allowed := _supported_properties(range)
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String or not allowed.has(raw_name):
			return Errors.make(
				"UNSUPPORTED_RANGE_PROPERTY",
				"Unsupported %s property: %s" % [range.get_class(), str(raw_name)],
				false,
				"Call range_2d_get to inspect supported_properties for this node type."
			)
		var property_name: String = raw_name
		var value_result := _parse_property_value(property_name, raw_properties[property_name])
		if value_result.has("_error"):
			return value_result
		updates[property_name] = value_result["value"]
	return {"updates": updates}


func _parse_property_value(property_name: String, raw_value: Variant) -> Dictionary:
	if property_name in ["allow_greater", "allow_lesser", "exp_edit", "rounded", "indeterminate", "show_percentage", "editor_preview_indeterminate", "editable", "scrollable", "ticks_on_borders", "custom_arrow_round", "select_all_on_focus", "update_on_text_changed"]:
		return _parse_bool(raw_value, property_name)
	if property_name in ["min_value", "max_value", "value"]:
		return _parse_number(raw_value, property_name, -MAX_ABSOLUTE_VALUE, MAX_ABSOLUTE_VALUE)
	if property_name in ["step", "page", "custom_arrow_step"]:
		return _parse_number(raw_value, property_name, 0.0, MAX_ABSOLUTE_VALUE)
	if property_name == "custom_step":
		var custom_step := _parse_number(raw_value, property_name, -1.0, MAX_ABSOLUTE_VALUE)
		if custom_step.has("_error"):
			return custom_step
		if float(custom_step["value"]) < 0.0 and float(custom_step["value"]) != -1.0:
			return _invalid_configuration("custom_step must be -1 or a non-negative number")
		return custom_step
	if property_name == "tick_count":
		return _parse_integer(raw_value, property_name, 0, 4096)
	if property_name == "fill_mode":
		return _parse_enum(raw_value, property_name, PROGRESS_BAR_FILL_MODES)
	if property_name == "ticks_position":
		return _parse_enum(raw_value, property_name, SLIDER_TICK_POSITIONS)
	if property_name == "alignment":
		return _parse_enum(raw_value, property_name, SPIN_BOX_ALIGNMENTS)
	if property_name in ["prefix", "suffix"]:
		if not raw_value is String or raw_value.length() > MAX_TEXT_LENGTH:
			return _invalid_configuration(
				"%s must be a string up to %d characters" % [property_name, MAX_TEXT_LENGTH]
			)
		return {"value": raw_value}
	return _invalid_configuration("Unsupported range control property: %s" % property_name)


func _parse_bool(raw_value: Variant, property_name: String) -> Dictionary:
	if not raw_value is bool:
		return _invalid_configuration("%s must be a boolean" % property_name)
	return {"value": raw_value}


func _parse_number(raw_value: Variant, property_name: String, minimum: float, maximum: float) -> Dictionary:
	if not (raw_value is int or raw_value is float) or not is_finite(float(raw_value)):
		return _invalid_configuration("%s must be a finite number" % property_name)
	var value := float(raw_value)
	if value < minimum or value > maximum:
		return _invalid_configuration(
			"%s must be between %s and %s" % [property_name, minimum, maximum]
		)
	return {"value": value}


func _parse_integer(raw_value: Variant, property_name: String, minimum: int, maximum: int) -> Dictionary:
	if not (raw_value is int or raw_value is float) or not is_finite(float(raw_value)) \
		or float(raw_value) != floorf(float(raw_value)):
		return _invalid_configuration("%s must be an integer between %d and %d" % [property_name, minimum, maximum])
	var value := int(raw_value)
	if value < minimum or value > maximum:
		return _invalid_configuration("%s must be an integer between %d and %d" % [property_name, minimum, maximum])
	return {"value": value}


func _parse_enum(raw_value: Variant, property_name: String, values: Dictionary) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must be one of: %s" % [property_name, _enum_options(values)])
	var name: String = raw_value.strip_edges().to_lower()
	if not values.has(name):
		return _invalid_configuration("%s must be one of: %s" % [property_name, _enum_options(values)])
	return {"value": values[name]}


func _validate_state(state: Dictionary) -> Dictionary:
	var minimum := float(state["min_value"])
	var maximum := float(state["max_value"])
	var value := float(state["value"])
	if minimum > maximum:
		return _invalid_configuration("min_value must be less than or equal to max_value")
	if float(state["step"]) < 0.0:
		return _invalid_configuration("step must be greater than or equal to zero")
	if float(state["page"]) < 0.0 or float(state["page"]) > maximum - minimum:
		return _invalid_configuration("page must be between zero and max_value - min_value")
	if bool(state["exp_edit"]) and minimum < 0.0:
		return _invalid_configuration("exp_edit requires min_value to be greater than or equal to zero")
	if not bool(state["allow_lesser"]) and value < minimum:
		return _invalid_configuration("value cannot be less than min_value unless allow_lesser is true")
	if not bool(state["allow_greater"]) and value > maximum - float(state["page"]):
		return _invalid_configuration(
			"value cannot be greater than max_value - page unless allow_greater is true"
		)
	return {}


func _range_state(range: Range) -> Dictionary:
	var state := {
		"min_value": range.get_min(),
		"max_value": range.get_max(),
		"value": range.get_value(),
		"step": range.get_step(),
		"page": range.get_page(),
		"allow_greater": range.is_greater_allowed(),
		"allow_lesser": range.is_lesser_allowed(),
		"exp_edit": range.is_ratio_exp(),
		"rounded": range.is_using_rounded_values(),
	}
	for property_name in _subclass_properties(range):
		state[property_name] = range.get(property_name)
	return state


func _apply_range_state(range: Range, state: Dictionary) -> void:
	# Allow boundary values first, then restore the final numeric state after all clamps are resolved.
	range.set_allow_lesser(bool(state["allow_lesser"]))
	range.set_allow_greater(bool(state["allow_greater"]))
	range.set_min(float(state["min_value"]))
	range.set_max(float(state["max_value"]))
	range.set_step(float(state["step"]))
	range.set_page(float(state["page"]))
	range.set_exp_ratio(bool(state["exp_edit"]))
	range.set_use_rounded_values(bool(state["rounded"]))
	for property_name in _subclass_properties(range):
		if state.has(property_name):
			range.set(property_name, state[property_name])
	range.set_value(float(state["value"]))


func _range_response(range: Range, scene_root: Node) -> Dictionary:
	var state := _range_state(range)
	var configuration := {
		"min_value": state["min_value"],
		"max_value": state["max_value"],
		"value": state["value"],
		"ratio": range.get_as_ratio(),
		"step": state["step"],
		"page": state["page"],
		"allow_greater": state["allow_greater"],
		"allow_lesser": state["allow_lesser"],
		"exp_edit": state["exp_edit"],
		"rounded": state["rounded"],
	}
	if range is ProgressBar:
		configuration["progress_bar"] = {
			"fill_mode": _enum_name(int(state["fill_mode"]), PROGRESS_BAR_FILL_MODES),
			"indeterminate": state["indeterminate"],
			"show_percentage": state["show_percentage"],
			"editor_preview_indeterminate": state["editor_preview_indeterminate"],
		}
	if range is Slider:
		configuration["slider"] = {
			"editable": state["editable"],
			"scrollable": state["scrollable"],
			"tick_count": state["tick_count"],
			"ticks_on_borders": state["ticks_on_borders"],
			"ticks_position": _enum_name(int(state["ticks_position"]), SLIDER_TICK_POSITIONS),
		}
	if range is ScrollBar:
		configuration["scroll_bar"] = {"custom_step": state["custom_step"]}
	if range is SpinBox:
		configuration["spin_box"] = {
			"alignment": _enum_name(int(state["alignment"]), SPIN_BOX_ALIGNMENTS),
			"custom_arrow_round": state["custom_arrow_round"],
			"custom_arrow_step": state["custom_arrow_step"],
			"editable": state["editable"],
			"prefix": state["prefix"],
			"suffix": state["suffix"],
			"select_all_on_focus": state["select_all_on_focus"],
			"update_on_text_changed": state["update_on_text_changed"],
		}
	return {
		"path": ScenePath.from_node(range, scene_root),
		"type": range.get_class(),
		"configuration": configuration,
		"supported_properties": _supported_properties(range),
	}


func _supported_properties(range: Range) -> Array:
	var properties: Array = BASE_PROPERTIES.duplicate()
	properties.append_array(_subclass_properties(range))
	return properties


func _subclass_properties(range: Range) -> Array:
	if range is ProgressBar:
		return PROGRESS_BAR_PROPERTIES
	if range is Slider:
		return SLIDER_PROPERTIES
	if range is ScrollBar:
		return SCROLL_BAR_PROPERTIES
	if range is SpinBox:
		return SPIN_BOX_PROPERTIES
	return []


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
	return Errors.make("INVALID_RANGE_CONFIGURATION", message)

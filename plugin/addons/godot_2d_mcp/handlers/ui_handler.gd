@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_STYLEBOX_PROPERTIES := 48
const MAX_LAYOUT_MAGNITUDE := 1000000.0
const STYLEBOX_PREFIX := "theme_override_styles/"
const PROTECTED_STYLEBOX_PROPERTIES := {
	"resource_path": true,
	"resource_name": true,
	"script": true,
}
const SIDE_NAMES := ["left", "top", "right", "bottom"]
const SIDES := [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]
const PRESET_BY_NAME := {
	"top_left": Control.PRESET_TOP_LEFT,
	"top_right": Control.PRESET_TOP_RIGHT,
	"bottom_left": Control.PRESET_BOTTOM_LEFT,
	"bottom_right": Control.PRESET_BOTTOM_RIGHT,
	"center_left": Control.PRESET_CENTER_LEFT,
	"center_top": Control.PRESET_CENTER_TOP,
	"center_right": Control.PRESET_CENTER_RIGHT,
	"center_bottom": Control.PRESET_CENTER_BOTTOM,
	"center": Control.PRESET_CENTER,
	"left_wide": Control.PRESET_LEFT_WIDE,
	"top_wide": Control.PRESET_TOP_WIDE,
	"right_wide": Control.PRESET_RIGHT_WIDE,
	"bottom_wide": Control.PRESET_BOTTOM_WIDE,
	"vcenter_wide": Control.PRESET_VCENTER_WIDE,
	"hcenter_wide": Control.PRESET_HCENTER_WIDE,
	"full_rect": Control.PRESET_FULL_RECT,
}
const PRESET_MODE_BY_NAME := {
	"min_size": Control.PRESET_MODE_MINSIZE,
	"keep_width": Control.PRESET_MODE_KEEP_WIDTH,
	"keep_height": Control.PRESET_MODE_KEEP_HEIGHT,
	"keep_size": Control.PRESET_MODE_KEEP_SIZE,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_layout(params: Dictionary) -> Dictionary:
	var resolved := _resolve_control(params, false)
	if resolved.has("_error"):
		return resolved
	var control: Control = resolved["control"]
	var scene_root: Node = resolved["scene_root"]
	return {
		"path": ScenePath.from_node(control, scene_root),
		"type": control.get_class(),
		"layout": _serialize_layout(control, scene_root),
	}


func set_layout(params: Dictionary) -> Dictionary:
	var resolved := _resolve_control(params)
	if resolved.has("_error"):
		return resolved
	var control: Control = resolved["control"]
	var scene_root: Node = resolved["scene_root"]
	var container_check := _require_manually_positionable(control)
	if container_check != null:
		return container_check
	var old_state := _layout_state(control)
	var requested_state := old_state.duplicate(true)
	var has_changes := false
	if params.has("anchors") and params["anchors"] != null:
		var anchors_result := _parse_layout_sides(params["anchors"], "anchors", 0.0, 1.0)
		if anchors_result.has("_error"):
			return anchors_result
		requested_state["anchors"] = anchors_result["sides"]
		has_changes = true
	if params.has("offsets") and params["offsets"] != null:
		var offsets_result := _parse_layout_sides(
			params["offsets"], "offsets", -MAX_LAYOUT_MAGNITUDE, MAX_LAYOUT_MAGNITUDE
		)
		if offsets_result.has("_error"):
			return offsets_result
		requested_state["offsets"] = offsets_result["sides"]
		has_changes = true
	if not has_changes:
		return Errors.make("MISSING_PARAMETER", "anchors or offsets must be supplied")
	if _layout_states_equal(old_state, requested_state):
		return {
			"path": ScenePath.from_node(control, scene_root),
			"layout": _serialize_layout(control, scene_root),
			"changed": false,
			"undoable": false,
		}
	_undo_redo.create_action(
		"Godot 2D MCP: Set layout for %s" % control.name,
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	_add_layout_state_operations(control, requested_state, true)
	_add_layout_state_operations(control, old_state, false)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(control, scene_root),
		"layout": _serialize_layout(control, scene_root),
		"changed": true,
		"undoable": true,
		"_scene_mutated": true,
	}


func set_layout_preset(params: Dictionary) -> Dictionary:
	var resolved := _resolve_control(params)
	if resolved.has("_error"):
		return resolved
	var control: Control = resolved["control"]
	var scene_root: Node = resolved["scene_root"]
	var container_check := _require_manually_positionable(control)
	if container_check != null:
		return container_check
	var preset_result := _parse_preset(params.get("preset", ""))
	if preset_result.has("_error"):
		return preset_result
	var resize_mode_result := _parse_preset_mode(params.get("resize_mode", "min_size"))
	if resize_mode_result.has("_error"):
		return resize_mode_result
	var margin_result := _parse_margin(params.get("margin", 0))
	if margin_result.has("_error"):
		return margin_result
	var old_state := _layout_state(control)
	_undo_redo.create_action(
		"Godot 2D MCP: Apply %s layout preset" % preset_result["name"],
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	_undo_redo.add_do_method(
		control,
		"set_anchors_and_offsets_preset",
		preset_result["preset"],
		resize_mode_result["resize_mode"],
		margin_result["margin"]
	)
	_add_layout_state_operations(control, old_state, false)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(control, scene_root),
		"preset": preset_result["name"],
		"resize_mode": resize_mode_result["name"],
		"margin": margin_result["margin"],
		"layout": _serialize_layout(control, scene_root),
		"undoable": true,
		"_scene_mutated": true,
	}


func get_styleboxes(params: Dictionary) -> Dictionary:
	var resolved := _resolve_control(params, false)
	if resolved.has("_error"):
		return resolved
	var control: Control = resolved["control"]
	var scene_root: Node = resolved["scene_root"]
	var styles: Array[Dictionary] = []
	for state_name in _stylebox_states(control):
		var has_override := control.has_theme_stylebox_override(StringName(state_name))
		var has_effective := control.has_theme_stylebox(StringName(state_name))
		var effective: StyleBox = null
		if has_effective:
			effective = control.get_theme_stylebox(StringName(state_name))
		styles.append(_serialize_stylebox_state(state_name, has_override, effective))
	return {
		"path": ScenePath.from_node(control, scene_root),
		"type": control.get_class(),
		"styles": styles,
		"count": styles.size(),
	}


func upsert_stylebox_flat(params: Dictionary) -> Dictionary:
	var resolved := _resolve_control(params)
	if resolved.has("_error"):
		return resolved
	var control: Control = resolved["control"]
	var scene_root: Node = resolved["scene_root"]
	var state_result := _resolve_stylebox_state(control, params.get("state", ""))
	if state_result.has("_error"):
		return state_result
	var properties_result := _parse_stylebox_properties(params.get("properties", {}))
	if properties_result.has("_error"):
		return properties_result
	var state_name: String = state_result["name"]
	var had_override := control.has_theme_stylebox_override(StringName(state_name))
	var old_override: StyleBox = null
	if had_override:
		old_override = control.get_theme_stylebox(StringName(state_name))
	var source: StyleBox = old_override
	if source == null and control.has_theme_stylebox(StringName(state_name)):
		source = control.get_theme_stylebox(StringName(state_name))
	var replacement: StyleBoxFlat
	if source is StyleBoxFlat:
		replacement = source.duplicate(true) as StyleBoxFlat
	else:
		replacement = StyleBoxFlat.new()
	if replacement == null:
		return Errors.make("STYLEBOX_DUPLICATE_FAILED", "Godot failed to create a StyleBoxFlat override")
	var applied_result := _apply_stylebox_properties(replacement, properties_result["properties"])
	if applied_result.has("_error"):
		return applied_result
	_undo_redo.create_action(
		"Godot 2D MCP: Update %s style" % state_name,
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	_undo_redo.add_do_method(
		control, "add_theme_stylebox_override", StringName(state_name), replacement
	)
	_undo_redo.add_do_reference(replacement)
	if had_override:
		_undo_redo.add_undo_method(
			control, "add_theme_stylebox_override", StringName(state_name), old_override
		)
		_undo_redo.add_undo_reference(old_override)
	else:
		_undo_redo.add_undo_method(control, "remove_theme_stylebox_override", StringName(state_name))
	_undo_redo.add_undo_reference(replacement)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(control, scene_root),
		"style": _serialize_stylebox_state(state_name, true, replacement),
		"replaced_override": had_override,
		"undoable": true,
		"_scene_mutated": true,
	}


func clear_stylebox_override(params: Dictionary) -> Dictionary:
	var resolved := _resolve_control(params)
	if resolved.has("_error"):
		return resolved
	var control: Control = resolved["control"]
	var scene_root: Node = resolved["scene_root"]
	var state_result := _resolve_stylebox_state(control, params.get("state", ""))
	if state_result.has("_error"):
		return state_result
	var state_name: String = state_result["name"]
	if not control.has_theme_stylebox_override(StringName(state_name)):
		return Errors.make(
			"STYLEBOX_OVERRIDE_NOT_FOUND",
			"Control has no local stylebox override for '%s'" % state_name,
			false,
			"Call control_get_styleboxes to inspect local overrides."
		)
	var old_override := control.get_theme_stylebox(StringName(state_name))
	if old_override == null:
		return Errors.make("STYLEBOX_OVERRIDE_NOT_FOUND", "The local stylebox override is unavailable")
	_undo_redo.create_action(
		"Godot 2D MCP: Clear %s style override" % state_name,
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_method(control, "remove_theme_stylebox_override", StringName(state_name))
	_undo_redo.add_undo_method(
		control, "add_theme_stylebox_override", StringName(state_name), old_override
	)
	_undo_redo.add_undo_reference(old_override)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(control, scene_root),
		"state": state_name,
		"undoable": true,
		"_scene_mutated": true,
	}


func _resolve_control(params: Dictionary, require_writable: bool = true) -> Dictionary:
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
			"Control not found: %s" % path,
			false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if not node is Control:
		return Errors.make(
			"CONTROL_REQUIRED",
			"Node '%s' is %s, not a Control" % [node.name, node.get_class()],
			false,
			"Choose a Control-derived UI node."
		)
	var control: Control = node
	if require_writable and control != scene_root and control.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit Control '%s' because it belongs to an instanced scene" % control.name,
			false,
			"Edit the source PackedScene or target a locally owned Control."
		)
	return {"control": control, "scene_root": scene_root}


func _require_manually_positionable(control: Control) -> Variant:
	var parent := control.get_parent()
	if parent is Container:
		return Errors.make(
			"CONTAINER_LAYOUT_MANAGED",
			"Control '%s' is positioned by parent Container '%s'" % [control.name, parent.name],
			false,
			"Configure the parent's container settings or target a Control outside a Container."
		)
	return null


func _layout_state(control: Control) -> Dictionary:
	var anchors := {}
	var offsets := {}
	for index in SIDE_NAMES.size():
		anchors[SIDE_NAMES[index]] = control.get_anchor(SIDES[index])
		offsets[SIDE_NAMES[index]] = control.get_offset(SIDES[index])
	return {"anchors": anchors, "offsets": offsets}


func _serialize_layout(control: Control, scene_root: Node) -> Dictionary:
	var parent := control.get_parent()
	var parent_path := ""
	if parent != null and (parent == scene_root or scene_root.is_ancestor_of(parent)):
		parent_path = ScenePath.from_node(parent, scene_root)
	return {
		"anchors": _layout_state(control)["anchors"],
		"offsets": _layout_state(control)["offsets"],
		"position": VariantCodec.serialize(control.position),
		"size": VariantCodec.serialize(control.size),
		"custom_minimum_size": VariantCodec.serialize(control.custom_minimum_size),
		"pivot_offset": VariantCodec.serialize(control.pivot_offset),
		"grow_horizontal": int(control.grow_horizontal),
		"grow_vertical": int(control.grow_vertical),
		"size_flags_horizontal": int(control.size_flags_horizontal),
		"size_flags_vertical": int(control.size_flags_vertical),
		"parent_path": parent_path,
		"container_managed": parent is Container,
	}


func _parse_layout_sides(
	raw_sides: Variant, label: String, minimum: float, maximum: float
) -> Dictionary:
	if not raw_sides is Dictionary or raw_sides.size() != SIDE_NAMES.size():
		return Errors.make("INVALID_LAYOUT", "%s must contain left, top, right, and bottom" % label)
	var parsed := {}
	for side_name in SIDE_NAMES:
		if not raw_sides.has(side_name) or not _is_finite_number(raw_sides[side_name]):
			return Errors.make("INVALID_LAYOUT", "%s.%s must be a finite number" % [label, side_name])
		var value := float(raw_sides[side_name])
		if value < minimum or value > maximum:
			return Errors.make(
				"INVALID_LAYOUT",
				"%s.%s must be between %s and %s" % [label, side_name, minimum, maximum]
			)
		parsed[side_name] = value
	return {"sides": parsed}


func _parse_preset(raw_preset: Variant) -> Dictionary:
	if not raw_preset is String:
		return Errors.make("INVALID_LAYOUT_PRESET", "preset must be a layout preset name")
	var name: String = raw_preset.to_lower().strip_edges()
	if not PRESET_BY_NAME.has(name):
		return Errors.make("INVALID_LAYOUT_PRESET", "preset is not supported")
	return {"name": name, "preset": PRESET_BY_NAME[name]}


func _parse_preset_mode(raw_mode: Variant) -> Dictionary:
	if not raw_mode is String:
		return Errors.make("INVALID_LAYOUT_PRESET_MODE", "resize_mode must be a preset mode name")
	var name: String = raw_mode.to_lower().strip_edges()
	if not PRESET_MODE_BY_NAME.has(name):
		return Errors.make("INVALID_LAYOUT_PRESET_MODE", "resize_mode is not supported")
	return {"name": name, "resize_mode": PRESET_MODE_BY_NAME[name]}


func _parse_margin(raw_margin: Variant) -> Dictionary:
	if not _is_integral_number(raw_margin):
		return Errors.make("INVALID_LAYOUT_MARGIN", "margin must be an integer")
	var margin := int(raw_margin)
	if abs(margin) > int(MAX_LAYOUT_MAGNITUDE):
		return Errors.make("INVALID_LAYOUT_MARGIN", "margin is outside the supported range")
	return {"margin": margin}


func _add_layout_state_operations(control: Control, state: Dictionary, is_do: bool) -> void:
	for index in SIDE_NAMES.size():
		var side_name: String = SIDE_NAMES[index]
		if is_do:
			_undo_redo.add_do_method(
				control,
				"set_anchor_and_offset",
				SIDES[index],
				state["anchors"][side_name],
				state["offsets"][side_name],
				false
			)
		else:
			_undo_redo.add_undo_method(
				control,
				"set_anchor_and_offset",
				SIDES[index],
				state["anchors"][side_name],
				state["offsets"][side_name],
				false
			)


func _layout_states_equal(first: Dictionary, second: Dictionary) -> bool:
	for group_name in ["anchors", "offsets"]:
		for side_name in SIDE_NAMES:
			if not is_equal_approx(first[group_name][side_name], second[group_name][side_name]):
				return false
	return true


func _stylebox_states(control: Control) -> Array[String]:
	var states: Array[String] = []
	for property_info_value in control.get_property_list():
		var property_info: Dictionary = property_info_value
		var property_name := str(property_info.get("name", ""))
		if not property_name.begins_with(STYLEBOX_PREFIX):
			continue
		var state_name := property_name.trim_prefix(STYLEBOX_PREFIX)
		if not state_name.is_empty() and not states.has(state_name):
			states.append(state_name)
	states.sort()
	return states


func _resolve_stylebox_state(control: Control, raw_state: Variant) -> Dictionary:
	if not raw_state is String:
		return Errors.make("INVALID_STYLEBOX_STATE", "state must be a stylebox state name")
	var state_name: String = raw_state.strip_edges()
	if state_name.is_empty() or state_name.length() > 256 or not _stylebox_states(control).has(state_name):
		return Errors.make(
			"INVALID_STYLEBOX_STATE",
			"Stylebox state '%s' is not available on %s" % [state_name, control.get_class()],
			false,
			"Call control_get_styleboxes to inspect supported style states."
		)
	return {"name": state_name}


func _parse_stylebox_properties(raw_properties: Variant) -> Dictionary:
	if not raw_properties is Dictionary or raw_properties.is_empty():
		return Errors.make("MISSING_PARAMETER", "properties must be a non-empty object")
	if raw_properties.size() > MAX_STYLEBOX_PROPERTIES:
		return Errors.make(
			"REQUEST_LIMIT_EXCEEDED",
			"StyleBoxFlat updates can contain at most %d properties" % MAX_STYLEBOX_PROPERTIES
		)
	return {"properties": raw_properties}


func _apply_stylebox_properties(stylebox: StyleBoxFlat, requested: Dictionary) -> Dictionary:
	var property_info_by_name := {}
	for property_info_value in stylebox.get_property_list():
		var property_info: Dictionary = property_info_value
		property_info_by_name[str(property_info.get("name", ""))] = property_info
	for property_name_value in requested:
		var property_name := str(property_name_value)
		if not property_info_by_name.has(property_name):
			return Errors.make(
				"STYLEBOX_PROPERTY_NOT_FOUND",
				"StyleBoxFlat property '%s' does not exist" % property_name,
				false,
				"Use control_get_styleboxes to inspect the current flat style properties."
			)
		var property_info: Dictionary = property_info_by_name[property_name]
		var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
		if (
			PROTECTED_STYLEBOX_PROPERTIES.has(property_name)
			or not _is_writable_public_property(usage)
		):
			return Errors.make(
				"STYLEBOX_PROPERTY_NOT_WRITABLE",
				"StyleBoxFlat property '%s' is not writable through this tool" % property_name
			)
		var decoded := VariantCodec.decode(
			requested[property_name_value], property_info, stylebox.get(property_name)
		)
		if decoded.has("_error"):
			return Errors.make(
				"STYLEBOX_PROPERTY_TYPE_MISMATCH",
				decoded["_error"]["message"],
				false,
				"Use a JSON value compatible with the StyleBoxFlat property type.",
				{"property": property_name}
			)
		stylebox.set(property_name, decoded["value"])
	return {}


func _serialize_stylebox_state(
	state_name: String, has_override: bool, effective: StyleBox
) -> Dictionary:
	var result := {
		"state": state_name,
		"has_override": has_override,
		"effective_type": "" if effective == null else effective.get_class(),
		"effective_resource_path": "" if effective == null else effective.resource_path,
	}
	if effective is StyleBoxFlat:
		result["flat_properties"] = _serialize_flat_properties(effective)
	return result


func _serialize_flat_properties(stylebox: StyleBoxFlat) -> Dictionary:
	var properties := {}
	for property_info_value in stylebox.get_property_list():
		var property_info: Dictionary = property_info_value
		var property_name := str(property_info.get("name", ""))
		var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
		if (
			property_name.is_empty()
			or PROTECTED_STYLEBOX_PROPERTIES.has(property_name)
			or not _is_public_property(usage)
		):
			continue
		properties[property_name] = VariantCodec.serialize(stylebox.get(property_name))
	return properties


func _is_public_property(usage: int) -> bool:
	return bool(usage & (PROPERTY_USAGE_STORAGE | PROPERTY_USAGE_EDITOR))


func _is_writable_public_property(usage: int) -> bool:
	return _is_public_property(usage) and not bool(usage & PROPERTY_USAGE_READ_ONLY)


func _is_finite_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


func _is_integral_number(value: Variant) -> bool:
	return _is_finite_number(value) and is_equal_approx(float(value), round(float(value)))

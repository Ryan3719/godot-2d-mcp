@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_PROPERTIES := 32
const MAX_CHILDREN := 256
const MAX_LAYOUT_MAGNITUDE := 1000000.0
const BASE_PROPERTIES := ["accessibility_region"]
const BOX_PROPERTIES := ["alignment"]
const GRID_PROPERTIES := ["columns"]
const CENTER_PROPERTIES := ["use_top_left"]
const ASPECT_PROPERTIES := ["ratio", "stretch_mode", "alignment_horizontal", "alignment_vertical"]
const FLOW_PROPERTIES := ["alignment", "last_wrap_alignment", "reverse_fill"]
const SPLIT_PROPERTIES := [
	"split_offsets", "collapsed", "dragging_enabled", "dragger_visibility", "touch_dragger_enabled",
	"drag_nested_intersections", "drag_area_margin_begin", "drag_area_margin_end", "drag_area_offset",
	"drag_area_highlight_in_editor",
]
const SCROLL_PROPERTIES := [
	"follow_focus", "draw_focus_border", "scroll_horizontal", "scroll_vertical",
	"scroll_horizontal_custom_step", "scroll_vertical_custom_step", "horizontal_scroll_mode",
	"vertical_scroll_mode", "scroll_horizontal_by_default", "scroll_deadzone", "scroll_hint_mode",
	"tile_scroll_hint",
]
const TAB_PROPERTIES := [
	"tab_alignment", "current_tab", "tabs_position", "clip_tabs", "tabs_visible",
	"switch_on_drag_hover", "drag_to_rearrange_enabled", "tabs_rearrange_group",
	"use_hidden_tabs_for_min_size", "tab_focus_mode", "deselect_enabled",
]
const SUBVIEWPORT_PROPERTIES := ["stretch", "stretch_shrink", "mouse_target"]
const CHILD_LAYOUT_PROPERTIES := [
	"custom_minimum_size", "size_flags_horizontal", "size_flags_vertical", "size_flags_stretch_ratio",
]
const PROPERTY_ORDER := [
	"accessibility_region", "alignment", "columns", "use_top_left", "ratio", "stretch_mode",
	"alignment_horizontal", "alignment_vertical", "last_wrap_alignment", "reverse_fill", "split_offsets",
	"collapsed", "dragging_enabled", "dragger_visibility", "touch_dragger_enabled",
	"drag_nested_intersections", "drag_area_margin_begin", "drag_area_margin_end", "drag_area_offset",
	"drag_area_highlight_in_editor", "follow_focus", "draw_focus_border", "scroll_horizontal",
	"scroll_vertical", "scroll_horizontal_custom_step", "scroll_vertical_custom_step",
	"horizontal_scroll_mode", "vertical_scroll_mode", "scroll_horizontal_by_default", "scroll_deadzone",
	"scroll_hint_mode", "tile_scroll_hint", "tab_alignment", "current_tab", "tabs_position",
	"clip_tabs", "tabs_visible", "switch_on_drag_hover", "drag_to_rearrange_enabled",
	"tabs_rearrange_group", "use_hidden_tabs_for_min_size", "tab_focus_mode", "deselect_enabled",
	"stretch", "stretch_shrink", "mouse_target",
]
const ALIGNMENTS := {"begin": 0, "center": 1, "end": 2}
const ASPECT_STRETCH_MODES := {
	"width_controls_height": 0,
	"height_controls_width": 1,
	"fit": 2,
	"cover": 3,
}
const FLOW_LAST_WRAP_ALIGNMENTS := {"inherit": 0, "begin": 1, "center": 2, "end": 3}
const DRAGGER_VISIBILITIES := {"visible": 0, "hidden": 1, "hidden_and_collapsed": 2}
const SCROLL_MODES := {
	"disabled": 0,
	"auto": 1,
	"always_show": 2,
	"never_show": 3,
	"reserve": 4,
	"maximize_first": 5,
}
const SCROLL_HINT_MODES := {
	"disabled": 0,
	"all": 1,
	"top_and_left": 2,
	"bottom_and_right": 3,
}
const TAB_ALIGNMENTS := {"left": 0, "center": 1, "right": 2}
const TAB_POSITIONS := {"top": 0, "bottom": 1}
const FOCUS_MODES := {"none": 0, "click": 1, "all": 2}
const SIZE_FLAGS := {"fill": 1, "expand": 2, "shrink_center": 4, "shrink_end": 8}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_container(params: Dictionary) -> Dictionary:
	var resolved := _resolve_container(params, false)
	if resolved.has("_error"):
		return resolved
	var page := _parse_child_page(params)
	if page.has("_error"):
		return page
	return _container_response(resolved["container"], resolved["scene_root"], page["offset"], page["limit"])


func set_container(params: Dictionary) -> Dictionary:
	var resolved := _resolve_container(params)
	if resolved.has("_error"):
		return resolved
	var container: Container = resolved["container"]
	var parsed := _parse_container_updates(params, container)
	if parsed.has("_error"):
		return parsed
	var changed := _changed_container_properties(container, parsed["updates"])
	if changed.is_empty():
		var unchanged := _container_response(container, resolved["scene_root"], 0, MAX_CHILDREN)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_container_updates(container, resolved["scene_root"], changed)
	var result := _container_response(container, resolved["scene_root"], 0, MAX_CHILDREN)
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_child_layout(params: Dictionary) -> Dictionary:
	var resolved := _resolve_container(params)
	if resolved.has("_error"):
		return resolved
	var child_result := _resolve_direct_child(params, resolved)
	if child_result.has("_error"):
		return child_result
	var child: Control = child_result["child"]
	var parsed := _parse_child_layout_updates(params)
	if parsed.has("_error"):
		return parsed
	var changed := _changed_child_layout_properties(child, parsed["updates"])
	if changed.is_empty():
		return {
			"container_path": ScenePath.from_node(resolved["container"], resolved["scene_root"]),
			"child": _serialize_child_layout(child, resolved["scene_root"]),
			"changed": false,
			"undoable": false,
		}
	_commit_child_layout_updates(child, resolved["scene_root"], changed)
	return {
		"container_path": ScenePath.from_node(resolved["container"], resolved["scene_root"]),
		"child": _serialize_child_layout(child, resolved["scene_root"]),
		"changed": true,
		"undoable": true,
		"_scene_mutated": true,
	}


func _resolve_container(params: Dictionary, require_writable: bool = true) -> Dictionary:
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
			"NODE_NOT_FOUND", "Node not found: %s" % path, false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if not node is Container:
		return Errors.make(
			"CONTAINER_REQUIRED", "Node '%s' is %s, not a Container" % [node.name, node.get_class()],
			false, "Target a Control-derived Container node."
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit Container '%s' because it belongs to an instanced scene" % node.name,
			false, "Edit the source PackedScene or target a locally owned Container."
		)
	return {"container": node as Container, "scene_root": scene_root}


func _resolve_direct_child(params: Dictionary, resolved: Dictionary) -> Dictionary:
	var child_path := str(params.get("child_path", "")).strip_edges()
	if child_path.is_empty():
		return Errors.make("MISSING_PARAMETER", "child_path is required")
	var scene_root: Node = resolved["scene_root"]
	var child := ScenePath.resolve(child_path, scene_root)
	if child == null:
		return Errors.make(
			"NODE_NOT_FOUND", "Child node not found: %s" % child_path, false,
			"Use container_2d_get to inspect direct Control children."
		)
	if not child is Control:
		return Errors.make(
			"CONTAINER_CHILD_CONTROL_REQUIRED", "Node '%s' is not a Control" % child.name, false,
			"Target a direct Control child of the Container."
		)
	var container: Container = resolved["container"]
	if child.get_parent() != container:
		return Errors.make(
			"CONTAINER_CHILD_NOT_DIRECT", "Node '%s' is not a direct child of '%s'" % [child.name, container.name],
			false, "Only direct Control children participate in this Container's layout."
		)
	if child != scene_root and child.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit child '%s' because it belongs to an instanced scene" % child.name,
			false, "Edit the source PackedScene or target a locally owned child."
		)
	return {"child": child as Control}


func _parse_child_page(params: Dictionary) -> Dictionary:
	var offset_result := _parse_integer(params.get("child_offset", 0), "child_offset", 0, MAX_CHILDREN)
	if offset_result.has("_error"):
		return offset_result
	var limit_result := _parse_integer(params.get("child_limit", 100), "child_limit", 1, MAX_CHILDREN)
	if limit_result.has("_error"):
		return limit_result
	return {"offset": offset_result["value"], "limit": limit_result["value"]}


func _parse_container_updates(params: Dictionary, container: Container) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > MAX_PROPERTIES:
		return _invalid_configuration("properties must be a non-empty object containing at most %d entries" % MAX_PROPERTIES)
	var allowed := _supported_properties(container)
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String or not allowed.has(raw_name):
			return Errors.make(
				"UNSUPPORTED_CONTAINER_PROPERTY", "Unsupported %s property: %s" % [container.get_class(), str(raw_name)],
				false, "Call container_2d_get to inspect supported_properties for this node type."
			)
		var value_result := _parse_container_property(str(raw_name), raw_properties[raw_name], container)
		if value_result.has("_error"):
			return value_result
		updates[value_result["property_name"]] = value_result["value"]
	return {"updates": updates}


func _parse_container_property(name: String, raw_value: Variant, container: Container) -> Dictionary:
	match name:
		"accessibility_region", "use_top_left", "reverse_fill", "collapsed", "dragging_enabled", \
		"touch_dragger_enabled", "drag_nested_intersections", "drag_area_highlight_in_editor", \
		"follow_focus", "draw_focus_border", "scroll_horizontal_by_default", "tile_scroll_hint", \
		"clip_tabs", "tabs_visible", "switch_on_drag_hover", "drag_to_rearrange_enabled", \
		"use_hidden_tabs_for_min_size", "deselect_enabled", "stretch", "mouse_target":
			return _parse_bool(raw_value, name)
		"alignment", "alignment_horizontal", "alignment_vertical":
			return _parse_enum(raw_value, name, ALIGNMENTS)
		"stretch_mode":
			return _parse_enum(raw_value, name, ASPECT_STRETCH_MODES)
		"last_wrap_alignment":
			return _parse_enum(raw_value, name, FLOW_LAST_WRAP_ALIGNMENTS)
		"dragger_visibility":
			return _parse_enum(raw_value, name, DRAGGER_VISIBILITIES)
		"horizontal_scroll_mode", "vertical_scroll_mode":
			return _parse_enum(raw_value, name, SCROLL_MODES)
		"scroll_hint_mode":
			return _parse_enum(raw_value, name, SCROLL_HINT_MODES)
		"tab_alignment":
			return _parse_enum(raw_value, name, TAB_ALIGNMENTS)
		"tabs_position":
			return _parse_enum(raw_value, name, TAB_POSITIONS)
		"tab_focus_mode":
			return _parse_enum(raw_value, name, FOCUS_MODES)
		"columns":
			return _parse_integer(raw_value, name, 1, 1024)
		"ratio":
			return _parse_number(raw_value, name, 0.001, MAX_LAYOUT_MAGNITUDE)
		"split_offsets":
			return _parse_split_offsets(raw_value, container)
		"drag_area_margin_begin", "drag_area_margin_end", "drag_area_offset":
			return _parse_integer(raw_value, name, -int(MAX_LAYOUT_MAGNITUDE), int(MAX_LAYOUT_MAGNITUDE))
		"scroll_horizontal", "scroll_vertical", "scroll_deadzone":
			return _parse_integer(raw_value, name, 0, int(MAX_LAYOUT_MAGNITUDE))
		"scroll_horizontal_custom_step", "scroll_vertical_custom_step":
			return _parse_number(raw_value, name, -1.0, 4096.0)
		"current_tab":
			return _parse_integer(raw_value, name, -1, _direct_control_children(container).size() - 1)
		"tabs_rearrange_group":
			return _parse_integer(raw_value, name, -1, int(MAX_LAYOUT_MAGNITUDE))
		"stretch_shrink":
			return _parse_integer(raw_value, name, 1, int(MAX_LAYOUT_MAGNITUDE))
	return _invalid_configuration("Unsupported Container property: %s" % name)


func _parse_split_offsets(raw_value: Variant, container: Container) -> Dictionary:
	if not raw_value is Array:
		return _invalid_configuration("split_offsets must be an array of integer pixel offsets")
	var expected_size := maxi(_direct_control_children(container).size() - 1, 0)
	if raw_value.size() != expected_size:
		return _invalid_configuration("split_offsets must contain exactly %d entries" % expected_size)
	var offsets := PackedInt32Array()
	for index in range(raw_value.size()):
		var parsed := _parse_integer(
			raw_value[index], "split_offsets[%d]" % index,
			-int(MAX_LAYOUT_MAGNITUDE), int(MAX_LAYOUT_MAGNITUDE)
		)
		if parsed.has("_error"):
			return parsed
		offsets.append(parsed["value"])
	return {"property_name": "split_offsets", "value": offsets}


func _parse_child_layout_updates(params: Dictionary) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > CHILD_LAYOUT_PROPERTIES.size():
		return _invalid_configuration("properties must be a non-empty child layout object")
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String or not CHILD_LAYOUT_PROPERTIES.has(raw_name):
			return _invalid_configuration("Unsupported container child layout property: %s" % str(raw_name))
		var parsed := _parse_child_layout_property(str(raw_name), raw_properties[raw_name])
		if parsed.has("_error"):
			return parsed
		updates[parsed["property_name"]] = parsed["value"]
	return {"updates": updates}


func _parse_child_layout_property(name: String, raw_value: Variant) -> Dictionary:
	match name:
		"custom_minimum_size":
			var decoded := VariantCodec.decode(raw_value, {"type": TYPE_VECTOR2}, Vector2.ZERO)
			if decoded.has("_error"):
				return _invalid_configuration("custom_minimum_size must contain finite x and y values")
			var value: Vector2 = decoded["value"]
			if not is_finite(value.x) or not is_finite(value.y) or value.x < 0.0 or value.y < 0.0 \
			or value.x > MAX_LAYOUT_MAGNITUDE or value.y > MAX_LAYOUT_MAGNITUDE:
				return _invalid_configuration("custom_minimum_size values must be between 0 and 1000000")
			return {"property_name": name, "value": value}
		"size_flags_horizontal", "size_flags_vertical":
			var flags := _parse_size_flags(raw_value, name)
			if flags.has("_error"):
				return flags
			return flags
		"size_flags_stretch_ratio":
			return _parse_number(raw_value, name, 0.0, MAX_LAYOUT_MAGNITUDE)
	return _invalid_configuration("Unsupported container child layout property: %s" % name)


func _parse_size_flags(raw_value: Variant, property_name: String) -> Dictionary:
	if not raw_value is Array or raw_value.size() > SIZE_FLAGS.size():
		return _invalid_configuration("%s must be an array of size flag names" % property_name)
	var mask := 0
	var seen := {}
	var shrink_count := 0
	for raw_name in raw_value:
		if not raw_name is String:
			return _invalid_configuration("%s must be an array of size flag names" % property_name)
		var name: String = raw_name.strip_edges().to_lower()
		if name == "shrink_begin":
			if raw_value.size() != 1:
				return _invalid_configuration("shrink_begin cannot be combined with other size flags")
			return {"property_name": property_name, "value": 0}
		if not SIZE_FLAGS.has(name) or seen.has(name):
			return _invalid_configuration("%s contains an unsupported or duplicate size flag" % property_name)
		if name.begins_with("shrink_"):
			shrink_count += 1
			if shrink_count > 1:
				return _invalid_configuration("%s can contain only one shrink flag" % property_name)
		seen[name] = true
		mask |= int(SIZE_FLAGS[name])
	return {"property_name": property_name, "value": mask}


func _parse_bool(raw_value: Variant, property_name: String) -> Dictionary:
	if not raw_value is bool:
		return _invalid_configuration("%s must be a boolean" % property_name)
	return {"property_name": property_name, "value": raw_value}


func _parse_integer(raw_value: Variant, property_name: String, minimum: int, maximum: int) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool \
		or not is_finite(float(raw_value)) or float(raw_value) != floorf(float(raw_value)):
		return _invalid_configuration("%s must be an integer" % property_name)
	var value := int(raw_value)
	if value < minimum or value > maximum:
		return _invalid_configuration("%s must be between %d and %d" % [property_name, minimum, maximum])
	return {"property_name": property_name, "value": value}


func _parse_number(raw_value: Variant, property_name: String, minimum: float, maximum: float) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool or not is_finite(float(raw_value)):
		return _invalid_configuration("%s must be a finite number" % property_name)
	var value := float(raw_value)
	if value < minimum or value > maximum:
		return _invalid_configuration("%s must be between %s and %s" % [property_name, minimum, maximum])
	return {"property_name": property_name, "value": value}


func _parse_enum(raw_value: Variant, property_name: String, values: Dictionary) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must be one of: %s" % [property_name, _enum_options(values)])
	var name: String = raw_value.strip_edges().to_lower()
	if not values.has(name):
		return _invalid_configuration("%s must be one of: %s" % [property_name, _enum_options(values)])
	return {"property_name": property_name, "value": values[name]}


func _changed_container_properties(container: Container, updates: Dictionary) -> Dictionary:
	var changed := {}
	for property_name in PROPERTY_ORDER:
		if updates.has(property_name) and container.get(property_name) != updates[property_name]:
			changed[property_name] = updates[property_name]
	return changed


func _changed_child_layout_properties(child: Control, updates: Dictionary) -> Dictionary:
	var changed := {}
	for property_name in CHILD_LAYOUT_PROPERTIES:
		if updates.has(property_name) and child.get(property_name) != updates[property_name]:
			changed[property_name] = updates[property_name]
	return changed


func _commit_container_updates(container: Container, scene_root: Node, updates: Dictionary) -> void:
	_undo_redo.create_action(
		"Godot 2D MCP: Update %s %s" % [container.get_class(), container.name],
		UndoRedo.MERGE_DISABLE, scene_root, true
	)
	for property_name in PROPERTY_ORDER:
		if not updates.has(property_name):
			continue
		_undo_redo.add_do_property(container, property_name, updates[property_name])
		_undo_redo.add_undo_property(container, property_name, container.get(property_name))
	_undo_redo.commit_action()


func _commit_child_layout_updates(child: Control, scene_root: Node, updates: Dictionary) -> void:
	_undo_redo.create_action(
		"Godot 2D MCP: Update Container layout for %s" % child.name,
		UndoRedo.MERGE_DISABLE, scene_root, true
	)
	for property_name in CHILD_LAYOUT_PROPERTIES:
		if not updates.has(property_name):
			continue
		_undo_redo.add_do_property(child, property_name, updates[property_name])
		_undo_redo.add_undo_property(child, property_name, child.get(property_name))
	_undo_redo.commit_action()


func _container_response(container: Container, scene_root: Node, offset: int, limit: int) -> Dictionary:
	var children := _direct_control_children(container)
	var start := mini(offset, children.size())
	var end := mini(start + limit, children.size())
	var serialized_children: Array = []
	for index in range(start, end):
		serialized_children.append(_serialize_child_layout(children[index], scene_root))
	return {
		"path": ScenePath.from_node(container, scene_root),
		"type": container.get_class(),
		"configuration": _serialize_configuration(container),
		"supported_properties": _supported_properties(container),
		"children_total": children.size(),
		"child_offset": start,
		"children": serialized_children,
		"children_truncated": end < children.size(),
		"supported_child_layout_properties": CHILD_LAYOUT_PROPERTIES.duplicate(),
	}


func _serialize_configuration(container: Container) -> Dictionary:
	var configuration := {"accessibility_region": bool(container.get("accessibility_region"))}
	if container is BoxContainer:
		configuration["alignment"] = _enum_name(int(container.get("alignment")), ALIGNMENTS)
	if container is GridContainer:
		configuration["columns"] = int(container.get("columns"))
	if container is CenterContainer:
		configuration["use_top_left"] = bool(container.get("use_top_left"))
	if container is AspectRatioContainer:
		configuration["ratio"] = float(container.get("ratio"))
		configuration["stretch_mode"] = _enum_name(
			int(container.get("stretch_mode")), ASPECT_STRETCH_MODES
		)
		configuration["alignment_horizontal"] = _enum_name(
			int(container.get("alignment_horizontal")), ALIGNMENTS
		)
		configuration["alignment_vertical"] = _enum_name(
			int(container.get("alignment_vertical")), ALIGNMENTS
		)
	if container is FlowContainer:
		configuration["alignment"] = _enum_name(int(container.get("alignment")), ALIGNMENTS)
		configuration["last_wrap_alignment"] = _enum_name(
			int(container.get("last_wrap_alignment")), FLOW_LAST_WRAP_ALIGNMENTS
		)
		configuration["reverse_fill"] = bool(container.get("reverse_fill"))
	if container is SplitContainer:
		configuration["split_offsets"] = _serialize_packed_ints(container.get("split_offsets"))
		configuration["collapsed"] = bool(container.get("collapsed"))
		configuration["dragging_enabled"] = bool(container.get("dragging_enabled"))
		configuration["dragger_visibility"] = _enum_name(
			int(container.get("dragger_visibility")), DRAGGER_VISIBILITIES
		)
		configuration["touch_dragger_enabled"] = bool(container.get("touch_dragger_enabled"))
		configuration["drag_nested_intersections"] = bool(container.get("drag_nested_intersections"))
		configuration["drag_area_margin_begin"] = int(container.get("drag_area_margin_begin"))
		configuration["drag_area_margin_end"] = int(container.get("drag_area_margin_end"))
		configuration["drag_area_offset"] = int(container.get("drag_area_offset"))
		configuration["drag_area_highlight_in_editor"] = bool(
			container.get("drag_area_highlight_in_editor")
		)
	if container is ScrollContainer:
		for property_name in [
			"follow_focus", "draw_focus_border", "scroll_horizontal", "scroll_vertical",
			"scroll_horizontal_custom_step", "scroll_vertical_custom_step",
			"scroll_horizontal_by_default", "scroll_deadzone", "tile_scroll_hint",
		]:
			configuration[property_name] = container.get(property_name)
		configuration["horizontal_scroll_mode"] = _enum_name(
			int(container.get("horizontal_scroll_mode")), SCROLL_MODES
		)
		configuration["vertical_scroll_mode"] = _enum_name(
			int(container.get("vertical_scroll_mode")), SCROLL_MODES
		)
		configuration["scroll_hint_mode"] = _enum_name(
			int(container.get("scroll_hint_mode")), SCROLL_HINT_MODES
		)
	if container is TabContainer:
		for property_name in [
			"current_tab", "clip_tabs", "tabs_visible", "switch_on_drag_hover",
			"drag_to_rearrange_enabled", "tabs_rearrange_group", "use_hidden_tabs_for_min_size",
			"deselect_enabled",
		]:
			configuration[property_name] = container.get(property_name)
		configuration["tab_alignment"] = _enum_name(
			int(container.get("tab_alignment")), TAB_ALIGNMENTS
		)
		configuration["tabs_position"] = _enum_name(
			int(container.get("tabs_position")), TAB_POSITIONS
		)
		configuration["tab_focus_mode"] = _enum_name(
			int(container.get("tab_focus_mode")), FOCUS_MODES
		)
	if container is SubViewportContainer:
		configuration["stretch"] = bool(container.get("stretch"))
		configuration["stretch_shrink"] = int(container.get("stretch_shrink"))
		configuration["mouse_target"] = bool(container.get("mouse_target"))
	return configuration


func _serialize_child_layout(child: Control, scene_root: Node) -> Dictionary:
	return {
		"path": ScenePath.from_node(child, scene_root),
		"type": child.get_class(),
		"custom_minimum_size": VariantCodec.serialize(child.custom_minimum_size),
		"size_flags_horizontal": _serialize_size_flags(int(child.size_flags_horizontal)),
		"size_flags_vertical": _serialize_size_flags(int(child.size_flags_vertical)),
		"size_flags_stretch_ratio": child.size_flags_stretch_ratio,
	}


func _direct_control_children(container: Container) -> Array:
	var controls: Array = []
	for child in container.get_children(false):
		if child is Control:
			controls.append(child as Control)
	return controls


func _supported_properties(container: Container) -> Array:
	var properties: Array = BASE_PROPERTIES.duplicate()
	if container is BoxContainer:
		properties.append_array(BOX_PROPERTIES)
	if container is GridContainer:
		properties.append_array(GRID_PROPERTIES)
	if container is CenterContainer:
		properties.append_array(CENTER_PROPERTIES)
	if container is AspectRatioContainer:
		properties.append_array(ASPECT_PROPERTIES)
	if container is FlowContainer:
		properties.append_array(FLOW_PROPERTIES)
	if container is SplitContainer:
		properties.append_array(SPLIT_PROPERTIES)
	if container is ScrollContainer:
		properties.append_array(SCROLL_PROPERTIES)
	if container is TabContainer:
		properties.append_array(TAB_PROPERTIES)
	if container is SubViewportContainer:
		properties.append_array(SUBVIEWPORT_PROPERTIES)
	return properties


func _serialize_packed_ints(raw_value: Variant) -> Array[int]:
	var values: Array[int] = []
	for value in raw_value:
		values.append(int(value))
	return values


func _serialize_size_flags(flags: int) -> Array[String]:
	if flags == 0:
		return ["shrink_begin"]
	var names: Array[String] = []
	for name_value in ["fill", "expand", "shrink_center", "shrink_end"]:
		var name: String = name_value
		if flags & int(SIZE_FLAGS[name]):
			names.append(name)
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
	return Errors.make("INVALID_CONTAINER_CONFIGURATION", message)

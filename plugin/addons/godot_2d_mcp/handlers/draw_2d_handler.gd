@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_DRAW_PROPERTIES := 20
const MAX_DRAW_POINTS := 512
const MAX_FRAME_COUNT := 16_384
const MAX_COORDINATE := 1_000_000.0

const SPRITE_PROPERTIES := [
	"texture_path", "centered", "offset", "flip_h", "flip_v", "hframes", "vframes", "frame",
	"frame_coords", "region_enabled", "region_rect", "region_filter_clip_enabled",
]
const SPRITE_PROPERTY_ORDER := [
	"texture", "centered", "offset", "flip_h", "flip_v", "hframes", "vframes", "frame",
	"region_enabled", "region_rect", "region_filter_clip_enabled",
]
const LINE_PROPERTIES := [
	"points", "closed", "width", "width_curve_path", "default_color", "gradient_path", "texture_path",
	"texture_mode", "joint_mode", "begin_cap_mode", "end_cap_mode", "sharp_limit", "round_precision",
	"antialiased",
]
const LINE_PROPERTY_ORDER := [
	"points", "closed", "width", "width_curve", "default_color", "gradient", "texture", "texture_mode",
	"joint_mode", "begin_cap_mode", "end_cap_mode", "sharp_limit", "round_precision", "antialiased",
]
const POLYGON_PROPERTIES := [
	"polygon", "uv", "vertex_colors", "color", "texture_path", "texture_offset", "texture_rotation",
	"texture_scale", "invert_enabled", "invert_border", "antialiased", "offset",
]
const POLYGON_PROPERTY_ORDER := [
	"polygon", "uv", "vertex_colors", "color", "texture", "texture_offset", "texture_rotation",
	"texture_scale", "invert_enabled", "invert_border", "antialiased", "offset",
]
const LINE_TEXTURE_MODES := {
	"none": Line2D.LINE_TEXTURE_NONE,
	"tile": Line2D.LINE_TEXTURE_TILE,
	"stretch": Line2D.LINE_TEXTURE_STRETCH,
}
const LINE_JOINT_MODES := {
	"sharp": Line2D.LINE_JOINT_SHARP,
	"bevel": Line2D.LINE_JOINT_BEVEL,
	"round": Line2D.LINE_JOINT_ROUND,
}
const LINE_CAP_MODES := {
	"none": Line2D.LINE_CAP_NONE,
	"box": Line2D.LINE_CAP_BOX,
	"round": Line2D.LINE_CAP_ROUND,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_sprite_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_sprite_2d(params, false)
	if resolved.has("_error"):
		return resolved
	return _sprite_response(resolved["sprite"], resolved["scene_root"])


func set_sprite_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_sprite_2d(params)
	if resolved.has("_error"):
		return resolved
	var sprite: Sprite2D = resolved["sprite"]
	var parsed := _parse_sprite_updates(params, sprite)
	if parsed.has("_error"):
		return parsed
	var changed := _changed_properties(sprite, SPRITE_PROPERTY_ORDER, parsed["updates"])
	if changed.is_empty():
		var unchanged := _sprite_response(sprite, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_property_updates(
		sprite,
		resolved["scene_root"],
		SPRITE_PROPERTY_ORDER,
		changed,
		["texture"],
		"Update Sprite2D %s" % sprite.name
	)
	var result := _sprite_response(sprite, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func get_line_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_line_2d(params, false)
	if resolved.has("_error"):
		return resolved
	return _line_response(resolved["line"], resolved["scene_root"])


func set_line_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_line_2d(params)
	if resolved.has("_error"):
		return resolved
	var line: Line2D = resolved["line"]
	var parsed := _parse_line_updates(params, line)
	if parsed.has("_error"):
		return parsed
	var changed := _changed_properties(line, LINE_PROPERTY_ORDER, parsed["updates"])
	if changed.is_empty():
		var unchanged := _line_response(line, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_property_updates(
		line,
		resolved["scene_root"],
		LINE_PROPERTY_ORDER,
		changed,
		["width_curve", "gradient", "texture"],
		"Update Line2D %s" % line.name
	)
	var result := _line_response(line, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func get_polygon_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_polygon_2d(params, false)
	if resolved.has("_error"):
		return resolved
	return _polygon_response(resolved["polygon"], resolved["scene_root"])


func set_polygon_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_polygon_2d(params)
	if resolved.has("_error"):
		return resolved
	var polygon: Polygon2D = resolved["polygon"]
	var parsed := _parse_polygon_updates(params, polygon)
	if parsed.has("_error"):
		return parsed
	var changed := _changed_properties(polygon, POLYGON_PROPERTY_ORDER, parsed["updates"])
	if changed.is_empty():
		var unchanged := _polygon_response(polygon, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_property_updates(
		polygon,
		resolved["scene_root"],
		POLYGON_PROPERTY_ORDER,
		changed,
		["texture"],
		"Update Polygon2D %s" % polygon.name
	)
	var result := _polygon_response(polygon, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_sprite_2d(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is Sprite2D:
		return Errors.make(
			"SPRITE_2D_REQUIRED",
			"Node '%s' is %s, not Sprite2D" % [resolved["node"].name, resolved["node"].get_class()],
			false,
			"Target a Sprite2D node."
		)
	resolved["sprite"] = resolved["node"] as Sprite2D
	return resolved


func _resolve_line_2d(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is Line2D:
		return Errors.make(
			"LINE_2D_REQUIRED",
			"Node '%s' is %s, not Line2D" % [resolved["node"].name, resolved["node"].get_class()],
			false,
			"Target a Line2D node."
		)
	resolved["line"] = resolved["node"] as Line2D
	return resolved


func _resolve_polygon_2d(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is Polygon2D:
		return Errors.make(
			"POLYGON_2D_REQUIRED",
			"Node '%s' is %s, not Polygon2D" % [resolved["node"].name, resolved["node"].get_class()],
			false,
			"Target a Polygon2D node."
		)
	resolved["polygon"] = resolved["node"] as Polygon2D
	return resolved


func _resolve_node(params: Dictionary, require_writable: bool) -> Dictionary:
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
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit node '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned node."
		)
	return {"node": node, "scene_root": scene_root}


func _parse_sprite_updates(params: Dictionary, sprite: Sprite2D) -> Dictionary:
	var raw_properties := _require_properties(params, SPRITE_PROPERTIES)
	if raw_properties.has("_error"):
		return raw_properties
	if raw_properties["properties"].has("frame") and raw_properties["properties"].has("frame_coords"):
		return _invalid_configuration("frame and frame_coords cannot be supplied together")
	var updates := {}
	for raw_name in raw_properties["properties"]:
		var name: String = raw_name
		var value_result := _parse_sprite_value(name, raw_properties["properties"][name])
		if value_result.has("_error"):
			return value_result
		updates[value_result["property_name"]] = value_result["value"]
	var hframes := int(updates.get("hframes", sprite.hframes))
	var vframes := int(updates.get("vframes", sprite.vframes))
	var frame := int(updates.get("frame", sprite.frame))
	if raw_properties["properties"].has("frame_coords"):
		var coords: Vector2i = updates["frame_coords"]
		updates.erase("frame_coords")
		if coords.x < 0 or coords.y < 0 or coords.x >= hframes or coords.y >= vframes:
			return _invalid_configuration("frame_coords must be inside the configured hframes and vframes grid")
		frame = coords.y * hframes + coords.x
		updates["frame"] = frame
	var maximum_frame := hframes * vframes - 1
	if frame < 0 or frame > maximum_frame:
		return _invalid_configuration("frame must be between 0 and %d for the configured frame grid" % maximum_frame)
	if not updates.has("frame") and sprite.frame > maximum_frame:
		updates["frame"] = maximum_frame
	return {"updates": updates}


func _parse_sprite_value(name: String, raw_value: Variant) -> Dictionary:
	match name:
		"texture_path":
			return _load_project_resource(raw_value, "Texture2D", "texture_path", "texture")
		"centered", "flip_h", "flip_v", "region_enabled", "region_filter_clip_enabled":
			return _parse_bool(raw_value, name)
		"offset":
			return _parse_vector2(raw_value, name)
		"hframes", "vframes":
			return _parse_integer(raw_value, name, 1, MAX_FRAME_COUNT)
		"frame":
			return _parse_integer(raw_value, name, 0, MAX_FRAME_COUNT * MAX_FRAME_COUNT - 1)
		"frame_coords":
			var coords := _parse_vector2i(raw_value, name)
			if coords.has("_error"):
				return coords
			return {"property_name": name, "value": coords["value"]}
		"region_rect":
			return _parse_rect2(raw_value, name, true)
	return _invalid_configuration("Unsupported Sprite2D property: %s" % name)


func _parse_line_updates(params: Dictionary, line: Line2D) -> Dictionary:
	var raw_properties := _require_properties(params, LINE_PROPERTIES)
	if raw_properties.has("_error"):
		return raw_properties
	var updates := {}
	for raw_name in raw_properties["properties"]:
		var name: String = raw_name
		var value_result := _parse_line_value(name, raw_properties["properties"][name])
		if value_result.has("_error"):
			return value_result
		updates[value_result["property_name"]] = value_result["value"]
	var points: PackedVector2Array = updates.get("points", line.points)
	var closed: bool = updates.get("closed", line.closed)
	if closed and points.size() > 0 and points.size() < 3:
		return _invalid_configuration("closed Line2D requires zero or at least three points")
	return {"updates": updates}


func _parse_line_value(name: String, raw_value: Variant) -> Dictionary:
	match name:
		"points":
			return _parse_vector2_array(raw_value, name)
		"closed", "antialiased":
			return _parse_bool(raw_value, name)
		"width":
			return _parse_number(raw_value, name, 0.0, MAX_COORDINATE)
		"width_curve_path":
			return _load_project_resource(raw_value, "Curve", name, "width_curve")
		"default_color":
			return _parse_color(raw_value, name)
		"gradient_path":
			return _load_project_resource(raw_value, "Gradient", name, "gradient")
		"texture_path":
			return _load_project_resource(raw_value, "Texture2D", name, "texture")
		"texture_mode":
			return _parse_enum(raw_value, name, LINE_TEXTURE_MODES)
		"joint_mode":
			return _parse_enum(raw_value, name, LINE_JOINT_MODES)
		"begin_cap_mode", "end_cap_mode":
			return _parse_enum(raw_value, name, LINE_CAP_MODES)
		"sharp_limit":
			return _parse_number(raw_value, name, 0.0, 1_000.0)
		"round_precision":
			return _parse_integer(raw_value, name, 1, 32)
	return _invalid_configuration("Unsupported Line2D property: %s" % name)


func _parse_polygon_updates(params: Dictionary, polygon: Polygon2D) -> Dictionary:
	var raw_properties := _require_properties(params, POLYGON_PROPERTIES)
	if raw_properties.has("_error"):
		return raw_properties
	var updates := {}
	for raw_name in raw_properties["properties"]:
		var name: String = raw_name
		var value_result := _parse_polygon_value(name, raw_properties["properties"][name])
		if value_result.has("_error"):
			return value_result
		updates[value_result["property_name"]] = value_result["value"]
	var points: PackedVector2Array = updates.get("polygon", polygon.polygon)
	var geometry_result := _validate_polygon(points)
	if geometry_result.has("_error"):
		return geometry_result
	var uv: PackedVector2Array = updates.get("uv", polygon.uv)
	if not uv.is_empty() and uv.size() != points.size():
		return _invalid_configuration("uv must be empty or contain one entry per polygon point")
	var vertex_colors: PackedColorArray = updates.get("vertex_colors", polygon.vertex_colors)
	if not vertex_colors.is_empty() and vertex_colors.size() != points.size():
		return _invalid_configuration("vertex_colors must be empty or contain one entry per polygon point")
	return {"updates": updates}


func _parse_polygon_value(name: String, raw_value: Variant) -> Dictionary:
	match name:
		"polygon", "uv":
			return _parse_vector2_array(raw_value, name)
		"vertex_colors":
			return _parse_color_array(raw_value, name)
		"color":
			return _parse_color(raw_value, name)
		"texture_path":
			return _load_project_resource(raw_value, "Texture2D", name, "texture")
		"texture_offset", "offset":
			return _parse_vector2(raw_value, name)
		"texture_rotation":
			return _parse_number(raw_value, name, -36_000.0, 36_000.0)
		"texture_scale":
			var scale := _parse_vector2(raw_value, name)
			if scale.has("_error"):
				return scale
			var scale_value: Vector2 = scale["value"]
			if is_zero_approx(scale_value.x) or is_zero_approx(scale_value.y):
				return _invalid_configuration("texture_scale x and y must be non-zero")
			return scale
		"invert_enabled", "antialiased":
			return _parse_bool(raw_value, name)
		"invert_border":
			return _parse_number(raw_value, name, 0.0, MAX_COORDINATE)
	return _invalid_configuration("Unsupported Polygon2D property: %s" % name)


func _require_properties(params: Dictionary, supported_properties: Array) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() \
		or raw_properties.size() > MAX_DRAW_PROPERTIES:
		return _invalid_configuration(
			"properties must be a non-empty object containing at most %d entries" % MAX_DRAW_PROPERTIES
		)
	for raw_name in raw_properties:
		if not raw_name is String or not supported_properties.has(raw_name):
			return Errors.make(
				"UNSUPPORTED_DRAW_2D_PROPERTY",
				"Unsupported 2D drawing property: %s" % str(raw_name),
				false,
				"Call the matching *_get tool to inspect supported_properties."
			)
	return {"properties": raw_properties}


func _load_project_resource(
	raw_value: Variant, expected_type: String, input_name: String, property_name: String
) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must be a res:// string or an empty string" % input_name)
	var resource_path: String = raw_value.strip_edges()
	if resource_path.is_empty():
		return {"property_name": property_name, "value": null}
	if resource_path.length() > 4096 or not resource_path.begins_with("res://") \
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


func _parse_vector2(raw_value: Variant, property_name: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_VECTOR2}, Vector2())
	if decoded.has("_error"):
		return _invalid_configuration("%s must contain finite x and y values" % property_name)
	var value: Vector2 = decoded["value"]
	if not _is_bounded_vector2(value):
		return _invalid_configuration("%s must contain bounded finite x and y values" % property_name)
	return {"property_name": property_name, "value": value}


func _parse_vector2i(raw_value: Variant, property_name: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_VECTOR2I}, Vector2i())
	if decoded.has("_error"):
		return _invalid_configuration("%s must contain integral x and y values" % property_name)
	return {"property_name": property_name, "value": decoded["value"]}


func _parse_rect2(raw_value: Variant, property_name: String, require_nonnegative_size: bool) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_RECT2}, Rect2())
	if decoded.has("_error"):
		return _invalid_configuration("%s must contain position and size Vector2 values" % property_name)
	var value: Rect2 = decoded["value"]
	if not _is_bounded_vector2(value.position) or not _is_bounded_vector2(value.size):
		return _invalid_configuration("%s must contain bounded finite values" % property_name)
	if require_nonnegative_size and (value.size.x < 0.0 or value.size.y < 0.0):
		return _invalid_configuration("%s size must be non-negative" % property_name)
	return {"property_name": property_name, "value": value}


func _parse_color(raw_value: Variant, property_name: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_COLOR}, Color.WHITE)
	if decoded.has("_error") or not _is_finite_color(decoded.get("value", Color.WHITE)):
		return _invalid_configuration("%s must be a finite Color value" % property_name)
	return {"property_name": property_name, "value": decoded["value"]}


func _parse_vector2_array(raw_value: Variant, property_name: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_PACKED_VECTOR2_ARRAY}, PackedVector2Array())
	if decoded.has("_error") or decoded["value"].size() > MAX_DRAW_POINTS:
		return _invalid_configuration(
			"%s must contain at most %d bounded Vector2 values" % [property_name, MAX_DRAW_POINTS]
		)
	var values: PackedVector2Array = decoded["value"]
	for value in values:
		if not _is_bounded_vector2(value):
			return _invalid_configuration("%s must contain bounded finite Vector2 values" % property_name)
	return {"property_name": property_name, "value": values}


func _parse_color_array(raw_value: Variant, property_name: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_PACKED_COLOR_ARRAY}, PackedColorArray())
	if decoded.has("_error") or decoded["value"].size() > MAX_DRAW_POINTS:
		return _invalid_configuration(
			"%s must contain at most %d finite Color values" % [property_name, MAX_DRAW_POINTS]
		)
	var values: PackedColorArray = decoded["value"]
	for value in values:
		if not _is_finite_color(value):
			return _invalid_configuration("%s must contain finite Color values" % property_name)
	return {"property_name": property_name, "value": values}


func _parse_enum(raw_value: Variant, property_name: String, options: Dictionary) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must use a supported mode name" % property_name)
	var label: String = raw_value.strip_edges().to_lower()
	if not options.has(label):
		return _invalid_configuration(
			"%s must be one of: %s" % [property_name, ", ".join(options.keys())]
		)
	return {"property_name": property_name, "value": options[label]}


func _validate_polygon(points: PackedVector2Array) -> Dictionary:
	if points.is_empty():
		return {}
	if points.size() < 3:
		return _invalid_configuration("polygon must be empty or contain at least three points")
	if is_zero_approx(_polygon_twice_area(points)):
		return _invalid_configuration("polygon must enclose a non-zero area")
	if Geometry2D.triangulate_polygon(points).is_empty():
		return _invalid_configuration("polygon must be non-degenerate and triangulable")
	return {}


func _polygon_twice_area(points: PackedVector2Array) -> float:
	var result := 0.0
	for index in points.size():
		var current: Vector2 = points[index]
		var following: Vector2 = points[(index + 1) % points.size()]
		result += current.x * following.y - following.x * current.y
	return result


func _changed_properties(node: Node, order: Array, updates: Dictionary) -> Dictionary:
	var changed := {}
	for property_name_value in order:
		var property_name := str(property_name_value)
		if updates.has(property_name) and node.get(property_name) != updates[property_name]:
			changed[property_name] = updates[property_name]
	return changed


func _commit_property_updates(
	node: Node,
	scene_root: Node,
	order: Array,
	updates: Dictionary,
	resource_properties: Array,
	action_label: String
) -> void:
	_undo_redo.create_action("Godot 2D MCP: %s" % action_label, UndoRedo.MERGE_DISABLE, scene_root, true)
	for property_name_value in order:
		var property_name := str(property_name_value)
		if not updates.has(property_name):
			continue
		var old_value = node.get(property_name)
		var new_value = updates[property_name]
		_undo_redo.add_do_property(node, property_name, new_value)
		if resource_properties.has(property_name) and new_value is Resource:
			_undo_redo.add_do_reference(new_value)
		_undo_redo.add_undo_property(node, property_name, old_value)
		if resource_properties.has(property_name) and old_value is Resource:
			_undo_redo.add_undo_reference(old_value)
	_undo_redo.commit_action()


func _sprite_response(sprite: Sprite2D, scene_root: Node) -> Dictionary:
	var texture: Texture2D = sprite.texture
	return {
		"path": ScenePath.from_node(sprite, scene_root),
		"type": sprite.get_class(),
		"configuration": {
			"texture_path": "" if texture == null else texture.resource_path,
			"texture_type": "" if texture == null else texture.get_class(),
			"centered": sprite.centered,
			"offset": VariantCodec.serialize(sprite.offset),
			"flip_h": sprite.flip_h,
			"flip_v": sprite.flip_v,
			"hframes": sprite.hframes,
			"vframes": sprite.vframes,
			"frame": sprite.frame,
			"frame_coords": VariantCodec.serialize(sprite.frame_coords),
			"region_enabled": sprite.region_enabled,
			"region_rect": VariantCodec.serialize(sprite.region_rect),
			"region_filter_clip_enabled": sprite.region_filter_clip_enabled,
		},
		"supported_properties": SPRITE_PROPERTIES,
	}


func _line_response(line: Line2D, scene_root: Node) -> Dictionary:
	var curve: Curve = line.width_curve
	var gradient: Gradient = line.gradient
	var texture: Texture2D = line.texture
	return {
		"path": ScenePath.from_node(line, scene_root),
		"type": line.get_class(),
		"configuration": {
			"points": VariantCodec.serialize(line.points),
			"closed": line.closed,
			"width": line.width,
			"width_curve_path": "" if curve == null else curve.resource_path,
			"width_curve_type": "" if curve == null else curve.get_class(),
			"default_color": VariantCodec.serialize(line.default_color),
			"gradient_path": "" if gradient == null else gradient.resource_path,
			"gradient_type": "" if gradient == null else gradient.get_class(),
			"texture_path": "" if texture == null else texture.resource_path,
			"texture_type": "" if texture == null else texture.get_class(),
			"texture_mode": _enum_name(LINE_TEXTURE_MODES, line.texture_mode),
			"joint_mode": _enum_name(LINE_JOINT_MODES, line.joint_mode),
			"begin_cap_mode": _enum_name(LINE_CAP_MODES, line.begin_cap_mode),
			"end_cap_mode": _enum_name(LINE_CAP_MODES, line.end_cap_mode),
			"sharp_limit": line.sharp_limit,
			"round_precision": line.round_precision,
			"antialiased": line.antialiased,
		},
		"supported_properties": LINE_PROPERTIES,
	}


func _polygon_response(polygon: Polygon2D, scene_root: Node) -> Dictionary:
	var texture: Texture2D = polygon.texture
	return {
		"path": ScenePath.from_node(polygon, scene_root),
		"type": polygon.get_class(),
		"configuration": {
			"polygon": VariantCodec.serialize(polygon.polygon),
			"uv": VariantCodec.serialize(polygon.uv),
			"vertex_colors": VariantCodec.serialize(polygon.vertex_colors),
			"color": VariantCodec.serialize(polygon.color),
			"texture_path": "" if texture == null else texture.resource_path,
			"texture_type": "" if texture == null else texture.get_class(),
			"texture_offset": VariantCodec.serialize(polygon.texture_offset),
			"texture_rotation": polygon.texture_rotation,
			"texture_scale": VariantCodec.serialize(polygon.texture_scale),
			"invert_enabled": polygon.invert_enabled,
			"invert_border": polygon.invert_border,
			"antialiased": polygon.antialiased,
			"offset": VariantCodec.serialize(polygon.offset),
		},
		"supported_properties": POLYGON_PROPERTIES,
	}


func _enum_name(options: Dictionary, value: int) -> String:
	for name in options:
		if options[name] == value:
			return name
	return ""


func _is_bounded_vector2(value: Vector2) -> bool:
	return is_finite(value.x) and is_finite(value.y) \
		and absf(value.x) <= MAX_COORDINATE and absf(value.y) <= MAX_COORDINATE


func _is_finite_color(value: Color) -> bool:
	return is_finite(value.r) and is_finite(value.g) and is_finite(value.b) and is_finite(value.a)


func _invalid_configuration(message: String) -> Dictionary:
	return Errors.make("INVALID_DRAW_2D_CONFIGURATION", message)

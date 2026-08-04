@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_LIGHT_PROPERTIES := 18
const MAX_LIGHT_MASK_LAYERS := 32
const MAX_OCCLUDER_POINTS := 512
const LIGHT_COMMON_PROPERTIES := [
	"enabled", "editor_only", "color", "energy", "blend_mode", "range_z_min", "range_z_max",
	"range_layer_min", "range_layer_max", "range_item_cull_layers", "shadow_enabled",
	"shadow_color", "shadow_filter", "shadow_filter_smooth", "shadow_item_cull_layers", "height",
]
const POINT_LIGHT_PROPERTIES := ["texture_path", "offset", "texture_scale"]
const DIRECTIONAL_LIGHT_PROPERTIES := ["max_distance"]
const LIGHT_ENUM_OPTIONS := {
	"blend_mode": {
		"add": Light2D.BLEND_MODE_ADD,
		"subtract": Light2D.BLEND_MODE_SUB,
		"mix": Light2D.BLEND_MODE_MIX,
	},
	"shadow_filter": {
		"none": Light2D.SHADOW_FILTER_NONE,
		"pcf5": Light2D.SHADOW_FILTER_PCF5,
		"pcf13": Light2D.SHADOW_FILTER_PCF13,
	},
}
const LIGHT_MASK_PROPERTIES := {
	"range_item_cull_layers": "range_item_cull_mask",
	"shadow_item_cull_layers": "shadow_item_cull_mask",
}
const OCCLUDER_CULL_MODES := {
	"disabled": OccluderPolygon2D.CULL_DISABLED,
	"clockwise": OccluderPolygon2D.CULL_CLOCKWISE,
	"counter_clockwise": OccluderPolygon2D.CULL_COUNTER_CLOCKWISE,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_light_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_light_2d(params, false)
	if resolved.has("_error"):
		return resolved
	return _light_2d_response(resolved["light"], resolved["scene_root"])


func set_light_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_light_2d(params)
	if resolved.has("_error"):
		return resolved
	var light: Light2D = resolved["light"]
	var parsed := _parse_light_updates(params, light)
	if parsed.has("_error"):
		return parsed
	var updates: Dictionary = parsed["updates"]
	var changed := {}
	for property_name_value in updates:
		var property_name := str(property_name_value)
		if light.get(property_name) != updates[property_name_value]:
			changed[property_name] = updates[property_name_value]
	if changed.is_empty():
		var unchanged := _light_2d_response(light, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Update %s" % light.name,
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	for property_name_value in changed:
		var property_name := str(property_name_value)
		var old_value = light.get(property_name)
		var new_value = changed[property_name]
		_undo_redo.add_do_property(light, property_name, new_value)
		if property_name == "texture" and new_value != null:
			_undo_redo.add_do_reference(new_value)
		_undo_redo.add_undo_property(light, property_name, old_value)
		if property_name == "texture" and old_value != null:
			_undo_redo.add_undo_reference(old_value)
	_undo_redo.commit_action()
	var result := _light_2d_response(light, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func get_light_occluder_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_light_occluder_2d(params, false)
	if resolved.has("_error"):
		return resolved
	return _light_occluder_response(resolved["occluder"], resolved["scene_root"])


func set_light_occluder_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_light_occluder_2d(params)
	if resolved.has("_error"):
		return resolved
	var occluder: LightOccluder2D = resolved["occluder"]
	var parsed := _parse_light_occluder_updates(params)
	if parsed.has("_error"):
		return parsed
	var updates: Dictionary = parsed["updates"]
	var replacement_requested: bool = parsed["replacement_requested"]
	var replacement: OccluderPolygon2D = parsed["replacement"]
	var changed := {}
	for property_name_value in updates:
		var property_name := str(property_name_value)
		if occluder.get(property_name) != updates[property_name_value]:
			changed[property_name] = updates[property_name_value]
	if changed.is_empty() and not replacement_requested:
		var unchanged := _light_occluder_response(occluder, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	var old_occluder: OccluderPolygon2D = occluder.occluder
	_undo_redo.create_action(
		"Godot 2D MCP: Update %s" % occluder.name,
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	for property_name_value in changed:
		var property_name := str(property_name_value)
		_undo_redo.add_do_property(occluder, property_name, changed[property_name])
		_undo_redo.add_undo_property(occluder, property_name, occluder.get(property_name))
	if replacement_requested:
		_undo_redo.add_do_property(occluder, "occluder", replacement)
		if replacement != null:
			_undo_redo.add_do_reference(replacement)
		_undo_redo.add_undo_property(occluder, "occluder", old_occluder)
		if old_occluder != null:
			_undo_redo.add_undo_reference(old_occluder)
	_undo_redo.commit_action()
	var result := _light_occluder_response(occluder, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_light_2d(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is Light2D:
		return Errors.make(
			"LIGHT_2D_REQUIRED",
			"Node '%s' is %s, not Light2D" % [resolved["node"].name, resolved["node"].get_class()],
			false,
			"Target a PointLight2D or DirectionalLight2D node."
		)
	resolved["light"] = resolved["node"] as Light2D
	return resolved


func _resolve_light_occluder_2d(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is LightOccluder2D:
		return Errors.make(
			"LIGHT_OCCLUDER_2D_REQUIRED",
			"Node '%s' is %s, not LightOccluder2D" % [resolved["node"].name, resolved["node"].get_class()],
			false,
			"Target a LightOccluder2D node."
		)
	resolved["occluder"] = resolved["node"] as LightOccluder2D
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


func _light_2d_response(light: Light2D, scene_root: Node) -> Dictionary:
	var configuration := {
		"enabled": light.enabled,
		"editor_only": light.editor_only,
		"color": VariantCodec.serialize(light.color),
		"energy": light.energy,
		"blend_mode": _light_enum_name("blend_mode", light.blend_mode),
		"range_z_min": light.range_z_min,
		"range_z_max": light.range_z_max,
		"range_layer_min": light.range_layer_min,
		"range_layer_max": light.range_layer_max,
		"range_item_cull_layers": _mask_to_layer_numbers(light.range_item_cull_mask),
		"shadow_enabled": light.shadow_enabled,
		"shadow_color": VariantCodec.serialize(light.shadow_color),
		"shadow_filter": _light_enum_name("shadow_filter", light.shadow_filter),
		"shadow_filter_smooth": light.shadow_filter_smooth,
		"shadow_item_cull_layers": _mask_to_layer_numbers(light.shadow_item_cull_mask),
		"height": light.height,
	}
	var supported := LIGHT_COMMON_PROPERTIES.duplicate()
	if light is PointLight2D:
		var point_light := light as PointLight2D
		configuration["texture_path"] = "" if point_light.texture == null else point_light.texture.resource_path
		configuration["offset"] = VariantCodec.serialize(point_light.offset)
		configuration["texture_scale"] = point_light.texture_scale
		supported.append_array(POINT_LIGHT_PROPERTIES)
	elif light is DirectionalLight2D:
		configuration["max_distance"] = (light as DirectionalLight2D).max_distance
		supported.append_array(DIRECTIONAL_LIGHT_PROPERTIES)
	return {
		"path": ScenePath.from_node(light, scene_root),
		"type": light.get_class(),
		"configuration": configuration,
		"supported_properties": supported,
	}


func _light_occluder_response(occluder: LightOccluder2D, scene_root: Node) -> Dictionary:
	return {
		"path": ScenePath.from_node(occluder, scene_root),
		"type": occluder.get_class(),
		"occluder_light_mask": occluder.occluder_light_mask,
		"layers": _mask_to_layer_numbers(occluder.occluder_light_mask),
		"sdf_collision": occluder.sdf_collision,
		"polygon": _serialize_occluder_polygon(occluder.occluder),
	}


func _parse_light_updates(params: Dictionary, light: Light2D) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() \
		or raw_properties.size() > MAX_LIGHT_PROPERTIES:
		return Errors.make(
			"INVALID_LIGHT_PROPERTIES",
			"properties must be a non-empty object containing at most %d entries" % MAX_LIGHT_PROPERTIES
		)
	var allowed := LIGHT_COMMON_PROPERTIES.duplicate()
	if light is PointLight2D:
		allowed.append_array(POINT_LIGHT_PROPERTIES)
	elif light is DirectionalLight2D:
		allowed.append_array(DIRECTIONAL_LIGHT_PROPERTIES)
	else:
		return Errors.make(
			"UNSUPPORTED_LIGHT_2D",
			"Light2D subtype '%s' is not supported" % light.get_class(),
			false,
			"Use PointLight2D or DirectionalLight2D."
		)
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String:
			return Errors.make("INVALID_LIGHT_PROPERTIES", "property names must be strings")
		var property_name: String = raw_name
		if not allowed.has(property_name):
			return Errors.make(
				"UNSUPPORTED_LIGHT_PROPERTY",
				"Property '%s' is not supported for %s" % [property_name, light.get_class()],
				false,
				"Call light_2d_get to inspect supported_properties."
			)
		var decoded := _decode_light_value(light, property_name, raw_properties[raw_name])
		if decoded.has("_error"):
			return decoded
		updates[decoded["property_name"]] = decoded["value"]
	return _validate_light_updates(light, updates)


func _decode_light_value(light: Light2D, property_name: String, raw_value: Variant) -> Dictionary:
	if LIGHT_MASK_PROPERTIES.has(property_name):
		var layers_result := _parse_layer_numbers(raw_value, property_name)
		if layers_result.has("_error"):
			return layers_result
		return {"property_name": LIGHT_MASK_PROPERTIES[property_name], "value": layers_result["mask"]}
	if property_name == "texture_path":
		var texture_result := _load_point_light_texture(raw_value)
		if texture_result.has("_error"):
			return texture_result
		return {"property_name": "texture", "value": texture_result["texture"]}
	if LIGHT_ENUM_OPTIONS.has(property_name):
		if not raw_value is String:
			return Errors.make("INVALID_LIGHT_ENUM", "%s must use a supported mode name" % property_name)
		var label: String = raw_value.to_lower().strip_edges()
		var options: Dictionary = LIGHT_ENUM_OPTIONS[property_name]
		if not options.has(label):
			return Errors.make(
				"INVALID_LIGHT_ENUM",
				"%s must use one of: %s" % [property_name, ", ".join(options.keys())]
			)
		return {"property_name": property_name, "value": options[label]}
	var actual_property := property_name
	if property_name == "offset":
		actual_property = "offset"
	var property_info := _find_property_info(light, actual_property)
	if property_info.is_empty():
		return Errors.make("LIGHT_PROPERTY_NOT_FOUND", "Property '%s' is not available" % property_name)
	var decoded := VariantCodec.decode(raw_value, property_info, light.get(actual_property))
	if decoded.has("_error"):
		return Errors.make(
			"LIGHT_PROPERTY_TYPE_MISMATCH",
			decoded["_error"]["message"],
			false,
			"Use the JSON values returned by light_2d_get.",
			{"property": property_name}
		)
	return {"property_name": actual_property, "value": decoded["value"]}


func _validate_light_updates(light: Light2D, updates: Dictionary) -> Dictionary:
	for property_name_value in updates:
		var property_name := str(property_name_value)
		var value = updates[property_name]
		if property_name in ["energy", "shadow_filter_smooth", "texture_scale", "height", "max_distance"]:
			if not (value is int or value is float) or not is_finite(float(value)):
				return Errors.make("INVALID_LIGHT_CONFIGURATION", "%s must be a finite number" % property_name)
		if property_name == "energy" and float(value) < 0.0:
			return Errors.make("INVALID_LIGHT_CONFIGURATION", "energy must be greater than or equal to zero")
		if property_name == "shadow_filter_smooth" and (float(value) < 0.0 or float(value) > 64.0):
			return Errors.make("INVALID_LIGHT_CONFIGURATION", "shadow_filter_smooth must be between 0 and 64")
		if property_name == "texture_scale" and float(value) < 0.01:
			return Errors.make("INVALID_LIGHT_CONFIGURATION", "texture_scale must be greater than or equal to 0.01")
		if property_name == "max_distance" and float(value) < 0.0:
			return Errors.make("INVALID_LIGHT_CONFIGURATION", "max_distance must be greater than or equal to zero")
		if property_name == "height" and float(value) < 0.0:
			return Errors.make("INVALID_LIGHT_CONFIGURATION", "height must be greater than or equal to zero")
	if light is DirectionalLight2D and updates.has("height") and float(updates["height"]) > 1.0:
		return Errors.make("INVALID_LIGHT_CONFIGURATION", "DirectionalLight2D height must be between 0 and 1")
	var z_min := int(updates.get("range_z_min", light.range_z_min))
	var z_max := int(updates.get("range_z_max", light.range_z_max))
	if z_min > z_max:
		return Errors.make("INVALID_LIGHT_CONFIGURATION", "range_z_min cannot exceed range_z_max")
	var layer_min := int(updates.get("range_layer_min", light.range_layer_min))
	var layer_max := int(updates.get("range_layer_max", light.range_layer_max))
	if layer_min > layer_max:
		return Errors.make("INVALID_LIGHT_CONFIGURATION", "range_layer_min cannot exceed range_layer_max")
	return {"updates": updates}


func _parse_light_occluder_updates(params: Dictionary) -> Dictionary:
	var updates := {}
	var has_update := false
	if params.has("layers") and params["layers"] != null:
		var layers_result := _parse_layer_numbers(params["layers"], "layers")
		if layers_result.has("_error"):
			return layers_result
		updates["occluder_light_mask"] = layers_result["mask"]
		has_update = true
	if params.has("sdf_collision") and params["sdf_collision"] != null:
		if not params["sdf_collision"] is bool:
			return Errors.make("INVALID_LIGHT_OCCLUDER", "sdf_collision must be a boolean")
		updates["sdf_collision"] = params["sdf_collision"]
		has_update = true
	var clear := false
	if params.has("clear") and params["clear"] != null:
		if not params["clear"] is bool:
			return Errors.make("INVALID_LIGHT_OCCLUDER", "clear must be a boolean")
		clear = params["clear"]
	var has_polygon := params.has("polygon") and params["polygon"] != null
	if clear and has_polygon:
		return Errors.make("INVALID_LIGHT_OCCLUDER", "clear cannot be combined with polygon")
	if not has_update and not clear and not has_polygon:
		return Errors.make("MISSING_PARAMETER", "layers, sdf_collision, polygon, or clear must be supplied")
	if clear:
		return {"updates": updates, "replacement_requested": true, "replacement": null}
	if has_polygon:
		var polygon_result := _parse_occluder_polygon(params["polygon"])
		if polygon_result.has("_error"):
			return polygon_result
		return {
			"updates": updates,
			"replacement_requested": true,
			"replacement": polygon_result["polygon"],
		}
	return {"updates": updates, "replacement_requested": false, "replacement": null}


func _parse_occluder_polygon(raw_value: Variant) -> Dictionary:
	if not raw_value is Dictionary or not raw_value.has("points"):
		return Errors.make("INVALID_LIGHT_OCCLUDER_POLYGON", "polygon must contain points")
	for name in raw_value:
		if name != "points" and name != "closed" and name != "cull_mode":
			return Errors.make("INVALID_LIGHT_OCCLUDER_POLYGON", "polygon contains an unsupported property")
	var closed := true
	if raw_value.has("closed"):
		if not raw_value["closed"] is bool:
			return Errors.make("INVALID_LIGHT_OCCLUDER_POLYGON", "polygon.closed must be a boolean")
		closed = raw_value["closed"]
	var points_result := _parse_occluder_points(raw_value["points"], closed)
	if points_result.has("_error"):
		return points_result
	var cull_mode := "disabled"
	if raw_value.has("cull_mode"):
		if not raw_value["cull_mode"] is String:
			return Errors.make("INVALID_LIGHT_OCCLUDER_POLYGON", "polygon.cull_mode must be a supported mode name")
		cull_mode = raw_value["cull_mode"].to_lower().strip_edges()
		if not OCCLUDER_CULL_MODES.has(cull_mode):
			return Errors.make(
				"INVALID_LIGHT_OCCLUDER_POLYGON",
				"polygon.cull_mode must be disabled, clockwise, or counter_clockwise"
			)
	var polygon := OccluderPolygon2D.new()
	polygon.polygon = points_result["points"]
	polygon.closed = closed
	polygon.cull_mode = OCCLUDER_CULL_MODES[cull_mode]
	return {"polygon": polygon}


func _parse_occluder_points(raw_value: Variant, closed: bool) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_PACKED_VECTOR2_ARRAY}, PackedVector2Array())
	if decoded.has("_error"):
		return Errors.make("INVALID_LIGHT_OCCLUDER_POLYGON", "polygon.points must be an array of Vector2 objects")
	var points: PackedVector2Array = decoded["value"]
	var minimum_points := 3 if closed else 2
	if points.size() < minimum_points or points.size() > MAX_OCCLUDER_POINTS:
		return Errors.make(
			"INVALID_LIGHT_OCCLUDER_POLYGON",
			"polygon.points must contain between %d and %d points" % [minimum_points, MAX_OCCLUDER_POINTS]
		)
	for point_index in points.size():
		if not is_finite(points[point_index].x) or not is_finite(points[point_index].y):
			return Errors.make("INVALID_LIGHT_OCCLUDER_POLYGON", "polygon.points must be finite")
		for later_index in range(point_index + 1, points.size()):
			if points[point_index].is_equal_approx(points[later_index]):
				return Errors.make("INVALID_LIGHT_OCCLUDER_POLYGON", "polygon.points must be unique")
	if closed:
		var signed_area := 0.0
		for point_index in points.size():
			var next_index := (point_index + 1) % points.size()
			signed_area += points[point_index].cross(points[next_index])
		if is_zero_approx(signed_area) \
			or _polygon_has_intersecting_edges(points) \
			or Geometry2D.triangulate_polygon(points).is_empty():
			return Errors.make(
				"INVALID_LIGHT_OCCLUDER_POLYGON",
				"closed polygon.points must describe a valid simple polygon"
			)
	return {"points": points}


func _polygon_has_intersecting_edges(points: PackedVector2Array) -> bool:
	for first_index in points.size():
		var first_next := (first_index + 1) % points.size()
		for second_index in range(first_index + 1, points.size()):
			var second_next := (second_index + 1) % points.size()
			if first_index == second_index \
				or first_index == second_next \
				or first_next == second_index \
				or first_next == second_next:
				continue
			if Geometry2D.segment_intersects_segment(
				points[first_index], points[first_next], points[second_index], points[second_next]
			) != null:
				return true
	return false


func _serialize_occluder_polygon(polygon: OccluderPolygon2D) -> Variant:
	if polygon == null:
		return null
	return {
		"points": VariantCodec.serialize(polygon.polygon),
		"closed": polygon.closed,
		"cull_mode": _occluder_cull_mode_name(polygon.cull_mode),
	}


func _load_point_light_texture(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_TEXTURE_PATH", "texture_path must be a res:// string or an empty string")
	var texture_path: String = raw_value.strip_edges()
	if texture_path.is_empty():
		return {"texture": null}
	if not texture_path.begins_with("res://") or "/../" in texture_path or texture_path.ends_with("/.."):
		return Errors.make("INVALID_TEXTURE_PATH", "texture_path must remain inside the Godot project res:// directory")
	if not ResourceLoader.exists(texture_path):
		return Errors.make("RESOURCE_NOT_FOUND", "texture_path does not exist: %s" % texture_path)
	var texture := ResourceLoader.load(texture_path)
	if not texture is Texture2D:
		return Errors.make("RESOURCE_TYPE_MISMATCH", "texture_path does not load a Texture2D resource")
	return {"texture": texture as Texture2D}


func _find_property_info(node: Node, property_name: String) -> Dictionary:
	for property_info_value in node.get_property_list():
		var property_info: Dictionary = property_info_value
		if str(property_info.get("name", "")) == property_name:
			return property_info
	return {}


func _parse_layer_numbers(raw_values: Variant, label: String) -> Dictionary:
	if not raw_values is Array or raw_values.size() > MAX_LIGHT_MASK_LAYERS:
		return Errors.make(
			"INVALID_LIGHT_MASK",
			"%s must contain at most %d layer numbers" % [label, MAX_LIGHT_MASK_LAYERS]
		)
	var mask := 0
	for raw_value in raw_values:
		if not _is_integral_number(raw_value):
			return Errors.make("INVALID_LIGHT_MASK", "%s entries must be integers from 1 to 32" % label)
		var layer := int(raw_value)
		if layer < 1 or layer > MAX_LIGHT_MASK_LAYERS or mask & (1 << (layer - 1)) != 0:
			return Errors.make(
				"INVALID_LIGHT_MASK",
				"%s entries must be unique integers from 1 to 32" % label
			)
		mask |= 1 << (layer - 1)
	return {"mask": mask}


func _mask_to_layer_numbers(mask: int) -> Array[int]:
	var layers: Array[int] = []
	for index in MAX_LIGHT_MASK_LAYERS:
		if mask & (1 << index) != 0:
			layers.append(index + 1)
	return layers


func _light_enum_name(property_name: String, value: int) -> String:
	var options: Dictionary = LIGHT_ENUM_OPTIONS[property_name]
	for label in options:
		if int(options[label]) == value:
			return label
	return "unknown"


func _occluder_cull_mode_name(cull_mode: int) -> String:
	for label in OCCLUDER_CULL_MODES:
		if int(OCCLUDER_CULL_MODES[label]) == cull_mode:
			return label
	return "disabled"


func _is_integral_number(value: Variant) -> bool:
	return value is int or (value is float and is_finite(value) and value == floorf(value))

@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_PROPERTIES := 64
const MAX_EMISSION_POINTS := 512
const CPU_PROPERTIES := [
	"emitting", "amount", "texture_path", "lifetime", "one_shot", "preprocess", "speed_scale",
	"explosiveness", "randomness", "use_fixed_seed", "seed", "lifetime_randomness", "fixed_fps",
	"fractional_delta", "local_coords", "draw_order", "emission_shape", "emission_sphere_radius",
	"emission_rect_extents", "emission_points", "emission_normals", "emission_colors",
	"emission_ring_inner_radius", "emission_ring_radius", "align_y_to_velocity", "direction", "spread",
	"gravity", "initial_velocity_min", "initial_velocity_max", "angular_velocity_min", "angular_velocity_max",
	"orbit_velocity_min", "orbit_velocity_max", "linear_accel_min", "linear_accel_max", "radial_accel_min",
	"radial_accel_max", "tangential_accel_min", "tangential_accel_max", "damping_min", "damping_max",
	"angle_min", "angle_max", "scale_amount_min", "scale_amount_max", "hue_variation_min",
	"hue_variation_max", "anim_speed_min", "anim_speed_max", "anim_offset_min", "anim_offset_max",
	"split_scale", "color",
]
const PROPERTY_ORDER := [
	"emitting", "amount", "texture", "lifetime", "one_shot", "preprocess", "speed_scale",
	"explosiveness", "randomness", "use_fixed_seed", "seed", "lifetime_randomness", "fixed_fps",
	"fract_delta", "local_coords", "draw_order", "emission_shape", "emission_sphere_radius",
	"emission_rect_extents", "emission_points", "emission_normals", "emission_colors",
	"emission_ring_inner_radius", "emission_ring_radius", "particle_flag_align_y", "direction", "spread",
	"gravity", "initial_velocity_min", "initial_velocity_max", "angular_velocity_min", "angular_velocity_max",
	"orbit_velocity_min", "orbit_velocity_max", "linear_accel_min", "linear_accel_max", "radial_accel_min",
	"radial_accel_max", "tangential_accel_min", "tangential_accel_max", "damping_min", "damping_max",
	"angle_min", "angle_max", "scale_amount_min", "scale_amount_max", "hue_variation_min",
	"hue_variation_max", "anim_speed_min", "anim_speed_max", "anim_offset_min", "anim_offset_max",
	"split_scale", "color",
]
const DRAW_ORDERS := {
	"index": CPUParticles2D.DRAW_ORDER_INDEX,
	"lifetime": CPUParticles2D.DRAW_ORDER_LIFETIME,
}
const EMISSION_SHAPES := {
	"point": CPUParticles2D.EMISSION_SHAPE_POINT,
	"sphere": CPUParticles2D.EMISSION_SHAPE_SPHERE,
	"sphere_surface": CPUParticles2D.EMISSION_SHAPE_SPHERE_SURFACE,
	"rectangle": CPUParticles2D.EMISSION_SHAPE_RECTANGLE,
	"points": CPUParticles2D.EMISSION_SHAPE_POINTS,
	"directed_points": CPUParticles2D.EMISSION_SHAPE_DIRECTED_POINTS,
	"ring": CPUParticles2D.EMISSION_SHAPE_RING,
}
const INTEGER_LIMITS := {
	"amount": {"minimum": 1, "maximum": 1000000},
	"seed": {"minimum": 0, "maximum": 4294967295},
	"fixed_fps": {"minimum": 0, "maximum": 1000},
}
const NUMBER_LIMITS := {
	"lifetime": {"minimum": 0.01, "maximum": 600.0},
	"preprocess": {"minimum": 0.0, "maximum": 600.0},
	"speed_scale": {"minimum": 0.0, "maximum": 64.0},
	"explosiveness": {"minimum": 0.0, "maximum": 1.0},
	"randomness": {"minimum": 0.0, "maximum": 1.0},
	"lifetime_randomness": {"minimum": 0.0, "maximum": 1.0},
	"emission_sphere_radius": {"minimum": 0.01, "maximum": 1000000.0},
	"emission_ring_inner_radius": {"minimum": 0.0, "maximum": 1000000.0},
	"emission_ring_radius": {"minimum": 0.0, "maximum": 1000000.0},
	"spread": {"minimum": 0.0, "maximum": 180.0},
	"initial_velocity_min": {"minimum": -1000000.0, "maximum": 1000000.0},
	"initial_velocity_max": {"minimum": -1000000.0, "maximum": 1000000.0},
	"angular_velocity_min": {"minimum": -1000000.0, "maximum": 1000000.0},
	"angular_velocity_max": {"minimum": -1000000.0, "maximum": 1000000.0},
	"orbit_velocity_min": {"minimum": -1000000.0, "maximum": 1000000.0},
	"orbit_velocity_max": {"minimum": -1000000.0, "maximum": 1000000.0},
	"linear_accel_min": {"minimum": -1000000.0, "maximum": 1000000.0},
	"linear_accel_max": {"minimum": -1000000.0, "maximum": 1000000.0},
	"radial_accel_min": {"minimum": -1000000.0, "maximum": 1000000.0},
	"radial_accel_max": {"minimum": -1000000.0, "maximum": 1000000.0},
	"tangential_accel_min": {"minimum": -1000000.0, "maximum": 1000000.0},
	"tangential_accel_max": {"minimum": -1000000.0, "maximum": 1000000.0},
	"damping_min": {"minimum": 0.0, "maximum": 1000000.0},
	"damping_max": {"minimum": 0.0, "maximum": 1000000.0},
	"angle_min": {"minimum": -1000000.0, "maximum": 1000000.0},
	"angle_max": {"minimum": -1000000.0, "maximum": 1000000.0},
	"scale_amount_min": {"minimum": 0.0, "maximum": 1000000.0},
	"scale_amount_max": {"minimum": 0.0, "maximum": 1000000.0},
	"hue_variation_min": {"minimum": -1.0, "maximum": 1.0},
	"hue_variation_max": {"minimum": -1.0, "maximum": 1.0},
	"anim_speed_min": {"minimum": -1000000.0, "maximum": 1000000.0},
	"anim_speed_max": {"minimum": -1000000.0, "maximum": 1000000.0},
	"anim_offset_min": {"minimum": 0.0, "maximum": 1.0},
	"anim_offset_max": {"minimum": 0.0, "maximum": 1.0},
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_cpu_particles_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_cpu_particles_2d(params, false)
	if resolved.has("_error"):
		return resolved
	return _particles_response(resolved["particles"], resolved["scene_root"])


func set_cpu_particles_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_cpu_particles_2d(params)
	if resolved.has("_error"):
		return resolved
	var particles: CPUParticles2D = resolved["particles"]
	var parsed := _parse_updates(params, particles)
	if parsed.has("_error"):
		return parsed
	var updates: Dictionary = parsed["updates"]
	var changed := {}
	for property_name in PROPERTY_ORDER:
		if updates.has(property_name) and particles.get(property_name) != updates[property_name]:
			changed[property_name] = updates[property_name]
	if changed.is_empty():
		var unchanged := _particles_response(particles, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Update CPUParticles2D %s" % particles.name,
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	for property_name in PROPERTY_ORDER:
		if not changed.has(property_name):
			continue
		var old_value = particles.get(property_name)
		var new_value = changed[property_name]
		_undo_redo.add_do_property(particles, property_name, new_value)
		if property_name == "texture" and new_value != null:
			_undo_redo.add_do_reference(new_value)
		_undo_redo.add_undo_property(particles, property_name, old_value)
		if property_name == "texture" and old_value != null:
			_undo_redo.add_undo_reference(old_value)
	_undo_redo.commit_action()
	var result := _particles_response(particles, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_cpu_particles_2d(params: Dictionary, require_writable: bool = true) -> Dictionary:
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
	if not node is CPUParticles2D:
		return Errors.make(
			"CPU_PARTICLES_2D_REQUIRED",
			"Node '%s' is %s, not CPUParticles2D" % [node.name, node.get_class()],
			false,
			"Target a CPUParticles2D node."
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit node '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned node."
		)
	return {"particles": node as CPUParticles2D, "scene_root": scene_root}


func _particles_response(particles: CPUParticles2D, scene_root: Node) -> Dictionary:
	var texture: Texture2D = particles.texture
	return {
		"path": ScenePath.from_node(particles, scene_root),
		"type": particles.get_class(),
		"configuration": {
			"emitting": particles.emitting,
			"amount": particles.amount,
			"texture_path": "" if texture == null else texture.resource_path,
			"texture_type": "" if texture == null else texture.get_class(),
			"lifetime": particles.lifetime,
			"one_shot": particles.one_shot,
			"preprocess": particles.preprocess,
			"speed_scale": particles.speed_scale,
			"explosiveness": particles.explosiveness,
			"randomness": particles.randomness,
			"use_fixed_seed": particles.use_fixed_seed,
			"seed": particles.seed,
			"lifetime_randomness": particles.lifetime_randomness,
			"fixed_fps": particles.fixed_fps,
			"fractional_delta": particles.fract_delta,
			"local_coords": particles.local_coords,
			"draw_order": _enum_name(DRAW_ORDERS, particles.draw_order),
			"emission_shape": _enum_name(EMISSION_SHAPES, particles.emission_shape),
			"emission_sphere_radius": particles.emission_sphere_radius,
			"emission_rect_extents": VariantCodec.serialize(particles.emission_rect_extents),
			"emission_points": VariantCodec.serialize(particles.emission_points),
			"emission_normals": VariantCodec.serialize(particles.emission_normals),
			"emission_colors": VariantCodec.serialize(particles.emission_colors),
			"emission_ring_inner_radius": particles.emission_ring_inner_radius,
			"emission_ring_radius": particles.emission_ring_radius,
			"align_y_to_velocity": particles.get_particle_flag(CPUParticles2D.PARTICLE_FLAG_ALIGN_Y_TO_VELOCITY),
			"direction": VariantCodec.serialize(particles.direction),
			"spread": particles.spread,
			"gravity": VariantCodec.serialize(particles.gravity),
			"initial_velocity_min": particles.get_param_min(CPUParticles2D.PARAM_INITIAL_LINEAR_VELOCITY),
			"initial_velocity_max": particles.get_param_max(CPUParticles2D.PARAM_INITIAL_LINEAR_VELOCITY),
			"angular_velocity_min": particles.get_param_min(CPUParticles2D.PARAM_ANGULAR_VELOCITY),
			"angular_velocity_max": particles.get_param_max(CPUParticles2D.PARAM_ANGULAR_VELOCITY),
			"orbit_velocity_min": particles.get_param_min(CPUParticles2D.PARAM_ORBIT_VELOCITY),
			"orbit_velocity_max": particles.get_param_max(CPUParticles2D.PARAM_ORBIT_VELOCITY),
			"linear_accel_min": particles.get_param_min(CPUParticles2D.PARAM_LINEAR_ACCEL),
			"linear_accel_max": particles.get_param_max(CPUParticles2D.PARAM_LINEAR_ACCEL),
			"radial_accel_min": particles.get_param_min(CPUParticles2D.PARAM_RADIAL_ACCEL),
			"radial_accel_max": particles.get_param_max(CPUParticles2D.PARAM_RADIAL_ACCEL),
			"tangential_accel_min": particles.get_param_min(CPUParticles2D.PARAM_TANGENTIAL_ACCEL),
			"tangential_accel_max": particles.get_param_max(CPUParticles2D.PARAM_TANGENTIAL_ACCEL),
			"damping_min": particles.get_param_min(CPUParticles2D.PARAM_DAMPING),
			"damping_max": particles.get_param_max(CPUParticles2D.PARAM_DAMPING),
			"angle_min": particles.get_param_min(CPUParticles2D.PARAM_ANGLE),
			"angle_max": particles.get_param_max(CPUParticles2D.PARAM_ANGLE),
			"scale_amount_min": particles.get_param_min(CPUParticles2D.PARAM_SCALE),
			"scale_amount_max": particles.get_param_max(CPUParticles2D.PARAM_SCALE),
			"hue_variation_min": particles.get_param_min(CPUParticles2D.PARAM_HUE_VARIATION),
			"hue_variation_max": particles.get_param_max(CPUParticles2D.PARAM_HUE_VARIATION),
			"anim_speed_min": particles.get_param_min(CPUParticles2D.PARAM_ANIM_SPEED),
			"anim_speed_max": particles.get_param_max(CPUParticles2D.PARAM_ANIM_SPEED),
			"anim_offset_min": particles.get_param_min(CPUParticles2D.PARAM_ANIM_OFFSET),
			"anim_offset_max": particles.get_param_max(CPUParticles2D.PARAM_ANIM_OFFSET),
			"split_scale": particles.split_scale,
			"color": VariantCodec.serialize(particles.color),
		},
		"draw_orders": DRAW_ORDERS.keys(),
		"emission_shapes": EMISSION_SHAPES.keys(),
		"supported_properties": CPU_PROPERTIES,
	}


func _parse_updates(params: Dictionary, particles: CPUParticles2D) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > MAX_PROPERTIES:
		return Errors.make(
			"INVALID_CPU_PARTICLES_PROPERTIES",
			"properties must be a non-empty object containing at most %d entries" % MAX_PROPERTIES
		)
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String or not CPU_PROPERTIES.has(raw_name):
			return Errors.make(
				"UNSUPPORTED_CPU_PARTICLES_PROPERTY",
				"Unsupported CPUParticles2D property: %s" % str(raw_name),
				false,
				"Call cpu_particles_2d_get to inspect supported_properties."
			)
		var parsed := _parse_property(raw_name, raw_properties[raw_name])
		if parsed.has("_error"):
			return parsed
		updates[parsed["property_name"]] = parsed["value"]
	var ring_inner: float = float(updates.get("emission_ring_inner_radius", particles.emission_ring_inner_radius))
	var ring_radius: float = float(updates.get("emission_ring_radius", particles.emission_ring_radius))
	if ring_inner > ring_radius:
		return Errors.make(
			"INVALID_CPU_PARTICLES_CONFIGURATION",
			"emission_ring_inner_radius cannot exceed emission_ring_radius"
		)
	return {"updates": updates}


func _parse_property(property_name: String, raw_value: Variant) -> Dictionary:
	if property_name == "texture_path":
		return _load_texture(raw_value)
	if property_name in ["draw_order", "emission_shape"]:
		var options: Dictionary = DRAW_ORDERS if property_name == "draw_order" else EMISSION_SHAPES
		var enum_result := _parse_enum(raw_value, property_name, options)
		if enum_result.has("_error"):
			return enum_result
		return {"property_name": property_name, "value": enum_result["value"]}
	if property_name == "align_y_to_velocity":
		if not raw_value is bool:
			return _invalid_value(property_name, "must be a boolean")
		return {"property_name": "particle_flag_align_y", "value": raw_value}
	if property_name in ["emitting", "one_shot", "use_fixed_seed", "fractional_delta", "local_coords", "split_scale"]:
		if not raw_value is bool:
			return _invalid_value(property_name, "must be a boolean")
		return {"property_name": _property_name(property_name), "value": raw_value}
	if property_name in ["emission_rect_extents", "direction", "gravity"]:
		var vector_result := _parse_vector2(raw_value, property_name)
		if vector_result.has("_error"):
			return vector_result
		if property_name == "emission_rect_extents" and (
			vector_result["value"].x < 0.0 or vector_result["value"].y < 0.0
		):
			return _invalid_value(property_name, "must have non-negative x and y")
		return {"property_name": property_name, "value": vector_result["value"]}
	if property_name in ["emission_points", "emission_normals"]:
		var points_result := _parse_point_array(raw_value, property_name)
		if points_result.has("_error"):
			return points_result
		return {"property_name": property_name, "value": points_result["value"]}
	if property_name == "emission_colors":
		var colors_result := _parse_color_array(raw_value)
		if colors_result.has("_error"):
			return colors_result
		return {"property_name": property_name, "value": colors_result["value"]}
	if property_name == "color":
		var color_result := _parse_color(raw_value, property_name)
		if color_result.has("_error"):
			return color_result
		return {"property_name": "color", "value": color_result["value"]}
	if INTEGER_LIMITS.has(property_name):
		var integer_result := _parse_integer(raw_value, property_name, INTEGER_LIMITS[property_name])
		if integer_result.has("_error"):
			return integer_result
		return {"property_name": property_name, "value": integer_result["value"]}
	var number_result := _parse_number(raw_value, property_name, NUMBER_LIMITS[property_name])
	if number_result.has("_error"):
		return number_result
	return {"property_name": property_name, "value": number_result["value"]}


func _load_texture(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_CPU_PARTICLES_TEXTURE_PATH", "texture_path must be a res:// string or an empty string")
	var resource_path: String = raw_value.strip_edges()
	if resource_path.is_empty():
		return {"property_name": "texture", "value": null}
	if not resource_path.begins_with("res://") or "/../" in resource_path or resource_path.ends_with("/.."):
		return Errors.make("INVALID_CPU_PARTICLES_TEXTURE_PATH", "texture_path must remain inside res://")
	if not ResourceLoader.exists(resource_path):
		return Errors.make("RESOURCE_NOT_FOUND", "texture_path does not exist: %s" % resource_path)
	var texture := ResourceLoader.load(resource_path)
	if not texture is Texture2D:
		return Errors.make("RESOURCE_TYPE_MISMATCH", "texture_path does not load a Texture2D resource")
	return {"property_name": "texture", "value": texture as Texture2D}


func _parse_enum(raw_value: Variant, property_name: String, options: Dictionary) -> Dictionary:
	if not raw_value is String:
		return _invalid_value(property_name, "must use a supported mode name")
	var label: String = raw_value.strip_edges().to_lower()
	if not options.has(label):
		return _invalid_value(property_name, "must be one of: %s" % ", ".join(options.keys()))
	return {"value": options[label]}


func _parse_vector2(raw_value: Variant, property_name: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_VECTOR2}, Vector2())
	if decoded.has("_error"):
		return _invalid_value(property_name, "must contain finite x and y values")
	var value: Vector2 = decoded["value"]
	if not is_finite(value.x) or not is_finite(value.y):
		return _invalid_value(property_name, "must contain finite x and y values")
	return {"value": value}


func _parse_point_array(raw_value: Variant, property_name: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_PACKED_VECTOR2_ARRAY}, PackedVector2Array())
	if decoded.has("_error") or decoded["value"].size() > MAX_EMISSION_POINTS:
		return _invalid_value(property_name, "must contain at most %d finite Vector2 values" % MAX_EMISSION_POINTS)
	var points: PackedVector2Array = decoded["value"]
	for point in points:
		if not is_finite(point.x) or not is_finite(point.y):
			return _invalid_value(property_name, "must contain finite Vector2 values")
	return {"value": points}


func _parse_color_array(raw_value: Variant) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_PACKED_COLOR_ARRAY}, PackedColorArray())
	if decoded.has("_error") or decoded["value"].size() > MAX_EMISSION_POINTS:
		return _invalid_value("emission_colors", "must contain at most %d finite Color values" % MAX_EMISSION_POINTS)
	var colors: PackedColorArray = decoded["value"]
	for color in colors:
		if not _is_finite_color(color):
			return _invalid_value("emission_colors", "must contain finite Color values")
	return {"value": colors}


func _parse_color(raw_value: Variant, property_name: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_COLOR}, Color.WHITE)
	if decoded.has("_error") or not _is_finite_color(decoded.get("value", Color.WHITE)):
		return _invalid_value(property_name, "must be a finite Color value")
	return {"value": decoded["value"]}


func _parse_integer(raw_value: Variant, property_name: String, limit: Dictionary) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool or not is_finite(float(raw_value)) \
		or float(raw_value) != floorf(float(raw_value)):
		return _invalid_value(property_name, "must be an integer")
	var value := int(raw_value)
	if value < int(limit["minimum"]) or value > int(limit["maximum"]):
		return _invalid_value(property_name, "must be between %s and %s" % [limit["minimum"], limit["maximum"]])
	return {"value": value}


func _parse_number(raw_value: Variant, property_name: String, limit: Dictionary) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool or not is_finite(float(raw_value)):
		return _invalid_value(property_name, "must be a finite number")
	var value := float(raw_value)
	if value < float(limit["minimum"]) or value > float(limit["maximum"]):
		return _invalid_value(property_name, "must be between %s and %s" % [limit["minimum"], limit["maximum"]])
	return {"value": value}


func _property_name(property_name: String) -> String:
	return {"fractional_delta": "fract_delta"}.get(property_name, property_name)


func _enum_name(options: Dictionary, value: int) -> String:
	for name in options:
		if options[name] == value:
			return name
	return ""


func _is_finite_color(value: Color) -> bool:
	return is_finite(value.r) and is_finite(value.g) and is_finite(value.b) and is_finite(value.a)


func _invalid_value(property_name: String, message: String) -> Dictionary:
	return Errors.make("INVALID_CPU_PARTICLES_CONFIGURATION", "%s %s" % [property_name, message])

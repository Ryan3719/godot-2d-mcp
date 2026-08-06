@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_CURVE_POINTS := 512
const MAX_GRADIENT_POINTS := 512
const MAX_ABSOLUTE_VALUE := 1000000.0
const CURVE_PROPERTIES := {
	"initial_velocity": "initial_velocity_curve",
	"angular_velocity": "angular_velocity_curve",
	"orbit_velocity": "orbit_velocity_curve",
	"linear_accel": "linear_accel_curve",
	"radial_accel": "radial_accel_curve",
	"tangential_accel": "tangential_accel_curve",
	"damping": "damping_curve",
	"angle": "angle_curve",
	"scale_amount": "scale_amount_curve",
	"scale_x": "scale_curve_x",
	"scale_y": "scale_curve_y",
	"hue_variation": "hue_variation_curve",
	"anim_speed": "anim_speed_curve",
	"anim_offset": "anim_offset_curve",
}
const CURVE_PARAMS := {
	"initial_velocity": CPUParticles2D.PARAM_INITIAL_LINEAR_VELOCITY,
	"angular_velocity": CPUParticles2D.PARAM_ANGULAR_VELOCITY,
	"orbit_velocity": CPUParticles2D.PARAM_ORBIT_VELOCITY,
	"linear_accel": CPUParticles2D.PARAM_LINEAR_ACCEL,
	"radial_accel": CPUParticles2D.PARAM_RADIAL_ACCEL,
	"tangential_accel": CPUParticles2D.PARAM_TANGENTIAL_ACCEL,
	"damping": CPUParticles2D.PARAM_DAMPING,
	"angle": CPUParticles2D.PARAM_ANGLE,
	"scale_amount": CPUParticles2D.PARAM_SCALE,
	"hue_variation": CPUParticles2D.PARAM_HUE_VARIATION,
	"anim_speed": CPUParticles2D.PARAM_ANIM_SPEED,
	"anim_offset": CPUParticles2D.PARAM_ANIM_OFFSET,
}
const GRADIENT_PROPERTIES := {
	"color": "color_ramp",
	"initial_color": "color_initial_ramp",
}
const CURVE_TANGENT_MODES := {
	"free": Curve.TANGENT_FREE,
	"linear": Curve.TANGENT_LINEAR,
}
const GRADIENT_INTERPOLATION_MODES := {
	"linear": Gradient.GRADIENT_INTERPOLATE_LINEAR,
	"constant": Gradient.GRADIENT_INTERPOLATE_CONSTANT,
	"cubic": Gradient.GRADIENT_INTERPOLATE_CUBIC,
}
const GRADIENT_COLOR_SPACES := {
	"srgb": Gradient.GRADIENT_COLOR_SPACE_SRGB,
	"linear_srgb": Gradient.GRADIENT_COLOR_SPACE_LINEAR_SRGB,
	"oklab": Gradient.GRADIENT_COLOR_SPACE_OKLAB,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_cpu_particles_2d_curve(params: Dictionary) -> Dictionary:
	var resolved := _resolve_cpu_particles_2d(params, false)
	if resolved.has("_error"):
		return resolved
	var curve_name_result := _parse_curve_name(params.get("curve", null))
	if curve_name_result.has("_error"):
		return curve_name_result
	return _curve_response(resolved["particles"], resolved["scene_root"], curve_name_result["name"])


func bind_cpu_particles_2d_curve(params: Dictionary) -> Dictionary:
	var resolved := _resolve_cpu_particles_2d(params)
	if resolved.has("_error"):
		return resolved
	var curve_name_result := _parse_curve_name(params.get("curve", null))
	if curve_name_result.has("_error"):
		return curve_name_result
	var resource_result := _load_resource(params.get("resource_path", null), "Curve")
	if resource_result.has("_error"):
		return resource_result
	var particles: CPUParticles2D = resolved["particles"]
	var curve_name: String = curve_name_result["name"]
	var current := _get_curve(particles, curve_name)
	var replacement: Curve = resource_result["resource"]
	if current == replacement:
		var unchanged := _curve_response(particles, resolved["scene_root"], curve_name)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_curve_replacement(
		particles,
		resolved["scene_root"],
		curve_name,
		replacement,
		"Bind CPUParticles2D %s curve on %s" % [curve_name, particles.name]
	)
	var result := _curve_response(particles, resolved["scene_root"], curve_name)
	result["changed"] = true
	result["bound_external_resource"] = not replacement.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_cpu_particles_2d_curve(params: Dictionary) -> Dictionary:
	var resolved := _resolve_cpu_particles_2d(params)
	if resolved.has("_error"):
		return resolved
	var curve_name_result := _parse_curve_name(params.get("curve", null))
	if curve_name_result.has("_error"):
		return curve_name_result
	var particles: CPUParticles2D = resolved["particles"]
	var curve_name: String = curve_name_result["name"]
	var current := _get_curve(particles, curve_name)
	if current != null and current.get_point_count() > MAX_CURVE_POINTS:
		return Errors.make(
			"CPU_PARTICLES_CURVE_POINT_LIMIT_EXCEEDED",
			"The current %s curve has more than %d points" % [curve_name, MAX_CURVE_POINTS],
			false,
			"Replace the curve after reducing it to the supported point limit."
		)
	var parsed := _parse_curve_updates(params.get("properties", null), current)
	if parsed.has("_error"):
		return parsed
	var replacement_result := _duplicate_or_create_curve(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: Curve = replacement_result["curve"]
	_apply_curve_updates(replacement, parsed["updates"])
	if _curves_match(current, replacement):
		var unchanged := _curve_response(particles, resolved["scene_root"], curve_name)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_curve_replacement(
		particles,
		resolved["scene_root"],
		curve_name,
		replacement,
		"Update CPUParticles2D %s curve on %s" % [curve_name, particles.name]
	)
	var result := _curve_response(particles, resolved["scene_root"], curve_name)
	result["changed"] = true
	result["created"] = current == null
	result["copied_external_resource"] = current != null and not current.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func clear_cpu_particles_2d_curve(params: Dictionary) -> Dictionary:
	var resolved := _resolve_cpu_particles_2d(params)
	if resolved.has("_error"):
		return resolved
	var curve_name_result := _parse_curve_name(params.get("curve", null))
	if curve_name_result.has("_error"):
		return curve_name_result
	var particles: CPUParticles2D = resolved["particles"]
	var curve_name: String = curve_name_result["name"]
	var current := _get_curve(particles, curve_name)
	if current == null:
		return _resource_not_assigned("curve", curve_name)
	_commit_curve_replacement(
		particles,
		resolved["scene_root"],
		curve_name,
		null,
		"Clear CPUParticles2D %s curve on %s" % [curve_name, particles.name]
	)
	var result := _curve_response(particles, resolved["scene_root"], curve_name)
	result["cleared"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func get_cpu_particles_2d_gradient(params: Dictionary) -> Dictionary:
	var resolved := _resolve_cpu_particles_2d(params, false)
	if resolved.has("_error"):
		return resolved
	var gradient_name_result := _parse_gradient_name(params.get("gradient", null))
	if gradient_name_result.has("_error"):
		return gradient_name_result
	return _gradient_response(
		resolved["particles"], resolved["scene_root"], gradient_name_result["name"]
	)


func bind_cpu_particles_2d_gradient(params: Dictionary) -> Dictionary:
	var resolved := _resolve_cpu_particles_2d(params)
	if resolved.has("_error"):
		return resolved
	var gradient_name_result := _parse_gradient_name(params.get("gradient", null))
	if gradient_name_result.has("_error"):
		return gradient_name_result
	var resource_result := _load_resource(params.get("resource_path", null), "Gradient")
	if resource_result.has("_error"):
		return resource_result
	var particles: CPUParticles2D = resolved["particles"]
	var gradient_name: String = gradient_name_result["name"]
	var current := _get_gradient(particles, gradient_name)
	var replacement: Gradient = resource_result["resource"]
	if current == replacement:
		var unchanged := _gradient_response(particles, resolved["scene_root"], gradient_name)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_resource_replacement(
		particles,
		resolved["scene_root"],
		GRADIENT_PROPERTIES[gradient_name],
		replacement,
		"Bind CPUParticles2D %s gradient on %s" % [gradient_name, particles.name]
	)
	var result := _gradient_response(particles, resolved["scene_root"], gradient_name)
	result["changed"] = true
	result["bound_external_resource"] = not replacement.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_cpu_particles_2d_gradient(params: Dictionary) -> Dictionary:
	var resolved := _resolve_cpu_particles_2d(params)
	if resolved.has("_error"):
		return resolved
	var gradient_name_result := _parse_gradient_name(params.get("gradient", null))
	if gradient_name_result.has("_error"):
		return gradient_name_result
	var particles: CPUParticles2D = resolved["particles"]
	var gradient_name: String = gradient_name_result["name"]
	var current := _get_gradient(particles, gradient_name)
	if current != null and current.get_point_count() > MAX_GRADIENT_POINTS:
		return Errors.make(
			"CPU_PARTICLES_GRADIENT_POINT_LIMIT_EXCEEDED",
			"The current %s gradient has more than %d points" % [gradient_name, MAX_GRADIENT_POINTS],
			false,
			"Replace the gradient after reducing it to the supported point limit."
		)
	var parsed := _parse_gradient_updates(params.get("properties", null))
	if parsed.has("_error"):
		return parsed
	var replacement_result := _duplicate_or_create_gradient(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: Gradient = replacement_result["gradient"]
	_apply_gradient_updates(replacement, parsed["updates"])
	if _gradients_match(current, replacement):
		var unchanged := _gradient_response(particles, resolved["scene_root"], gradient_name)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_resource_replacement(
		particles,
		resolved["scene_root"],
		GRADIENT_PROPERTIES[gradient_name],
		replacement,
		"Update CPUParticles2D %s gradient on %s" % [gradient_name, particles.name]
	)
	var result := _gradient_response(particles, resolved["scene_root"], gradient_name)
	result["changed"] = true
	result["created"] = current == null
	result["copied_external_resource"] = current != null and not current.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func clear_cpu_particles_2d_gradient(params: Dictionary) -> Dictionary:
	var resolved := _resolve_cpu_particles_2d(params)
	if resolved.has("_error"):
		return resolved
	var gradient_name_result := _parse_gradient_name(params.get("gradient", null))
	if gradient_name_result.has("_error"):
		return gradient_name_result
	var particles: CPUParticles2D = resolved["particles"]
	var gradient_name: String = gradient_name_result["name"]
	var current := _get_gradient(particles, gradient_name)
	if current == null:
		return _resource_not_assigned("gradient", gradient_name)
	_commit_resource_replacement(
		particles,
		resolved["scene_root"],
		GRADIENT_PROPERTIES[gradient_name],
		null,
		"Clear CPUParticles2D %s gradient on %s" % [gradient_name, particles.name]
	)
	var result := _gradient_response(particles, resolved["scene_root"], gradient_name)
	result["cleared"] = true
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


func _parse_curve_name(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_CPU_PARTICLES_CURVE", "curve must name a supported CPUParticles2D curve")
	var name: String = raw_value.strip_edges().to_lower()
	if not CURVE_PROPERTIES.has(name):
		return Errors.make(
			"INVALID_CPU_PARTICLES_CURVE",
			"curve must be one of: %s" % ", ".join(CURVE_PROPERTIES.keys())
		)
	return {"name": name}


func _parse_gradient_name(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_CPU_PARTICLES_GRADIENT", "gradient must name a supported CPUParticles2D gradient")
	var name: String = raw_value.strip_edges().to_lower()
	if not GRADIENT_PROPERTIES.has(name):
		return Errors.make(
			"INVALID_CPU_PARTICLES_GRADIENT",
			"gradient must be one of: %s" % ", ".join(GRADIENT_PROPERTIES.keys())
		)
	return {"name": name}


func _parse_curve_updates(raw_properties: Variant, current: Curve) -> Dictionary:
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > 6:
		return Errors.make(
			"INVALID_CPU_PARTICLES_CURVE",
			"properties must be a non-empty object containing at most 6 entries"
		)
	for raw_name in raw_properties:
		if not raw_name is String or raw_name not in [
			"min_domain", "max_domain", "min_value", "max_value", "bake_resolution", "points"
		]:
			return Errors.make("INVALID_CPU_PARTICLES_CURVE", "properties contains an unsupported Curve field")
	var reference := current if current != null else Curve.new()
	var updates := {}
	for property_name in ["min_domain", "max_domain", "min_value", "max_value"]:
		if raw_properties.has(property_name):
			var number_result := _parse_number(raw_properties[property_name], property_name)
			if number_result.has("_error"):
				return number_result
			updates[property_name] = number_result["value"]
	if raw_properties.has("bake_resolution"):
		var resolution_result := _parse_bake_resolution(raw_properties["bake_resolution"])
		if resolution_result.has("_error"):
			return resolution_result
		updates["bake_resolution"] = resolution_result["value"]
	var min_domain: float = float(updates.get("min_domain", reference.min_domain))
	var max_domain: float = float(updates.get("max_domain", reference.max_domain))
	var min_value: float = float(updates.get("min_value", reference.min_value))
	var max_value: float = float(updates.get("max_value", reference.max_value))
	if min_domain >= max_domain:
		return Errors.make("INVALID_CPU_PARTICLES_CURVE", "min_domain must be less than max_domain")
	if min_value >= max_value:
		return Errors.make("INVALID_CPU_PARTICLES_CURVE", "min_value must be less than max_value")
	if raw_properties.has("points"):
		var points_result := _parse_curve_points(
			raw_properties["points"], min_domain, max_domain, min_value, max_value
		)
		if points_result.has("_error"):
			return points_result
		updates["points"] = points_result["points"]
	return {"updates": updates}


func _parse_gradient_updates(raw_properties: Variant) -> Dictionary:
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > 3:
		return Errors.make(
			"INVALID_CPU_PARTICLES_GRADIENT",
			"properties must be a non-empty object containing at most 3 entries"
		)
	for raw_name in raw_properties:
		if not raw_name is String or raw_name not in [
			"points", "interpolation_mode", "interpolation_color_space"
		]:
			return Errors.make("INVALID_CPU_PARTICLES_GRADIENT", "properties contains an unsupported Gradient field")
	var updates := {}
	if raw_properties.has("points"):
		var points_result := _parse_gradient_points(raw_properties["points"])
		if points_result.has("_error"):
			return points_result
		updates["points"] = points_result["points"]
	for property_name in ["interpolation_mode", "interpolation_color_space"]:
		if not raw_properties.has(property_name):
			continue
		var options: Dictionary = (
			GRADIENT_INTERPOLATION_MODES if property_name == "interpolation_mode" else GRADIENT_COLOR_SPACES
		)
		var enum_result := _parse_enum(raw_properties[property_name], property_name, options)
		if enum_result.has("_error"):
			return enum_result
		updates[property_name] = enum_result["value"]
	return {"updates": updates}


func _parse_curve_points(
	raw_points: Variant,
	min_domain: float,
	max_domain: float,
	min_value: float,
	max_value: float
) -> Dictionary:
	if not raw_points is Array or raw_points.size() > MAX_CURVE_POINTS:
		return Errors.make(
			"INVALID_CPU_PARTICLES_CURVE",
			"points must contain at most %d Curve points" % MAX_CURVE_POINTS
		)
	var points: Array[Dictionary] = []
	var previous_x := -INF
	for index in raw_points.size():
		var point_result := _parse_curve_point(raw_points[index], index)
		if point_result.has("_error"):
			return point_result
		var point: Dictionary = point_result["point"]
		var position: Vector2 = point["position"]
		if position.x < min_domain or position.x > max_domain:
			return Errors.make(
				"INVALID_CPU_PARTICLES_CURVE",
				"points[%d].position.x must be between min_domain and max_domain" % index
			)
		if position.y < min_value or position.y > max_value:
			return Errors.make(
				"INVALID_CPU_PARTICLES_CURVE",
				"points[%d].position.y must be between min_value and max_value" % index
			)
		if position.x <= previous_x:
			return Errors.make(
				"INVALID_CPU_PARTICLES_CURVE",
				"points must use strictly increasing position.x values"
			)
		previous_x = position.x
		points.append(point)
	return {"points": points}


func _parse_curve_point(raw_point: Variant, index: int) -> Dictionary:
	if not raw_point is Dictionary or not raw_point.has("position"):
		return Errors.make("INVALID_CPU_PARTICLES_CURVE", "points[%d] must contain position" % index)
	for raw_name in raw_point:
		if not raw_name is String or raw_name not in [
			"position", "left_tangent", "right_tangent", "left_mode", "right_mode"
		]:
			return Errors.make("INVALID_CPU_PARTICLES_CURVE", "points[%d] contains an unsupported field" % index)
	var position_result := _parse_vector2(raw_point["position"], "points[%d].position" % index, "curve")
	if position_result.has("_error"):
		return position_result
	var point := {"position": position_result["value"]}
	for property_name in ["left_tangent", "right_tangent"]:
		var number_result := _parse_number(raw_point.get(property_name, 0.0), "points[%d].%s" % [index, property_name])
		if number_result.has("_error"):
			return number_result
		point[property_name] = number_result["value"]
	for property_name in ["left_mode", "right_mode"]:
		var mode_result := _parse_enum(
			raw_point.get(property_name, "free"), "points[%d].%s" % [index, property_name], CURVE_TANGENT_MODES
		)
		if mode_result.has("_error"):
			return mode_result
		point[property_name] = mode_result["value"]
	return {"point": point}


func _parse_gradient_points(raw_points: Variant) -> Dictionary:
	if not raw_points is Array or raw_points.size() < 2 or raw_points.size() > MAX_GRADIENT_POINTS:
		return Errors.make(
			"INVALID_CPU_PARTICLES_GRADIENT",
			"points must contain between 2 and %d Gradient points" % MAX_GRADIENT_POINTS
		)
	var points: Array[Dictionary] = []
	var previous_offset := -1.0
	for index in raw_points.size():
		var raw_point: Variant = raw_points[index]
		if not raw_point is Dictionary or raw_point.keys().size() != 2 or not raw_point.has("offset") or not raw_point.has("color"):
			return Errors.make(
				"INVALID_CPU_PARTICLES_GRADIENT",
				"points[%d] must contain exactly offset and color" % index
			)
		var offset_result := _parse_unit_number(raw_point["offset"], "points[%d].offset" % index)
		if offset_result.has("_error"):
			return offset_result
		if offset_result["value"] <= previous_offset:
			return Errors.make("INVALID_CPU_PARTICLES_GRADIENT", "points must use strictly increasing offsets")
		var color_result := _parse_color(raw_point["color"], "points[%d].color" % index)
		if color_result.has("_error"):
			return color_result
		previous_offset = offset_result["value"]
		points.append({"offset": offset_result["value"], "color": color_result["value"]})
	return {"points": points}


func _parse_number(raw_value: Variant, label: String) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool or not is_finite(float(raw_value)):
		return Errors.make("INVALID_CPU_PARTICLES_CURVE", "%s must be a finite number" % label)
	var value := float(raw_value)
	if absf(value) > MAX_ABSOLUTE_VALUE:
		return Errors.make(
			"INVALID_CPU_PARTICLES_CURVE",
			"%s must be between -%s and %s" % [label, MAX_ABSOLUTE_VALUE, MAX_ABSOLUTE_VALUE]
		)
	return {"value": value}


func _parse_unit_number(raw_value: Variant, label: String) -> Dictionary:
	var number_result := _parse_number(raw_value, label)
	if number_result.has("_error"):
		number_result["_error"]["code"] = "INVALID_CPU_PARTICLES_GRADIENT"
		return number_result
	if number_result["value"] < 0.0 or number_result["value"] > 1.0:
		return Errors.make("INVALID_CPU_PARTICLES_GRADIENT", "%s must be between 0 and 1" % label)
	return number_result


func _parse_bake_resolution(raw_value: Variant) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool or not is_finite(float(raw_value)) \
		or float(raw_value) != floorf(float(raw_value)):
		return Errors.make("INVALID_CPU_PARTICLES_CURVE", "bake_resolution must be an integer")
	var value := int(raw_value)
	if value < 1 or value > 1000:
		return Errors.make("INVALID_CPU_PARTICLES_CURVE", "bake_resolution must be between 1 and 1000")
	return {"value": value}


func _parse_vector2(raw_value: Variant, label: String, resource_type: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_VECTOR2}, Vector2())
	if decoded.has("_error"):
		return Errors.make("INVALID_CPU_PARTICLES_%s" % resource_type.to_upper(), "%s must contain finite x and y values" % label)
	var value: Vector2 = decoded["value"]
	if not is_finite(value.x) or not is_finite(value.y) or absf(value.x) > MAX_ABSOLUTE_VALUE or absf(value.y) > MAX_ABSOLUTE_VALUE:
		return Errors.make("INVALID_CPU_PARTICLES_%s" % resource_type.to_upper(), "%s must contain bounded finite x and y values" % label)
	return {"value": value}


func _parse_color(raw_value: Variant, label: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_COLOR}, Color.WHITE)
	if decoded.has("_error"):
		return Errors.make("INVALID_CPU_PARTICLES_GRADIENT", "%s must be a finite Color value" % label)
	var value: Color = decoded["value"]
	if not _is_finite_color(value):
		return Errors.make("INVALID_CPU_PARTICLES_GRADIENT", "%s must be a finite Color value" % label)
	return {"value": value}


func _parse_enum(raw_value: Variant, label: String, options: Dictionary) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_CPU_PARTICLES_RESOURCE", "%s must name a supported mode" % label)
	var value: String = raw_value.strip_edges().to_lower()
	if not options.has(value):
		return Errors.make(
			"INVALID_CPU_PARTICLES_RESOURCE",
			"%s must be one of: %s" % [label, ", ".join(options.keys())]
		)
	return {"value": options[value]}


func _load_resource(raw_value: Variant, expected_type: String) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_CPU_PARTICLES_RESOURCE_PATH", "resource_path must be a res:// path")
	var resource_path: String = raw_value.strip_edges()
	if resource_path.is_empty() or not resource_path.begins_with("res://") or "/../" in resource_path or resource_path.ends_with("/.."):
		return Errors.make("INVALID_CPU_PARTICLES_RESOURCE_PATH", "resource_path must stay inside res://")
	if not ResourceLoader.exists(resource_path):
		return Errors.make("RESOURCE_NOT_FOUND", "resource_path does not exist: %s" % resource_path)
	var resource := ResourceLoader.load(resource_path)
	if resource == null or resource.get_class() != expected_type:
		return Errors.make("RESOURCE_TYPE_MISMATCH", "resource_path does not load a %s resource" % expected_type)
	return {"resource": resource}


func _get_curve(particles: CPUParticles2D, curve_name: String) -> Curve:
	if CURVE_PARAMS.has(curve_name):
		return particles.get_param_curve(CURVE_PARAMS[curve_name])
	return particles.get(CURVE_PROPERTIES[curve_name]) as Curve


func _get_gradient(particles: CPUParticles2D, gradient_name: String) -> Gradient:
	return particles.get(GRADIENT_PROPERTIES[gradient_name]) as Gradient


func _duplicate_or_create_curve(current: Curve) -> Dictionary:
	if current == null:
		return {"curve": Curve.new()}
	var duplicated := current.duplicate(true)
	if duplicated == null or not duplicated is Curve:
		return Errors.make("CPU_PARTICLES_CURVE_DUPLICATION_FAILED", "Unable to duplicate the current Curve safely")
	return {"curve": duplicated as Curve}


func _duplicate_or_create_gradient(current: Gradient) -> Dictionary:
	if current == null:
		return {"gradient": Gradient.new()}
	var duplicated := current.duplicate(true)
	if duplicated == null or not duplicated is Gradient:
		return Errors.make("CPU_PARTICLES_GRADIENT_DUPLICATION_FAILED", "Unable to duplicate the current Gradient safely")
	return {"gradient": duplicated as Gradient}


func _apply_curve_updates(curve: Curve, updates: Dictionary) -> void:
	if updates.has("min_domain"):
		curve.min_domain = updates["min_domain"]
	if updates.has("max_domain"):
		curve.max_domain = updates["max_domain"]
	if updates.has("min_value"):
		curve.min_value = updates["min_value"]
	if updates.has("max_value"):
		curve.max_value = updates["max_value"]
	if updates.has("bake_resolution"):
		curve.bake_resolution = updates["bake_resolution"]
	if updates.has("points"):
		curve.clear_points()
		for point in updates["points"]:
			curve.add_point(
				point["position"],
				point["left_tangent"],
				point["right_tangent"],
				point["left_mode"],
				point["right_mode"]
			)


func _apply_gradient_updates(gradient: Gradient, updates: Dictionary) -> void:
	if updates.has("points"):
		var offsets := PackedFloat32Array()
		var colors := PackedColorArray()
		for point in updates["points"]:
			offsets.append(point["offset"])
			colors.append(point["color"])
		gradient.set_offsets(offsets)
		gradient.set_colors(colors)
	if updates.has("interpolation_mode"):
		gradient.interpolation_mode = updates["interpolation_mode"]
	if updates.has("interpolation_color_space"):
		gradient.interpolation_color_space = updates["interpolation_color_space"]


func _curve_response(particles: CPUParticles2D, scene_root: Node, curve_name: String) -> Dictionary:
	var curve := _get_curve(particles, curve_name)
	return {
		"path": ScenePath.from_node(particles, scene_root),
		"type": particles.get_class(),
		"curve": curve_name,
		"resource": _resource_info(curve),
		"configuration": _serialize_curve(curve),
		"curve_names": CURVE_PROPERTIES.keys(),
		"tangent_modes": CURVE_TANGENT_MODES.keys(),
	}


func _gradient_response(particles: CPUParticles2D, scene_root: Node, gradient_name: String) -> Dictionary:
	var gradient := _get_gradient(particles, gradient_name)
	return {
		"path": ScenePath.from_node(particles, scene_root),
		"type": particles.get_class(),
		"gradient": gradient_name,
		"resource": _resource_info(gradient),
		"configuration": _serialize_gradient(gradient),
		"gradient_names": GRADIENT_PROPERTIES.keys(),
		"interpolation_modes": GRADIENT_INTERPOLATION_MODES.keys(),
		"color_spaces": GRADIENT_COLOR_SPACES.keys(),
	}


func _resource_info(resource: Resource) -> Dictionary:
	return {
		"assigned": resource != null,
		"type": "" if resource == null else resource.get_class(),
		"resource_path": "" if resource == null else resource.resource_path,
		"origin": "none" if resource == null else ("external" if not resource.resource_path.is_empty() else "embedded"),
	}


func _serialize_curve(curve: Curve) -> Variant:
	if curve == null:
		return null
	var points: Array = []
	for index in curve.get_point_count():
		points.append({
			"position": VariantCodec.serialize(curve.get_point_position(index)),
			"left_tangent": curve.get_point_left_tangent(index),
			"right_tangent": curve.get_point_right_tangent(index),
			"left_mode": _enum_name(CURVE_TANGENT_MODES, curve.get_point_left_mode(index)),
			"right_mode": _enum_name(CURVE_TANGENT_MODES, curve.get_point_right_mode(index)),
		})
	return {
		"min_domain": curve.min_domain,
		"max_domain": curve.max_domain,
		"min_value": curve.min_value,
		"max_value": curve.max_value,
		"bake_resolution": curve.bake_resolution,
		"points": points,
	}


func _serialize_gradient(gradient: Gradient) -> Variant:
	if gradient == null:
		return null
	var points: Array = []
	for index in gradient.get_point_count():
		points.append({
			"offset": gradient.get_offset(index),
			"color": VariantCodec.serialize(gradient.get_color(index)),
		})
	return {
		"interpolation_mode": _enum_name(GRADIENT_INTERPOLATION_MODES, gradient.interpolation_mode),
		"interpolation_color_space": _enum_name(
			GRADIENT_COLOR_SPACES, gradient.interpolation_color_space
		),
		"points": points,
	}


func _curves_match(first: Curve, second: Curve) -> bool:
	if first == null or second == null:
		return first == second
	if not is_equal_approx(first.min_domain, second.min_domain) \
		or not is_equal_approx(first.max_domain, second.max_domain) \
		or not is_equal_approx(first.min_value, second.min_value) \
		or not is_equal_approx(first.max_value, second.max_value) \
		or first.bake_resolution != second.bake_resolution \
		or first.get_point_count() != second.get_point_count():
		return false
	for index in first.get_point_count():
		if not first.get_point_position(index).is_equal_approx(second.get_point_position(index)) \
			or not is_equal_approx(first.get_point_left_tangent(index), second.get_point_left_tangent(index)) \
			or not is_equal_approx(first.get_point_right_tangent(index), second.get_point_right_tangent(index)) \
			or first.get_point_left_mode(index) != second.get_point_left_mode(index) \
			or first.get_point_right_mode(index) != second.get_point_right_mode(index):
			return false
	return true


func _gradients_match(first: Gradient, second: Gradient) -> bool:
	if first == null or second == null:
		return first == second
	if first.interpolation_mode != second.interpolation_mode \
		or first.interpolation_color_space != second.interpolation_color_space \
		or first.get_point_count() != second.get_point_count():
		return false
	for index in first.get_point_count():
		if not is_equal_approx(first.get_offset(index), second.get_offset(index)) \
			or not first.get_color(index).is_equal_approx(second.get_color(index)):
			return false
	return true


func _commit_resource_replacement(
	particles: CPUParticles2D,
	scene_root: Node,
	property_name: String,
	replacement: Resource,
	action_name: String
) -> void:
	var old_resource := particles.get(property_name) as Resource
	_undo_redo.create_action("Godot 2D MCP: %s" % action_name, UndoRedo.MERGE_DISABLE, scene_root, true)
	_undo_redo.add_do_property(particles, property_name, replacement)
	if replacement != null:
		_undo_redo.add_do_reference(replacement)
	_undo_redo.add_undo_property(particles, property_name, old_resource)
	if old_resource != null:
		_undo_redo.add_undo_reference(old_resource)
	_undo_redo.commit_action()


func _commit_curve_replacement(
	particles: CPUParticles2D,
	scene_root: Node,
	curve_name: String,
	replacement: Curve,
	action_name: String
) -> void:
	if not CURVE_PARAMS.has(curve_name):
		_commit_resource_replacement(
			particles,
			scene_root,
			CURVE_PROPERTIES[curve_name],
			replacement,
			action_name
		)
		return
	var old_curve := _get_curve(particles, curve_name)
	var parameter: int = CURVE_PARAMS[curve_name]
	_undo_redo.create_action("Godot 2D MCP: %s" % action_name, UndoRedo.MERGE_DISABLE, scene_root, true)
	_undo_redo.add_do_method(particles, "set_param_curve", parameter, replacement)
	if replacement != null:
		_undo_redo.add_do_reference(replacement)
	_undo_redo.add_undo_method(particles, "set_param_curve", parameter, old_curve)
	if old_curve != null:
		_undo_redo.add_undo_reference(old_curve)
	_undo_redo.commit_action()


func _resource_not_assigned(resource_type: String, resource_name: String) -> Dictionary:
	return Errors.make(
		"CPU_PARTICLES_RESOURCE_NOT_ASSIGNED",
		"CPUParticles2D has no %s %s resource" % [resource_name, resource_type],
		false,
		"Call the corresponding set tool before clearing this resource."
	)


func _enum_name(options: Dictionary, value: int) -> String:
	for name in options:
		if options[name] == value:
			return name
	return ""


func _is_finite_color(value: Color) -> bool:
	return is_finite(value.r) and is_finite(value.g) and is_finite(value.b) and is_finite(value.a)

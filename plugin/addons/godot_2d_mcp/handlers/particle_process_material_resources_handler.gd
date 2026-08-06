@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_CURVE_POINTS := 512
const MAX_GRADIENT_POINTS := 512
const MAX_ABSOLUTE_VALUE := 1000000.0
const CURVE_PARAMS := {
	"angle": ParticleProcessMaterial.PARAM_ANGLE,
	"angular_velocity": ParticleProcessMaterial.PARAM_ANGULAR_VELOCITY,
	"orbit_velocity": ParticleProcessMaterial.PARAM_ORBIT_VELOCITY,
	"radial_velocity": ParticleProcessMaterial.PARAM_RADIAL_VELOCITY,
	"linear_accel": ParticleProcessMaterial.PARAM_LINEAR_ACCEL,
	"radial_accel": ParticleProcessMaterial.PARAM_RADIAL_ACCEL,
	"tangential_accel": ParticleProcessMaterial.PARAM_TANGENTIAL_ACCEL,
	"damping": ParticleProcessMaterial.PARAM_DAMPING,
	"scale": ParticleProcessMaterial.PARAM_SCALE,
	"scale_over_velocity": ParticleProcessMaterial.PARAM_SCALE_OVER_VELOCITY,
	"hue_variation": ParticleProcessMaterial.PARAM_HUE_VARIATION,
	"anim_speed": ParticleProcessMaterial.PARAM_ANIM_SPEED,
	"anim_offset": ParticleProcessMaterial.PARAM_ANIM_OFFSET,
	"turbulence_influence_over_life": ParticleProcessMaterial.PARAM_TURB_INFLUENCE_OVER_LIFE,
}
const DIRECT_CURVE_PROPERTIES := {
	"velocity_limit": "velocity_limit_curve",
	"alpha": "alpha_curve",
	"emission": "emission_curve",
}
const GRADIENT_PROPERTIES := {
	"color": "color_ramp",
	"initial_color": "color_initial_ramp",
}
const CURVE_TANGENT_MODES := {
	"free": Curve.TANGENT_FREE,
	"linear": Curve.TANGENT_LINEAR,
}
const CURVE_TEXTURE_MODES := {
	"rgb": CurveTexture.TEXTURE_MODE_RGB,
	"red": CurveTexture.TEXTURE_MODE_RED,
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


func get_particle_process_material_2d_curve(params: Dictionary) -> Dictionary:
	var resolved := _resolve_material(params, false)
	if resolved.has("_error"):
		return resolved
	var curve_name_result := _parse_curve_name(params.get("curve", null))
	if curve_name_result.has("_error"):
		return curve_name_result
	return _curve_response(resolved, curve_name_result["name"])


func bind_particle_process_material_2d_curve(params: Dictionary) -> Dictionary:
	var resolved := _resolve_material(params)
	if resolved.has("_error"):
		return resolved
	var curve_name_result := _parse_curve_name(params.get("curve", null))
	if curve_name_result.has("_error"):
		return curve_name_result
	var resource_result := _load_resource(params.get("resource_path", null), "CurveTexture")
	if resource_result.has("_error"):
		return resource_result
	var curve_name: String = curve_name_result["name"]
	var current: CurveTexture = _get_curve_texture(resolved["material"], curve_name)
	var replacement_texture: CurveTexture = resource_result["resource"]
	if current == replacement_texture:
		return _unchanged_response(_curve_response(resolved, curve_name))
	var material_result := _duplicate_material(resolved["material"])
	if material_result.has("_error"):
		return material_result
	var replacement_material: ParticleProcessMaterial = material_result["material"]
	_set_curve_texture(replacement_material, curve_name, replacement_texture)
	_commit_material_replacement(
		resolved["particles"],
		resolved["scene_root"],
		replacement_material,
		"Bind ParticleProcessMaterial %s curve on %s" % [curve_name, resolved["particles"].name]
	)
	var replacement_resolved := _replacement_resolved(resolved, replacement_material)
	var result := _curve_response(replacement_resolved, curve_name)
	result["changed"] = true
	result["bound_external_resource"] = not replacement_texture.resource_path.is_empty()
	result["copied_external_material"] = not resolved["material"].resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_particle_process_material_2d_curve(params: Dictionary) -> Dictionary:
	var resolved := _resolve_material(params)
	if resolved.has("_error"):
		return resolved
	var curve_name_result := _parse_curve_name(params.get("curve", null))
	if curve_name_result.has("_error"):
		return curve_name_result
	var curve_name: String = curve_name_result["name"]
	var current_texture: CurveTexture = _get_curve_texture(resolved["material"], curve_name)
	var current_curve: Curve = null if current_texture == null else current_texture.get_curve()
	if current_curve != null and current_curve.get_point_count() > MAX_CURVE_POINTS:
		return Errors.make(
			"PROCESS_MATERIAL_CURVE_POINT_LIMIT_EXCEEDED",
			"The current %s curve has more than %d points" % [curve_name, MAX_CURVE_POINTS],
			false,
			"Replace the curve after reducing it to the supported point limit."
		)
	var parsed := _parse_curve_updates(params.get("properties", null), current_curve)
	if parsed.has("_error"):
		return parsed
	var texture_result := _duplicate_or_create_curve_texture(current_texture)
	if texture_result.has("_error"):
		return texture_result
	var replacement_texture: CurveTexture = texture_result["texture"]
	_apply_curve_texture_updates(replacement_texture, parsed["updates"])
	if _curve_textures_match(current_texture, replacement_texture):
		return _unchanged_response(_curve_response(resolved, curve_name))
	var material_result := _duplicate_material(resolved["material"])
	if material_result.has("_error"):
		return material_result
	var replacement_material: ParticleProcessMaterial = material_result["material"]
	_set_curve_texture(replacement_material, curve_name, replacement_texture)
	_commit_material_replacement(
		resolved["particles"],
		resolved["scene_root"],
		replacement_material,
		"Update ParticleProcessMaterial %s curve on %s" % [curve_name, resolved["particles"].name]
	)
	var replacement_resolved := _replacement_resolved(resolved, replacement_material)
	var result := _curve_response(replacement_resolved, curve_name)
	result["changed"] = true
	result["created"] = current_texture == null
	result["copied_external_resource"] = current_texture != null and not current_texture.resource_path.is_empty()
	result["copied_external_material"] = not resolved["material"].resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func clear_particle_process_material_2d_curve(params: Dictionary) -> Dictionary:
	var resolved := _resolve_material(params)
	if resolved.has("_error"):
		return resolved
	var curve_name_result := _parse_curve_name(params.get("curve", null))
	if curve_name_result.has("_error"):
		return curve_name_result
	var curve_name: String = curve_name_result["name"]
	if _get_curve_texture(resolved["material"], curve_name) == null:
		return _resource_not_assigned("curve", curve_name)
	var material_result := _duplicate_material(resolved["material"])
	if material_result.has("_error"):
		return material_result
	var replacement_material: ParticleProcessMaterial = material_result["material"]
	_set_curve_texture(replacement_material, curve_name, null)
	_commit_material_replacement(
		resolved["particles"],
		resolved["scene_root"],
		replacement_material,
		"Clear ParticleProcessMaterial %s curve on %s" % [curve_name, resolved["particles"].name]
	)
	var replacement_resolved := _replacement_resolved(resolved, replacement_material)
	var result := _curve_response(replacement_resolved, curve_name)
	result["cleared"] = true
	result["copied_external_material"] = not resolved["material"].resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func get_particle_process_material_2d_gradient(params: Dictionary) -> Dictionary:
	var resolved := _resolve_material(params, false)
	if resolved.has("_error"):
		return resolved
	var gradient_name_result := _parse_gradient_name(params.get("gradient", null))
	if gradient_name_result.has("_error"):
		return gradient_name_result
	return _gradient_response(resolved, gradient_name_result["name"])


func bind_particle_process_material_2d_gradient(params: Dictionary) -> Dictionary:
	var resolved := _resolve_material(params)
	if resolved.has("_error"):
		return resolved
	var gradient_name_result := _parse_gradient_name(params.get("gradient", null))
	if gradient_name_result.has("_error"):
		return gradient_name_result
	var resource_result := _load_resource(params.get("resource_path", null), "GradientTexture1D")
	if resource_result.has("_error"):
		return resource_result
	var gradient_name: String = gradient_name_result["name"]
	var current: GradientTexture1D = _get_gradient_texture(resolved["material"], gradient_name)
	var replacement_texture: GradientTexture1D = resource_result["resource"]
	if current == replacement_texture:
		return _unchanged_response(_gradient_response(resolved, gradient_name))
	var material_result := _duplicate_material(resolved["material"])
	if material_result.has("_error"):
		return material_result
	var replacement_material: ParticleProcessMaterial = material_result["material"]
	_set_gradient_texture(replacement_material, gradient_name, replacement_texture)
	_commit_material_replacement(
		resolved["particles"],
		resolved["scene_root"],
		replacement_material,
		"Bind ParticleProcessMaterial %s gradient on %s" % [gradient_name, resolved["particles"].name]
	)
	var replacement_resolved := _replacement_resolved(resolved, replacement_material)
	var result := _gradient_response(replacement_resolved, gradient_name)
	result["changed"] = true
	result["bound_external_resource"] = not replacement_texture.resource_path.is_empty()
	result["copied_external_material"] = not resolved["material"].resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_particle_process_material_2d_gradient(params: Dictionary) -> Dictionary:
	var resolved := _resolve_material(params)
	if resolved.has("_error"):
		return resolved
	var gradient_name_result := _parse_gradient_name(params.get("gradient", null))
	if gradient_name_result.has("_error"):
		return gradient_name_result
	var gradient_name: String = gradient_name_result["name"]
	var current_texture: GradientTexture1D = _get_gradient_texture(resolved["material"], gradient_name)
	var current_gradient: Gradient = null if current_texture == null else current_texture.get_gradient()
	if current_gradient != null and current_gradient.get_point_count() > MAX_GRADIENT_POINTS:
		return Errors.make(
			"PROCESS_MATERIAL_GRADIENT_POINT_LIMIT_EXCEEDED",
			"The current %s gradient has more than %d points" % [gradient_name, MAX_GRADIENT_POINTS],
			false,
			"Replace the gradient after reducing it to the supported point limit."
		)
	var parsed := _parse_gradient_updates(params.get("properties", null))
	if parsed.has("_error"):
		return parsed
	var texture_result := _duplicate_or_create_gradient_texture(current_texture)
	if texture_result.has("_error"):
		return texture_result
	var replacement_texture: GradientTexture1D = texture_result["texture"]
	_apply_gradient_texture_updates(replacement_texture, parsed["updates"])
	if _gradient_textures_match(current_texture, replacement_texture):
		return _unchanged_response(_gradient_response(resolved, gradient_name))
	var material_result := _duplicate_material(resolved["material"])
	if material_result.has("_error"):
		return material_result
	var replacement_material: ParticleProcessMaterial = material_result["material"]
	_set_gradient_texture(replacement_material, gradient_name, replacement_texture)
	_commit_material_replacement(
		resolved["particles"],
		resolved["scene_root"],
		replacement_material,
		"Update ParticleProcessMaterial %s gradient on %s" % [gradient_name, resolved["particles"].name]
	)
	var replacement_resolved := _replacement_resolved(resolved, replacement_material)
	var result := _gradient_response(replacement_resolved, gradient_name)
	result["changed"] = true
	result["created"] = current_texture == null
	result["copied_external_resource"] = current_texture != null and not current_texture.resource_path.is_empty()
	result["copied_external_material"] = not resolved["material"].resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func clear_particle_process_material_2d_gradient(params: Dictionary) -> Dictionary:
	var resolved := _resolve_material(params)
	if resolved.has("_error"):
		return resolved
	var gradient_name_result := _parse_gradient_name(params.get("gradient", null))
	if gradient_name_result.has("_error"):
		return gradient_name_result
	var gradient_name: String = gradient_name_result["name"]
	if _get_gradient_texture(resolved["material"], gradient_name) == null:
		return _resource_not_assigned("gradient", gradient_name)
	var material_result := _duplicate_material(resolved["material"])
	if material_result.has("_error"):
		return material_result
	var replacement_material: ParticleProcessMaterial = material_result["material"]
	_set_gradient_texture(replacement_material, gradient_name, null)
	_commit_material_replacement(
		resolved["particles"],
		resolved["scene_root"],
		replacement_material,
		"Clear ParticleProcessMaterial %s gradient on %s" % [gradient_name, resolved["particles"].name]
	)
	var replacement_resolved := _replacement_resolved(resolved, replacement_material)
	var result := _gradient_response(replacement_resolved, gradient_name)
	result["cleared"] = true
	result["copied_external_material"] = not resolved["material"].resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_material(params: Dictionary, require_writable: bool = true) -> Dictionary:
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
	if not node is GPUParticles2D:
		return Errors.make(
			"GPU_PARTICLES_2D_REQUIRED",
			"Node '%s' is %s, not GPUParticles2D" % [node.name, node.get_class()],
			false,
			"Target a GPUParticles2D node."
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit node '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned node."
		)
	var particles := node as GPUParticles2D
	var material := particles.process_material as ParticleProcessMaterial
	if material == null:
		return Errors.make(
			"PARTICLE_PROCESS_MATERIAL_REQUIRED",
			"GPUParticles2D '%s' has no assigned ParticleProcessMaterial" % particles.name,
			false,
			"Call particle_process_material_2d_create or bind an existing ParticleProcessMaterial first."
		)
	return {"particles": particles, "material": material, "scene_root": scene_root}


func _replacement_resolved(resolved: Dictionary, material: ParticleProcessMaterial) -> Dictionary:
	return {
		"particles": resolved["particles"],
		"material": material,
		"scene_root": resolved["scene_root"],
	}


func _parse_curve_name(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_PROCESS_MATERIAL_CURVE", "curve must name a supported ParticleProcessMaterial curve")
	var name: String = raw_value.strip_edges().to_lower()
	if not CURVE_PARAMS.has(name) and not DIRECT_CURVE_PROPERTIES.has(name):
		return Errors.make(
			"INVALID_PROCESS_MATERIAL_CURVE",
			"curve must be one of: %s" % ", ".join(_curve_names())
		)
	return {"name": name}


func _parse_gradient_name(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_PROCESS_MATERIAL_GRADIENT", "gradient must name a supported ParticleProcessMaterial gradient")
	var name: String = raw_value.strip_edges().to_lower()
	if not GRADIENT_PROPERTIES.has(name):
		return Errors.make(
			"INVALID_PROCESS_MATERIAL_GRADIENT",
			"gradient must be one of: %s" % ", ".join(GRADIENT_PROPERTIES.keys())
		)
	return {"name": name}


func _parse_curve_updates(raw_properties: Variant, current: Curve) -> Dictionary:
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > 8:
		return Errors.make(
			"INVALID_PROCESS_MATERIAL_CURVE",
			"properties must be a non-empty object containing at most 8 entries"
		)
	for raw_name in raw_properties:
		if not raw_name is String or raw_name not in [
			"width", "texture_mode", "min_domain", "max_domain", "min_value", "max_value", "bake_resolution", "points"
		]:
			return Errors.make("INVALID_PROCESS_MATERIAL_CURVE", "properties contains an unsupported CurveTexture field")
	var reference := current if current != null else Curve.new()
	var updates := {}
	if raw_properties.has("width"):
		var width_result := _parse_integer(raw_properties["width"], "width", 32, 4096)
		if width_result.has("_error"):
			return width_result
		updates["width"] = width_result["value"]
	if raw_properties.has("texture_mode"):
		var texture_mode_result := _parse_enum(raw_properties["texture_mode"], "texture_mode", CURVE_TEXTURE_MODES)
		if texture_mode_result.has("_error"):
			return texture_mode_result
		updates["texture_mode"] = texture_mode_result["value"]
	for property_name in ["min_domain", "max_domain", "min_value", "max_value"]:
		if raw_properties.has(property_name):
			var number_result := _parse_number(raw_properties[property_name], property_name, "CURVE")
			if number_result.has("_error"):
				return number_result
			updates[property_name] = number_result["value"]
	if raw_properties.has("bake_resolution"):
		var resolution_result := _parse_integer(raw_properties["bake_resolution"], "bake_resolution", 1, 1000)
		if resolution_result.has("_error"):
			return resolution_result
		updates["bake_resolution"] = resolution_result["value"]
	var min_domain: float = float(updates.get("min_domain", reference.min_domain))
	var max_domain: float = float(updates.get("max_domain", reference.max_domain))
	var min_value: float = float(updates.get("min_value", reference.min_value))
	var max_value: float = float(updates.get("max_value", reference.max_value))
	if min_domain >= max_domain:
		return Errors.make("INVALID_PROCESS_MATERIAL_CURVE", "min_domain must be less than max_domain")
	if min_value >= max_value:
		return Errors.make("INVALID_PROCESS_MATERIAL_CURVE", "min_value must be less than max_value")
	if raw_properties.has("points"):
		var points_result := _parse_curve_points(raw_properties["points"], min_domain, max_domain, min_value, max_value)
		if points_result.has("_error"):
			return points_result
		updates["points"] = points_result["points"]
	return {"updates": updates}


func _parse_gradient_updates(raw_properties: Variant) -> Dictionary:
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > 5:
		return Errors.make(
			"INVALID_PROCESS_MATERIAL_GRADIENT",
			"properties must be a non-empty object containing at most 5 entries"
		)
	for raw_name in raw_properties:
		if not raw_name is String or raw_name not in [
			"width", "use_hdr", "points", "interpolation_mode", "interpolation_color_space"
		]:
			return Errors.make("INVALID_PROCESS_MATERIAL_GRADIENT", "properties contains an unsupported GradientTexture1D field")
	var updates := {}
	if raw_properties.has("width"):
		var width_result := _parse_integer(raw_properties["width"], "width", 1, 16384)
		if width_result.has("_error"):
			return width_result
		updates["width"] = width_result["value"]
	if raw_properties.has("use_hdr"):
		if not raw_properties["use_hdr"] is bool:
			return Errors.make("INVALID_PROCESS_MATERIAL_GRADIENT", "use_hdr must be a boolean")
		updates["use_hdr"] = raw_properties["use_hdr"]
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


func _parse_curve_points(raw_points: Variant, min_domain: float, max_domain: float, min_value: float, max_value: float) -> Dictionary:
	if not raw_points is Array or raw_points.size() > MAX_CURVE_POINTS:
		return Errors.make(
			"INVALID_PROCESS_MATERIAL_CURVE",
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
		if position.x < min_domain or position.x > max_domain or position.y < min_value or position.y > max_value:
			return Errors.make(
				"INVALID_PROCESS_MATERIAL_CURVE",
				"points[%d].position must stay inside the configured domain and value range" % index
			)
		if position.x <= previous_x:
			return Errors.make("INVALID_PROCESS_MATERIAL_CURVE", "Curve point positions must use strictly increasing x values")
		previous_x = position.x
		points.append(point)
	return {"points": points}


func _parse_curve_point(raw_point: Variant, index: int) -> Dictionary:
	if not raw_point is Dictionary:
		return Errors.make("INVALID_PROCESS_MATERIAL_CURVE", "points[%d] must be an object" % index)
	for raw_name in raw_point:
		if not raw_name is String or raw_name not in [
			"position", "left_tangent", "right_tangent", "left_mode", "right_mode"
		]:
			return Errors.make("INVALID_PROCESS_MATERIAL_CURVE", "points[%d] contains an unsupported field" % index)
	if not raw_point.has("position"):
		return Errors.make("INVALID_PROCESS_MATERIAL_CURVE", "points[%d].position is required" % index)
	var position_result := _parse_vector2(raw_point["position"], "points[%d].position" % index, "CURVE")
	if position_result.has("_error"):
		return position_result
	var point := {
		"position": position_result["value"],
		"left_tangent": 0.0,
		"right_tangent": 0.0,
		"left_mode": Curve.TANGENT_FREE,
		"right_mode": Curve.TANGENT_FREE,
	}
	for property_name in ["left_tangent", "right_tangent"]:
		if raw_point.has(property_name):
			var tangent_result := _parse_number(raw_point[property_name], "points[%d].%s" % [index, property_name], "CURVE")
			if tangent_result.has("_error"):
				return tangent_result
			point[property_name] = tangent_result["value"]
	for property_name in ["left_mode", "right_mode"]:
		if raw_point.has(property_name):
			var mode_result := _parse_enum(raw_point[property_name], "points[%d].%s" % [index, property_name], CURVE_TANGENT_MODES)
			if mode_result.has("_error"):
				return mode_result
			point[property_name] = mode_result["value"]
	return {"point": point}


func _parse_gradient_points(raw_points: Variant) -> Dictionary:
	if not raw_points is Array or raw_points.size() < 2 or raw_points.size() > MAX_GRADIENT_POINTS:
		return Errors.make(
			"INVALID_PROCESS_MATERIAL_GRADIENT",
			"points must contain between 2 and %d Gradient points" % MAX_GRADIENT_POINTS
		)
	var points: Array[Dictionary] = []
	var previous_offset := -1.0
	for index in raw_points.size():
		var raw_point: Variant = raw_points[index]
		if not raw_point is Dictionary or raw_point.size() != 2 or not raw_point.has("offset") or not raw_point.has("color"):
			return Errors.make("INVALID_PROCESS_MATERIAL_GRADIENT", "points[%d] must contain offset and color" % index)
		var offset_result := _parse_unit_interval(raw_point["offset"], "points[%d].offset" % index)
		if offset_result.has("_error"):
			return offset_result
		if offset_result["value"] <= previous_offset:
			return Errors.make("INVALID_PROCESS_MATERIAL_GRADIENT", "Gradient point offsets must be strictly increasing")
		var color_result := _parse_color(raw_point["color"], "points[%d].color" % index)
		if color_result.has("_error"):
			return color_result
		previous_offset = offset_result["value"]
		points.append({"offset": offset_result["value"], "color": color_result["value"]})
	return {"points": points}


func _get_curve_texture(material: ParticleProcessMaterial, curve_name: String) -> CurveTexture:
	if CURVE_PARAMS.has(curve_name):
		return material.get_param_texture(CURVE_PARAMS[curve_name]) as CurveTexture
	return material.get(DIRECT_CURVE_PROPERTIES[curve_name]) as CurveTexture


func _set_curve_texture(material: ParticleProcessMaterial, curve_name: String, texture: CurveTexture) -> void:
	if CURVE_PARAMS.has(curve_name):
		material.set_param_texture(CURVE_PARAMS[curve_name], texture)
		return
	material.set(DIRECT_CURVE_PROPERTIES[curve_name], texture)


func _get_gradient_texture(material: ParticleProcessMaterial, gradient_name: String) -> GradientTexture1D:
	return material.get(GRADIENT_PROPERTIES[gradient_name]) as GradientTexture1D


func _set_gradient_texture(material: ParticleProcessMaterial, gradient_name: String, texture: GradientTexture1D) -> void:
	material.set(GRADIENT_PROPERTIES[gradient_name], texture)


func _duplicate_or_create_curve_texture(current: CurveTexture) -> Dictionary:
	if current == null:
		var created := CurveTexture.new()
		created.set_curve(Curve.new())
		return {"texture": created}
	var duplicated := current.duplicate(true)
	if not duplicated is CurveTexture:
		return Errors.make("PROCESS_MATERIAL_CURVE_DUPLICATION_FAILED", "Unable to duplicate the current CurveTexture safely")
	var texture := duplicated as CurveTexture
	var current_curve := current.get_curve()
	if current_curve == null:
		texture.set_curve(Curve.new())
	else:
		var duplicated_curve := current_curve.duplicate(true)
		if not duplicated_curve is Curve:
			return Errors.make("PROCESS_MATERIAL_CURVE_DUPLICATION_FAILED", "Unable to duplicate the current Curve safely")
		texture.set_curve(duplicated_curve as Curve)
	return {"texture": texture}


func _duplicate_or_create_gradient_texture(current: GradientTexture1D) -> Dictionary:
	if current == null:
		var created := GradientTexture1D.new()
		created.set_gradient(Gradient.new())
		return {"texture": created}
	var duplicated := current.duplicate(true)
	if not duplicated is GradientTexture1D:
		return Errors.make("PROCESS_MATERIAL_GRADIENT_DUPLICATION_FAILED", "Unable to duplicate the current GradientTexture1D safely")
	var texture := duplicated as GradientTexture1D
	var current_gradient := current.get_gradient()
	if current_gradient == null:
		texture.set_gradient(Gradient.new())
	else:
		var duplicated_gradient := current_gradient.duplicate(true)
		if not duplicated_gradient is Gradient:
			return Errors.make("PROCESS_MATERIAL_GRADIENT_DUPLICATION_FAILED", "Unable to duplicate the current Gradient safely")
		texture.set_gradient(duplicated_gradient as Gradient)
	return {"texture": texture}


func _duplicate_material(current: ParticleProcessMaterial) -> Dictionary:
	var duplicated = current.duplicate(true)
	if not duplicated is ParticleProcessMaterial:
		return Errors.make("PROCESS_MATERIAL_DUPLICATE_FAILED", "Unable to duplicate the current ParticleProcessMaterial safely")
	return {"material": duplicated as ParticleProcessMaterial}


func _apply_curve_texture_updates(texture: CurveTexture, updates: Dictionary) -> void:
	if updates.has("width"):
		texture.set_width(updates["width"])
	if updates.has("texture_mode"):
		texture.set_texture_mode(updates["texture_mode"])
	var curve := texture.get_curve()
	if curve == null:
		curve = Curve.new()
		texture.set_curve(curve)
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
			curve.add_point(point["position"], point["left_tangent"], point["right_tangent"], point["left_mode"], point["right_mode"])


func _apply_gradient_texture_updates(texture: GradientTexture1D, updates: Dictionary) -> void:
	if updates.has("width"):
		texture.set_width(updates["width"])
	if updates.has("use_hdr"):
		texture.set_use_hdr(updates["use_hdr"])
	var gradient := texture.get_gradient()
	if gradient == null:
		gradient = Gradient.new()
		texture.set_gradient(gradient)
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


func _commit_material_replacement(particles: GPUParticles2D, scene_root: Node, replacement: ParticleProcessMaterial, action_name: String) -> void:
	var old_material: Material = particles.process_material
	_undo_redo.create_action("Godot 2D MCP: %s" % action_name, UndoRedo.MERGE_DISABLE, scene_root, true)
	_undo_redo.add_do_property(particles, "process_material", replacement)
	_undo_redo.add_do_reference(replacement)
	_undo_redo.add_undo_property(particles, "process_material", old_material)
	if old_material != null:
		_undo_redo.add_undo_reference(old_material)
	_undo_redo.commit_action()


func _curve_response(resolved: Dictionary, curve_name: String) -> Dictionary:
	var texture := _get_curve_texture(resolved["material"], curve_name)
	return {
		"path": ScenePath.from_node(resolved["particles"], resolved["scene_root"]),
		"type": resolved["particles"].get_class(),
		"curve": curve_name,
		"material": _resource_info(resolved["material"]),
		"resource": _resource_info(texture),
		"configuration": _serialize_curve_texture(texture),
		"curve_names": _curve_names(),
		"tangent_modes": CURVE_TANGENT_MODES.keys(),
		"texture_modes": CURVE_TEXTURE_MODES.keys(),
	}


func _gradient_response(resolved: Dictionary, gradient_name: String) -> Dictionary:
	var texture := _get_gradient_texture(resolved["material"], gradient_name)
	return {
		"path": ScenePath.from_node(resolved["particles"], resolved["scene_root"]),
		"type": resolved["particles"].get_class(),
		"gradient": gradient_name,
		"material": _resource_info(resolved["material"]),
		"resource": _resource_info(texture),
		"configuration": _serialize_gradient_texture(texture),
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


func _serialize_curve_texture(texture: CurveTexture) -> Variant:
	if texture == null:
		return null
	return {
		"width": texture.get_width(),
		"texture_mode": _enum_name(CURVE_TEXTURE_MODES, texture.get_texture_mode()),
		"curve": _serialize_curve(texture.get_curve()),
	}


func _serialize_gradient_texture(texture: GradientTexture1D) -> Variant:
	if texture == null:
		return null
	return {
		"width": texture.get_width(),
		"use_hdr": texture.is_using_hdr(),
		"gradient": _serialize_gradient(texture.get_gradient()),
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
		"interpolation_color_space": _enum_name(GRADIENT_COLOR_SPACES, gradient.interpolation_color_space),
		"points": points,
	}


func _curve_textures_match(first: CurveTexture, second: CurveTexture) -> bool:
	if first == null or second == null:
		return first == second
	return first.get_width() == second.get_width() and first.get_texture_mode() == second.get_texture_mode() and _curves_match(first.get_curve(), second.get_curve())


func _gradient_textures_match(first: GradientTexture1D, second: GradientTexture1D) -> bool:
	if first == null or second == null:
		return first == second
	return first.get_width() == second.get_width() and first.is_using_hdr() == second.is_using_hdr() and _gradients_match(first.get_gradient(), second.get_gradient())


func _curves_match(first: Curve, second: Curve) -> bool:
	if first == null or second == null:
		return first == second
	if not is_equal_approx(first.min_domain, second.min_domain) or not is_equal_approx(first.max_domain, second.max_domain) or not is_equal_approx(first.min_value, second.min_value) or not is_equal_approx(first.max_value, second.max_value) or first.bake_resolution != second.bake_resolution or first.get_point_count() != second.get_point_count():
		return false
	for index in first.get_point_count():
		if not first.get_point_position(index).is_equal_approx(second.get_point_position(index)) or not is_equal_approx(first.get_point_left_tangent(index), second.get_point_left_tangent(index)) or not is_equal_approx(first.get_point_right_tangent(index), second.get_point_right_tangent(index)) or first.get_point_left_mode(index) != second.get_point_left_mode(index) or first.get_point_right_mode(index) != second.get_point_right_mode(index):
			return false
	return true


func _gradients_match(first: Gradient, second: Gradient) -> bool:
	if first == null or second == null:
		return first == second
	if first.interpolation_mode != second.interpolation_mode or first.interpolation_color_space != second.interpolation_color_space or first.get_point_count() != second.get_point_count():
		return false
	for index in first.get_point_count():
		if not is_equal_approx(first.get_offset(index), second.get_offset(index)) or not first.get_color(index).is_equal_approx(second.get_color(index)):
			return false
	return true


func _load_resource(raw_value: Variant, expected_type: String) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_PROCESS_MATERIAL_RESOURCE_PATH", "resource_path must be a res:// path")
	var resource_path: String = raw_value.strip_edges()
	if resource_path.is_empty() or not resource_path.begins_with("res://") or "/../" in resource_path or resource_path.ends_with("/.."):
		return Errors.make("INVALID_PROCESS_MATERIAL_RESOURCE_PATH", "resource_path must stay inside res://")
	if not ResourceLoader.exists(resource_path):
		return Errors.make("RESOURCE_NOT_FOUND", "resource_path does not exist: %s" % resource_path)
	var resource := ResourceLoader.load(resource_path)
	if resource == null or resource.get_class() != expected_type:
		return Errors.make("RESOURCE_TYPE_MISMATCH", "resource_path does not load a %s resource" % expected_type)
	return {"resource": resource}


func _parse_integer(raw_value: Variant, label: String, minimum: int, maximum: int) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool or not is_finite(float(raw_value)) or float(raw_value) != floorf(float(raw_value)):
		return Errors.make("INVALID_PROCESS_MATERIAL_RESOURCE", "%s must be an integer" % label)
	var value := int(raw_value)
	if value < minimum or value > maximum:
		return Errors.make("INVALID_PROCESS_MATERIAL_RESOURCE", "%s must be between %d and %d" % [label, minimum, maximum])
	return {"value": value}


func _parse_number(raw_value: Variant, label: String, resource_kind: String) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool or not is_finite(float(raw_value)) or absf(float(raw_value)) > MAX_ABSOLUTE_VALUE:
		return Errors.make("INVALID_PROCESS_MATERIAL_%s" % resource_kind, "%s must be a bounded finite number" % label)
	return {"value": float(raw_value)}


func _parse_unit_interval(raw_value: Variant, label: String) -> Dictionary:
	var number_result := _parse_number(raw_value, label, "GRADIENT")
	if number_result.has("_error"):
		return number_result
	if number_result["value"] < 0.0 or number_result["value"] > 1.0:
		return Errors.make("INVALID_PROCESS_MATERIAL_GRADIENT", "%s must be between 0 and 1" % label)
	return number_result


func _parse_vector2(raw_value: Variant, label: String, resource_kind: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_VECTOR2}, Vector2())
	if decoded.has("_error"):
		return Errors.make("INVALID_PROCESS_MATERIAL_%s" % resource_kind, "%s must contain finite x and y values" % label)
	var value: Vector2 = decoded["value"]
	if not is_finite(value.x) or not is_finite(value.y) or absf(value.x) > MAX_ABSOLUTE_VALUE or absf(value.y) > MAX_ABSOLUTE_VALUE:
		return Errors.make("INVALID_PROCESS_MATERIAL_%s" % resource_kind, "%s must contain bounded finite x and y values" % label)
	return {"value": value}


func _parse_color(raw_value: Variant, label: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_COLOR}, Color.WHITE)
	if decoded.has("_error"):
		return Errors.make("INVALID_PROCESS_MATERIAL_GRADIENT", "%s must be a finite Color value" % label)
	var value: Color = decoded["value"]
	if not is_finite(value.r) or not is_finite(value.g) or not is_finite(value.b) or not is_finite(value.a):
		return Errors.make("INVALID_PROCESS_MATERIAL_GRADIENT", "%s must be a finite Color value" % label)
	return {"value": value}


func _parse_enum(raw_value: Variant, label: String, options: Dictionary) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_PROCESS_MATERIAL_RESOURCE", "%s must name a supported mode" % label)
	var value: String = raw_value.strip_edges().to_lower()
	if not options.has(value):
		return Errors.make("INVALID_PROCESS_MATERIAL_RESOURCE", "%s must be one of: %s" % [label, ", ".join(options.keys())])
	return {"value": options[value]}


func _enum_name(options: Dictionary, value: int) -> String:
	for name in options:
		if options[name] == value:
			return name
	return ""


func _curve_names() -> Array:
	var names: Array = CURVE_PARAMS.keys()
	names.append_array(DIRECT_CURVE_PROPERTIES.keys())
	return names


func _resource_not_assigned(resource_kind: String, resource_name: String) -> Dictionary:
	return Errors.make(
		"PROCESS_MATERIAL_%s_NOT_ASSIGNED" % resource_kind.to_upper(),
		"ParticleProcessMaterial %s '%s' is not assigned" % [resource_kind, resource_name],
		false,
		"Call the corresponding set or bind tool first."
	)


func _unchanged_response(response: Dictionary) -> Dictionary:
	response["changed"] = false
	response["undoable"] = false
	return response

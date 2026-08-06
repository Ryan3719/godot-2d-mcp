@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_PROPERTIES := 64
const CORE_PROPERTIES := [
	"lifetime_randomness", "align_y_to_velocity", "disable_z", "damping_as_friction",
	"emission_shape", "emission_shape_offset", "emission_shape_scale",
	"emission_sphere_radius", "emission_box_extents", "emission_point_count", "emission_ring_height",
	"emission_ring_radius", "emission_ring_inner_radius", "emission_ring_cone_angle", "direction",
	"spread", "flatness", "inherit_velocity_ratio", "velocity_pivot", "initial_velocity_min",
	"initial_velocity_max", "angular_velocity_min", "angular_velocity_max", "orbit_velocity_min",
	"orbit_velocity_max", "radial_velocity_min", "radial_velocity_max", "directional_velocity_min",
	"directional_velocity_max", "gravity", "linear_accel_min", "linear_accel_max", "radial_accel_min",
	"radial_accel_max", "tangential_accel_min", "tangential_accel_max", "damping_min", "damping_max",
	"attractor_interaction_enabled", "scale_min", "scale_max", "color", "turbulence_enabled",
	"turbulence_noise_strength", "turbulence_noise_scale", "turbulence_noise_speed",
	"turbulence_noise_speed_random", "collision_mode", "collision_friction", "collision_bounce",
	"collision_use_scale", "sub_emitter_mode", "sub_emitter_frequency", "sub_emitter_amount_at_end",
	"sub_emitter_amount_at_collision", "sub_emitter_amount_at_start", "sub_emitter_keep_velocity",
]
const PARAMETER_PROPERTIES := {
	"initial_velocity": ParticleProcessMaterial.PARAM_INITIAL_LINEAR_VELOCITY,
	"angular_velocity": ParticleProcessMaterial.PARAM_ANGULAR_VELOCITY,
	"orbit_velocity": ParticleProcessMaterial.PARAM_ORBIT_VELOCITY,
	"radial_velocity": ParticleProcessMaterial.PARAM_RADIAL_VELOCITY,
	"directional_velocity": ParticleProcessMaterial.PARAM_DIRECTIONAL_VELOCITY,
	"linear_accel": ParticleProcessMaterial.PARAM_LINEAR_ACCEL,
	"radial_accel": ParticleProcessMaterial.PARAM_RADIAL_ACCEL,
	"tangential_accel": ParticleProcessMaterial.PARAM_TANGENTIAL_ACCEL,
	"damping": ParticleProcessMaterial.PARAM_DAMPING,
	"scale": ParticleProcessMaterial.PARAM_SCALE,
}
const FLAG_PROPERTIES := {
	"align_y_to_velocity": ParticleProcessMaterial.PARTICLE_FLAG_ALIGN_Y_TO_VELOCITY,
	"disable_z": ParticleProcessMaterial.PARTICLE_FLAG_DISABLE_Z,
	"damping_as_friction": ParticleProcessMaterial.PARTICLE_FLAG_DAMPING_AS_FRICTION,
}
const EMISSION_SHAPES := {
	"point": ParticleProcessMaterial.EMISSION_SHAPE_POINT,
	"sphere": ParticleProcessMaterial.EMISSION_SHAPE_SPHERE,
	"sphere_surface": ParticleProcessMaterial.EMISSION_SHAPE_SPHERE_SURFACE,
	"box": ParticleProcessMaterial.EMISSION_SHAPE_BOX,
	"points": ParticleProcessMaterial.EMISSION_SHAPE_POINTS,
	"directed_points": ParticleProcessMaterial.EMISSION_SHAPE_DIRECTED_POINTS,
	"ring": ParticleProcessMaterial.EMISSION_SHAPE_RING,
}
const COLLISION_MODES := {
	"disabled": ParticleProcessMaterial.COLLISION_DISABLED,
	"rigid": ParticleProcessMaterial.COLLISION_RIGID,
	"hide_on_contact": ParticleProcessMaterial.COLLISION_HIDE_ON_CONTACT,
}
const SUB_EMITTER_MODES := {
	"disabled": ParticleProcessMaterial.SUB_EMITTER_DISABLED,
	"constant": ParticleProcessMaterial.SUB_EMITTER_CONSTANT,
	"at_end": ParticleProcessMaterial.SUB_EMITTER_AT_END,
	"at_collision": ParticleProcessMaterial.SUB_EMITTER_AT_COLLISION,
	"at_start": ParticleProcessMaterial.SUB_EMITTER_AT_START,
}
const VECTOR_PROPERTIES := {
	"direction": "direction",
	"velocity_pivot": "velocity_pivot",
	"gravity": "gravity",
	"emission_shape_offset": "emission_shape_offset",
	"emission_shape_scale": "emission_shape_scale",
	"emission_box_extents": "emission_box_extents",
	"turbulence_noise_speed": "turbulence_noise_speed",
}
const BOOLEAN_PROPERTIES := [
	"attractor_interaction_enabled", "turbulence_enabled", "collision_use_scale", "sub_emitter_keep_velocity",
]
const INTEGER_LIMITS := {
	"emission_point_count": {"minimum": 0, "maximum": 1000000},
	"sub_emitter_amount_at_end": {"minimum": 1, "maximum": 32},
	"sub_emitter_amount_at_collision": {"minimum": 1, "maximum": 32},
	"sub_emitter_amount_at_start": {"minimum": 1, "maximum": 32},
}
const NUMBER_LIMITS := {
	"lifetime_randomness": {"minimum": 0.0, "maximum": 1.0},
	"emission_sphere_radius": {"minimum": 0.01, "maximum": 1000000.0},
	"emission_ring_height": {"minimum": 0.0, "maximum": 1000000.0},
	"emission_ring_radius": {"minimum": 0.0, "maximum": 1000000.0},
	"emission_ring_inner_radius": {"minimum": 0.0, "maximum": 1000000.0},
	"emission_ring_cone_angle": {"minimum": 0.0, "maximum": 90.0},
	"spread": {"minimum": 0.0, "maximum": 180.0},
	"flatness": {"minimum": 0.0, "maximum": 1.0},
	"inherit_velocity_ratio": {"minimum": -1000.0, "maximum": 1000.0},
	"turbulence_noise_strength": {"minimum": 0.0, "maximum": 20.0},
	"turbulence_noise_scale": {"minimum": 0.0, "maximum": 1000000.0},
	"turbulence_noise_speed_random": {"minimum": 0.0, "maximum": 4.0},
	"collision_friction": {"minimum": 0.0, "maximum": 1.0},
	"collision_bounce": {"minimum": 0.0, "maximum": 1.0},
	"sub_emitter_frequency": {"minimum": 0.01, "maximum": 100.0},
}
const PARAMETER_LIMITS := {
	"initial_velocity": {"minimum": -1000000.0, "maximum": 1000000.0},
	"angular_velocity": {"minimum": -1000000.0, "maximum": 1000000.0},
	"orbit_velocity": {"minimum": -1000000.0, "maximum": 1000000.0},
	"radial_velocity": {"minimum": -1000000.0, "maximum": 1000000.0},
	"directional_velocity": {"minimum": -1000000.0, "maximum": 1000000.0},
	"linear_accel": {"minimum": -1000000.0, "maximum": 1000000.0},
	"radial_accel": {"minimum": -1000000.0, "maximum": 1000000.0},
	"tangential_accel": {"minimum": -1000000.0, "maximum": 1000000.0},
	"damping": {"minimum": 0.0, "maximum": 1000000.0},
	"scale": {"minimum": 0.0, "maximum": 1000000.0},
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_particle_process_material_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_particles(params, false)
	if resolved.has("_error"):
		return resolved
	return _material_response(resolved["particles"], resolved["scene_root"])


func create_particle_process_material_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_particles(params)
	if resolved.has("_error"):
		return resolved
	var replace_existing_result := _parse_replace_existing(params)
	if replace_existing_result.has("_error"):
		return replace_existing_result
	var particles: GPUParticles2D = resolved["particles"]
	var old_material: Material = particles.process_material
	if old_material != null and not replace_existing_result["replace_existing"]:
		return Errors.make(
			"PROCESS_MATERIAL_ALREADY_ASSIGNED",
			"GPUParticles2D '%s' already has a %s process material" % [particles.name, old_material.get_class()],
			false,
			"Inspect it first or pass replace_existing: true to replace it with an embedded ParticleProcessMaterial."
		)
	var replacement := ParticleProcessMaterial.new()
	replacement.set_particle_flag(ParticleProcessMaterial.PARTICLE_FLAG_DISABLE_Z, true)
	_commit_material_replacement(
		particles,
		resolved["scene_root"],
		replacement,
		"Create ParticleProcessMaterial on %s" % particles.name
	)
	var result := _material_response(particles, resolved["scene_root"])
	result["created"] = true
	result["replaced_existing"] = old_material != null
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_particle_process_material_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_particles(params)
	if resolved.has("_error"):
		return resolved
	var particles: GPUParticles2D = resolved["particles"]
	var current := particles.process_material as ParticleProcessMaterial
	if current == null:
		return Errors.make(
			"PARTICLE_PROCESS_MATERIAL_REQUIRED",
			"GPUParticles2D '%s' has no assigned ParticleProcessMaterial" % particles.name,
			false,
			"Call particle_process_material_2d_create or bind an existing ParticleProcessMaterial first."
		)
	var parsed := _parse_updates(params, current)
	if parsed.has("_error"):
		return parsed
	var duplicate_result := _duplicate_material(current)
	if duplicate_result.has("_error"):
		return duplicate_result
	var replacement: ParticleProcessMaterial = duplicate_result["material"]
	for property_name_value in parsed["updates"]:
		_apply_update(replacement, str(property_name_value), parsed["updates"][property_name_value])
	if replacement.get_emission_ring_inner_radius() > replacement.get_emission_ring_radius():
		return Errors.make(
			"INVALID_PROCESS_MATERIAL_CONFIGURATION",
			"emission_ring_inner_radius cannot exceed emission_ring_radius"
		)
	if _serialize_configuration(current) == _serialize_configuration(replacement):
		var unchanged := _material_response(particles, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_material_replacement(
		particles,
		resolved["scene_root"],
		replacement,
		"Update ParticleProcessMaterial on %s" % particles.name
	)
	var result := _material_response(particles, resolved["scene_root"])
	result["changed"] = true
	result["copied_external_material"] = not current.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_particles(params: Dictionary, require_writable: bool = true) -> Dictionary:
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
	return {"particles": node as GPUParticles2D, "scene_root": scene_root}


func _material_response(particles: GPUParticles2D, scene_root: Node) -> Dictionary:
	var material: Material = particles.process_material
	var process_material := material as ParticleProcessMaterial
	return {
		"path": ScenePath.from_node(particles, scene_root),
		"type": particles.get_class(),
		"material": {
			"assigned": material != null,
			"type": "" if material == null else material.get_class(),
			"resource_path": "" if material == null else material.resource_path,
			"origin": "none" if material == null else ("external" if not material.resource_path.is_empty() else "embedded"),
			"is_particle_process_material": process_material != null,
		},
		"configuration": null if process_material == null else _serialize_configuration(process_material),
		"supported_properties": CORE_PROPERTIES if process_material == null else _supported_properties(process_material),
		"emission_shapes": EMISSION_SHAPES.keys(),
		"collision_modes": COLLISION_MODES.keys(),
		"sub_emitter_modes": SUB_EMITTER_MODES.keys(),
	}


func _serialize_configuration(material: ParticleProcessMaterial) -> Dictionary:
	var configuration := {
		"lifetime_randomness": material.get_lifetime_randomness(),
		"align_y_to_velocity": material.get_particle_flag(ParticleProcessMaterial.PARTICLE_FLAG_ALIGN_Y_TO_VELOCITY),
		"disable_z": material.get_particle_flag(ParticleProcessMaterial.PARTICLE_FLAG_DISABLE_Z),
		"damping_as_friction": material.get_particle_flag(ParticleProcessMaterial.PARTICLE_FLAG_DAMPING_AS_FRICTION),
		"emission_shape": _enum_name(EMISSION_SHAPES, material.get_emission_shape()),
		"emission_shape_offset": _vector3_to_vector2(material.get_emission_shape_offset()),
		"emission_shape_scale": _vector3_to_vector2(material.get_emission_shape_scale()),
		"emission_sphere_radius": material.get_emission_sphere_radius(),
		"emission_box_extents": _vector3_to_vector2(material.get_emission_box_extents()),
		"emission_point_count": material.get_emission_point_count(),
		"emission_ring_height": material.get_emission_ring_height(),
		"emission_ring_radius": material.get_emission_ring_radius(),
		"emission_ring_inner_radius": material.get_emission_ring_inner_radius(),
		"emission_ring_cone_angle": material.get_emission_ring_cone_angle(),
		"direction": _vector3_to_vector2(material.get_direction()),
		"spread": material.get_spread(),
		"flatness": material.get_flatness(),
		"inherit_velocity_ratio": material.get_inherit_velocity_ratio(),
		"velocity_pivot": _vector3_to_vector2(material.get_velocity_pivot()),
		"gravity": _vector3_to_vector2(material.get_gravity()),
		"attractor_interaction_enabled": material.is_attractor_interaction_enabled(),
		"color": VariantCodec.serialize(material.get_color()),
		"turbulence_enabled": material.get_turbulence_enabled(),
		"turbulence_noise_strength": material.get_turbulence_noise_strength(),
		"turbulence_noise_scale": material.get_turbulence_noise_scale(),
		"turbulence_noise_speed": _vector3_to_vector2(material.get_turbulence_noise_speed()),
		"turbulence_noise_speed_random": material.get_turbulence_noise_speed_random(),
		"collision_mode": _enum_name(COLLISION_MODES, material.get_collision_mode()),
		"collision_friction": material.get_collision_friction(),
		"collision_bounce": material.get_collision_bounce(),
		"collision_use_scale": material.is_collision_using_scale(),
		"sub_emitter_mode": _enum_name(SUB_EMITTER_MODES, material.get_sub_emitter_mode()),
		"sub_emitter_frequency": material.get_sub_emitter_frequency(),
		"sub_emitter_amount_at_end": material.get_sub_emitter_amount_at_end(),
		"sub_emitter_amount_at_collision": material.get_sub_emitter_amount_at_collision(),
		"sub_emitter_amount_at_start": material.get_sub_emitter_amount_at_start(),
		"sub_emitter_keep_velocity": material.get_sub_emitter_keep_velocity(),
	}
	for parameter_name_value in PARAMETER_PROPERTIES:
		var parameter_name := str(parameter_name_value)
		var parameter: int = PARAMETER_PROPERTIES[parameter_name]
		configuration["%s_min" % parameter_name] = material.get_param_min(parameter)
		configuration["%s_max" % parameter_name] = material.get_param_max(parameter)
	if _has_property(material, "particle_flag_inherit_emitter_scale"):
		configuration["inherit_emitter_scale"] = material.get("particle_flag_inherit_emitter_scale")
	return configuration


func _parse_replace_existing(params: Dictionary) -> Dictionary:
	var raw_value: Variant = params.get("replace_existing", false)
	if not raw_value is bool:
		return Errors.make("INVALID_PROCESS_MATERIAL", "replace_existing must be a boolean")
	return {"replace_existing": raw_value}


func _parse_updates(params: Dictionary, material: ParticleProcessMaterial) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > MAX_PROPERTIES:
		return Errors.make(
			"INVALID_PROCESS_MATERIAL_PROPERTIES",
			"properties must be a non-empty object containing at most %d entries" % MAX_PROPERTIES
		)
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String or not (
			CORE_PROPERTIES.has(raw_name)
			or (raw_name == "inherit_emitter_scale" and _has_property(material, "particle_flag_inherit_emitter_scale"))
		):
			return Errors.make(
				"UNSUPPORTED_PROCESS_MATERIAL_PROPERTY",
				"Unsupported ParticleProcessMaterial property: %s" % str(raw_name),
				false,
				"Call particle_process_material_2d_get to inspect supported_properties."
			)
		var parsed := _parse_property(raw_name, raw_properties[raw_name])
		if parsed.has("_error"):
			return parsed
		updates[raw_name] = parsed["value"]
	return {"updates": updates}


func _parse_property(property_name: String, raw_value: Variant) -> Dictionary:
	if property_name == "inherit_emitter_scale" or FLAG_PROPERTIES.has(property_name) or BOOLEAN_PROPERTIES.has(property_name):
		if not raw_value is bool:
			return _invalid_value(property_name, "must be a boolean")
		return {"value": raw_value}
	if VECTOR_PROPERTIES.has(property_name):
		var vector_result := _parse_vector2(raw_value, property_name)
		if vector_result.has("_error"):
			return vector_result
		if property_name == "emission_box_extents" and (
			vector_result["value"].x < 0.0 or vector_result["value"].y < 0.0
		):
			return _invalid_value(property_name, "must have non-negative x and y")
		return vector_result
	if property_name == "color":
		var decoded := VariantCodec.decode(raw_value, {"type": TYPE_COLOR}, Color.WHITE)
		if decoded.has("_error") or not _is_finite_color(decoded.get("value", Color.WHITE)):
			return _invalid_value(property_name, "must be a finite Color value")
		return {"value": decoded["value"]}
	if property_name == "emission_shape":
		return _parse_enum(raw_value, property_name, EMISSION_SHAPES)
	if property_name == "collision_mode":
		return _parse_enum(raw_value, property_name, COLLISION_MODES)
	if property_name == "sub_emitter_mode":
		return _parse_enum(raw_value, property_name, SUB_EMITTER_MODES)
	if INTEGER_LIMITS.has(property_name):
		return _parse_integer(property_name, raw_value, INTEGER_LIMITS[property_name])
	var parameter_result := _parse_parameter_property(property_name, raw_value)
	if parameter_result.has("handled"):
		return parameter_result
	return _parse_number(property_name, raw_value, NUMBER_LIMITS[property_name])


func _parse_parameter_property(property_name: String, raw_value: Variant) -> Dictionary:
	for parameter_name_value in PARAMETER_PROPERTIES:
		var parameter_name := str(parameter_name_value)
		if property_name != "%s_min" % parameter_name and property_name != "%s_max" % parameter_name:
			continue
		var parsed := _parse_number(property_name, raw_value, PARAMETER_LIMITS[parameter_name])
		parsed["handled"] = true
		return parsed
	return {}


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


func _parse_integer(property_name: String, raw_value: Variant, limit: Dictionary) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool or not is_finite(float(raw_value)) \
		or float(raw_value) != floorf(float(raw_value)):
		return _invalid_value(property_name, "must be an integer")
	var value := int(raw_value)
	if value < int(limit["minimum"]) or value > int(limit["maximum"]):
		return _invalid_value(
			property_name, "must be between %s and %s" % [limit["minimum"], limit["maximum"]]
		)
	return {"value": value}


func _parse_number(property_name: String, raw_value: Variant, limit: Dictionary) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool or not is_finite(float(raw_value)):
		return _invalid_value(property_name, "must be a finite number")
	var value := float(raw_value)
	if value < float(limit["minimum"]) or value > float(limit["maximum"]):
		return _invalid_value(
			property_name, "must be between %s and %s" % [limit["minimum"], limit["maximum"]]
		)
	return {"value": value}


func _apply_update(material: ParticleProcessMaterial, property_name: String, value: Variant) -> void:
	if VECTOR_PROPERTIES.has(property_name):
		material.set(VECTOR_PROPERTIES[property_name], Vector3(value.x, value.y, 0.0))
		return
	if FLAG_PROPERTIES.has(property_name):
		material.set_particle_flag(FLAG_PROPERTIES[property_name], value)
		return
	if property_name == "inherit_emitter_scale":
		material.set("particle_flag_inherit_emitter_scale", value)
		return
	for parameter_name_value in PARAMETER_PROPERTIES:
		var parameter_name := str(parameter_name_value)
		if property_name == "%s_min" % parameter_name:
			material.set_param_min(PARAMETER_PROPERTIES[parameter_name], value)
			return
		if property_name == "%s_max" % parameter_name:
			material.set_param_max(PARAMETER_PROPERTIES[parameter_name], value)
			return
	material.set(property_name, value)


func _duplicate_material(current: ParticleProcessMaterial) -> Dictionary:
	var duplicated = current.duplicate(true)
	if not duplicated is ParticleProcessMaterial:
		return Errors.make(
			"PROCESS_MATERIAL_DUPLICATE_FAILED",
			"Unable to duplicate the current ParticleProcessMaterial safely"
		)
	return {"material": duplicated as ParticleProcessMaterial}


func _commit_material_replacement(
	particles: GPUParticles2D,
	scene_root: Node,
	replacement: ParticleProcessMaterial,
	action_name: String
) -> void:
	var old_material: Material = particles.process_material
	_undo_redo.create_action("Godot 2D MCP: %s" % action_name, UndoRedo.MERGE_DISABLE, scene_root, true)
	_undo_redo.add_do_property(particles, "process_material", replacement)
	_undo_redo.add_do_reference(replacement)
	_undo_redo.add_undo_property(particles, "process_material", old_material)
	if old_material != null:
		_undo_redo.add_undo_reference(old_material)
	_undo_redo.commit_action()


func _vector3_to_vector2(value: Vector3) -> Dictionary:
	return {"x": value.x, "y": value.y}


func _enum_name(options: Dictionary, value: int) -> String:
	for name in options:
		if options[name] == value:
			return name
	return ""


func _supported_properties(material: ParticleProcessMaterial) -> Array:
	var supported: Array = CORE_PROPERTIES.duplicate()
	if _has_property(material, "particle_flag_inherit_emitter_scale"):
		supported.append("inherit_emitter_scale")
	return supported


func _has_property(object: Object, property_name: String) -> bool:
	for property_info in object.get_property_list():
		if str(property_info.get("name", "")) == property_name:
			return true
	return false


func _is_finite_color(value: Color) -> bool:
	return is_finite(value.r) and is_finite(value.g) and is_finite(value.b) and is_finite(value.a)


func _invalid_value(property_name: String, message: String) -> Dictionary:
	return Errors.make("INVALID_PROCESS_MATERIAL_CONFIGURATION", "%s %s" % [property_name, message])

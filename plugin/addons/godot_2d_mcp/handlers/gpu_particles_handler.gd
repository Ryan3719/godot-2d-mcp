@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_GPU_PARTICLES_PROPERTIES := 26
const GPU_PARTICLES_PROPERTIES := [
	"emitting", "amount", "amount_ratio", "sub_emitter_path", "texture_path", "process_material_path",
	"lifetime", "interp_to_end", "one_shot", "preprocess", "speed_scale", "explosiveness",
	"randomness", "use_fixed_seed", "seed", "fixed_fps", "interpolate", "fractional_delta",
	"collision_base_size", "visibility_rect", "local_coords", "draw_order", "trail_enabled",
	"trail_lifetime", "trail_sections", "trail_section_subdivisions",
]
const GPU_PARTICLES_PROPERTY_ORDER := [
	"emitting", "amount", "amount_ratio", "sub_emitter", "texture", "process_material", "lifetime",
	"interp_to_end", "one_shot", "preprocess", "speed_scale", "explosiveness", "randomness",
	"use_fixed_seed", "seed", "fixed_fps", "interpolate", "fract_delta", "collision_base_size",
	"visibility_rect", "local_coords", "draw_order", "trail_enabled", "trail_lifetime",
	"trail_sections", "trail_section_subdivisions",
]
const DRAW_ORDERS := {
	"index": GPUParticles2D.DRAW_ORDER_INDEX,
	"lifetime": GPUParticles2D.DRAW_ORDER_LIFETIME,
	"reverse_lifetime": GPUParticles2D.DRAW_ORDER_REVERSE_LIFETIME,
}
const INTEGER_LIMITS := {
	"amount": {"minimum": 1, "maximum": 1000000},
	"seed": {"minimum": 0, "maximum": 4294967295},
	"fixed_fps": {"minimum": 0, "maximum": 1000},
	"trail_sections": {"minimum": 2, "maximum": 128},
	"trail_section_subdivisions": {"minimum": 1, "maximum": 1024},
}
const NUMBER_LIMITS := {
	"amount_ratio": {"minimum": 0.0, "maximum": 1.0},
	"lifetime": {"minimum": 0.01, "maximum": 600.0},
	"interp_to_end": {"minimum": 0.0, "maximum": 1.0},
	"preprocess": {"minimum": 0.0, "maximum": 600.0},
	"speed_scale": {"minimum": 0.0, "maximum": 64.0},
	"explosiveness": {"minimum": 0.0, "maximum": 1.0},
	"randomness": {"minimum": 0.0, "maximum": 1.0},
	"collision_base_size": {"minimum": 0.0, "maximum": 1000000.0},
	"trail_lifetime": {"minimum": 0.01, "maximum": 600.0},
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_gpu_particles_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_gpu_particles_2d(params, false)
	if resolved.has("_error"):
		return resolved
	return _particles_response(resolved["particles"], resolved["scene_root"])


func set_gpu_particles_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_gpu_particles_2d(params)
	if resolved.has("_error"):
		return resolved
	var particles: GPUParticles2D = resolved["particles"]
	var parsed := _parse_updates(params, particles, resolved["scene_root"])
	if parsed.has("_error"):
		return parsed
	var updates: Dictionary = parsed["updates"]
	var changed := {}
	for property_name in GPU_PARTICLES_PROPERTY_ORDER:
		if updates.has(property_name) and particles.get(property_name) != updates[property_name]:
			changed[property_name] = updates[property_name]
	if changed.is_empty():
		var unchanged := _particles_response(particles, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Update GPUParticles2D %s" % particles.name,
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	for property_name in GPU_PARTICLES_PROPERTY_ORDER:
		if not changed.has(property_name):
			continue
		var old_value = particles.get(property_name)
		var new_value = changed[property_name]
		_undo_redo.add_do_property(particles, property_name, new_value)
		if property_name in ["texture", "process_material"] and new_value != null:
			_undo_redo.add_do_reference(new_value)
		_undo_redo.add_undo_property(particles, property_name, old_value)
		if property_name in ["texture", "process_material"] and old_value != null:
			_undo_redo.add_undo_reference(old_value)
	_undo_redo.commit_action()
	var result := _particles_response(particles, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_gpu_particles_2d(params: Dictionary, require_writable: bool = true) -> Dictionary:
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


func _particles_response(particles: GPUParticles2D, scene_root: Node) -> Dictionary:
	var texture: Texture2D = particles.texture
	var process_material: Material = particles.process_material
	return {
		"path": ScenePath.from_node(particles, scene_root),
		"type": particles.get_class(),
		"configuration": {
			"emitting": particles.emitting,
			"amount": particles.amount,
			"amount_ratio": particles.amount_ratio,
			"sub_emitter_path": _serialize_sub_emitter(particles, scene_root),
			"texture_path": "" if texture == null else texture.resource_path,
			"texture_type": "" if texture == null else texture.get_class(),
			"process_material_path": "" if process_material == null else process_material.resource_path,
			"process_material_type": "" if process_material == null else process_material.get_class(),
			"lifetime": particles.lifetime,
			"interp_to_end": particles.interp_to_end,
			"one_shot": particles.one_shot,
			"preprocess": particles.preprocess,
			"speed_scale": particles.speed_scale,
			"explosiveness": particles.explosiveness,
			"randomness": particles.randomness,
			"use_fixed_seed": particles.use_fixed_seed,
			"seed": particles.seed,
			"fixed_fps": particles.fixed_fps,
			"interpolate": particles.interpolate,
			"fractional_delta": particles.fract_delta,
			"collision_base_size": particles.collision_base_size,
			"visibility_rect": VariantCodec.serialize(particles.visibility_rect),
			"local_coords": particles.local_coords,
			"draw_order": _draw_order_name(particles.draw_order),
			"trail_enabled": particles.trail_enabled,
			"trail_lifetime": particles.trail_lifetime,
			"trail_sections": particles.trail_sections,
			"trail_section_subdivisions": particles.trail_section_subdivisions,
		},
		"draw_orders": DRAW_ORDERS.keys(),
		"supported_properties": GPU_PARTICLES_PROPERTIES,
	}


func _parse_updates(params: Dictionary, particles: GPUParticles2D, scene_root: Node) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() \
		or raw_properties.size() > MAX_GPU_PARTICLES_PROPERTIES:
		return Errors.make(
			"INVALID_GPU_PARTICLES_PROPERTIES",
			"properties must be a non-empty object containing at most %d entries" % MAX_GPU_PARTICLES_PROPERTIES
		)
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String or not GPU_PARTICLES_PROPERTIES.has(raw_name):
			return Errors.make(
				"UNSUPPORTED_GPU_PARTICLES_PROPERTY",
				"Unsupported GPUParticles2D property: %s" % str(raw_name),
				false,
				"Call gpu_particles_2d_get to inspect supported_properties."
			)
		var parsed := _parse_property(raw_name, raw_properties[raw_name], particles, scene_root)
		if parsed.has("_error"):
			return parsed
		updates[parsed["property_name"]] = parsed["value"]
	return {"updates": updates}


func _parse_property(
	property_name: String,
	raw_value: Variant,
	particles: GPUParticles2D,
	scene_root: Node
) -> Dictionary:
	if property_name == "sub_emitter_path":
		return _parse_sub_emitter(raw_value, particles, scene_root)
	if property_name == "texture_path":
		return _load_resource(raw_value, "texture", "Texture2D")
	if property_name == "process_material_path":
		return _load_resource(raw_value, "process_material", "Material")
	if property_name == "draw_order":
		if not raw_value is String or not DRAW_ORDERS.has(raw_value.strip_edges().to_lower()):
			return Errors.make(
				"INVALID_GPU_PARTICLES_CONFIGURATION",
				"draw_order must be one of: %s" % ", ".join(DRAW_ORDERS.keys())
			)
		return {"property_name": "draw_order", "value": DRAW_ORDERS[raw_value.strip_edges().to_lower()]}
	if property_name == "visibility_rect":
		var decoded := VariantCodec.decode(raw_value, {"type": TYPE_RECT2}, Rect2())
		if decoded.has("_error") or not _is_finite_rect2(decoded.get("value", Rect2())):
			return Errors.make(
				"INVALID_GPU_PARTICLES_CONFIGURATION",
				"visibility_rect must contain finite position and size Vector2 values"
			)
		return {"property_name": "visibility_rect", "value": decoded["value"]}
	if property_name in ["emitting", "one_shot", "use_fixed_seed", "interpolate", "fractional_delta", "local_coords", "trail_enabled"]:
		if not raw_value is bool:
			return Errors.make(
				"INVALID_GPU_PARTICLES_CONFIGURATION", "%s must be a boolean" % property_name
			)
		return {"property_name": _property_name(property_name), "value": raw_value}
	if INTEGER_LIMITS.has(property_name):
		return _parse_integer(property_name, raw_value)
	return _parse_number(property_name, raw_value)


func _parse_sub_emitter(raw_value: Variant, particles: GPUParticles2D, scene_root: Node) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_SUB_EMITTER", "sub_emitter_path must be a scene node path string")
	var requested_path: String = raw_value.strip_edges()
	if requested_path.is_empty():
		return {"property_name": "sub_emitter", "value": NodePath("")}
	var target := ScenePath.resolve(requested_path, scene_root)
	if target == null:
		return Errors.make(
			"SUB_EMITTER_NOT_FOUND",
			"sub_emitter_path does not resolve to a node in the active scene: %s" % requested_path,
			false,
			"Use scene_get_hierarchy and pass a GPUParticles2D path from the current scene."
		)
	if not target is GPUParticles2D:
		return Errors.make(
			"GPU_PARTICLES_2D_REQUIRED",
			"sub_emitter_path targets %s instead of GPUParticles2D" % target.get_class(),
			false,
			"Create or target a different GPUParticles2D node."
		)
	if target == particles:
		return Errors.make(
			"INVALID_SUB_EMITTER", "A GPUParticles2D node cannot be its own sub emitter")
	return {"property_name": "sub_emitter", "value": particles.get_path_to(target)}


func _load_resource(raw_value: Variant, property_name: String, expected_type: String) -> Dictionary:
	if not raw_value is String:
		return Errors.make(
			"INVALID_GPU_PARTICLES_RESOURCE_PATH",
			"%s must be a res:// string or an empty string" % property_name
		)
	var resource_path: String = raw_value.strip_edges()
	if resource_path.is_empty():
		return {"property_name": property_name, "value": null}
	if not resource_path.begins_with("res://") or "/../" in resource_path or resource_path.ends_with("/.."):
		return Errors.make(
			"INVALID_GPU_PARTICLES_RESOURCE_PATH",
			"%s must remain inside the Godot project res:// directory" % property_name
		)
	if not ResourceLoader.exists(resource_path):
		return Errors.make("RESOURCE_NOT_FOUND", "%s does not exist: %s" % [property_name, resource_path])
	var resource := ResourceLoader.load(resource_path)
	if expected_type == "Texture2D" and not resource is Texture2D:
		return Errors.make("RESOURCE_TYPE_MISMATCH", "texture_path does not load a Texture2D resource")
	if expected_type == "Material" and not (
		resource is ParticleProcessMaterial or resource is ShaderMaterial
	):
		return Errors.make(
			"RESOURCE_TYPE_MISMATCH",
			"process_material_path must load a ParticleProcessMaterial or ShaderMaterial resource"
		)
	return {"property_name": property_name, "value": resource}


func _parse_integer(property_name: String, raw_value: Variant) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool or not is_finite(float(raw_value)) \
		or float(raw_value) != floorf(float(raw_value)):
		return Errors.make("INVALID_GPU_PARTICLES_CONFIGURATION", "%s must be an integer" % property_name)
	var value := int(raw_value)
	var limit: Dictionary = INTEGER_LIMITS[property_name]
	if value < int(limit["minimum"]) or value > int(limit["maximum"]):
		return Errors.make(
			"INVALID_GPU_PARTICLES_CONFIGURATION",
			"%s must be between %s and %s" % [property_name, limit["minimum"], limit["maximum"]]
		)
	return {"property_name": _property_name(property_name), "value": value}


func _parse_number(property_name: String, raw_value: Variant) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool or not is_finite(float(raw_value)):
		return Errors.make("INVALID_GPU_PARTICLES_CONFIGURATION", "%s must be a finite number" % property_name)
	var value := float(raw_value)
	var limit: Dictionary = NUMBER_LIMITS[property_name]
	if value < float(limit["minimum"]) or value > float(limit["maximum"]):
		return Errors.make(
			"INVALID_GPU_PARTICLES_CONFIGURATION",
			"%s must be between %s and %s" % [property_name, limit["minimum"], limit["maximum"]]
		)
	return {"property_name": _property_name(property_name), "value": value}


func _property_name(property_name: String) -> String:
	return {
		"fractional_delta": "fract_delta",
	}.get(property_name, property_name)


func _serialize_sub_emitter(particles: GPUParticles2D, scene_root: Node) -> String:
	if particles.sub_emitter.is_empty():
		return ""
	var target := particles.get_node_or_null(particles.sub_emitter)
	if target != null and (target == scene_root or scene_root.is_ancestor_of(target)):
		return ScenePath.from_node(target, scene_root)
	return str(particles.sub_emitter)


func _draw_order_name(value: int) -> String:
	for name in DRAW_ORDERS:
		if DRAW_ORDERS[name] == value:
			return name
	return "index"


func _is_finite_rect2(value: Rect2) -> bool:
	return is_finite(value.position.x) and is_finite(value.position.y) \
		and is_finite(value.size.x) and is_finite(value.size.y)

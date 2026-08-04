@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_SHAPE_PROPERTIES := 16
const MAX_LAYER_COUNT := 32
const MAX_POLYGON_POINTS := 512
const MAX_PHYSICS_PROPERTIES := 32
const PROTECTED_SHAPE_PROPERTIES := {
	"resource_path": true,
	"resource_name": true,
	"script": true,
}
const SHAPES_BY_NAME := {
	"circle": {"class": "CircleShape2D", "required": ["radius"]},
	"rectangle": {"class": "RectangleShape2D", "required": ["size"]},
	"capsule": {"class": "CapsuleShape2D", "required": ["radius", "height"]},
	"segment": {"class": "SegmentShape2D", "required": ["a", "b"]},
	"separation_ray": {"class": "SeparationRayShape2D", "required": ["length"]},
	"world_boundary": {"class": "WorldBoundaryShape2D", "required": ["normal", "distance"]},
	"convex_polygon": {"class": "ConvexPolygonShape2D", "required": ["points"]},
	"concave_polygon": {"class": "ConcavePolygonShape2D", "required": ["segments"]},
}
const AREA_CONFIGURATION_PROPERTIES := [
	"monitoring", "monitorable", "priority", "gravity_space_override", "gravity_point",
	"gravity_point_unit_distance", "gravity_point_center", "gravity_direction", "gravity",
	"linear_damp_space_override", "linear_damp", "angular_damp_space_override", "angular_damp",
]
const STATIC_BODY_CONFIGURATION_PROPERTIES := [
	"constant_linear_velocity", "constant_angular_velocity",
]
const ANIMATABLE_BODY_CONFIGURATION_PROPERTIES := [
	"constant_linear_velocity", "constant_angular_velocity", "sync_to_physics",
]
const CHARACTER_BODY_CONFIGURATION_PROPERTIES := [
	"motion_mode", "up_direction", "velocity", "slide_on_ceiling", "max_slides",
	"wall_min_slide_angle", "floor_stop_on_slope", "floor_constant_speed", "floor_block_on_wall",
	"floor_max_angle", "floor_snap_length", "platform_on_leave", "platform_floor_layers",
	"platform_wall_layers", "safe_margin",
]
const RIGID_BODY_CONFIGURATION_PROPERTIES := [
	"mass", "gravity_scale", "center_of_mass_mode", "center_of_mass", "inertia", "sleeping",
	"can_sleep", "lock_rotation", "freeze", "freeze_mode", "custom_integrator", "continuous_cd",
	"contact_monitor", "max_contacts_reported", "linear_velocity", "linear_damp_mode",
	"linear_damp", "angular_velocity", "angular_damp_mode", "angular_damp", "constant_force",
	"constant_torque",
]
const PIN_JOINT_CONFIGURATION_PROPERTIES := [
	"bias", "disable_collision", "softness", "angular_limit_enabled", "angular_limit_lower",
	"angular_limit_upper", "motor_enabled", "motor_target_velocity",
]
const GROOVE_JOINT_CONFIGURATION_PROPERTIES := ["bias", "disable_collision", "length", "initial_offset"]
const DAMPED_SPRING_JOINT_CONFIGURATION_PROPERTIES := [
	"bias", "disable_collision", "length", "rest_length", "stiffness", "damping",
]
const RAY_CAST_CONFIGURATION_PROPERTIES := [
	"enabled", "exclude_parent", "target_position", "hit_from_inside", "collide_with_areas",
	"collide_with_bodies",
]
const SHAPE_CAST_CONFIGURATION_PROPERTIES := [
	"enabled", "exclude_parent", "target_position", "margin", "max_results", "collide_with_areas",
	"collide_with_bodies",
]
const ENUM_OPTIONS_BY_PROPERTY := {
	"gravity_space_override": {
		"disabled": 0, "combine": 1, "combine_replace": 2, "replace": 3, "replace_combine": 4,
	},
	"linear_damp_space_override": {
		"disabled": 0, "combine": 1, "combine_replace": 2, "replace": 3, "replace_combine": 4,
	},
	"angular_damp_space_override": {
		"disabled": 0, "combine": 1, "combine_replace": 2, "replace": 3, "replace_combine": 4,
	},
	"motion_mode": {"grounded": 0, "floating": 1},
	"platform_on_leave": {
		"add_velocity": 0, "add_upward_velocity": 1, "do_nothing": 2,
	},
	"center_of_mass_mode": {"auto": 0, "custom": 1},
	"freeze_mode": {"static": 0, "kinematic": 1},
	"continuous_cd": {"disabled": 0, "cast_ray": 1, "cast_shape": 2},
	"linear_damp_mode": {"combine": 0, "replace": 1},
	"angular_damp_mode": {"combine": 0, "replace": 1},
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_collision_shape(params: Dictionary) -> Dictionary:
	var resolved := _resolve_collision_shape(params, false)
	if resolved.has("_error"):
		return resolved
	var collision_shape: CollisionShape2D = resolved["collision_shape"]
	var scene_root: Node = resolved["scene_root"]
	return {
		"path": ScenePath.from_node(collision_shape, scene_root),
		"type": collision_shape.get_class(),
		"shape": _serialize_shape(collision_shape.shape),
		"disabled": collision_shape.disabled,
		"one_way_collision": collision_shape.one_way_collision,
		"one_way_collision_margin": collision_shape.one_way_collision_margin,
	}


func set_collision_shape(params: Dictionary) -> Dictionary:
	var resolved := _resolve_collision_shape(params)
	if resolved.has("_error"):
		return resolved
	var shape_result := _build_shape(params, resolved["collision_shape"].shape)
	if shape_result.has("_error"):
		return shape_result
	var collision_shape: CollisionShape2D = resolved["collision_shape"]
	var scene_root: Node = resolved["scene_root"]
	var old_shape: Shape2D = collision_shape.shape
	var replacement: Shape2D = shape_result["shape"]
	_undo_redo.create_action(
		"Godot 2D MCP: Set %s on %s" % [replacement.get_class(), collision_shape.name],
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	_undo_redo.add_do_property(collision_shape, "shape", replacement)
	_undo_redo.add_do_reference(replacement)
	_undo_redo.add_undo_property(collision_shape, "shape", old_shape)
	if old_shape != null:
		_undo_redo.add_undo_reference(old_shape)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(collision_shape, scene_root),
		"replaced": old_shape != null,
		"shape": _serialize_shape(replacement),
		"undoable": true,
		"_scene_mutated": true,
	}


func clear_collision_shape(params: Dictionary) -> Dictionary:
	var resolved := _resolve_collision_shape(params)
	if resolved.has("_error"):
		return resolved
	var collision_shape: CollisionShape2D = resolved["collision_shape"]
	var scene_root: Node = resolved["scene_root"]
	var old_shape: Shape2D = collision_shape.shape
	if old_shape == null:
		return Errors.make(
			"COLLISION_SHAPE_NOT_ASSIGNED",
			"CollisionShape2D '%s' has no Shape2D resource" % collision_shape.name,
			false,
			"Call collision_shape_get before clearing a shape."
		)
	_undo_redo.create_action(
		"Godot 2D MCP: Clear shape on %s" % collision_shape.name,
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	_undo_redo.add_do_property(collision_shape, "shape", null)
	_undo_redo.add_undo_property(collision_shape, "shape", old_shape)
	_undo_redo.add_undo_reference(old_shape)
	_undo_redo.commit_action()
	return {
		"path": ScenePath.from_node(collision_shape, scene_root),
		"cleared": true,
		"undoable": true,
		"_scene_mutated": true,
	}


func get_collision_layers(params: Dictionary) -> Dictionary:
	var resolved := _resolve_collision_object(params, false)
	if resolved.has("_error"):
		return resolved
	var collision_object: CollisionObject2D = resolved["collision_object"]
	var scene_root: Node = resolved["scene_root"]
	return _serialize_collision_layers(collision_object, scene_root)


func set_collision_layers(params: Dictionary) -> Dictionary:
	var resolved := _resolve_collision_object(params)
	if resolved.has("_error"):
		return resolved
	var update_result := _parse_layer_update(params)
	if update_result.has("_error"):
		return update_result
	var collision_object: CollisionObject2D = resolved["collision_object"]
	var scene_root: Node = resolved["scene_root"]
	var old_layer := int(collision_object.collision_layer)
	var old_mask := int(collision_object.collision_mask)
	var new_layer := int(update_result.get("layer", old_layer))
	var new_mask := int(update_result.get("mask", old_mask))
	if old_layer == new_layer and old_mask == new_mask:
		var unchanged := _serialize_collision_layers(collision_object, scene_root)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Update collision layers for %s" % collision_object.name,
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	if old_layer != new_layer:
		_undo_redo.add_do_property(collision_object, "collision_layer", new_layer)
		_undo_redo.add_undo_property(collision_object, "collision_layer", old_layer)
	if old_mask != new_mask:
		_undo_redo.add_do_property(collision_object, "collision_mask", new_mask)
		_undo_redo.add_undo_property(collision_object, "collision_mask", old_mask)
	_undo_redo.commit_action()
	var result := _serialize_collision_layers(collision_object, scene_root)
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func get_area(params: Dictionary) -> Dictionary:
	var resolved := _resolve_area(params, false)
	if resolved.has("_error"):
		return resolved
	var area: Area2D = resolved["area"]
	return _configuration_response(area, resolved["scene_root"], AREA_CONFIGURATION_PROPERTIES)


func set_area(params: Dictionary) -> Dictionary:
	var resolved := _resolve_area(params)
	if resolved.has("_error"):
		return resolved
	var area: Area2D = resolved["area"]
	var parsed := _parse_configuration(params, area, AREA_CONFIGURATION_PROPERTIES, true)
	if parsed.has("_error"):
		return parsed
	var validity := _validate_area_configuration(area, parsed["updates"])
	if validity.has("_error"):
		return validity
	return _commit_configuration(
		area,
		resolved["scene_root"],
		AREA_CONFIGURATION_PROPERTIES,
		parsed["updates"],
		"Update Area2D configuration"
	)


func get_physics_body(params: Dictionary) -> Dictionary:
	var resolved := _resolve_physics_body(params, false)
	if resolved.has("_error"):
		return resolved
	var body: PhysicsBody2D = resolved["physics_body"]
	var configuration_properties := _body_configuration_properties(body)
	if configuration_properties.is_empty():
		return _unsupported_physics_body(body)
	var response := _configuration_response(body, resolved["scene_root"], configuration_properties)
	response["body_kind"] = body.get_class()
	return response


func set_physics_body(params: Dictionary) -> Dictionary:
	var resolved := _resolve_physics_body(params)
	if resolved.has("_error"):
		return resolved
	var body: PhysicsBody2D = resolved["physics_body"]
	var configuration_properties := _body_configuration_properties(body)
	if configuration_properties.is_empty():
		return _unsupported_physics_body(body)
	var parsed := _parse_configuration(params, body, configuration_properties, true)
	if parsed.has("_error"):
		return parsed
	var validity := _validate_body_configuration(body, parsed["updates"])
	if validity.has("_error"):
		return validity
	var result := _commit_configuration(
		body,
		resolved["scene_root"],
		configuration_properties,
		parsed["updates"],
		"Update %s configuration" % body.get_class()
	)
	if not result.has("_error"):
		result["body_kind"] = body.get_class()
	return result


func get_joint(params: Dictionary) -> Dictionary:
	var resolved := _resolve_joint(params, false)
	if resolved.has("_error"):
		return resolved
	var joint: Joint2D = resolved["joint"]
	var configuration_properties := _joint_configuration_properties(joint)
	if configuration_properties.is_empty():
		return _unsupported_joint(joint)
	return _joint_response(joint, resolved["scene_root"], configuration_properties)


func set_joint(params: Dictionary) -> Dictionary:
	var resolved := _resolve_joint(params)
	if resolved.has("_error"):
		return resolved
	var joint: Joint2D = resolved["joint"]
	var scene_root: Node = resolved["scene_root"]
	var configuration_properties := _joint_configuration_properties(joint)
	if configuration_properties.is_empty():
		return _unsupported_joint(joint)
	var parsed := _parse_configuration(params, joint, configuration_properties, false)
	if parsed.has("_error"):
		return parsed
	var endpoints := _parse_joint_endpoints(params, joint, scene_root)
	if endpoints.has("_error"):
		return endpoints
	if parsed["updates"].is_empty() and endpoints["updates"].is_empty():
		return Errors.make("MISSING_PARAMETER", "properties, node_a_path, or node_b_path must be supplied")
	var validity := _validate_joint_configuration(joint, parsed["updates"])
	if validity.has("_error"):
		return validity
	var endpoint_validity := _validate_joint_endpoints(joint, endpoints["updates"])
	if endpoint_validity.has("_error"):
		return endpoint_validity
	var updates: Dictionary = parsed["updates"].duplicate()
	updates.merge(endpoints["updates"])
	var result := _commit_configuration(
		joint,
		scene_root,
		configuration_properties,
		updates,
		"Update %s configuration" % joint.get_class()
	)
	if result.has("_error"):
		return result
	return _joint_response_with_mutation(result, joint, scene_root, configuration_properties)


func get_ray_cast(params: Dictionary) -> Dictionary:
	var resolved := _resolve_ray_cast(params, false)
	if resolved.has("_error"):
		return resolved
	return _cast_response(
		resolved["ray_cast"], resolved["scene_root"], RAY_CAST_CONFIGURATION_PROPERTIES
	)


func set_ray_cast(params: Dictionary) -> Dictionary:
	var resolved := _resolve_ray_cast(params)
	if resolved.has("_error"):
		return resolved
	var ray_cast: RayCast2D = resolved["ray_cast"]
	var parsed := _parse_configuration(params, ray_cast, RAY_CAST_CONFIGURATION_PROPERTIES, false)
	if parsed.has("_error"):
		return parsed
	var mask_update := _parse_cast_mask_update(params)
	if mask_update.has("_error"):
		return mask_update
	var updates: Dictionary = parsed["updates"].duplicate()
	updates.merge(mask_update["updates"])
	if updates.is_empty():
		return Errors.make("MISSING_PARAMETER", "properties or masks must be supplied")
	var result := _commit_configuration(
		ray_cast,
		resolved["scene_root"],
		RAY_CAST_CONFIGURATION_PROPERTIES,
		updates,
		"Update RayCast2D configuration"
	)
	if result.has("_error"):
		return result
	return _cast_response_with_mutation(
		result, ray_cast, resolved["scene_root"], RAY_CAST_CONFIGURATION_PROPERTIES
	)


func get_shape_cast(params: Dictionary) -> Dictionary:
	var resolved := _resolve_shape_cast(params, false)
	if resolved.has("_error"):
		return resolved
	return _shape_cast_response(resolved["shape_cast"], resolved["scene_root"])


func set_shape_cast(params: Dictionary) -> Dictionary:
	var resolved := _resolve_shape_cast(params)
	if resolved.has("_error"):
		return resolved
	var shape_cast: ShapeCast2D = resolved["shape_cast"]
	var scene_root: Node = resolved["scene_root"]
	var parsed := _parse_configuration(params, shape_cast, SHAPE_CAST_CONFIGURATION_PROPERTIES, false)
	if parsed.has("_error"):
		return parsed
	var mask_update := _parse_cast_mask_update(params)
	if mask_update.has("_error"):
		return mask_update
	var shape_update := _parse_shape_cast_shape(params, shape_cast.shape)
	if shape_update.has("_error"):
		return shape_update
	var updates: Dictionary = parsed["updates"].duplicate()
	updates.merge(mask_update["updates"])
	if updates.is_empty() and not shape_update["requested"]:
		return Errors.make("MISSING_PARAMETER", "properties, masks, or shape_type must be supplied")
	var validity := _validate_shape_cast_configuration(shape_cast, updates)
	if validity.has("_error"):
		return validity
	return _commit_shape_cast_configuration(shape_cast, scene_root, updates, shape_update)


func clear_shape_cast_shape(params: Dictionary) -> Dictionary:
	var resolved := _resolve_shape_cast(params)
	if resolved.has("_error"):
		return resolved
	var shape_cast: ShapeCast2D = resolved["shape_cast"]
	var scene_root: Node = resolved["scene_root"]
	var old_shape: Shape2D = shape_cast.shape
	if old_shape == null:
		return Errors.make(
			"SHAPE_CAST_SHAPE_NOT_ASSIGNED",
			"ShapeCast2D '%s' has no Shape2D resource" % shape_cast.name,
			false,
			"Call shape_cast_2d_get before clearing a shape."
		)
	_undo_redo.create_action(
		"Godot 2D MCP: Clear shape on %s" % shape_cast.name,
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	_undo_redo.add_do_property(shape_cast, "shape", null)
	_undo_redo.add_undo_property(shape_cast, "shape", old_shape)
	_undo_redo.add_undo_reference(old_shape)
	_undo_redo.commit_action()
	var result := _shape_cast_response(shape_cast, scene_root)
	result["cleared"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_area(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is Area2D:
		return Errors.make(
			"AREA_2D_REQUIRED",
			"Node '%s' is %s, not Area2D" % [resolved["node"].name, resolved["node"].get_class()],
			false,
			"Target an Area2D node."
		)
	resolved["area"] = resolved["node"] as Area2D
	return resolved


func _resolve_physics_body(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is PhysicsBody2D:
		return Errors.make(
			"PHYSICS_BODY_2D_REQUIRED",
			"Node '%s' is %s, not PhysicsBody2D" % [resolved["node"].name, resolved["node"].get_class()],
			false,
			"Target a StaticBody2D, AnimatableBody2D, CharacterBody2D, or RigidBody2D node."
		)
	resolved["physics_body"] = resolved["node"] as PhysicsBody2D
	return resolved


func _resolve_joint(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is Joint2D:
		return Errors.make(
			"JOINT_2D_REQUIRED",
			"Node '%s' is %s, not Joint2D" % [resolved["node"].name, resolved["node"].get_class()],
			false,
			"Target a PinJoint2D, GrooveJoint2D, or DampedSpringJoint2D node."
		)
	resolved["joint"] = resolved["node"] as Joint2D
	return resolved


func _resolve_ray_cast(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is RayCast2D:
		return Errors.make(
			"RAY_CAST_2D_REQUIRED",
			"Node '%s' is %s, not RayCast2D" % [resolved["node"].name, resolved["node"].get_class()],
			false,
			"Target a RayCast2D node."
		)
	resolved["ray_cast"] = resolved["node"] as RayCast2D
	return resolved


func _resolve_shape_cast(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is ShapeCast2D:
		return Errors.make(
			"SHAPE_CAST_2D_REQUIRED",
			"Node '%s' is %s, not ShapeCast2D" % [resolved["node"].name, resolved["node"].get_class()],
			false,
			"Target a ShapeCast2D node."
		)
	resolved["shape_cast"] = resolved["node"] as ShapeCast2D
	return resolved


func _resolve_collision_shape(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is CollisionShape2D:
		return Errors.make(
			"COLLISION_SHAPE_REQUIRED",
			"Node '%s' is %s, not CollisionShape2D" % [
				resolved["node"].name, resolved["node"].get_class()
			],
			false,
			"Target a CollisionShape2D node."
		)
	resolved["collision_shape"] = resolved["node"] as CollisionShape2D
	return resolved


func _resolve_collision_object(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is CollisionObject2D:
		return Errors.make(
			"COLLISION_OBJECT_REQUIRED",
			"Node '%s' is %s, not CollisionObject2D" % [
				resolved["node"].name, resolved["node"].get_class()
			],
			false,
			"Target an Area2D, PhysicsBody2D, or other CollisionObject2D node."
		)
	resolved["collision_object"] = resolved["node"] as CollisionObject2D
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


func _configuration_response(node: Node, scene_root: Node, allowed_properties: Array) -> Dictionary:
	return {
		"path": ScenePath.from_node(node, scene_root),
		"type": node.get_class(),
		"configuration": _serialize_configuration(node, allowed_properties),
		"supported_properties": allowed_properties.duplicate(),
	}


func _serialize_configuration(node: Node, allowed_properties: Array) -> Dictionary:
	var configuration := {}
	for property_name_value in allowed_properties:
		var property_name := str(property_name_value)
		configuration[property_name] = _serialize_configuration_value(property_name, node.get(property_name))
	return configuration


func _serialize_configuration_value(property_name: String, value: Variant) -> Variant:
	if ENUM_OPTIONS_BY_PROPERTY.has(property_name):
		var options: Dictionary = ENUM_OPTIONS_BY_PROPERTY[property_name]
		for label in options:
			if int(options[label]) == int(value):
				return label
	if property_name in ["platform_floor_layers", "platform_wall_layers"]:
		return _mask_to_layer_numbers(int(value))
	return VariantCodec.serialize(value)


func _parse_configuration(
	params: Dictionary,
	node: Node,
	allowed_properties: Array,
	require_properties: bool
) -> Dictionary:
	var raw_properties := params.get("properties", null)
	if raw_properties == null:
		if require_properties:
			return Errors.make("MISSING_PARAMETER", "properties must be supplied")
		return {"updates": {}}
	if not raw_properties is Dictionary or raw_properties.size() > MAX_PHYSICS_PROPERTIES:
		return Errors.make(
			"INVALID_PHYSICS_PROPERTIES",
			"properties must be an object containing at most %d entries" % MAX_PHYSICS_PROPERTIES
		)
	if require_properties and raw_properties.is_empty():
		return Errors.make("INVALID_PHYSICS_PROPERTIES", "properties must be a non-empty object")
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String:
			return Errors.make("INVALID_PHYSICS_PROPERTIES", "property names must be strings")
		var property_name: String = raw_name
		if not allowed_properties.has(property_name):
			return Errors.make(
				"UNSUPPORTED_PHYSICS_PROPERTY",
				"Property '%s' is not supported for %s" % [property_name, node.get_class()],
				false,
				"Call the corresponding *_get tool to inspect supported_properties."
			)
		var property_info := _find_property_info(node, property_name)
		if property_info.is_empty() or not _is_writable_public_property(
			int(property_info.get("usage", PROPERTY_USAGE_NONE))
		):
			return Errors.make("PHYSICS_PROPERTY_NOT_WRITABLE", "Property '%s' is not writable" % property_name)
		var decoded := _decode_configuration_value(
			property_name, raw_properties[raw_name], property_info, node.get(property_name)
		)
		if decoded.has("_error"):
			return decoded
		updates[property_name] = decoded["value"]
	return {"updates": updates}


func _decode_configuration_value(
	property_name: String,
	raw_value: Variant,
	property_info: Dictionary,
	current_value: Variant
) -> Dictionary:
	if ENUM_OPTIONS_BY_PROPERTY.has(property_name) and raw_value is String:
		var label: String = raw_value.to_lower().strip_edges()
		var options: Dictionary = ENUM_OPTIONS_BY_PROPERTY[property_name]
		if not options.has(label):
			return Errors.make(
				"INVALID_PHYSICS_ENUM",
				"%s must use one of: %s" % [property_name, ", ".join(options.keys())]
			)
		return {"value": options[label]}
	if property_name in ["platform_floor_layers", "platform_wall_layers"]:
		var layers := _parse_layer_numbers(raw_value, property_name)
		if layers.has("_error"):
			return layers
		return {"value": layers["mask"]}
	var decoded := VariantCodec.decode(raw_value, property_info, current_value)
	if decoded.has("_error"):
		return Errors.make(
			"PHYSICS_PROPERTY_TYPE_MISMATCH",
			decoded["_error"]["message"],
			false,
			"Use the JSON values reported by the corresponding *_get tool.",
			{"property": property_name}
		)
	if ENUM_OPTIONS_BY_PROPERTY.has(property_name) and not _enum_contains_value(
		ENUM_OPTIONS_BY_PROPERTY[property_name], decoded["value"]
	):
		return Errors.make("INVALID_PHYSICS_ENUM", "%s uses an unsupported enum value" % property_name)
	return decoded


func _find_property_info(node: Node, property_name: String) -> Dictionary:
	for property_info_value in node.get_property_list():
		var property_info: Dictionary = property_info_value
		if str(property_info.get("name", "")) == property_name:
			return property_info
	return {}


func _enum_contains_value(options: Dictionary, value: Variant) -> bool:
	for label in options:
		if int(options[label]) == int(value):
			return true
	return false


func _commit_configuration(
	node: Node,
	scene_root: Node,
	allowed_properties: Array,
	updates: Dictionary,
	action_name: String
) -> Dictionary:
	var changed := {}
	for property_name_value in updates:
		var property_name := str(property_name_value)
		if node.get(property_name) != updates[property_name_value]:
			changed[property_name] = updates[property_name_value]
	if changed.is_empty():
		var unchanged := _configuration_response(node, scene_root, allowed_properties)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(action_name, UndoRedo.MERGE_DISABLE, scene_root, true)
	for property_name_value in changed:
		var property_name := str(property_name_value)
		_undo_redo.add_do_property(node, property_name, changed[property_name])
		_undo_redo.add_undo_property(node, property_name, node.get(property_name))
	_undo_redo.commit_action()
	var result := _configuration_response(node, scene_root, allowed_properties)
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _parse_cast_mask_update(params: Dictionary) -> Dictionary:
	if not params.has("masks") or params["masks"] == null:
		return {"updates": {}}
	var mask_result := _parse_layer_numbers(params["masks"], "masks")
	if mask_result.has("_error"):
		return mask_result
	return {"updates": {"collision_mask": mask_result["mask"]}}


func _cast_response(cast_node: Node, scene_root: Node, configuration_properties: Array) -> Dictionary:
	var response := _configuration_response(cast_node, scene_root, configuration_properties)
	var mask := int(cast_node.get("collision_mask"))
	response["collision_mask"] = mask
	response["masks"] = _mask_to_layer_numbers(mask)
	return response


func _cast_response_with_mutation(
	mutation: Dictionary,
	cast_node: Node,
	scene_root: Node,
	configuration_properties: Array
) -> Dictionary:
	var response := _cast_response(cast_node, scene_root, configuration_properties)
	for key in ["changed", "undoable", "_scene_mutated"]:
		if mutation.has(key):
			response[key] = mutation[key]
	return response


func _shape_cast_response(shape_cast: ShapeCast2D, scene_root: Node) -> Dictionary:
	var response := _cast_response(shape_cast, scene_root, SHAPE_CAST_CONFIGURATION_PROPERTIES)
	response["shape"] = _serialize_shape(shape_cast.shape)
	return response


func _parse_shape_cast_shape(params: Dictionary, existing: Shape2D) -> Dictionary:
	if not params.has("shape_type") or params["shape_type"] == null:
		return {"requested": false, "shape": null}
	var shape_params := {
		"shape_type": params["shape_type"],
		"properties": params.get("shape_properties", null),
	}
	var built := _build_shape(shape_params, existing)
	if built.has("_error"):
		return built
	return {"requested": true, "shape": built["shape"]}


func _validate_shape_cast_configuration(shape_cast: ShapeCast2D, updates: Dictionary) -> Dictionary:
	if float(_configuration_value(shape_cast, updates, "margin")) < 0.0:
		return _invalid_physics_configuration("margin must be greater than or equal to zero")
	if int(_configuration_value(shape_cast, updates, "max_results")) < 1:
		return _invalid_physics_configuration("max_results must be at least one")
	return {}


func _commit_shape_cast_configuration(
	shape_cast: ShapeCast2D,
	scene_root: Node,
	updates: Dictionary,
	shape_update: Dictionary
) -> Dictionary:
	var changed := {}
	for property_name_value in updates:
		var property_name := str(property_name_value)
		if shape_cast.get(property_name) != updates[property_name_value]:
			changed[property_name] = updates[property_name_value]
	var new_shape: Shape2D = shape_update["shape"]
	var old_shape: Shape2D = shape_cast.shape
	var replacing_shape: bool = bool(shape_update["requested"])
	if changed.is_empty() and not replacing_shape:
		var unchanged := _shape_cast_response(shape_cast, scene_root)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Update ShapeCast2D configuration",
		UndoRedo.MERGE_DISABLE,
		scene_root,
		true
	)
	for property_name_value in changed:
		var property_name := str(property_name_value)
		_undo_redo.add_do_property(shape_cast, property_name, changed[property_name])
		_undo_redo.add_undo_property(shape_cast, property_name, shape_cast.get(property_name))
	if replacing_shape:
		_undo_redo.add_do_property(shape_cast, "shape", new_shape)
		_undo_redo.add_do_reference(new_shape)
		_undo_redo.add_undo_property(shape_cast, "shape", old_shape)
		if old_shape != null:
			_undo_redo.add_undo_reference(old_shape)
	_undo_redo.commit_action()
	var result := _shape_cast_response(shape_cast, scene_root)
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _body_configuration_properties(body: PhysicsBody2D) -> Array:
	if body is RigidBody2D:
		return RIGID_BODY_CONFIGURATION_PROPERTIES
	if body is CharacterBody2D:
		return CHARACTER_BODY_CONFIGURATION_PROPERTIES
	if body is AnimatableBody2D:
		return ANIMATABLE_BODY_CONFIGURATION_PROPERTIES
	if body is StaticBody2D:
		return STATIC_BODY_CONFIGURATION_PROPERTIES
	return []


func _joint_configuration_properties(joint: Joint2D) -> Array:
	if joint is PinJoint2D:
		return PIN_JOINT_CONFIGURATION_PROPERTIES
	if joint is GrooveJoint2D:
		return GROOVE_JOINT_CONFIGURATION_PROPERTIES
	if joint is DampedSpringJoint2D:
		return DAMPED_SPRING_JOINT_CONFIGURATION_PROPERTIES
	return []


func _unsupported_physics_body(body: PhysicsBody2D) -> Dictionary:
	return Errors.make(
		"UNSUPPORTED_PHYSICS_BODY_2D",
		"PhysicsBody2D type '%s' is not yet supported" % body.get_class(),
		false,
		"Use node_get_properties for generic inspection or choose a supported 2D body type."
	)


func _unsupported_joint(joint: Joint2D) -> Dictionary:
	return Errors.make(
		"UNSUPPORTED_JOINT_2D",
		"Joint2D type '%s' is not yet supported" % joint.get_class(),
		false,
		"Use PinJoint2D, GrooveJoint2D, or DampedSpringJoint2D."
	)


func _validate_area_configuration(area: Area2D, updates: Dictionary) -> Dictionary:
	if float(_configuration_value(area, updates, "gravity_point_unit_distance")) < 0.0:
		return _invalid_physics_configuration("gravity_point_unit_distance must be greater than or equal to zero")
	if float(_configuration_value(area, updates, "linear_damp")) < 0.0:
		return _invalid_physics_configuration("linear_damp must be greater than or equal to zero")
	if float(_configuration_value(area, updates, "angular_damp")) < 0.0:
		return _invalid_physics_configuration("angular_damp must be greater than or equal to zero")
	return {}


func _validate_body_configuration(body: PhysicsBody2D, updates: Dictionary) -> Dictionary:
	if body is CharacterBody2D:
		var motion_mode := int(_configuration_value(body, updates, "motion_mode"))
		var up_direction: Vector2 = _configuration_value(body, updates, "up_direction")
		if motion_mode == 0 and up_direction.length_squared() <= 0.0:
			return _invalid_physics_configuration("grounded CharacterBody2D requires a non-zero up_direction")
		if int(_configuration_value(body, updates, "max_slides")) < 1:
			return _invalid_physics_configuration("max_slides must be at least one")
		if float(_configuration_value(body, updates, "wall_min_slide_angle")) < 0.0:
			return _invalid_physics_configuration("wall_min_slide_angle must be greater than or equal to zero")
		var floor_max_angle := float(_configuration_value(body, updates, "floor_max_angle"))
		if floor_max_angle < 0.0 or floor_max_angle > PI:
			return _invalid_physics_configuration("floor_max_angle must be between zero and PI radians")
		if float(_configuration_value(body, updates, "floor_snap_length")) < 0.0:
			return _invalid_physics_configuration("floor_snap_length must be greater than or equal to zero")
		if float(_configuration_value(body, updates, "safe_margin")) < 0.001:
			return _invalid_physics_configuration("safe_margin must be at least 0.001")
	if body is RigidBody2D:
		if float(_configuration_value(body, updates, "mass")) <= 0.0:
			return _invalid_physics_configuration("mass must be greater than zero")
		if float(_configuration_value(body, updates, "inertia")) < 0.0:
			return _invalid_physics_configuration("inertia must be greater than or equal to zero")
		if int(_configuration_value(body, updates, "max_contacts_reported")) < 0:
			return _invalid_physics_configuration("max_contacts_reported must be greater than or equal to zero")
		if float(_configuration_value(body, updates, "linear_damp")) < -1.0:
			return _invalid_physics_configuration("linear_damp must be greater than or equal to -1")
		if float(_configuration_value(body, updates, "angular_damp")) < -1.0:
			return _invalid_physics_configuration("angular_damp must be greater than or equal to -1")
	return {}


func _validate_joint_configuration(joint: Joint2D, updates: Dictionary) -> Dictionary:
	var bias := float(_configuration_value(joint, updates, "bias"))
	if bias < 0.0 or bias > 0.9:
		return _invalid_physics_configuration("bias must be between zero and 0.9")
	if joint is PinJoint2D:
		if float(_configuration_value(joint, updates, "softness")) < 0.0:
			return _invalid_physics_configuration("softness must be greater than or equal to zero")
		if bool(_configuration_value(joint, updates, "angular_limit_enabled")):
			var lower := float(_configuration_value(joint, updates, "angular_limit_lower"))
			var upper := float(_configuration_value(joint, updates, "angular_limit_upper"))
			if lower > upper:
				return _invalid_physics_configuration("angular_limit_lower cannot exceed angular_limit_upper")
	if joint is GrooveJoint2D:
		if float(_configuration_value(joint, updates, "length")) < 1.0:
			return _invalid_physics_configuration("length must be at least one pixel")
		if float(_configuration_value(joint, updates, "initial_offset")) < 1.0:
			return _invalid_physics_configuration("initial_offset must be at least one pixel")
	if joint is DampedSpringJoint2D:
		if float(_configuration_value(joint, updates, "length")) < 1.0:
			return _invalid_physics_configuration("length must be at least one pixel")
		if float(_configuration_value(joint, updates, "rest_length")) < 0.0:
			return _invalid_physics_configuration("rest_length must be greater than or equal to zero")
		if float(_configuration_value(joint, updates, "stiffness")) <= 0.0:
			return _invalid_physics_configuration("stiffness must be greater than zero")
		if float(_configuration_value(joint, updates, "damping")) <= 0.0:
			return _invalid_physics_configuration("damping must be greater than zero")
	return {}


func _configuration_value(node: Node, updates: Dictionary, property_name: String) -> Variant:
	return updates.get(property_name, node.get(property_name))


func _invalid_physics_configuration(message: String) -> Dictionary:
	return Errors.make("INVALID_PHYSICS_CONFIGURATION", message)


func _parse_joint_endpoints(params: Dictionary, joint: Joint2D, scene_root: Node) -> Dictionary:
	var updates := {}
	for endpoint in ["a", "b"]:
		var parameter_name := "node_%s_path" % endpoint
		if not params.has(parameter_name) or params[parameter_name] == null:
			continue
		if not params[parameter_name] is String:
			return Errors.make("INVALID_JOINT_ENDPOINT", "%s must be a node path string" % parameter_name)
		var requested_path: String = params[parameter_name].strip_edges()
		var property_name := "node_%s" % endpoint
		if requested_path.is_empty():
			updates[property_name] = NodePath("")
			continue
		var target := ScenePath.resolve(requested_path, scene_root)
		if target == null:
			return Errors.make(
				"JOINT_ENDPOINT_NOT_FOUND",
				"%s does not resolve to a node in the active scene: %s" % [parameter_name, requested_path],
				false,
				"Use scene_get_hierarchy and pass the returned stable node path."
			)
		if not target is PhysicsBody2D:
			return Errors.make(
				"JOINT_ENDPOINT_BODY_REQUIRED",
				"%s targets %s instead of PhysicsBody2D" % [parameter_name, target.get_class()],
				false,
				"Target a StaticBody2D, AnimatableBody2D, CharacterBody2D, or RigidBody2D node."
			)
		updates[property_name] = joint.get_path_to(target)
	return {"updates": updates}


func _validate_joint_endpoints(joint: Joint2D, updates: Dictionary) -> Dictionary:
	var node_a: Node = _joint_endpoint_target(joint, updates.get("node_a", joint.node_a))
	var node_b: Node = _joint_endpoint_target(joint, updates.get("node_b", joint.node_b))
	if node_a != null and node_b != null and node_a == node_b:
		return Errors.make(
			"INVALID_JOINT_ENDPOINTS",
			"node_a_path and node_b_path cannot reference the same PhysicsBody2D",
			false,
			"Use two distinct bodies or leave one endpoint empty to attach to the world."
		)
	return {}


func _joint_endpoint_target(joint: Joint2D, node_path: NodePath) -> Node:
	if node_path.is_empty():
		return null
	return joint.get_node_or_null(node_path)


func _joint_response(joint: Joint2D, scene_root: Node, configuration_properties: Array) -> Dictionary:
	var response := _configuration_response(joint, scene_root, configuration_properties)
	response["joint_kind"] = joint.get_class()
	response["node_a_path"] = _serialize_joint_endpoint(joint, scene_root, joint.node_a)
	response["node_b_path"] = _serialize_joint_endpoint(joint, scene_root, joint.node_b)
	return response


func _joint_response_with_mutation(
	mutation: Dictionary,
	joint: Joint2D,
	scene_root: Node,
	configuration_properties: Array
) -> Dictionary:
	var response := _joint_response(joint, scene_root, configuration_properties)
	for key in ["changed", "undoable", "_scene_mutated"]:
		if mutation.has(key):
			response[key] = mutation[key]
	return response


func _serialize_joint_endpoint(joint: Joint2D, scene_root: Node, node_path: NodePath) -> String:
	if node_path.is_empty():
		return ""
	var target := joint.get_node_or_null(node_path)
	if target != null and (target == scene_root or scene_root.is_ancestor_of(target)):
		return ScenePath.from_node(target, scene_root)
	return str(node_path)


func _build_shape(params: Dictionary, existing: Shape2D) -> Dictionary:
	var shape_name_result := _parse_shape_name(params.get("shape_type", ""))
	if shape_name_result.has("_error"):
		return shape_name_result
	var properties_result := _parse_shape_properties(
		params.get("properties", {}), shape_name_result["definition"]
	)
	if properties_result.has("_error"):
		return properties_result
	var definition: Dictionary = shape_name_result["definition"]
	var requested_class: String = definition["class"]
	var shape: Shape2D
	if existing != null and existing.get_class() == requested_class and existing.is_built_in():
		shape = existing.duplicate(true) as Shape2D
	else:
		var created := ClassDB.instantiate(StringName(requested_class))
		if not created is Shape2D:
			if created != null:
				created.free()
			return Errors.make("SHAPE_INSTANTIATION_FAILED", "Godot failed to instantiate %s" % requested_class)
		shape = created as Shape2D
	if shape == null:
		return Errors.make("SHAPE_INSTANTIATION_FAILED", "Godot failed to create a collision shape")
	var applied := _apply_shape_properties(shape, properties_result["properties"])
	if applied.has("_error"):
		return applied
	var validity := _validate_shape_geometry(shape, shape_name_result["name"])
	if validity.has("_error"):
		return validity
	return {"shape": shape}


func _parse_shape_name(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_SHAPE_TYPE", "shape_type must be a supported Shape2D name")
	var name: String = raw_value.to_lower().strip_edges()
	if not SHAPES_BY_NAME.has(name):
		return Errors.make("INVALID_SHAPE_TYPE", "shape_type is not supported")
	return {"name": name, "definition": SHAPES_BY_NAME[name]}


func _parse_shape_properties(raw_properties: Variant, definition: Dictionary) -> Dictionary:
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > MAX_SHAPE_PROPERTIES:
		return Errors.make("INVALID_SHAPE_PROPERTIES", "properties must be a non-empty object")
	for required_name in definition["required"]:
		if not raw_properties.has(required_name):
			return Errors.make("INVALID_SHAPE_PROPERTIES", "properties.%s is required" % required_name)
	return {"properties": raw_properties}


func _apply_shape_properties(shape: Shape2D, requested: Dictionary) -> Dictionary:
	var property_info_by_name := {}
	for property_info_value in shape.get_property_list():
		var property_info: Dictionary = property_info_value
		property_info_by_name[str(property_info.get("name", ""))] = property_info
	for property_name_value in requested:
		var property_name := str(property_name_value)
		if not property_info_by_name.has(property_name):
			return Errors.make(
				"SHAPE_PROPERTY_NOT_FOUND",
				"Shape property '%s' does not exist on %s" % [property_name, shape.get_class()],
				false,
				"Use collision_shape_get to inspect the current shape."
			)
		var property_info: Dictionary = property_info_by_name[property_name]
		var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
		if PROTECTED_SHAPE_PROPERTIES.has(property_name) or not _is_writable_public_property(usage):
			return Errors.make("SHAPE_PROPERTY_NOT_WRITABLE", "Shape property '%s' is not writable" % property_name)
		var decoded := VariantCodec.decode(requested[property_name_value], property_info, shape.get(property_name))
		if decoded.has("_error"):
			return Errors.make(
				"SHAPE_PROPERTY_TYPE_MISMATCH",
				decoded["_error"]["message"],
				false,
				"Use the JSON shape reported by collision_shape_get.",
				{"property": property_name}
			)
		shape.set(property_name, decoded["value"])
	return {}


func _validate_shape_geometry(shape: Shape2D, shape_name: String) -> Dictionary:
	match shape_name:
		"circle":
			if shape.radius <= 0.0:
				return _invalid_geometry("circle radius must be greater than zero")
		"rectangle":
			if shape.size.x <= 0.0 or shape.size.y <= 0.0:
				return _invalid_geometry("rectangle size.x and size.y must be greater than zero")
		"capsule":
			if shape.radius <= 0.0 or shape.height <= shape.radius * 2.0:
				return _invalid_geometry("capsule height must be greater than twice its positive radius")
		"segment":
			if shape.a.is_equal_approx(shape.b):
				return _invalid_geometry("segment endpoints must be distinct")
		"separation_ray":
			if shape.length <= 0.0:
				return _invalid_geometry("separation_ray length must be greater than zero")
		"world_boundary":
			if shape.normal.length_squared() <= 0.0:
				return _invalid_geometry("world_boundary normal must be non-zero")
		"convex_polygon":
			var convex_check := _validate_convex_polygon(shape.points)
			if convex_check.has("_error"):
				return convex_check
		"concave_polygon":
			var concave_check := _validate_concave_segments(shape.segments)
			if concave_check.has("_error"):
				return concave_check
	return {}


func _validate_convex_polygon(points: PackedVector2Array) -> Dictionary:
	if points.size() > MAX_POLYGON_POINTS:
		return _invalid_geometry("polygon points exceed the supported limit")
	if points.size() < 3:
		return _invalid_geometry("convex_polygon requires at least three points")
	for index in points.size():
		for later_index in range(index + 1, points.size()):
			if points[index].is_equal_approx(points[later_index]):
				return _invalid_geometry("convex_polygon points must be unique")
	var winding := 0.0
	for index in points.size():
		var next_index := (index + 1) % points.size()
		var after_next_index := (index + 2) % points.size()
		var cross := (points[next_index] - points[index]).cross(
			points[after_next_index] - points[next_index]
		)
		if is_zero_approx(cross):
			return _invalid_geometry("convex_polygon cannot contain collinear edges")
		if is_zero_approx(winding):
			winding = sign(cross)
		elif sign(cross) != winding:
			return _invalid_geometry("convex_polygon points must form a convex ordered polygon")
	return {}


func _validate_concave_segments(points: PackedVector2Array) -> Dictionary:
	if points.size() > MAX_POLYGON_POINTS:
		return _invalid_geometry("polygon points exceed the supported limit")
	if points.size() < 2 or points.size() % 2 != 0:
		return _invalid_geometry("concave_polygon segments require pairs of at least two points")
	for index in range(0, points.size(), 2):
		if points[index].is_equal_approx(points[index + 1]):
			return _invalid_geometry("concave_polygon segment endpoints must be distinct")
	return {}


func _invalid_geometry(message: String) -> Dictionary:
	return Errors.make("INVALID_SHAPE_GEOMETRY", message)


func _parse_layer_update(params: Dictionary) -> Dictionary:
	var result := {}
	var has_update := false
	if params.has("layers") and params["layers"] != null:
		var layers_result := _parse_layer_numbers(params["layers"], "layers")
		if layers_result.has("_error"):
			return layers_result
		result["layer"] = layers_result["mask"]
		has_update = true
	if params.has("masks") and params["masks"] != null:
		var masks_result := _parse_layer_numbers(params["masks"], "masks")
		if masks_result.has("_error"):
			return masks_result
		result["mask"] = masks_result["mask"]
		has_update = true
	if not has_update:
		return Errors.make("MISSING_PARAMETER", "layers or masks must be supplied")
	return result


func _parse_layer_numbers(raw_values: Variant, label: String) -> Dictionary:
	if not raw_values is Array or raw_values.size() > MAX_LAYER_COUNT:
		return Errors.make("INVALID_COLLISION_LAYERS", "%s must contain at most %d layer numbers" % [label, MAX_LAYER_COUNT])
	var mask := 0
	for raw_value in raw_values:
		if not _is_integral_number(raw_value):
			return Errors.make("INVALID_COLLISION_LAYERS", "%s entries must be integers from 1 to 32" % label)
		var layer := int(raw_value)
		if layer < 1 or layer > MAX_LAYER_COUNT or mask & (1 << (layer - 1)) != 0:
			return Errors.make("INVALID_COLLISION_LAYERS", "%s entries must be unique integers from 1 to 32" % label)
		mask |= 1 << (layer - 1)
	return {"mask": mask}


func _serialize_collision_layers(collision_object: CollisionObject2D, scene_root: Node) -> Dictionary:
	var layer := int(collision_object.collision_layer)
	var mask := int(collision_object.collision_mask)
	return {
		"path": ScenePath.from_node(collision_object, scene_root),
		"type": collision_object.get_class(),
		"collision_layer": layer,
		"collision_mask": mask,
		"layers": _mask_to_layer_numbers(layer),
		"masks": _mask_to_layer_numbers(mask),
	}


func _mask_to_layer_numbers(mask: int) -> Array[int]:
	var layers: Array[int] = []
	for index in MAX_LAYER_COUNT:
		if mask & (1 << index) != 0:
			layers.append(index + 1)
	return layers


func _serialize_shape(shape: Shape2D) -> Variant:
	if shape == null:
		return null
	var properties := {}
	for property_info_value in shape.get_property_list():
		var property_info: Dictionary = property_info_value
		var property_name := str(property_info.get("name", ""))
		var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
		if property_name.is_empty() or PROTECTED_SHAPE_PROPERTIES.has(property_name) or not _is_public_property(usage):
			continue
		properties[property_name] = VariantCodec.serialize(shape.get(property_name))
	return {
		"resource_type": shape.get_class(),
		"resource_path": shape.resource_path,
		"resource_name": shape.resource_name,
		"built_in": shape.is_built_in(),
		"properties": properties,
	}


func _is_public_property(usage: int) -> bool:
	return bool(usage & (PROPERTY_USAGE_STORAGE | PROPERTY_USAGE_EDITOR))


func _is_writable_public_property(usage: int) -> bool:
	return _is_public_property(usage) and not bool(usage & PROPERTY_USAGE_READ_ONLY)


func _is_integral_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and is_equal_approx(float(value), round(float(value)))

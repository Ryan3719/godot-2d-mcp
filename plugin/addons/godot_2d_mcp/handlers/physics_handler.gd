@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_SHAPE_PROPERTIES := 16
const MAX_LAYER_COUNT := 32
const MAX_POLYGON_POINTS := 512
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

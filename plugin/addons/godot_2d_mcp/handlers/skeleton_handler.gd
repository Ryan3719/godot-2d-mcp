@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_SKELETON_BONES := 512
const MIN_BONE_LENGTH := 1.0
const MAX_BONE_LENGTH := 1024.0
const MIN_BONE_ANGLE_DEGREES := -360.0
const MAX_BONE_ANGLE_DEGREES := 360.0
const BONE_PROPERTIES := ["rest", "auto_calculate_length_and_angle", "length", "angle_degrees"]

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_skeleton_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_skeleton_2d(params, false)
	if resolved.has("_error"):
		return resolved
	var bones_result := _collect_skeleton_bones(resolved["skeleton"])
	if bones_result.has("_error"):
		return bones_result
	return _skeleton_response(resolved["skeleton"], resolved["scene_root"], bones_result["bones"])


func get_bone_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_bone_2d(params, false)
	if resolved.has("_error"):
		return resolved
	return _bone_response(resolved["bone"], resolved["scene_root"])


func create_skeleton_2d_bone(params: Dictionary) -> Dictionary:
	var resolved := _resolve_skeleton_2d(params)
	if resolved.has("_error"):
		return resolved
	var skeleton: Skeleton2D = resolved["skeleton"]
	var parent_result := _resolve_bone_parent(params, skeleton, resolved["scene_root"])
	if parent_result.has("_error"):
		return parent_result
	var parsed := _parse_new_bone(params)
	if parsed.has("_error"):
		return parsed
	var parent: Node = parent_result["parent"]
	for sibling in parent.get_children(false):
		if String(sibling.name) == parsed["name"]:
			return Errors.make(
				"NODE_NAME_CONFLICT",
				"Parent already has a child named '%s'" % parsed["name"],
				false,
				"Choose a unique sibling name."
			)
	var bone := Bone2D.new()
	bone.name = parsed["name"]
	bone.set_rest(parsed["rest"])
	bone.set_autocalculate_length_and_angle(false)
	bone.set_length(parsed["length"])
	bone.set_bone_angle(deg_to_rad(parsed["angle_degrees"]))
	_undo_redo.create_action(
		"Godot 2D MCP: Create Bone2D %s" % bone.name,
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	_undo_redo.add_do_method(parent, "add_child", bone, true)
	_undo_redo.add_do_method(bone, "set_owner", resolved["scene_root"])
	_undo_redo.add_do_reference(bone)
	_undo_redo.add_undo_method(parent, "remove_child", bone)
	_undo_redo.commit_action()
	var result := _bone_response(bone, resolved["scene_root"])
	result["parent_path"] = ScenePath.from_node(parent, resolved["scene_root"])
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_bone_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_bone_2d(params)
	if resolved.has("_error"):
		return resolved
	var bone: Bone2D = resolved["bone"]
	var hierarchy := _require_valid_bone_hierarchy(bone)
	if hierarchy.has("_error"):
		return hierarchy
	var parsed := _parse_bone_updates(params, bone)
	if parsed.has("_error"):
		return parsed
	var changes: Array[Dictionary] = parsed["changes"]
	if changes.is_empty():
		var unchanged := _bone_response(bone, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Update Bone2D %s" % bone.name,
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	for change in changes:
		_undo_redo.add_do_property(bone, change["property_name"], change["new_value"])
		_undo_redo.add_undo_property(bone, change["property_name"], change["old_value"])
	_undo_redo.commit_action()
	var result := _bone_response(bone, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func reset_skeleton_2d_to_rest(params: Dictionary) -> Dictionary:
	var resolved := _resolve_skeleton_2d(params)
	if resolved.has("_error"):
		return resolved
	var bones_result := _collect_skeleton_bones(resolved["skeleton"], resolved["scene_root"], true, true)
	if bones_result.has("_error"):
		return bones_result
	var bones: Array[Bone2D] = bones_result["bones"]
	var changes: Array[Bone2D] = []
	for bone in bones:
		if bone.get_transform() != bone.get_rest():
			changes.append(bone)
	if changes.is_empty():
		var unchanged := _skeleton_response(resolved["skeleton"], resolved["scene_root"], bones)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Reset Skeleton2D %s to Rest Pose" % resolved["skeleton"].name,
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	for bone in changes:
		_undo_redo.add_do_method(bone, "set_transform", bone.get_rest())
		_undo_redo.add_undo_method(bone, "set_transform", bone.get_transform())
	_undo_redo.commit_action()
	var result := _skeleton_response(resolved["skeleton"], resolved["scene_root"], bones)
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func make_skeleton_2d_rest_from_current(params: Dictionary) -> Dictionary:
	var resolved := _resolve_skeleton_2d(params)
	if resolved.has("_error"):
		return resolved
	var bones_result := _collect_skeleton_bones(resolved["skeleton"], resolved["scene_root"], true, true)
	if bones_result.has("_error"):
		return bones_result
	var bones: Array[Bone2D] = bones_result["bones"]
	var changes: Array[Bone2D] = []
	for bone in bones:
		if bone.get_rest() != bone.get_transform():
			changes.append(bone)
	if changes.is_empty():
		var unchanged := _skeleton_response(resolved["skeleton"], resolved["scene_root"], bones)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Make Skeleton2D %s Rest Pose" % resolved["skeleton"].name,
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	for bone in changes:
		_undo_redo.add_do_method(bone, "set_rest", bone.get_transform())
		_undo_redo.add_undo_method(bone, "set_rest", bone.get_rest())
	_undo_redo.commit_action()
	var result := _skeleton_response(resolved["skeleton"], resolved["scene_root"], bones)
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_skeleton_2d(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is Skeleton2D:
		return Errors.make(
			"SKELETON_2D_REQUIRED",
			"Node '%s' is %s, not Skeleton2D" % [resolved["node"].name, resolved["node"].get_class()],
			false,
			"Target a Skeleton2D node."
		)
	resolved["skeleton"] = resolved["node"] as Skeleton2D
	return resolved


func _resolve_bone_2d(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is Bone2D:
		return Errors.make(
			"BONE_2D_REQUIRED",
			"Node '%s' is %s, not Bone2D" % [resolved["node"].name, resolved["node"].get_class()],
			false,
			"Target a Bone2D node."
		)
	resolved["bone"] = resolved["node"] as Bone2D
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


func _collect_skeleton_bones(
	skeleton: Skeleton2D,
	scene_root: Node = null,
	require_writable: bool = false,
	require_nonempty: bool = false
) -> Dictionary:
	var count := skeleton.get_bone_count()
	if count < 1 and require_nonempty:
		return Errors.make(
			"SKELETON_2D_BONES_REQUIRED",
			"Skeleton2D '%s' has no valid Bone2D descendants" % skeleton.name,
			false,
			"Create Bone2D children directly below Skeleton2D or another Bone2D."
		)
	if count > MAX_SKELETON_BONES:
		return Errors.make(
			"SKELETON_2D_BONE_LIMIT_EXCEEDED",
			"Skeleton2D has more than the supported %d bones" % MAX_SKELETON_BONES
		)
	var bones: Array[Bone2D] = []
	for index in count:
		var bone := skeleton.get_bone(index)
		if bone == null:
			return Errors.make("SKELETON_2D_BONE_LOOKUP_FAILED", "Unable to resolve Skeleton2D bone %d" % index)
		if require_writable and scene_root != null and bone != scene_root and bone.owner != scene_root:
			return Errors.make(
				"PACKED_SCENE_BOUNDARY",
				"Cannot edit Bone2D '%s' because it belongs to an instanced scene" % bone.name,
				false,
				"Edit the source PackedScene or target a fully local Skeleton2D hierarchy."
			)
		bones.append(bone)
	return {"bones": bones}


func _require_valid_bone_hierarchy(bone: Bone2D) -> Dictionary:
	var current: Node = bone.get_parent()
	while current != null:
		if current is Skeleton2D:
			return {"skeleton": current as Skeleton2D}
		if not current is Bone2D:
			break
		current = current.get_parent()
	return Errors.make(
		"BONE_2D_HIERARCHY_INVALID",
		"Bone2D '%s' must be a direct or chained child of Skeleton2D" % bone.name,
		false,
		"Create it under Skeleton2D or another Bone2D before editing skeleton properties."
	)


func _resolve_bone_parent(params: Dictionary, skeleton: Skeleton2D, scene_root: Node) -> Dictionary:
	var parent: Node = skeleton
	var parent_path := str(params.get("parent_bone_path", "")).strip_edges()
	if not parent_path.is_empty():
		var node := ScenePath.resolve(parent_path, scene_root)
		if node == null:
			return Errors.make(
				"NODE_NOT_FOUND",
				"Parent Bone2D not found: %s" % parent_path,
				false,
				"Use skeleton_2d_get to inspect valid bone paths."
			)
		if not node is Bone2D:
			return Errors.make(
				"BONE_2D_REQUIRED",
				"Parent node '%s' is %s, not Bone2D" % [node.name, node.get_class()]
			)
		var hierarchy := _require_valid_bone_hierarchy(node as Bone2D)
		if hierarchy.has("_error"):
			return hierarchy
		if hierarchy["skeleton"] != skeleton:
			return Errors.make(
				"BONE_2D_SKELETON_MISMATCH",
				"Parent Bone2D '%s' belongs to a different Skeleton2D" % node.name
			)
		parent = node
	if parent != scene_root and parent.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot add a Bone2D below '%s' because it belongs to an instanced scene" % parent.name,
			false,
			"Edit the source PackedScene or target a locally owned Bone2D."
		)
	return {"parent": parent}


func _skeleton_response(skeleton: Skeleton2D, scene_root: Node, bones: Array[Bone2D]) -> Dictionary:
	var entries: Array = []
	for index in bones.size():
		entries.append(_bone_summary(bones[index], scene_root, index))
	return {
		"path": ScenePath.from_node(skeleton, scene_root),
		"type": skeleton.get_class(),
		"bone_count": bones.size(),
		"bones": entries,
	}


func _bone_response(bone: Bone2D, scene_root: Node) -> Dictionary:
	var hierarchy := _require_valid_bone_hierarchy(bone)
	var response := _bone_summary(bone, scene_root, bone.get_index_in_skeleton() if not hierarchy.has("_error") else -1)
	response["valid_hierarchy"] = not hierarchy.has("_error")
	response["skeleton_path"] = "" if hierarchy.has("_error") else ScenePath.from_node(hierarchy["skeleton"], scene_root)
	response["hierarchy_error"] = "" if not hierarchy.has("_error") else hierarchy["_error"]["message"]
	return response


func _bone_summary(bone: Bone2D, scene_root: Node, index: int) -> Dictionary:
	var parent_path := ""
	if bone.get_parent() is Bone2D:
		parent_path = ScenePath.from_node(bone.get_parent(), scene_root)
	return {
		"index": index,
		"path": ScenePath.from_node(bone, scene_root),
		"name": String(bone.name),
		"parent_bone_path": parent_path,
		"rest": VariantCodec.serialize(bone.get_rest()),
		"transform": VariantCodec.serialize(bone.get_transform()),
		"auto_calculate_length_and_angle": bone.get_autocalculate_length_and_angle(),
		"length": bone.get_length(),
		"angle_degrees": rad_to_deg(bone.get_bone_angle()),
	}


func _parse_bone_updates(params: Dictionary, bone: Bone2D) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > BONE_PROPERTIES.size():
		return Errors.make(
			"INVALID_BONE_2D_PROPERTIES",
			"properties must be a non-empty object containing only Bone2D semantic properties"
		)
	for raw_name in raw_properties:
		if not raw_name is String or not BONE_PROPERTIES.has(raw_name):
			return Errors.make(
				"UNSUPPORTED_BONE_2D_PROPERTY",
				"Unsupported Bone2D property: %s" % str(raw_name),
				false,
				"Call bone_2d_get to inspect supported properties."
			)
	var updates := {}
	if raw_properties.has("rest"):
		var decoded := VariantCodec.decode(raw_properties["rest"], {"type": TYPE_TRANSFORM2D}, bone.get_rest())
		if decoded.has("_error"):
			return Errors.make(
				"INVALID_BONE_2D_PROPERTIES",
				"rest must be a finite, invertible Transform2D",
				false,
				"Use x, y, and origin Vector2 fields."
			)
		var rest: Transform2D = decoded["value"]
		if not _is_valid_transform(rest):
			return Errors.make("INVALID_BONE_2D_PROPERTIES", "rest must be finite and invertible")
		updates["rest"] = rest
	if raw_properties.has("auto_calculate_length_and_angle"):
		if not raw_properties["auto_calculate_length_and_angle"] is bool:
			return Errors.make("INVALID_BONE_2D_PROPERTIES", "auto_calculate_length_and_angle must be a boolean")
		updates["auto_calculate_length_and_angle"] = raw_properties["auto_calculate_length_and_angle"]
	if raw_properties.has("length"):
		var length_result := _parse_bone_number(
			raw_properties["length"], "length", MIN_BONE_LENGTH, MAX_BONE_LENGTH
		)
		if length_result.has("_error"):
			return length_result
		updates["length"] = length_result["value"]
	if raw_properties.has("angle_degrees"):
		var angle_result := _parse_bone_number(
			raw_properties["angle_degrees"], "angle_degrees", MIN_BONE_ANGLE_DEGREES, MAX_BONE_ANGLE_DEGREES
		)
		if angle_result.has("_error"):
			return angle_result
		updates["angle_degrees"] = angle_result["value"]
	var effective_auto: bool = updates.get(
		"auto_calculate_length_and_angle", bone.get_autocalculate_length_and_angle()
	)
	if effective_auto and (updates.has("length") or updates.has("angle_degrees")):
		return Errors.make(
			"BONE_2D_AUTO_CALCULATION_CONFLICT",
			"Set auto_calculate_length_and_angle to false before setting length or angle_degrees",
			false,
			"Automatic Bone2D length and angle are derived from its child bones."
		)
	var changes: Array[Dictionary] = []
	for entry in [
		{"input_name": "auto_calculate_length_and_angle", "property_name": "auto_calculate_length_and_angle"},
		{"input_name": "rest", "property_name": "rest"},
		{"input_name": "length", "property_name": "length"},
		{"input_name": "angle_degrees", "property_name": "bone_angle"},
	]:
		var input_name: String = entry["input_name"]
		if not updates.has(input_name):
			continue
		var old_value = bone.get(entry["property_name"])
		var new_value = updates[input_name]
		if old_value == new_value:
			continue
		changes.append(
			{
				"property_name": entry["property_name"],
				"old_value": old_value,
				"new_value": new_value,
			}
		)
	return {"changes": changes}


func _parse_new_bone(params: Dictionary) -> Dictionary:
	var requested_name := str(params.get("name", "")).strip_edges()
	if requested_name.is_empty():
		requested_name = "Bone2D"
	if requested_name.length() > 256 or requested_name.validate_node_name() != requested_name:
		return Errors.make("INVALID_NODE_NAME", "Invalid node name: %s" % requested_name)
	var raw_rest: Variant = params.get("rest", null)
	var rest: Transform2D = Transform2D.IDENTITY
	if raw_rest != null:
		var decoded := VariantCodec.decode(raw_rest, {"type": TYPE_TRANSFORM2D}, rest)
		if decoded.has("_error"):
			return Errors.make(
				"INVALID_BONE_2D_PROPERTIES",
				"rest must be a finite, invertible Transform2D",
				false,
				"Use x, y, and origin Vector2 fields."
			)
		rest = decoded["value"]
	if not _is_valid_transform(rest):
		return Errors.make("INVALID_BONE_2D_PROPERTIES", "rest must be finite and invertible")
	var length_result := _parse_bone_number(
		params.get("length", 16.0), "length", MIN_BONE_LENGTH, MAX_BONE_LENGTH
	)
	if length_result.has("_error"):
		return length_result
	var angle_result := _parse_bone_number(
		params.get("angle_degrees", 0.0), "angle_degrees", MIN_BONE_ANGLE_DEGREES, MAX_BONE_ANGLE_DEGREES
	)
	if angle_result.has("_error"):
		return angle_result
	return {
		"name": requested_name,
		"rest": rest,
		"length": length_result["value"],
		"angle_degrees": angle_result["value"],
	}


func _parse_bone_number(raw_value: Variant, label: String, minimum: float, maximum: float) -> Dictionary:
	if not (raw_value is int or raw_value is float) or not is_finite(float(raw_value)):
		return Errors.make("INVALID_BONE_2D_PROPERTIES", "%s must be a finite number" % label)
	var value := float(raw_value)
	if value < minimum or value > maximum:
		return Errors.make(
			"INVALID_BONE_2D_PROPERTIES",
			"%s must be between %s and %s" % [label, minimum, maximum]
		)
	return {"value": value}


func _is_valid_transform(transform: Transform2D) -> bool:
	return is_finite(transform.x.x) and is_finite(transform.x.y) \
		and is_finite(transform.y.x) and is_finite(transform.y.y) \
		and is_finite(transform.origin.x) and is_finite(transform.origin.y) \
		and not is_zero_approx(transform.determinant())

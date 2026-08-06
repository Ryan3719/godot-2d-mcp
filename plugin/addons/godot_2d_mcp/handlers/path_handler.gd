@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_CURVE_POINTS := 512
const MIN_BAKE_INTERVAL := 0.01
const MAX_BAKE_INTERVAL := 512.0

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_path_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_path_2d(params, false)
	if resolved.has("_error"):
		return resolved
	var page := _parse_page(params)
	if page.has("_error"):
		return page
	return _path_response(resolved["path_2d"], resolved["scene_root"], page["offset"], page["limit"])


func set_path_curve(params: Dictionary) -> Dictionary:
	var resolved := _resolve_path_2d(params)
	if resolved.has("_error"):
		return resolved
	var points_result := _parse_curve_points(params.get("points", null))
	if points_result.has("_error"):
		return points_result
	var bake_interval_result := _parse_bake_interval(params.get("bake_interval", 5.0))
	if bake_interval_result.has("_error"):
		return bake_interval_result
	var replacement := Curve2D.new()
	replacement.bake_interval = bake_interval_result["bake_interval"]
	for point in points_result["points"]:
		replacement.add_point(point["position"], point["in"], point["out"])
	var path_2d: Path2D = resolved["path_2d"]
	if _curves_match(path_2d.curve, replacement):
		var unchanged := _path_response(path_2d, resolved["scene_root"], 0, MAX_CURVE_POINTS)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_curve(
		path_2d,
		resolved["scene_root"],
		replacement,
		"Set Curve2D on %s" % path_2d.name
	)
	var result := _path_response(path_2d, resolved["scene_root"], 0, MAX_CURVE_POINTS)
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func insert_path_curve_point(params: Dictionary) -> Dictionary:
	var resolved := _resolve_path_2d(params)
	if resolved.has("_error"):
		return resolved
	var path_2d: Path2D = resolved["path_2d"]
	var current: Curve2D = path_2d.curve
	if current == null:
		return _curve_required(path_2d)
	var limit_check := _require_curve_point_limit(current)
	if limit_check.has("_error"):
		return limit_check
	if current.get_point_count() >= MAX_CURVE_POINTS:
		return Errors.make(
			"PATH_CURVE_POINT_LIMIT_EXCEEDED",
			"Curve2D already has the maximum of %d points" % MAX_CURVE_POINTS
		)
	var point_result := _parse_curve_point(params.get("point", null), "point")
	if point_result.has("_error"):
		return point_result
	var index_result := _parse_insert_index(params, current.get_point_count())
	if index_result.has("_error"):
		return index_result
	var replacement_result := _duplicate_curve(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: Curve2D = replacement_result["curve"]
	var point: Dictionary = point_result["point"]
	replacement.add_point(point["position"], point["in"], point["out"], index_result["index"])
	_commit_curve(
		path_2d,
		resolved["scene_root"],
		replacement,
		"Insert Curve2D point on %s" % path_2d.name
	)
	var result := _path_response(path_2d, resolved["scene_root"], 0, MAX_CURVE_POINTS)
	result["point_index"] = index_result["index"]
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_path_curve_point(params: Dictionary) -> Dictionary:
	var resolved := _resolve_path_2d(params)
	if resolved.has("_error"):
		return resolved
	var path_2d: Path2D = resolved["path_2d"]
	var current: Curve2D = path_2d.curve
	if current == null:
		return _curve_required(path_2d)
	var limit_check := _require_curve_point_limit(current)
	if limit_check.has("_error"):
		return limit_check
	var index_result := _parse_existing_index(params, current.get_point_count())
	if index_result.has("_error"):
		return index_result
	var point_result := _parse_curve_point(params.get("point", null), "point")
	if point_result.has("_error"):
		return point_result
	var replacement_result := _duplicate_curve(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: Curve2D = replacement_result["curve"]
	var point: Dictionary = point_result["point"]
	var index: int = index_result["index"]
	replacement.set_point_position(index, point["position"])
	replacement.set_point_in(index, point["in"])
	replacement.set_point_out(index, point["out"])
	if _curves_match(current, replacement):
		var unchanged := _path_response(path_2d, resolved["scene_root"], 0, MAX_CURVE_POINTS)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_curve(
		path_2d,
		resolved["scene_root"],
		replacement,
		"Set Curve2D point on %s" % path_2d.name
	)
	var result := _path_response(path_2d, resolved["scene_root"], 0, MAX_CURVE_POINTS)
	result["point_index"] = index
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func remove_path_curve_point(params: Dictionary) -> Dictionary:
	var resolved := _resolve_path_2d(params)
	if resolved.has("_error"):
		return resolved
	var path_2d: Path2D = resolved["path_2d"]
	var current: Curve2D = path_2d.curve
	if current == null:
		return _curve_required(path_2d)
	var limit_check := _require_curve_point_limit(current)
	if limit_check.has("_error"):
		return limit_check
	var index_result := _parse_existing_index(params, current.get_point_count())
	if index_result.has("_error"):
		return index_result
	var replacement_result := _duplicate_curve(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: Curve2D = replacement_result["curve"]
	var index: int = index_result["index"]
	replacement.remove_point(index)
	_commit_curve(
		path_2d,
		resolved["scene_root"],
		replacement,
		"Remove Curve2D point from %s" % path_2d.name
	)
	var result := _path_response(path_2d, resolved["scene_root"], 0, MAX_CURVE_POINTS)
	result["removed_point_index"] = index
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func clear_path_curve(params: Dictionary) -> Dictionary:
	var resolved := _resolve_path_2d(params)
	if resolved.has("_error"):
		return resolved
	var path_2d: Path2D = resolved["path_2d"]
	if path_2d.curve == null:
		return Errors.make(
			"PATH_CURVE_NOT_ASSIGNED",
			"Path2D '%s' has no Curve2D resource" % path_2d.name,
			false,
			"Call path_2d_curve_set before clearing a curve."
		)
	_commit_curve(path_2d, resolved["scene_root"], null, "Clear Curve2D on %s" % path_2d.name)
	var result := _path_response(path_2d, resolved["scene_root"], 0, MAX_CURVE_POINTS)
	result["cleared"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_path_2d(params: Dictionary, require_writable: bool = true) -> Dictionary:
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
	if not node is Path2D:
		return Errors.make(
			"PATH_2D_REQUIRED",
			"Node '%s' is %s, not Path2D" % [node.name, node.get_class()],
			false,
			"Target a Path2D node."
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit node '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned node."
		)
	return {"path_2d": node as Path2D, "scene_root": scene_root}


func _path_response(path_2d: Path2D, scene_root: Node, offset: int, limit: int) -> Dictionary:
	var curve: Curve2D = path_2d.curve
	var points: Array = []
	var point_count := 0
	var start := 0
	if curve != null:
		point_count = curve.get_point_count()
		start = mini(offset, point_count)
		var end := mini(start + limit, point_count)
		for index in range(start, end):
			points.append(_serialize_curve_point(curve, index))
	return {
		"path": ScenePath.from_node(path_2d, scene_root),
		"type": path_2d.get_class(),
		"curve": _serialize_curve_summary(curve),
		"points": points,
		"total_points": point_count,
		"offset": start,
		"limit": limit,
		"truncated": start + points.size() < point_count,
	}


func _serialize_curve_summary(curve: Curve2D) -> Variant:
	if curve == null:
		return null
	return {
		"resource_type": curve.get_class(),
		"resource_path": curve.resource_path,
		"embedded": curve.resource_path.is_empty(),
		"bake_interval": curve.bake_interval,
		"point_count": curve.get_point_count(),
	}


func _serialize_curve_point(curve: Curve2D, index: int) -> Dictionary:
	return {
		"index": index,
		"position": VariantCodec.serialize(curve.get_point_position(index)),
		"in": VariantCodec.serialize(curve.get_point_in(index)),
		"out": VariantCodec.serialize(curve.get_point_out(index)),
	}


func _parse_page(params: Dictionary) -> Dictionary:
	var offset_result := _parse_nonnegative_integer(params.get("offset", 0), "offset")
	if offset_result.has("_error"):
		return offset_result
	var limit_result := _parse_nonnegative_integer(params.get("limit", 100), "limit")
	if limit_result.has("_error"):
		return limit_result
	var limit: int = limit_result["value"]
	if limit < 1 or limit > MAX_CURVE_POINTS:
		return Errors.make(
			"INVALID_PATH_PAGE",
			"limit must be an integer between 1 and %d" % MAX_CURVE_POINTS
		)
	return {"offset": offset_result["value"], "limit": limit}


func _parse_curve_points(raw_points: Variant) -> Dictionary:
	if not raw_points is Array or raw_points.size() > MAX_CURVE_POINTS:
		return Errors.make(
			"INVALID_PATH_CURVE",
			"points must be an array containing at most %d points" % MAX_CURVE_POINTS
		)
	var points: Array[Dictionary] = []
	for index in raw_points.size():
		var point_result := _parse_curve_point(raw_points[index], "points[%d]" % index)
		if point_result.has("_error"):
			return point_result
		points.append(point_result["point"])
	return {"points": points}


func _parse_curve_point(raw_point: Variant, label: String) -> Dictionary:
	if not raw_point is Dictionary or not raw_point.has("position"):
		return Errors.make("INVALID_PATH_CURVE", "%s must contain position" % label)
	for property_name_value in raw_point:
		var property_name := str(property_name_value)
		if property_name not in ["position", "in", "out"]:
			return Errors.make("INVALID_PATH_CURVE", "%s contains an unsupported property" % label)
	var position_result := _parse_vector2(raw_point["position"], "%s.position" % label)
	if position_result.has("_error"):
		return position_result
	var in_result := _parse_vector2(raw_point.get("in", {"x": 0.0, "y": 0.0}), "%s.in" % label)
	if in_result.has("_error"):
		return in_result
	var out_result := _parse_vector2(raw_point.get("out", {"x": 0.0, "y": 0.0}), "%s.out" % label)
	if out_result.has("_error"):
		return out_result
	return {
		"point": {
			"position": position_result["value"],
			"in": in_result["value"],
			"out": out_result["value"],
		}
	}


func _parse_vector2(raw_value: Variant, label: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_VECTOR2}, Vector2())
	if decoded.has("_error"):
		return Errors.make(
			"INVALID_PATH_CURVE",
			"%s must be a Vector2 object with numeric x and y fields" % label
		)
	var value: Vector2 = decoded["value"]
	if not is_finite(value.x) or not is_finite(value.y):
		return Errors.make("INVALID_PATH_CURVE", "%s must be finite" % label)
	return {"value": value}


func _parse_bake_interval(raw_value: Variant) -> Dictionary:
	if not (raw_value is int or raw_value is float) or not is_finite(float(raw_value)):
		return Errors.make("INVALID_PATH_CURVE", "bake_interval must be a finite number")
	var bake_interval := float(raw_value)
	if bake_interval < MIN_BAKE_INTERVAL or bake_interval > MAX_BAKE_INTERVAL:
		return Errors.make(
			"INVALID_PATH_CURVE",
			"bake_interval must be between %s and %s" % [MIN_BAKE_INTERVAL, MAX_BAKE_INTERVAL]
		)
	return {"bake_interval": bake_interval}


func _parse_insert_index(params: Dictionary, point_count: int) -> Dictionary:
	if not params.has("index") or params["index"] == null:
		return {"index": point_count}
	var index_result := _parse_nonnegative_integer(params["index"], "index")
	if index_result.has("_error"):
		return index_result
	if index_result["value"] > point_count:
		return Errors.make(
			"PATH_CURVE_INDEX_OUT_OF_RANGE",
			"index must be between 0 and %d for insertion" % point_count
		)
	return {"index": index_result["value"]}


func _parse_existing_index(params: Dictionary, point_count: int) -> Dictionary:
	if not params.has("index"):
		return Errors.make("MISSING_PARAMETER", "index is required")
	var index_result := _parse_nonnegative_integer(params["index"], "index")
	if index_result.has("_error"):
		return index_result
	if index_result["value"] >= point_count:
		return Errors.make(
			"PATH_CURVE_POINT_NOT_FOUND",
			"Curve2D point index %d is out of range" % index_result["value"],
			false,
			"Call path_2d_get to inspect the current point indexes."
		)
	return {"index": index_result["value"]}


func _parse_nonnegative_integer(raw_value: Variant, label: String) -> Dictionary:
	if not (raw_value is int or raw_value is float) \
		or not is_finite(float(raw_value)) \
		or float(raw_value) != floorf(float(raw_value)) \
		or float(raw_value) < 0.0:
		return Errors.make("INVALID_PATH_CURVE", "%s must be a non-negative integer" % label)
	return {"value": int(raw_value)}


func _duplicate_curve(curve: Curve2D) -> Dictionary:
	var duplicated = curve.duplicate(true)
	if duplicated == null or not duplicated is Curve2D:
		return Errors.make("PATH_CURVE_DUPLICATION_FAILED", "Unable to duplicate the Curve2D resource")
	return {"curve": duplicated as Curve2D}


func _require_curve_point_limit(curve: Curve2D) -> Dictionary:
	if curve.get_point_count() > MAX_CURVE_POINTS:
		return Errors.make(
			"PATH_CURVE_POINT_LIMIT_EXCEEDED",
			"Curve2D has more than the supported %d points" % MAX_CURVE_POINTS,
			false,
			"Replace the curve with path_2d_curve_set using at most 512 points."
		)
	return {}


func _curves_match(first: Curve2D, second: Curve2D) -> bool:
	if first == null or second == null:
		return first == second
	if not is_equal_approx(first.bake_interval, second.bake_interval):
		return false
	if first.get_point_count() != second.get_point_count():
		return false
	for index in first.get_point_count():
		if not first.get_point_position(index).is_equal_approx(second.get_point_position(index)):
			return false
		if not first.get_point_in(index).is_equal_approx(second.get_point_in(index)):
			return false
		if not first.get_point_out(index).is_equal_approx(second.get_point_out(index)):
			return false
	return true


func _commit_curve(path_2d: Path2D, scene_root: Node, curve: Curve2D, action_name: String) -> void:
	var old_curve: Curve2D = path_2d.curve
	_undo_redo.create_action("Godot 2D MCP: %s" % action_name, UndoRedo.MERGE_DISABLE, scene_root, true)
	_undo_redo.add_do_property(path_2d, "curve", curve)
	if curve != null:
		_undo_redo.add_do_reference(curve)
	_undo_redo.add_undo_property(path_2d, "curve", old_curve)
	if old_curve != null:
		_undo_redo.add_undo_reference(old_curve)
	_undo_redo.commit_action()


func _curve_required(path_2d: Path2D) -> Dictionary:
	return Errors.make(
		"PATH_CURVE_NOT_ASSIGNED",
		"Path2D '%s' has no Curve2D resource" % path_2d.name,
		false,
		"Call path_2d_curve_set before editing curve points."
	)

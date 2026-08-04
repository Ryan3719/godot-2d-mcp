@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")

const MAX_CONTAINER_ITEMS := 512
const MAX_DEPTH := 8


static func decode(value: Variant, property_info: Dictionary, current_value: Variant) -> Dictionary:
	var target_type := int(property_info.get("type", TYPE_NIL))
	if target_type == TYPE_NIL:
		target_type = typeof(current_value)

	match target_type:
		TYPE_NIL:
			return _success(value)
		TYPE_BOOL:
			if value is bool:
				return _success(value)
		TYPE_INT:
			if _is_integral_number(value):
				return _success(int(value))
		TYPE_FLOAT:
			if _is_number(value):
				return _success(float(value))
		TYPE_STRING:
			if value is String:
				return _success(value)
		TYPE_STRING_NAME:
			if value is String:
				return _success(StringName(value))
		TYPE_NODE_PATH:
			if value is String:
				return _success(NodePath(value))
		TYPE_VECTOR2:
			return _decode_vector2(value)
		TYPE_VECTOR2I:
			return _decode_vector2i(value)
		TYPE_RECT2:
			return _decode_rect2(value)
		TYPE_RECT2I:
			return _decode_rect2i(value)
		TYPE_TRANSFORM2D:
			return _decode_transform2d(value)
		TYPE_COLOR:
			return _decode_color(value)
		TYPE_ARRAY:
			if value is Array and value.size() <= MAX_CONTAINER_ITEMS:
				if current_value is Array and current_value.is_typed():
					return _failure("Typed arrays are not supported in this release")
				return _success(value.duplicate(true))
		TYPE_DICTIONARY:
			if value is Dictionary and value.size() <= MAX_CONTAINER_ITEMS:
				if current_value is Dictionary and current_value.is_typed():
					return _failure("Typed dictionaries are not supported in this release")
				return _success(value.duplicate(true))
		TYPE_PACKED_BYTE_ARRAY:
			return _decode_packed_numbers(value, target_type)
		TYPE_PACKED_INT32_ARRAY, TYPE_PACKED_INT64_ARRAY:
			return _decode_packed_numbers(value, target_type)
		TYPE_PACKED_FLOAT32_ARRAY, TYPE_PACKED_FLOAT64_ARRAY:
			return _decode_packed_numbers(value, target_type)
		TYPE_PACKED_STRING_ARRAY:
			return _decode_packed_strings(value)
		TYPE_PACKED_VECTOR2_ARRAY:
			return _decode_packed_vector2(value)
		TYPE_PACKED_COLOR_ARRAY:
			return _decode_packed_colors(value)
		TYPE_OBJECT:
			if value == null:
				return _success(null)

	return _failure(
		"Cannot convert JSON value to Godot property type %s" % type_string(target_type),
		{"expected_type": type_string(target_type), "received_type": type_string(typeof(value))}
	)


static func serialize(value: Variant, depth: int = 0) -> Variant:
	if depth > MAX_DEPTH:
		return null
	if value == null:
		return null
	match typeof(value):
		TYPE_BOOL, TYPE_INT, TYPE_STRING:
			return value
		TYPE_FLOAT:
			return _safe_float(value)
		TYPE_STRING_NAME, TYPE_NODE_PATH:
			return str(value)
		TYPE_VECTOR2I:
			return {"x": value.x, "y": value.y}
		TYPE_VECTOR2:
			return {"x": _safe_float(value.x), "y": _safe_float(value.y)}
		TYPE_RECT2I:
			return {
				"position": serialize(value.position, depth + 1),
				"size": serialize(value.size, depth + 1),
			}
		TYPE_RECT2:
			return {
				"position": serialize(value.position, depth + 1),
				"size": serialize(value.size, depth + 1),
			}
		TYPE_TRANSFORM2D:
			return {
				"x": serialize(value.x, depth + 1),
				"y": serialize(value.y, depth + 1),
				"origin": serialize(value.origin, depth + 1),
			}
		TYPE_COLOR:
			return {
				"r": _safe_float(value.r),
				"g": _safe_float(value.g),
				"b": _safe_float(value.b),
				"a": _safe_float(value.a),
			}
		TYPE_ARRAY, TYPE_PACKED_BYTE_ARRAY, TYPE_PACKED_INT32_ARRAY, TYPE_PACKED_INT64_ARRAY, TYPE_PACKED_FLOAT32_ARRAY, TYPE_PACKED_FLOAT64_ARRAY, TYPE_PACKED_STRING_ARRAY, TYPE_PACKED_VECTOR2_ARRAY, TYPE_PACKED_COLOR_ARRAY:
			var output: Array = []
			var count := mini(value.size(), MAX_CONTAINER_ITEMS)
			for index in count:
				output.append(serialize(value[index], depth + 1))
			return output
		TYPE_DICTIONARY:
			var output := {}
			var count := 0
			for key in value:
				if count >= MAX_CONTAINER_ITEMS:
					break
				output[str(key)] = serialize(value[key], depth + 1)
				count += 1
			return output
		TYPE_OBJECT:
			if value is Resource:
				return {
					"resource_type": value.get_class(),
					"resource_path": value.resource_path,
				}
	return null


static func _decode_vector2(value: Variant) -> Dictionary:
	if value is Dictionary and _has_exact_keys(value, ["x", "y"]):
		if _is_number(value["x"]) and _is_number(value["y"]):
			return _success(Vector2(float(value["x"]), float(value["y"])))
	return _failure("Vector2 requires exactly numeric x and y fields")


static func _decode_vector2i(value: Variant) -> Dictionary:
	if value is Dictionary and _has_exact_keys(value, ["x", "y"]):
		if _is_integral_number(value["x"]) and _is_integral_number(value["y"]):
			return _success(Vector2i(int(value["x"]), int(value["y"])))
	return _failure("Vector2i requires exactly integral x and y fields")


static func _decode_rect2(value: Variant) -> Dictionary:
	if not value is Dictionary or not _has_exact_keys(value, ["position", "size"]):
		return _failure("Rect2 requires position and size Vector2 fields")
	var position := _decode_vector2(value["position"])
	var size := _decode_vector2(value["size"])
	if position.has("_error") or size.has("_error"):
		return _failure("Rect2 requires valid position and size Vector2 fields")
	return _success(Rect2(position["value"], size["value"]))


static func _decode_rect2i(value: Variant) -> Dictionary:
	if not value is Dictionary or not _has_exact_keys(value, ["position", "size"]):
		return _failure("Rect2i requires position and size Vector2i fields")
	var position := _decode_vector2i(value["position"])
	var size := _decode_vector2i(value["size"])
	if position.has("_error") or size.has("_error"):
		return _failure("Rect2i requires valid position and size Vector2i fields")
	return _success(Rect2i(position["value"], size["value"]))


static func _decode_transform2d(value: Variant) -> Dictionary:
	if not value is Dictionary or not _has_exact_keys(value, ["x", "y", "origin"]):
		return _failure("Transform2D requires x, y, and origin Vector2 fields")
	var x_axis := _decode_vector2(value["x"])
	var y_axis := _decode_vector2(value["y"])
	var origin := _decode_vector2(value["origin"])
	if x_axis.has("_error") or y_axis.has("_error") or origin.has("_error"):
		return _failure("Transform2D requires valid x, y, and origin Vector2 fields")
	return _success(Transform2D(x_axis["value"], y_axis["value"], origin["value"]))


static func _decode_color(value: Variant) -> Dictionary:
	if value is String:
		var first := Color.from_string(value, Color(-1.0, -1.0, -1.0, -1.0))
		var second := Color.from_string(value, Color(-2.0, -2.0, -2.0, -2.0))
		if first == second:
			return _success(first)
	if value is Dictionary:
		var keys := Array(value.keys())
		keys.sort()
		if keys == ["b", "g", "r"] or keys == ["a", "b", "g", "r"]:
			var alpha: Variant = value.get("a", 1.0)
			if _is_number(value["r"]) and _is_number(value["g"]) and _is_number(value["b"]) and _is_number(alpha):
				return _success(
					Color(float(value["r"]), float(value["g"]), float(value["b"]), float(alpha))
				)
	return _failure("Color requires a valid color string or numeric r, g, b, and optional a fields")


static func _decode_packed_numbers(value: Variant, target_type: int) -> Dictionary:
	if not value is Array or value.size() > MAX_CONTAINER_ITEMS:
		return _failure("Packed numeric arrays require a bounded JSON array")
	var output: Array = []
	for item in value:
		if target_type in [TYPE_PACKED_FLOAT32_ARRAY, TYPE_PACKED_FLOAT64_ARRAY]:
			if not _is_number(item):
				return _failure("Packed float arrays require numeric values")
			output.append(float(item))
		else:
			if not _is_integral_number(item):
				return _failure("Packed integer arrays require integral values")
			output.append(int(item))
	match target_type:
		TYPE_PACKED_BYTE_ARRAY:
			return _success(PackedByteArray(output))
		TYPE_PACKED_INT32_ARRAY:
			return _success(PackedInt32Array(output))
		TYPE_PACKED_INT64_ARRAY:
			return _success(PackedInt64Array(output))
		TYPE_PACKED_FLOAT32_ARRAY:
			return _success(PackedFloat32Array(output))
	return _success(PackedFloat64Array(output))


static func _decode_packed_strings(value: Variant) -> Dictionary:
	if not value is Array or value.size() > MAX_CONTAINER_ITEMS:
		return _failure("PackedStringArray requires a bounded JSON array")
	for item in value:
		if not item is String:
			return _failure("PackedStringArray requires string values")
	return _success(PackedStringArray(value))


static func _decode_packed_vector2(value: Variant) -> Dictionary:
	if not value is Array or value.size() > MAX_CONTAINER_ITEMS:
		return _failure("PackedVector2Array requires a bounded JSON array")
	var output := PackedVector2Array()
	for item in value:
		var decoded := _decode_vector2(item)
		if decoded.has("_error"):
			return decoded
		output.append(decoded["value"])
	return _success(output)


static func _decode_packed_colors(value: Variant) -> Dictionary:
	if not value is Array or value.size() > MAX_CONTAINER_ITEMS:
		return _failure("PackedColorArray requires a bounded JSON array")
	var output := PackedColorArray()
	for item in value:
		var decoded := _decode_color(item)
		if decoded.has("_error"):
			return decoded
		output.append(decoded["value"])
	return _success(output)


static func _has_exact_keys(value: Dictionary, expected: Array[String]) -> bool:
	var actual := Array(value.keys())
	actual.sort()
	var sorted_expected := expected.duplicate()
	sorted_expected.sort()
	return actual == sorted_expected


static func _is_number(value: Variant) -> bool:
	return value is int or value is float


static func _is_integral_number(value: Variant) -> bool:
	return value is int or (value is float and is_finite(value) and value == floorf(value))


static func _safe_float(value: float) -> Variant:
	return value if is_finite(value) else null


static func _success(value: Variant) -> Dictionary:
	return {"value": value}


static func _failure(message: String, details: Dictionary = {}) -> Dictionary:
	return Errors.make(
		"PROPERTY_TYPE_MISMATCH",
		message,
		false,
		"Use the JSON shape reported by node_get_properties for this property.",
		details
	)

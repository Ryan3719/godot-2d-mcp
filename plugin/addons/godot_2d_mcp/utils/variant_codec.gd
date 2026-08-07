@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")

const MAX_CONTAINER_ITEMS := 512
const MAX_DEPTH := 8
const MAX_RESOURCE_PATH_LENGTH := 4096


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
			return _decode_array(value, current_value)
		TYPE_DICTIONARY:
			return _decode_dictionary(value, current_value)
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
			return _decode_resource_reference(value, property_info, current_value)

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
			return _serialize_dictionary(value, depth + 1)
		TYPE_OBJECT:
			if value is Resource:
				return {
					"resource_type": value.get_class(),
					"resource_path": value.resource_path,
				}
	return null


static func decode_json_value(value: Variant) -> Dictionary:
	return _decode_json_variant(value)


static func describe_container(value: Variant) -> Variant:
	if value is Array and value.is_typed():
		return {
			"kind": "array",
			"element": _describe_container_type(
				value.get_typed_builtin(), value.get_typed_class_name(), value.get_typed_script()
			),
		}
	if value is Dictionary and value.is_typed():
		return {
			"kind": "dictionary",
			"key": _describe_container_type(
				value.get_typed_key_builtin(),
				value.get_typed_key_class_name(),
				value.get_typed_key_script()
			),
			"value": _describe_container_type(
				value.get_typed_value_builtin(),
				value.get_typed_value_class_name(),
				value.get_typed_value_script()
			),
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


static func _decode_array(value: Variant, current_value: Variant) -> Dictionary:
	if not value is Array or value.size() > MAX_CONTAINER_ITEMS:
		return _failure("Arrays require a bounded JSON array")
	if not current_value is Array or not current_value.is_typed():
		return _success(value.duplicate(true))

	var output := Array(
		[],
		current_value.get_typed_builtin(),
		current_value.get_typed_class_name(),
		current_value.get_typed_script()
	)
	for index in range(value.size()):
		var current_item: Variant = current_value[index] if index < current_value.size() else null
		var decoded := _decode_typed_container_item(
			value[index],
			current_value.get_typed_builtin(),
			current_value.get_typed_class_name(),
			current_value.get_typed_script(),
			current_item
		)
		if decoded.has("_error"):
			decoded["_error"]["details"]["index"] = index
			return decoded
		output.append(decoded["value"])
	return _success(output)


static func _decode_dictionary(value: Variant, current_value: Variant) -> Dictionary:
	if not current_value is Dictionary or not current_value.is_typed():
		if value is Dictionary and value.size() <= MAX_CONTAINER_ITEMS:
			return _success(value.duplicate(true))
		return _failure("Dictionaries require a bounded JSON object")

	var key_type: int = current_value.get_typed_key_builtin()
	var key_class_name: StringName = current_value.get_typed_key_class_name()
	var key_script: Variant = current_value.get_typed_key_script()
	var value_type: int = current_value.get_typed_value_builtin()
	var value_class_name: StringName = current_value.get_typed_value_class_name()
	var value_script: Variant = current_value.get_typed_value_script()
	var output := Dictionary(
		{}, key_type, key_class_name, key_script, value_type, value_class_name, value_script
	)
	if _is_string_dictionary_key(key_type):
		if not value is Dictionary or value.size() > MAX_CONTAINER_ITEMS:
			return _failure("String-keyed typed dictionaries require a bounded JSON object")
		for raw_key in value:
			var decoded_key := _decode_typed_container_item(
				str(raw_key), key_type, key_class_name, key_script, null
			)
			if decoded_key.has("_error"):
				decoded_key["_error"]["details"]["key"] = str(raw_key)
				return decoded_key
			var decoded_value := _decode_typed_container_item(
				value[raw_key], value_type, value_class_name, value_script, null
			)
			if decoded_value.has("_error"):
				decoded_value["_error"]["details"]["key"] = str(raw_key)
				return decoded_value
			output[decoded_key["value"]] = decoded_value["value"]
		return _success(output)

	if not value is Dictionary or not _has_exact_keys(value, ["entries"]):
		return _failure("Non-string-keyed typed dictionaries require exactly an entries array")
	var entries: Variant = value["entries"]
	if not entries is Array or entries.size() > MAX_CONTAINER_ITEMS:
		return _failure("Typed dictionary entries require a bounded JSON array")
	for index in range(entries.size()):
		var entry: Variant = entries[index]
		if not entry is Dictionary or not _has_exact_keys(entry, ["key", "value"]):
			return _failure("Typed dictionary entries require exactly key and value fields", {"index": index})
		var decoded_key := _decode_typed_container_item(
			entry["key"], key_type, key_class_name, key_script, null
		)
		if decoded_key.has("_error"):
			decoded_key["_error"]["details"]["index"] = index
			return decoded_key
		if output.has(decoded_key["value"]):
			return _failure("Typed dictionary entries must not repeat a key", {"index": index})
		var decoded_value := _decode_typed_container_item(
			entry["value"], value_type, value_class_name, value_script, null
		)
		if decoded_value.has("_error"):
			decoded_value["_error"]["details"]["index"] = index
			return decoded_value
		output[decoded_key["value"]] = decoded_value["value"]
	return _success(output)


static func _decode_typed_container_item(
	value: Variant,
	item_variant_type: int,
	item_class_name: StringName,
	typed_script: Variant,
	current_value: Variant
) -> Dictionary:
	if typed_script != null:
		return _failure("Script-constrained typed container items are not supported")
	if item_variant_type == TYPE_NIL:
		return _decode_json_variant(value)
	if item_variant_type == TYPE_OBJECT:
		return _decode_typed_resource_reference(value, item_class_name)
	return decode(value, {"type": item_variant_type}, current_value)


static func _decode_typed_resource_reference(value: Variant, expected_type: StringName) -> Dictionary:
	if value == null:
		return _success(null)
	if expected_type.is_empty() or not ClassDB.class_exists(expected_type):
		return _failure("Typed Object container items require a declared native Resource type")
	if expected_type != &"Resource" and not ClassDB.is_parent_class(expected_type, &"Resource"):
		return _failure("Typed Object container items must be Resources, not scene object references")
	if not value is Dictionary or not _has_exact_keys(value, ["resource_path"]):
		return _failure("Typed Resource container items require null or an object with exactly resource_path")
	var resource_path := str(value["resource_path"]).strip_edges()
	if (
		resource_path.is_empty()
		or resource_path.length() > MAX_RESOURCE_PATH_LENGTH
		or not resource_path.begins_with("res://")
		or resource_path.contains("/../")
		or resource_path.ends_with("/..")
	):
		return _failure("resource_path must be a bounded project-local res:// path")
	var resource := ResourceLoader.load(resource_path)
	if resource == null or not resource is Resource:
		return _failure("resource_path does not load a Godot Resource: %s" % resource_path)
	if not resource.is_class(expected_type):
		return _failure(
			"resource_path must load %s, received %s" % [expected_type, resource.get_class()]
		)
	return _success(resource)


static func _decode_json_variant(value: Variant, depth: int = 0) -> Dictionary:
	if depth > MAX_DEPTH:
		return _failure("JSON container nesting exceeds the supported depth")
	if value == null or value is bool or value is String:
		return _success(value)
	if _is_number(value):
		if value is float and not is_finite(value):
			return _failure("JSON numbers must be finite")
		return _success(value)
	if value is Array:
		if value.size() > MAX_CONTAINER_ITEMS:
			return _failure("JSON arrays must be bounded")
		var output: Array = []
		for index in range(value.size()):
			var decoded := _decode_json_variant(value[index], depth + 1)
			if decoded.has("_error"):
				decoded["_error"]["details"]["index"] = index
				return decoded
			output.append(decoded["value"])
		return _success(output)
	if value is Dictionary:
		if value.size() > MAX_CONTAINER_ITEMS:
			return _failure("JSON objects must be bounded")
		var output := {}
		for raw_key in value:
			var decoded := _decode_json_variant(value[raw_key], depth + 1)
			if decoded.has("_error"):
				decoded["_error"]["details"]["key"] = str(raw_key)
				return decoded
			output[str(raw_key)] = decoded["value"]
		return _success(output)
	return _failure("Typed Variant container items must be JSON-compatible values")


static func _serialize_dictionary(value: Dictionary, depth: int) -> Variant:
	var use_entries := false
	if value.is_typed() and not _is_string_dictionary_key(value.get_typed_key_builtin()):
		use_entries = true
	if not use_entries:
		for key in value:
			if not (key is String) and not (key is StringName):
				use_entries = true
				break
	if use_entries:
		var entries: Array = []
		for key in value:
			if entries.size() >= MAX_CONTAINER_ITEMS:
				break
			entries.append(
				{
					"key": serialize(key, depth + 1),
					"value": serialize(value[key], depth + 1),
				}
			)
		return {"entries": entries}
	var output := {}
	for key in value:
		if output.size() >= MAX_CONTAINER_ITEMS:
			break
		output[str(key)] = serialize(value[key], depth + 1)
	return output


static func _is_string_dictionary_key(item_variant_type: int) -> bool:
	return item_variant_type == TYPE_STRING or item_variant_type == TYPE_STRING_NAME


static func _describe_container_type(
	item_variant_type: int, item_class_name: StringName, typed_script: Variant
) -> Dictionary:
	var description := {
		"type": "Variant" if item_variant_type == TYPE_NIL else type_string(item_variant_type)
	}
	if not item_class_name.is_empty():
		description["class_name"] = String(item_class_name)
	if typed_script != null:
		description["script_constrained"] = true
	return description


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


static func _decode_resource_reference(
	value: Variant, property_info: Dictionary, current_value: Variant
) -> Dictionary:
	if value == null:
		return _success(null)
	if not value is Dictionary or not _has_exact_keys(value, ["resource_path"]):
		return _failure("Resource properties require null or an object with exactly resource_path")
	var resource_path := str(value["resource_path"]).strip_edges()
	if (
		resource_path.is_empty()
		or resource_path.length() > MAX_RESOURCE_PATH_LENGTH
		or not resource_path.begins_with("res://")
		or resource_path.contains("/../")
		or resource_path.ends_with("/..")
	):
		return _failure("resource_path must be a bounded project-local res:// path")
	if int(property_info.get("hint", PROPERTY_HINT_NONE)) != PROPERTY_HINT_RESOURCE_TYPE:
		return _failure("Only Godot Resource properties accept resource_path references")
	var resource := ResourceLoader.load(resource_path)
	if resource == null or not resource is Resource:
		return _failure("resource_path does not load a Godot Resource: %s" % resource_path)
	var expected_type := str(property_info.get("hint_string", "")).strip_edges()
	if expected_type.is_empty() and current_value is Resource:
		expected_type = current_value.get_class()
	if expected_type.is_empty() or not resource.is_class(expected_type):
		return _failure(
			"resource_path must load %s, received %s" % [
				expected_type if not expected_type.is_empty() else "the declared resource type",
				resource.get_class(),
			]
		)
	return _success(resource)


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

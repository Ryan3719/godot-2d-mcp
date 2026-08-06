@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_CONFIGURATION_PROPERTIES := 32
const CAMERA_PROPERTIES := [
	"anchor_mode", "custom_viewport_path", "drag_bottom_margin", "drag_horizontal_enabled",
	"drag_horizontal_offset", "drag_left_margin", "drag_right_margin", "drag_top_margin",
	"drag_vertical_enabled", "drag_vertical_offset", "editor_draw_drag_margin", "editor_draw_limits",
	"editor_draw_screen", "enabled", "ignore_rotation", "limit_bottom", "limit_enabled",
	"limit_left", "limit_right", "limit_smoothed", "limit_top", "offset",
	"position_smoothing_enabled", "position_smoothing_speed", "process_callback",
	"rotation_smoothing_enabled", "rotation_smoothing_speed", "zoom",
]
const PARALLAX_PROPERTIES := [
	"autoscroll", "follow_viewport", "ignore_camera_scroll", "limit_begin", "limit_end",
	"repeat_size", "repeat_times", "screen_offset", "scroll_offset", "scroll_scale",
]
const CANVAS_LAYER_PROPERTIES := [
	"custom_viewport_path", "follow_viewport_enabled", "follow_viewport_scale", "layer",
	"offset", "rotation", "scale", "transform", "visible",
]
const ENUM_OPTIONS := {
	"anchor_mode": {
		"fixed_top_left": Camera2D.ANCHOR_MODE_FIXED_TOP_LEFT,
		"drag_center": Camera2D.ANCHOR_MODE_DRAG_CENTER,
	},
	"process_callback": {
		"physics": Camera2D.CAMERA2D_PROCESS_PHYSICS,
		"idle": Camera2D.CAMERA2D_PROCESS_IDLE,
	},
}
const CUSTOM_VIEWPORT_PATH := "custom_viewport_path"

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_camera_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_typed_node(params, "Camera2D", false)
	if resolved.has("_error"):
		return resolved
	return _camera_response(resolved["node"] as Camera2D, resolved["scene_root"])


func set_camera_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_typed_node(params, "Camera2D")
	if resolved.has("_error"):
		return resolved
	var camera: Camera2D = resolved["node"]
	var parsed := _parse_configuration(params, camera, CAMERA_PROPERTIES, resolved["scene_root"])
	if parsed.has("_error"):
		return parsed
	var validation := _validate_camera_updates(camera, parsed["updates"])
	if validation.has("_error"):
		return validation
	return _commit_configuration(
		camera,
		resolved["scene_root"],
		CAMERA_PROPERTIES,
		parsed["updates"],
		"Update Camera2D %s" % camera.name,
		_camera_response
	)


func get_parallax_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_typed_node(params, "Parallax2D", false)
	if resolved.has("_error"):
		return resolved
	return _configuration_response(resolved["node"], resolved["scene_root"], PARALLAX_PROPERTIES)


func set_parallax_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_typed_node(params, "Parallax2D")
	if resolved.has("_error"):
		return resolved
	var parallax: Parallax2D = resolved["node"]
	var parsed := _parse_configuration(params, parallax, PARALLAX_PROPERTIES, resolved["scene_root"])
	if parsed.has("_error"):
		return parsed
	var validation := _validate_parallax_updates(parallax, parsed["updates"])
	if validation.has("_error"):
		return validation
	return _commit_configuration(
		parallax,
		resolved["scene_root"],
		PARALLAX_PROPERTIES,
		parsed["updates"],
		"Update Parallax2D %s" % parallax.name,
		_configuration_response
	)


func get_canvas_layer(params: Dictionary) -> Dictionary:
	var resolved := _resolve_typed_node(params, "CanvasLayer", false)
	if resolved.has("_error"):
		return resolved
	return _canvas_layer_response(resolved["node"] as CanvasLayer, resolved["scene_root"])


func set_canvas_layer(params: Dictionary) -> Dictionary:
	var resolved := _resolve_typed_node(params, "CanvasLayer")
	if resolved.has("_error"):
		return resolved
	var canvas_layer: CanvasLayer = resolved["node"]
	var parsed := _parse_configuration(params, canvas_layer, CANVAS_LAYER_PROPERTIES, resolved["scene_root"])
	if parsed.has("_error"):
		return parsed
	var validation := _validate_canvas_layer_updates(canvas_layer, parsed["updates"])
	if validation.has("_error"):
		return validation
	return _commit_configuration(
		canvas_layer,
		resolved["scene_root"],
		CANVAS_LAYER_PROPERTIES,
		parsed["updates"],
		"Update CanvasLayer %s" % canvas_layer.name,
		_canvas_layer_response
	)


func _resolve_typed_node(
	params: Dictionary,
	expected_type: String,
	require_writable: bool = true
) -> Dictionary:
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
	if node.get_class() != expected_type:
		return Errors.make(
			"%s_REQUIRED" % expected_type.to_upper(),
			"Node '%s' is %s, not %s" % [node.name, node.get_class(), expected_type],
			false,
			"Target a %s node." % expected_type
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit node '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned node."
		)
	return {"node": node, "scene_root": scene_root}


func _camera_response(camera: Camera2D, scene_root: Node, _properties: Array = []) -> Dictionary:
	var response := _configuration_response(camera, scene_root, CAMERA_PROPERTIES)
	response["current"] = camera.is_current()
	response["target_position"] = VariantCodec.serialize(camera.get_target_position())
	response["screen_center_position"] = VariantCodec.serialize(camera.get_screen_center_position())
	response["screen_rotation"] = camera.get_screen_rotation()
	return response


func _canvas_layer_response(
	canvas_layer: CanvasLayer, scene_root: Node, _properties: Array = []
) -> Dictionary:
	var response := _configuration_response(canvas_layer, scene_root, CANVAS_LAYER_PROPERTIES)
	response["final_transform"] = VariantCodec.serialize(canvas_layer.get_final_transform())
	return response


func _configuration_response(node: Node, scene_root: Node, properties: Array) -> Dictionary:
	return {
		"path": ScenePath.from_node(node, scene_root),
		"type": node.get_class(),
		"configuration": _serialize_configuration(node, scene_root, properties),
		"supported_properties": properties.duplicate(),
	}


func _serialize_configuration(node: Node, scene_root: Node, properties: Array) -> Dictionary:
	var configuration := {}
	for property_name_value in properties:
		var property_name := str(property_name_value)
		if property_name == CUSTOM_VIEWPORT_PATH:
			configuration[property_name] = _serialize_custom_viewport(node, scene_root)
			continue
		var value = node.get(property_name)
		configuration[property_name] = _serialize_configuration_value(property_name, value)
	return configuration


func _serialize_configuration_value(property_name: String, value: Variant) -> Variant:
	if ENUM_OPTIONS.has(property_name):
		var options: Dictionary = ENUM_OPTIONS[property_name]
		for label in options:
			if int(options[label]) == int(value):
				return label
	return VariantCodec.serialize(value)


func _serialize_custom_viewport(node: Node, scene_root: Node) -> String:
	var viewport: Node = node.get_custom_viewport()
	if viewport == null or not scene_root.is_ancestor_of(viewport):
		return ""
	return ScenePath.from_node(viewport, scene_root)


func _parse_configuration(
	params: Dictionary,
	node: Node,
	allowed_properties: Array,
	scene_root: Node
) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() \
		or raw_properties.size() > MAX_CONFIGURATION_PROPERTIES:
		return Errors.make(
			"INVALID_VIEWPORT_CONFIGURATION",
			"properties must be a non-empty object containing at most %d entries" % MAX_CONFIGURATION_PROPERTIES
		)
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String:
			return Errors.make("INVALID_VIEWPORT_CONFIGURATION", "property names must be strings")
		var property_name: String = raw_name
		if not allowed_properties.has(property_name):
			return Errors.make(
				"UNSUPPORTED_VIEWPORT_PROPERTY",
				"Property '%s' is not supported for %s" % [property_name, node.get_class()],
				false,
				"Call the corresponding *_get tool to inspect supported_properties."
			)
		if property_name == CUSTOM_VIEWPORT_PATH:
			var viewport_result := _parse_custom_viewport(raw_properties[raw_name], scene_root)
			if viewport_result.has("_error"):
				return viewport_result
			updates["custom_viewport"] = viewport_result["viewport"]
			continue
		var decoded := _decode_configuration_value(node, property_name, raw_properties[raw_name])
		if decoded.has("_error"):
			return decoded
		updates[property_name] = decoded["value"]
	return {"updates": updates}


func _parse_custom_viewport(raw_value: Variant, scene_root: Node) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_VIEWPORT_PATH", "custom_viewport_path must be a scene path or an empty string")
	var path: String = (raw_value as String).strip_edges()
	if path.is_empty():
		return {"viewport": null}
	var node := ScenePath.resolve(path, scene_root)
	if node == null or not node is Viewport:
		return Errors.make(
			"VIEWPORT_NOT_FOUND",
			"custom_viewport_path must identify a Viewport node in the current scene"
		)
	return {"viewport": node as Viewport}


func _decode_configuration_value(node: Node, property_name: String, raw_value: Variant) -> Dictionary:
	if ENUM_OPTIONS.has(property_name) and raw_value is String:
		var label: String = raw_value.to_lower().strip_edges()
		var options: Dictionary = ENUM_OPTIONS[property_name]
		if not options.has(label):
			return Errors.make(
				"INVALID_VIEWPORT_ENUM",
				"%s must use one of: %s" % [property_name, ", ".join(options.keys())]
			)
		return {"value": options[label]}
	var property_info := _find_property_info(node, property_name)
	if property_info.is_empty():
		return Errors.make("VIEWPORT_PROPERTY_NOT_FOUND", "Property '%s' is not available" % property_name)
	var decoded := VariantCodec.decode(raw_value, property_info, node.get(property_name))
	if decoded.has("_error"):
		return Errors.make(
			"VIEWPORT_PROPERTY_TYPE_MISMATCH",
			decoded["_error"]["message"],
			false,
			"Use the JSON values returned by the corresponding *_get tool.",
			{"property": property_name}
		)
	if ENUM_OPTIONS.has(property_name) and not _enum_contains_value(ENUM_OPTIONS[property_name], decoded["value"]):
		return Errors.make("INVALID_VIEWPORT_ENUM", "%s uses an unsupported enum value" % property_name)
	return decoded


func _commit_configuration(
	node: Node,
	scene_root: Node,
	properties: Array,
	updates: Dictionary,
	action_name: String,
	response_builder: Callable
) -> Dictionary:
	var changed := {}
	for property_name_value in updates:
		var property_name := str(property_name_value)
		var old_value = node.get_custom_viewport() if property_name == "custom_viewport" else node.get(property_name)
		if old_value != updates[property_name]:
			changed[property_name] = updates[property_name]
	if changed.is_empty():
		var unchanged: Dictionary = response_builder.call(node, scene_root, properties)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action("Godot 2D MCP: %s" % action_name, UndoRedo.MERGE_DISABLE, scene_root, true)
	for property_name_value in changed:
		var property_name := str(property_name_value)
		var old_value = node.get_custom_viewport() if property_name == "custom_viewport" else node.get(property_name)
		if property_name == "custom_viewport":
			# Godot's setter rejects null even though a non-Viewport Node clears the binding.
			var do_viewport: Node = changed[property_name] if changed[property_name] != null else node
			var undo_viewport: Node = old_value if old_value != null else node
			_undo_redo.add_do_method(node, "set_custom_viewport", do_viewport)
			_undo_redo.add_undo_method(node, "set_custom_viewport", undo_viewport)
		else:
			_undo_redo.add_do_property(node, property_name, changed[property_name])
			_undo_redo.add_undo_property(node, property_name, old_value)
	_undo_redo.commit_action()
	var result: Dictionary = response_builder.call(node, scene_root, properties)
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _validate_camera_updates(camera: Camera2D, updates: Dictionary) -> Dictionary:
	for property_name in [
		"drag_bottom_margin", "drag_left_margin", "drag_right_margin", "drag_top_margin",
	]:
		if updates.has(property_name) and not _is_between(float(updates[property_name]), 0.0, 1.0):
			return _invalid_configuration("%s must be between 0 and 1" % property_name)
	for property_name in ["drag_horizontal_offset", "drag_vertical_offset"]:
		if updates.has(property_name) and not _is_between(float(updates[property_name]), -1.0, 1.0):
			return _invalid_configuration("%s must be between -1 and 1" % property_name)
	for property_name in ["position_smoothing_speed", "rotation_smoothing_speed"]:
		if updates.has(property_name) and float(updates[property_name]) <= 0.0:
			return _invalid_configuration("%s must be greater than zero" % property_name)
	var limit_left := int(updates.get("limit_left", camera.limit_left))
	var limit_right := int(updates.get("limit_right", camera.limit_right))
	var limit_top := int(updates.get("limit_top", camera.limit_top))
	var limit_bottom := int(updates.get("limit_bottom", camera.limit_bottom))
	if limit_left > limit_right or limit_top > limit_bottom:
		return _invalid_configuration("limit_left/top cannot exceed limit_right/bottom")
	var zoom: Vector2 = updates.get("zoom", camera.zoom)
	if not is_finite(zoom.x) or not is_finite(zoom.y) or zoom.x <= 0.0 or zoom.y <= 0.0:
		return _invalid_configuration("zoom components must be finite and greater than zero")
	return {}


func _validate_parallax_updates(parallax: Parallax2D, updates: Dictionary) -> Dictionary:
	var limit_begin: Vector2 = updates.get("limit_begin", parallax.limit_begin)
	var limit_end: Vector2 = updates.get("limit_end", parallax.limit_end)
	if limit_begin.x >= limit_end.x or limit_begin.y >= limit_end.y:
		return _invalid_configuration("limit_begin must be lower than limit_end on both axes")
	var repeat_size: Vector2 = updates.get("repeat_size", parallax.repeat_size)
	if repeat_size.x < 0.0 or repeat_size.y < 0.0:
		return _invalid_configuration("repeat_size components must be greater than or equal to zero")
	var repeat_times := int(updates.get("repeat_times", parallax.repeat_times))
	if repeat_times < 1 or repeat_times > 128:
		return _invalid_configuration("repeat_times must be an integer between 1 and 128")
	return {}


func _validate_canvas_layer_updates(canvas_layer: CanvasLayer, updates: Dictionary) -> Dictionary:
	if updates.has("transform") and (
		updates.has("offset") or updates.has("rotation") or updates.has("scale")
	):
		return _invalid_configuration("transform cannot be combined with offset, rotation, or scale")
	var layer := int(updates.get("layer", canvas_layer.layer))
	if layer < -2147483648 or layer > 2147483647:
		return _invalid_configuration("layer must fit in a signed 32-bit integer")
	if updates.has("transform"):
		var transform: Transform2D = updates["transform"]
		if not (
			is_finite(transform.x.x) and is_finite(transform.x.y)
			and is_finite(transform.y.x) and is_finite(transform.y.y)
			and is_finite(transform.origin.x) and is_finite(transform.origin.y)
		) or is_zero_approx(transform.determinant()):
			return _invalid_configuration("transform must be finite and have a non-zero determinant")
	var scale: Vector2 = updates.get("scale", canvas_layer.scale)
	if not is_finite(scale.x) or not is_finite(scale.y) or is_zero_approx(scale.x) or is_zero_approx(scale.y):
		return _invalid_configuration("scale components must be finite and non-zero")
	var follow_scale := float(updates.get("follow_viewport_scale", canvas_layer.follow_viewport_scale))
	if not is_finite(follow_scale) or is_zero_approx(follow_scale):
		return _invalid_configuration("follow_viewport_scale must be finite and non-zero")
	return {}


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


func _is_between(value: float, minimum: float, maximum: float) -> bool:
	return is_finite(value) and value >= minimum and value <= maximum


func _invalid_configuration(message: String) -> Dictionary:
	return Errors.make("INVALID_VIEWPORT_CONFIGURATION", message)

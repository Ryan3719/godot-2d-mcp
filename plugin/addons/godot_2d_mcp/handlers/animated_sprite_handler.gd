@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_PROPERTIES := 16
const MAX_ANIMATIONS := 128
const MAX_FRAMES := 512
const MAX_PATH_LENGTH := 4096
const MAX_COORDINATE := 1_000_000.0
const NODE_PROPERTIES := [
	"sprite_frames_path", "animation", "autoplay", "frame", "frame_progress", "speed_scale",
	"centered", "offset", "flip_h", "flip_v",
]
const NODE_PROPERTY_ORDER := [
	"sprite_frames", "animation", "autoplay", "frame", "frame_progress", "speed_scale",
	"centered", "offset", "flip_h", "flip_v",
]
const LOOP_MODES := {
	"none": 0,
	"linear": 1,
	"pingpong": 2,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_animated_sprite_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_sprite(params, false)
	if resolved.has("_error"):
		return resolved
	return _sprite_response(resolved["sprite"], resolved["scene_root"])


func set_animated_sprite_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_sprite(params)
	if resolved.has("_error"):
		return resolved
	var sprite: AnimatedSprite2D = resolved["sprite"]
	var parsed := _parse_node_updates(params, sprite)
	if parsed.has("_error"):
		return parsed
	var changed := _changed_properties(sprite, NODE_PROPERTY_ORDER, parsed["updates"])
	if changed.is_empty():
		var unchanged := _sprite_response(sprite, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_commit_property_updates(
		sprite,
		resolved["scene_root"],
		NODE_PROPERTY_ORDER,
		changed,
		"Update AnimatedSprite2D %s" % sprite.name
	)
	var result := _sprite_response(sprite, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func get_sprite_frames(params: Dictionary) -> Dictionary:
	var resolved := _resolve_sprite(params, false)
	if resolved.has("_error"):
		return resolved
	var page := _parse_frame_page(params)
	if page.has("_error"):
		return page
	var selected := _resolve_selected_animation(resolved["sprite"], params.get("animation", ""))
	if selected.has("_error"):
		return selected
	return _sprite_frames_response(
		resolved["sprite"], resolved["scene_root"], selected["animation"], page["offset"], page["limit"]
	)


func upsert_sprite_frames_animation(params: Dictionary) -> Dictionary:
	var resolved := _resolve_sprite(params)
	if resolved.has("_error"):
		return resolved
	var animation_result := _parse_animation_name(params.get("animation", null), "animation")
	if animation_result.has("_error"):
		return animation_result
	var speed_result := _parse_optional_speed(params)
	if speed_result.has("_error"):
		return speed_result
	var loop_result := _parse_optional_loop_mode(params)
	if loop_result.has("_error"):
		return loop_result
	var frames_result := _parse_optional_frames(params)
	if frames_result.has("_error"):
		return frames_result
	var sprite: AnimatedSprite2D = resolved["sprite"]
	var current: SpriteFrames = sprite.sprite_frames
	var animation_name: StringName = animation_result["name"]
	if current != null and not current.has_animation(animation_name) \
		and current.get_animation_names().size() >= MAX_ANIMATIONS:
		return Errors.make(
			"SPRITE_FRAMES_ANIMATION_LIMIT_EXCEEDED",
			"SpriteFrames cannot contain more than %d animations" % MAX_ANIMATIONS,
			false,
			"Reduce the SpriteFrames resource before editing it through MCP."
		)
	if _upsert_is_unchanged(current, animation_name, speed_result, loop_result, frames_result):
		var unchanged := _sprite_frames_response(sprite, resolved["scene_root"], animation_name, 0, 100)
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	var duplicate_result := _duplicate_or_create_sprite_frames(current)
	if duplicate_result.has("_error"):
		return duplicate_result
	var replacement: SpriteFrames = duplicate_result["sprite_frames"]
	if not replacement.has_animation(animation_name):
		replacement.add_animation(animation_name)
	if speed_result["provided"]:
		replacement.set_animation_speed(animation_name, speed_result["speed"])
	if loop_result["provided"]:
		var set_loop_result := _set_animation_loop_mode(
			replacement, animation_name, loop_result["loop_mode"]
		)
		if set_loop_result.has("_error"):
			return set_loop_result
	if frames_result["provided"]:
		replacement.clear(animation_name)
		for frame_value in frames_result["frames"]:
			var frame: Dictionary = frame_value
			replacement.add_frame(animation_name, frame["texture"], frame["duration"])
	var updates := {"sprite_frames": replacement}
	_apply_frame_bounds(sprite, replacement, animation_name, updates)
	_commit_property_updates(
		sprite,
		resolved["scene_root"],
		NODE_PROPERTY_ORDER,
		updates,
		"Update SpriteFrames animation %s on %s" % [animation_name, sprite.name]
	)
	var result := _sprite_frames_response(sprite, resolved["scene_root"], animation_name, 0, 100)
	result["changed"] = true
	result["created"] = current == null
	result["copied_external_resource"] = current != null and not current.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func rename_sprite_frames_animation(params: Dictionary) -> Dictionary:
	var resolved := _resolve_sprite(params)
	if resolved.has("_error"):
		return resolved
	var current_name_result := _parse_animation_name(params.get("animation", null), "animation")
	if current_name_result.has("_error"):
		return current_name_result
	var new_name_result := _parse_animation_name(params.get("new_name", null), "new_name")
	if new_name_result.has("_error"):
		return new_name_result
	var current_name: StringName = current_name_result["name"]
	var new_name: StringName = new_name_result["name"]
	if current_name == new_name:
		return Errors.make("SPRITE_FRAMES_RENAME_NOOP", "animation and new_name must differ")
	var sprite: AnimatedSprite2D = resolved["sprite"]
	var current: SpriteFrames = sprite.sprite_frames
	if current == null:
		return _sprite_frames_not_assigned()
	if not current.has_animation(current_name):
		return _animation_not_found(current_name)
	if current.has_animation(new_name):
		return Errors.make("SPRITE_FRAMES_ANIMATION_EXISTS", "Animation '%s' already exists" % new_name)
	var duplicate_result := _duplicate_or_create_sprite_frames(current)
	if duplicate_result.has("_error"):
		return duplicate_result
	var replacement: SpriteFrames = duplicate_result["sprite_frames"]
	replacement.rename_animation(current_name, new_name)
	var updates := {"sprite_frames": replacement}
	if sprite.animation == current_name:
		updates["animation"] = new_name
	if sprite.autoplay == current_name:
		updates["autoplay"] = new_name
	_commit_property_updates(
		sprite,
		resolved["scene_root"],
		NODE_PROPERTY_ORDER,
		updates,
		"Rename SpriteFrames animation %s on %s" % [current_name, sprite.name]
	)
	var result := _sprite_frames_response(sprite, resolved["scene_root"], new_name, 0, 100)
	result["renamed"] = true
	result["copied_external_resource"] = not current.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func remove_sprite_frames_animation(params: Dictionary) -> Dictionary:
	var resolved := _resolve_sprite(params)
	if resolved.has("_error"):
		return resolved
	var animation_result := _parse_animation_name(params.get("animation", null), "animation")
	if animation_result.has("_error"):
		return animation_result
	var animation_name: StringName = animation_result["name"]
	var sprite: AnimatedSprite2D = resolved["sprite"]
	var current: SpriteFrames = sprite.sprite_frames
	if current == null:
		return _sprite_frames_not_assigned()
	if not current.has_animation(animation_name):
		return _animation_not_found(animation_name)
	if current.get_animation_names().size() <= 1:
		return Errors.make(
			"SPRITE_FRAMES_LAST_ANIMATION",
			"Cannot remove the only SpriteFrames animation",
			false,
			"Keep at least one animation so AnimatedSprite2D remains in a valid editable state."
		)
	var duplicate_result := _duplicate_or_create_sprite_frames(current)
	if duplicate_result.has("_error"):
		return duplicate_result
	var replacement: SpriteFrames = duplicate_result["sprite_frames"]
	replacement.remove_animation(animation_name)
	var fallback := _first_animation_name(replacement)
	if fallback.is_empty():
		return Errors.make("SPRITE_FRAMES_NO_FALLBACK", "SpriteFrames has no remaining animation")
	var updates := {"sprite_frames": replacement}
	if sprite.animation == animation_name:
		updates["animation"] = fallback
		updates["frame"] = 0
		updates["frame_progress"] = 0.0
	if sprite.autoplay == animation_name:
		updates["autoplay"] = StringName()
	_commit_property_updates(
		sprite,
		resolved["scene_root"],
		NODE_PROPERTY_ORDER,
		updates,
		"Remove SpriteFrames animation %s on %s" % [animation_name, sprite.name]
	)
	var result := _sprite_frames_response(sprite, resolved["scene_root"], fallback, 0, 100)
	result["removed"] = true
	result["copied_external_resource"] = not current.resource_path.is_empty()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_sprite(params: Dictionary, require_writable: bool = true) -> Dictionary:
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
	if not node is AnimatedSprite2D:
		return Errors.make(
			"ANIMATED_SPRITE_2D_REQUIRED",
			"Node '%s' is %s, not AnimatedSprite2D" % [node.name, node.get_class()],
			false,
			"Target an AnimatedSprite2D node."
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit node '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned node."
		)
	return {"sprite": node as AnimatedSprite2D, "scene_root": scene_root}


func _parse_node_updates(params: Dictionary, sprite: AnimatedSprite2D) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() or raw_properties.size() > MAX_PROPERTIES:
		return _invalid_configuration(
			"properties must be a non-empty object containing at most %d entries" % MAX_PROPERTIES
		)
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String or not NODE_PROPERTIES.has(raw_name):
			return Errors.make(
				"UNSUPPORTED_ANIMATED_SPRITE_PROPERTY",
				"Unsupported AnimatedSprite2D property: %s" % str(raw_name),
				false,
				"Call animated_sprite_2d_get to inspect supported_properties."
			)
		var parsed := _parse_node_value(raw_name, raw_properties[raw_name])
		if parsed.has("_error"):
			return parsed
		updates[parsed["property_name"]] = parsed["value"]
	var validation := _validate_node_configuration(sprite, updates)
	if validation.has("_error"):
		return validation
	return {"updates": updates}


func _parse_node_value(name: String, raw_value: Variant) -> Dictionary:
	match name:
		"sprite_frames_path":
			return _load_optional_resource(raw_value, "SpriteFrames", "sprite_frames_path", "sprite_frames")
		"animation":
			return _parse_animation_name(raw_value, name, "animation")
		"autoplay":
			return _parse_optional_animation_name(raw_value, name, "autoplay")
		"frame":
			return _parse_integer(raw_value, name, 0, MAX_FRAMES - 1)
		"frame_progress":
			return _parse_number(raw_value, name, 0.0, 1.0)
		"speed_scale":
			return _parse_number(raw_value, name, -64.0, 64.0)
		"centered", "flip_h", "flip_v":
			return _parse_bool(raw_value, name)
		"offset":
			return _parse_vector2(raw_value, name)
	return _invalid_configuration("Unsupported AnimatedSprite2D property: %s" % name)


func _validate_node_configuration(sprite: AnimatedSprite2D, updates: Dictionary) -> Dictionary:
	var frames: SpriteFrames = updates.get("sprite_frames", sprite.sprite_frames)
	var state_properties := ["animation", "autoplay", "frame", "frame_progress"]
	if frames == null:
		for property_name in state_properties:
			if updates.has(property_name):
				return _invalid_configuration("%s requires an assigned SpriteFrames resource" % property_name)
		return {}
	if frames.get_animation_names().size() > MAX_ANIMATIONS:
		return Errors.make(
			"SPRITE_FRAMES_ANIMATION_LIMIT_EXCEEDED",
			"SpriteFrames has more than %d animations" % MAX_ANIMATIONS,
			false,
			"Reduce the SpriteFrames resource before editing it through MCP."
		)
	var animation: StringName = updates.get("animation", sprite.animation)
	if not frames.has_animation(animation):
		if updates.has("animation"):
			return _animation_not_found(animation)
		animation = _first_animation_name(frames)
		if animation.is_empty():
			return Errors.make("SPRITE_FRAMES_EMPTY", "SpriteFrames has no animations")
		updates["animation"] = animation
	var autoplay: StringName = updates.get("autoplay", sprite.autoplay)
	if not autoplay.is_empty() and not frames.has_animation(autoplay):
		if updates.has("autoplay"):
			return _animation_not_found(autoplay)
		updates["autoplay"] = StringName()
	var frame_count := frames.get_frame_count(animation)
	if frame_count > MAX_FRAMES:
		return Errors.make(
			"SPRITE_FRAMES_FRAME_LIMIT_EXCEEDED",
			"Animation '%s' has more than %d frames" % [animation, MAX_FRAMES],
			false,
			"Reduce the animation frame count before editing it through MCP."
		)
	var frame := int(updates.get("frame", sprite.frame))
	if frame_count == 0:
		if frame != 0:
			return _invalid_configuration("frame must be 0 when the selected animation has no frames")
	elif frame >= frame_count:
		return _invalid_configuration(
			"frame must be between 0 and %d for animation '%s'" % [frame_count - 1, animation]
		)
	if not updates.has("frame") and sprite.frame != frame and frame_count == 0:
		updates["frame"] = 0
	return {}


func _parse_frame_page(params: Dictionary) -> Dictionary:
	var offset_value: Variant = params.get("frame_offset", 0)
	var limit_value: Variant = params.get("frame_limit", 100)
	if not _is_integer(offset_value) or int(offset_value) < 0:
		return _invalid_configuration("frame_offset must be a non-negative integer")
	if not _is_integer(limit_value) or int(limit_value) < 1 or int(limit_value) > 256:
		return _invalid_configuration("frame_limit must be an integer between 1 and 256")
	return {"offset": int(offset_value), "limit": int(limit_value)}


func _resolve_selected_animation(sprite: AnimatedSprite2D, raw_animation: Variant) -> Dictionary:
	var frames: SpriteFrames = sprite.sprite_frames
	if frames == null:
		return {"animation": StringName()}
	var requested := str(raw_animation).strip_edges()
	var animation: StringName = StringName(requested) if not requested.is_empty() else sprite.animation
	if animation.is_empty() or not frames.has_animation(animation):
		animation = _first_animation_name(frames)
	if animation.is_empty():
		return Errors.make("SPRITE_FRAMES_EMPTY", "SpriteFrames has no animations")
	return {"animation": animation}


func _parse_optional_speed(params: Dictionary) -> Dictionary:
	if not params.has("speed"):
		return {"provided": false}
	var parsed := _parse_number(params["speed"], "speed", 0.0, 1_000.0)
	if parsed.has("_error"):
		return parsed
	return {"provided": true, "speed": parsed["value"]}


func _parse_optional_loop_mode(params: Dictionary) -> Dictionary:
	if not params.has("loop_mode"):
		return {"provided": false}
	if not params["loop_mode"] is String:
		return _invalid_configuration("loop_mode must be none, linear, or pingpong")
	var name := str(params["loop_mode"]).strip_edges().to_lower()
	if not LOOP_MODES.has(name):
		return _invalid_configuration("loop_mode must be none, linear, or pingpong")
	return {"provided": true, "loop_mode": LOOP_MODES[name]}


func _parse_optional_frames(params: Dictionary) -> Dictionary:
	if not params.has("frames"):
		return {"provided": false}
	var raw_frames: Variant = params["frames"]
	if not raw_frames is Array or raw_frames.size() > MAX_FRAMES:
		return _invalid_configuration("frames must contain at most %d entries" % MAX_FRAMES)
	var frames: Array[Dictionary] = []
	for index in raw_frames.size():
		var raw_frame: Variant = raw_frames[index]
		if not raw_frame is Dictionary or not raw_frame.has("texture_path") \
			or raw_frame.keys().any(func(key): return key not in ["texture_path", "duration"]):
			return _invalid_configuration(
				"frames[%d] must contain texture_path and optional duration" % index
			)
		var resource_result := _load_required_resource(
			raw_frame["texture_path"], "Texture2D", "frames[%d].texture_path" % index
		)
		if resource_result.has("_error"):
			return resource_result
		var duration := 1.0
		if raw_frame.has("duration"):
			var duration_result := _parse_number(raw_frame["duration"], "frames[%d].duration" % index, 0.001, 3600.0)
			if duration_result.has("_error"):
				return duration_result
			duration = duration_result["value"]
		frames.append({"texture": resource_result["resource"], "duration": duration})
	return {"provided": true, "frames": frames}


func _upsert_is_unchanged(
	frames: SpriteFrames, animation: StringName, speed_result: Dictionary, loop_result: Dictionary, frames_result: Dictionary
) -> bool:
	if frames == null or not frames.has_animation(animation):
		return false
	if speed_result["provided"] and not is_equal_approx(frames.get_animation_speed(animation), speed_result["speed"]):
		return false
	if loop_result["provided"] and _get_animation_loop_mode(frames, animation) != loop_result["loop_mode"]:
		return false
	if not frames_result["provided"]:
		return true
	var expected: Array = frames_result["frames"]
	if frames.get_frame_count(animation) != expected.size():
		return false
	for index in expected.size():
		var frame: Dictionary = expected[index]
		if frames.get_frame_texture(animation, index) != frame["texture"] \
			or not is_equal_approx(frames.get_frame_duration(animation, index), frame["duration"]):
			return false
	return true


func _duplicate_or_create_sprite_frames(current: SpriteFrames) -> Dictionary:
	if current == null:
		return {"sprite_frames": SpriteFrames.new()}
	var duplicated := current.duplicate(true)
	if not duplicated is SpriteFrames:
		return Errors.make(
			"SPRITE_FRAMES_DUPLICATION_FAILED",
			"Unable to duplicate the current SpriteFrames resource safely"
		)
	return {"sprite_frames": duplicated as SpriteFrames}


func _apply_frame_bounds(sprite: AnimatedSprite2D, frames: SpriteFrames, animation: StringName, updates: Dictionary) -> void:
	if sprite.animation != animation:
		return
	var count := frames.get_frame_count(animation)
	if count == 0 and sprite.frame != 0:
		updates["frame"] = 0
	elif count > 0 and sprite.frame >= count:
		updates["frame"] = count - 1


func _commit_property_updates(
	sprite: AnimatedSprite2D, scene_root: Node, order: Array, updates: Dictionary, action_label: String
) -> void:
	_undo_redo.create_action("Godot 2D MCP: %s" % action_label, UndoRedo.MERGE_DISABLE, scene_root, true)
	for property_name_value in order:
		var property_name := str(property_name_value)
		if not updates.has(property_name):
			continue
		var old_value = sprite.get(property_name)
		var new_value = updates[property_name]
		_undo_redo.add_do_property(sprite, property_name, new_value)
		if property_name == "sprite_frames" and new_value is Resource:
			_undo_redo.add_do_reference(new_value)
		_undo_redo.add_undo_property(sprite, property_name, old_value)
		if property_name == "sprite_frames" and old_value is Resource:
			_undo_redo.add_undo_reference(old_value)
	_undo_redo.commit_action()


func _changed_properties(sprite: AnimatedSprite2D, order: Array, updates: Dictionary) -> Dictionary:
	var changed := {}
	for property_name_value in order:
		var property_name := str(property_name_value)
		if updates.has(property_name) and sprite.get(property_name) != updates[property_name]:
			changed[property_name] = updates[property_name]
	return changed


func _sprite_response(sprite: AnimatedSprite2D, scene_root: Node) -> Dictionary:
	var frames: SpriteFrames = sprite.sprite_frames
	return {
		"path": ScenePath.from_node(sprite, scene_root),
		"type": sprite.get_class(),
		"sprite_frames": _sprite_frames_descriptor(frames),
		"configuration": {
			"sprite_frames_path": "" if frames == null else frames.resource_path,
			"animation": str(sprite.animation),
			"autoplay": str(sprite.autoplay),
			"frame": sprite.frame,
			"frame_progress": _safe_float(sprite.frame_progress),
			"speed_scale": _safe_float(sprite.speed_scale),
			"centered": sprite.centered,
			"offset": VariantCodec.serialize(sprite.offset),
			"flip_h": sprite.flip_h,
			"flip_v": sprite.flip_v,
		},
		"supported_properties": NODE_PROPERTIES,
	}


func _sprite_frames_response(
	sprite: AnimatedSprite2D, scene_root: Node, selected: StringName, offset: int, limit: int
) -> Dictionary:
	var frames: SpriteFrames = sprite.sprite_frames
	var result := _sprite_response(sprite, scene_root)
	if frames == null:
		result["animations"] = []
		result["selected_animation"] = null
		return result
	var names := frames.get_animation_names()
	if names.size() > MAX_ANIMATIONS:
		return Errors.make(
			"SPRITE_FRAMES_ANIMATION_LIMIT_EXCEEDED",
			"SpriteFrames has more than %d animations" % MAX_ANIMATIONS
		)
	var animations: Array[Dictionary] = []
	for animation_name in names:
		animations.append(_animation_summary(frames, StringName(animation_name)))
	result["animations"] = animations
	if selected.is_empty() or not frames.has_animation(selected):
		result["selected_animation"] = null
		return result
	var total := frames.get_frame_count(selected)
	if total > MAX_FRAMES:
		return Errors.make(
			"SPRITE_FRAMES_FRAME_LIMIT_EXCEEDED",
			"Animation '%s' has more than %d frames" % [selected, MAX_FRAMES]
		)
	var output_frames: Array[Dictionary] = []
	var end := mini(total, offset + limit)
	for index in range(offset, end):
		var texture: Texture2D = frames.get_frame_texture(selected, index)
		output_frames.append({
			"index": index,
			"texture_path": "" if texture == null else texture.resource_path,
			"texture_type": "" if texture == null else texture.get_class(),
			"duration": _safe_float(frames.get_frame_duration(selected, index)),
		})
	var selected_response := _animation_summary(frames, selected)
	selected_response["frames"] = output_frames
	selected_response["frame_offset"] = offset
	selected_response["frame_limit"] = limit
	selected_response["frames_truncated"] = end < total
	result["selected_animation"] = selected_response
	return result


func _sprite_frames_descriptor(frames: SpriteFrames) -> Variant:
	if frames == null:
		return {"assigned": false, "origin": "none", "resource_path": ""}
	return {
		"assigned": true,
		"origin": "external" if not frames.resource_path.is_empty() else "embedded",
		"resource_path": frames.resource_path,
		"resource_type": frames.get_class(),
	}


func _animation_summary(frames: SpriteFrames, animation: StringName) -> Dictionary:
	return {
		"name": str(animation),
		"speed": _safe_float(frames.get_animation_speed(animation)),
		"loop_mode": _loop_mode_name(_get_animation_loop_mode(frames, animation)),
		"frame_count": frames.get_frame_count(animation),
	}


func _load_optional_resource(
	raw_value: Variant, expected_type: String, input_name: String, property_name: String
) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must be a res:// string or an empty string" % input_name)
	var resource_path: String = raw_value.strip_edges()
	if resource_path.is_empty():
		return {"property_name": property_name, "value": null}
	var loaded := _load_required_resource(resource_path, expected_type, input_name)
	if loaded.has("_error"):
		return loaded
	return {"property_name": property_name, "value": loaded["resource"]}


func _load_required_resource(raw_value: Variant, expected_type: String, input_name: String) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must be a non-empty res:// string" % input_name)
	var resource_path: String = raw_value.strip_edges()
	if resource_path.is_empty() or resource_path.length() > MAX_PATH_LENGTH \
		or not resource_path.begins_with("res://") or resource_path.contains("/../") \
		or resource_path.ends_with("/.."):
		return _invalid_configuration("%s must remain inside the project res:// directory" % input_name)
	if not ResourceLoader.exists(resource_path):
		return Errors.make("RESOURCE_NOT_FOUND", "Resource does not exist: %s" % resource_path)
	var resource := ResourceLoader.load(resource_path)
	if resource == null or not resource.is_class(expected_type):
		return Errors.make(
			"RESOURCE_TYPE_MISMATCH",
			"%s must load %s" % [input_name, expected_type],
			false,
			"Use an existing project-local %s resource." % expected_type
		)
	return {"resource": resource}


func _parse_animation_name(raw_value: Variant, input_name: String, property_name: String = "") -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must be a non-empty animation name" % input_name)
	var name: String = raw_value.strip_edges()
	if name.is_empty() or name.length() > 128 or name.contains("/") or name.contains(":"):
		return _invalid_configuration("%s must be a non-empty animation name up to 128 characters" % input_name)
	var key := property_name if not property_name.is_empty() else input_name
	return {"property_name": key, "value": StringName(name), "name": StringName(name)}


func _parse_optional_animation_name(raw_value: Variant, input_name: String, property_name: String) -> Dictionary:
	if not raw_value is String:
		return _invalid_configuration("%s must be an animation name or an empty string" % input_name)
	if raw_value.strip_edges().is_empty():
		return {"property_name": property_name, "value": StringName()}
	return _parse_animation_name(raw_value, input_name, property_name)


func _parse_integer(raw_value: Variant, property_name: String, minimum: int, maximum: int) -> Dictionary:
	if not _is_integer(raw_value):
		return _invalid_configuration("%s must be an integer" % property_name)
	var value := int(raw_value)
	if value < minimum or value > maximum:
		return _invalid_configuration("%s must be between %d and %d" % [property_name, minimum, maximum])
	return {"property_name": property_name, "value": value}


func _parse_number(raw_value: Variant, property_name: String, minimum: float, maximum: float) -> Dictionary:
	if not (raw_value is int or raw_value is float) or raw_value is bool or not is_finite(float(raw_value)):
		return _invalid_configuration("%s must be a finite number" % property_name)
	var value := float(raw_value)
	if value < minimum or value > maximum:
		return _invalid_configuration("%s must be between %s and %s" % [property_name, minimum, maximum])
	return {"property_name": property_name, "value": value}


func _parse_bool(raw_value: Variant, property_name: String) -> Dictionary:
	if not raw_value is bool:
		return _invalid_configuration("%s must be a boolean" % property_name)
	return {"property_name": property_name, "value": raw_value}


func _parse_vector2(raw_value: Variant, property_name: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_VECTOR2}, Vector2())
	if decoded.has("_error"):
		return _invalid_configuration("%s must contain finite x and y values" % property_name)
	var value: Vector2 = decoded["value"]
	if not is_finite(value.x) or not is_finite(value.y) \
		or absf(value.x) > MAX_COORDINATE or absf(value.y) > MAX_COORDINATE:
		return _invalid_configuration("%s must contain bounded finite x and y values" % property_name)
	return {"property_name": property_name, "value": value}


func _is_integer(value: Variant) -> bool:
	return (value is int or value is float) and not value is bool \
		and is_finite(float(value)) and float(value) == floorf(float(value))


func _first_animation_name(frames: SpriteFrames) -> StringName:
	var names := frames.get_animation_names()
	return StringName(names[0]) if not names.is_empty() else StringName()


func _loop_mode_name(value: int) -> String:
	for name in LOOP_MODES:
		if LOOP_MODES[name] == value:
			return name
	return "unknown"


func _get_animation_loop_mode(frames: SpriteFrames, animation: StringName) -> int:
	if frames.has_method("get_animation_loop_mode"):
		return int(frames.call("get_animation_loop_mode", animation))
	return 1 if bool(frames.call("get_animation_loop", animation)) else 0


func _set_animation_loop_mode(frames: SpriteFrames, animation: StringName, loop_mode: int) -> Dictionary:
	if frames.has_method("set_animation_loop_mode"):
		frames.call("set_animation_loop_mode", animation, loop_mode)
		return {}
	if loop_mode == LOOP_MODES["pingpong"]:
		return Errors.make(
			"SPRITE_FRAMES_LOOP_MODE_UNSUPPORTED",
			"pingpong SpriteFrames looping requires Godot 4.7 or newer",
			false,
			"Use none or linear with this Godot editor, or upgrade to Godot 4.7."
		)
	frames.call("set_animation_loop", animation, loop_mode == LOOP_MODES["linear"])
	return {}


func _safe_float(value: float) -> Variant:
	return value if is_finite(value) else null


func _sprite_frames_not_assigned() -> Dictionary:
	return Errors.make(
		"SPRITE_FRAMES_NOT_ASSIGNED",
		"AnimatedSprite2D has no SpriteFrames resource",
		false,
		"Use sprite_frames_animation_upsert to create an embedded SpriteFrames resource."
	)


func _animation_not_found(animation: StringName) -> Dictionary:
	return Errors.make(
		"SPRITE_FRAMES_ANIMATION_NOT_FOUND",
		"SpriteFrames animation '%s' does not exist" % animation,
		false,
		"Call sprite_frames_get to inspect available animation names."
	)


func _invalid_configuration(message: String) -> Dictionary:
	return Errors.make("INVALID_ANIMATED_SPRITE_CONFIGURATION", message)

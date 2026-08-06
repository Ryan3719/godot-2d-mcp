@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")

const MAX_AUDIO_PROPERTIES := 11
const MAX_AUDIO_LAYERS := 32
const AUDIO_PROPERTIES := [
	"stream_path", "volume_db", "pitch_scale", "autoplay", "max_distance", "attenuation",
	"panning_strength", "max_polyphony", "bus", "area_layers", "playback_type",
]
const AUDIO_PROPERTY_ORDER := [
	"stream", "volume_db", "pitch_scale", "autoplay", "max_distance", "attenuation",
	"panning_strength", "max_polyphony", "bus", "area_mask", "playback_type",
]
const AUDIO_PLAYBACK_TYPES := {
	"default": AudioServer.PLAYBACK_TYPE_DEFAULT,
	"stream": AudioServer.PLAYBACK_TYPE_STREAM,
	"sample": AudioServer.PLAYBACK_TYPE_SAMPLE,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_audio_stream_player_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_audio_stream_player_2d(params, false)
	if resolved.has("_error"):
		return resolved
	return _audio_response(resolved["player"], resolved["scene_root"])


func set_audio_stream_player_2d(params: Dictionary) -> Dictionary:
	var resolved := _resolve_audio_stream_player_2d(params)
	if resolved.has("_error"):
		return resolved
	var player: AudioStreamPlayer2D = resolved["player"]
	var parsed := _parse_audio_updates(params)
	if parsed.has("_error"):
		return parsed
	var updates: Dictionary = parsed["updates"]
	var changed := {}
	for property_name in AUDIO_PROPERTY_ORDER:
		if not updates.has(property_name):
			continue
		if player.get(property_name) != updates[property_name]:
			changed[property_name] = updates[property_name]
	if changed.is_empty():
		var unchanged := _audio_response(player, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Update AudioStreamPlayer2D %s" % player.name,
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	for property_name in AUDIO_PROPERTY_ORDER:
		if not changed.has(property_name):
			continue
		var old_value = player.get(property_name)
		var new_value = changed[property_name]
		_undo_redo.add_do_property(player, property_name, new_value)
		if property_name == "stream" and new_value != null:
			_undo_redo.add_do_reference(new_value)
		_undo_redo.add_undo_property(player, property_name, old_value)
		if property_name == "stream" and old_value != null:
			_undo_redo.add_undo_reference(old_value)
	_undo_redo.commit_action()
	var result := _audio_response(player, resolved["scene_root"])
	result["changed"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _resolve_audio_stream_player_2d(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var resolved := _resolve_node(params, require_writable)
	if resolved.has("_error"):
		return resolved
	if not resolved["node"] is AudioStreamPlayer2D:
		return Errors.make(
			"AUDIO_STREAM_PLAYER_2D_REQUIRED",
			"Node '%s' is %s, not AudioStreamPlayer2D" % [resolved["node"].name, resolved["node"].get_class()],
			false,
			"Target an AudioStreamPlayer2D node."
		)
	resolved["player"] = resolved["node"] as AudioStreamPlayer2D
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


func _audio_response(player: AudioStreamPlayer2D, scene_root: Node) -> Dictionary:
	var stream := player.get_stream()
	return {
		"path": ScenePath.from_node(player, scene_root),
		"type": player.get_class(),
		"configuration": {
			"stream_path": "" if stream == null else stream.resource_path,
			"stream_type": "" if stream == null else stream.get_class(),
			"volume_db": player.get_volume_db(),
			"pitch_scale": player.get_pitch_scale(),
			"autoplay": player.is_autoplay_enabled(),
			"max_distance": player.get_max_distance(),
			"attenuation": player.get_attenuation(),
			"panning_strength": player.get_panning_strength(),
			"max_polyphony": player.get_max_polyphony(),
			"bus": str(player.get_bus()),
			"area_layers": _mask_to_layer_numbers(player.get_area_mask()),
			"playback_type": _playback_type_name(player.get_playback_type()),
		},
		"available_buses": _get_bus_names(),
		"supported_properties": AUDIO_PROPERTIES,
	}


func _parse_audio_updates(params: Dictionary) -> Dictionary:
	var raw_properties: Variant = params.get("properties", null)
	if not raw_properties is Dictionary or raw_properties.is_empty() \
		or raw_properties.size() > MAX_AUDIO_PROPERTIES:
		return Errors.make(
			"INVALID_AUDIO_PROPERTIES",
			"properties must be a non-empty object containing at most %d entries" % MAX_AUDIO_PROPERTIES
		)
	var updates := {}
	for raw_name in raw_properties:
		if not raw_name is String or not AUDIO_PROPERTIES.has(raw_name):
			return Errors.make(
				"UNSUPPORTED_AUDIO_PROPERTY",
				"Unsupported AudioStreamPlayer2D property: %s" % str(raw_name),
				false,
				"Call audio_stream_player_2d_get to inspect supported_properties."
			)
		var property_name: String = raw_name
		var value_result := _parse_audio_value(property_name, raw_properties[raw_name])
		if value_result.has("_error"):
			return value_result
		updates[value_result["property_name"]] = value_result["value"]
	return {"updates": updates}


func _parse_audio_value(property_name: String, raw_value: Variant) -> Dictionary:
	if property_name == "stream_path":
		var stream_result := _load_audio_stream(raw_value)
		if stream_result.has("_error"):
			return stream_result
		return {"property_name": "stream", "value": stream_result["stream"]}
	if property_name == "area_layers":
		var mask_result := _parse_area_layers(raw_value)
		if mask_result.has("_error"):
			return mask_result
		return {"property_name": "area_mask", "value": mask_result["mask"]}
	if property_name == "playback_type":
		if not raw_value is String:
			return Errors.make("INVALID_AUDIO_CONFIGURATION", "playback_type must be a supported mode name")
		var label: String = raw_value.to_lower().strip_edges()
		if not AUDIO_PLAYBACK_TYPES.has(label):
			return Errors.make(
				"INVALID_AUDIO_CONFIGURATION",
				"playback_type must be one of: %s" % ", ".join(AUDIO_PLAYBACK_TYPES.keys())
			)
		return {"property_name": "playback_type", "value": AUDIO_PLAYBACK_TYPES[label]}
	if property_name == "bus":
		if not raw_value is String:
			return Errors.make("INVALID_AUDIO_CONFIGURATION", "bus must be an existing audio bus name")
		var bus_name: String = raw_value.strip_edges()
		if bus_name.is_empty() or AudioServer.get_bus_index(bus_name) < 0:
			return Errors.make(
				"AUDIO_BUS_NOT_FOUND",
				"Audio bus not found: %s" % bus_name,
				false,
				"Call audio_stream_player_2d_get to inspect available_buses."
			)
		return {"property_name": "bus", "value": StringName(bus_name)}
	if property_name in ["autoplay"]:
		if not raw_value is bool:
			return Errors.make("INVALID_AUDIO_CONFIGURATION", "%s must be a boolean" % property_name)
		return {"property_name": property_name, "value": raw_value}
	var range_result := _parse_audio_number(property_name, raw_value)
	if range_result.has("_error"):
		return range_result
	return {"property_name": property_name, "value": range_result["value"]}


func _parse_audio_number(property_name: String, raw_value: Variant) -> Dictionary:
	if not (raw_value is int or raw_value is float) or not is_finite(float(raw_value)):
		return Errors.make("INVALID_AUDIO_CONFIGURATION", "%s must be a finite number" % property_name)
	var value := float(raw_value)
	var limits := {
		"volume_db": {"minimum": -80.0, "maximum": 120.0},
		"pitch_scale": {"minimum": 0.01, "maximum": 16.0},
		"max_distance": {"minimum": 1.0, "maximum": 1000000.0},
		"attenuation": {"minimum": 0.0, "maximum": 128.0},
		"panning_strength": {"minimum": 0.0, "maximum": 16.0},
		"max_polyphony": {"minimum": 1.0, "maximum": 256.0},
	}
	var limit: Dictionary = limits[property_name]
	if value < float(limit["minimum"]) or value > float(limit["maximum"]):
		return Errors.make(
			"INVALID_AUDIO_CONFIGURATION",
			"%s must be between %s and %s" % [property_name, limit["minimum"], limit["maximum"]]
		)
	if property_name == "max_polyphony" and value != floorf(value):
		return Errors.make("INVALID_AUDIO_CONFIGURATION", "max_polyphony must be an integer")
	return {"value": int(value) if property_name == "max_polyphony" else value}


func _load_audio_stream(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_AUDIO_STREAM_PATH", "stream_path must be a res:// string or an empty string")
	var stream_path: String = raw_value.strip_edges()
	if stream_path.is_empty():
		return {"stream": null}
	if not stream_path.begins_with("res://") or "/../" in stream_path or stream_path.ends_with("/.."):
		return Errors.make("INVALID_AUDIO_STREAM_PATH", "stream_path must remain inside the Godot project res:// directory")
	if not ResourceLoader.exists(stream_path):
		return Errors.make("RESOURCE_NOT_FOUND", "stream_path does not exist: %s" % stream_path)
	var stream := ResourceLoader.load(stream_path)
	if not stream is AudioStream:
		return Errors.make("RESOURCE_TYPE_MISMATCH", "stream_path does not load an AudioStream resource")
	return {"stream": stream as AudioStream}


func _parse_area_layers(raw_values: Variant) -> Dictionary:
	if not raw_values is Array or raw_values.size() > MAX_AUDIO_LAYERS:
		return Errors.make(
			"INVALID_AUDIO_AREA_LAYERS",
			"area_layers must contain at most %d layer numbers" % MAX_AUDIO_LAYERS
		)
	var mask := 0
	for raw_value in raw_values:
		if not (raw_value is int or raw_value is float) \
			or not is_finite(float(raw_value)) \
			or float(raw_value) != floorf(float(raw_value)):
			return Errors.make("INVALID_AUDIO_AREA_LAYERS", "area_layers entries must be integers from 1 to 32")
		var layer := int(raw_value)
		if layer < 1 or layer > MAX_AUDIO_LAYERS or mask & (1 << (layer - 1)) != 0:
			return Errors.make("INVALID_AUDIO_AREA_LAYERS", "area_layers entries must be unique integers from 1 to 32")
		mask |= 1 << (layer - 1)
	return {"mask": mask}


func _mask_to_layer_numbers(mask: int) -> Array[int]:
	var layers: Array[int] = []
	for layer in range(1, MAX_AUDIO_LAYERS + 1):
		if mask & (1 << (layer - 1)) != 0:
			layers.append(layer)
	return layers


func _playback_type_name(value: int) -> String:
	for label in AUDIO_PLAYBACK_TYPES:
		if int(AUDIO_PLAYBACK_TYPES[label]) == value:
			return label
	return "unknown"


func _get_bus_names() -> Array[String]:
	var buses: Array[String] = []
	for index in AudioServer.get_bus_count():
		buses.append(str(AudioServer.get_bus_name(index)))
	return buses

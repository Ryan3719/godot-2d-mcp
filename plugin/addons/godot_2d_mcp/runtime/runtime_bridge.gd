extends Node

const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const CAPTURE_NAME := "godot_2d_mcp"
const MAX_LOG_ENTRY_LENGTH := 2048
const MAX_PENDING_LOGS := 512
const MAX_SCREENSHOT_BYTES := 1_000_000
const MAX_SCREENSHOT_DIMENSION := 1024
const MAX_INPUT_EVENTS := 64
const MAX_COORDINATE := 100_000.0
const MAX_TOUCH_INDEX := 31
const MAX_TOUCH_PRESSURE := 1.0
const MAX_TOUCH_TILT := 1.0
const MAX_RUNTIME_NODE_PATH_LENGTH := 4096
const MAX_AUDIO_POSITION_SECONDS := 3600.0
const MIN_PERFORMANCE_SAMPLE_SECONDS := 0.1
const MAX_PERFORMANCE_SAMPLE_SECONDS := 30.0
const MAX_PENDING_PERFORMANCE_SAMPLES := 4
const MAX_ACTIVE_TWEENS := 32
const MAX_TWEEN_TRACKS := 16
const MAX_TWEEN_DURATION_SECONDS := 60.0
const MAX_TWEEN_DELAY_SECONDS := 60.0
const MAX_TWEEN_LOOPS := 100
const TWEEN_PROTECTED_PROPERTIES := {
	"owner": true,
	"scene_file_path": true,
	"script": true,
}
const TWEEN_COMPONENTS_BY_TYPE := {
	TYPE_VECTOR2: {"x": true, "y": true},
	TYPE_COLOR: {"r": true, "g": true, "b": true, "a": true},
}
const TWEEN_SUPPORTED_VALUE_TYPES := {
	TYPE_INT: true,
	TYPE_FLOAT: true,
	TYPE_VECTOR2: true,
	TYPE_VECTOR2I: true,
	TYPE_RECT2: true,
	TYPE_RECT2I: true,
	TYPE_TRANSFORM2D: true,
	TYPE_COLOR: true,
}
const TWEEN_TRANSITIONS := {
	"linear": Tween.TRANS_LINEAR,
	"sine": Tween.TRANS_SINE,
	"quint": Tween.TRANS_QUINT,
	"quart": Tween.TRANS_QUART,
	"quad": Tween.TRANS_QUAD,
	"expo": Tween.TRANS_EXPO,
	"elastic": Tween.TRANS_ELASTIC,
	"cubic": Tween.TRANS_CUBIC,
	"circ": Tween.TRANS_CIRC,
	"bounce": Tween.TRANS_BOUNCE,
	"back": Tween.TRANS_BACK,
	"spring": Tween.TRANS_SPRING,
}
const TWEEN_EASES := {
	"in": Tween.EASE_IN,
	"out": Tween.EASE_OUT,
	"in_out": Tween.EASE_IN_OUT,
	"out_in": Tween.EASE_OUT_IN,
}
const TWEEN_PROCESS_MODES := {
	"idle": Tween.TWEEN_PROCESS_IDLE,
	"physics": Tween.TWEEN_PROCESS_PHYSICS,
}
const TWEEN_PAUSE_MODES := {
	"bound": Tween.TWEEN_PAUSE_BOUND,
	"stop": Tween.TWEEN_PAUSE_STOP,
	"process": Tween.TWEEN_PAUSE_PROCESS,
}

var _logger: Logger
var _pending_logs: Array[Dictionary] = []
var _pending_log_mutex := Mutex.new()
var _pending_screenshots: Array[Dictionary] = []
var _pending_performance_samples: Array[Dictionary] = []
var _active_tweens: Dictionary = {}
var _debugger_active := false


class RuntimeLogger extends Logger:
	var receiver: Node

	func _init(target: Node) -> void:
		receiver = target

	func _log_message(message: String, error: bool) -> void:
		if receiver != null:
			receiver.queue_runtime_log(message, error)


func _ready() -> void:
	_debugger_active = EngineDebugger.is_active()
	if not _debugger_active:
		return
	if not EngineDebugger.has_capture(CAPTURE_NAME):
		EngineDebugger.register_message_capture(CAPTURE_NAME, _capture_debugger_message)
	_logger = RuntimeLogger.new(self)
	OS.add_logger(_logger)
	_send_message(
		"ready",
		[
			{
				"protocol_version": 1,
				"capabilities": [
					"logs", "screenshot", "input", "touch_input", "audio_stream_player_2d",
					"performance_sample", "tween",
				],
			}
		]
	)


func _exit_tree() -> void:
	_clear_active_tweens()
	if _logger != null:
		OS.remove_logger(_logger)
		_logger = null
	if _debugger_active and EngineDebugger.has_capture(CAPTURE_NAME):
		EngineDebugger.unregister_message_capture(CAPTURE_NAME)


func _process(delta: float) -> void:
	_flush_logs()
	_sweep_active_tweens()
	_update_performance_samples(delta)
	if _pending_screenshots.is_empty():
		return
	var request: Dictionary = _pending_screenshots.pop_front()
	_capture_screenshot(str(request["request_id"]), request["options"])


func queue_runtime_log(message: String, error: bool) -> void:
	var bounded_message := message.left(MAX_LOG_ENTRY_LENGTH)
	_pending_log_mutex.lock()
	if _pending_logs.size() >= MAX_PENDING_LOGS:
		_pending_logs.pop_front()
	_pending_logs.append({"message": bounded_message, "level": "error" if error else "info"})
	_pending_log_mutex.unlock()


func _flush_logs() -> void:
	if not _debugger_active:
		return
	_pending_log_mutex.lock()
	if _pending_logs.is_empty():
		_pending_log_mutex.unlock()
		return
	var logs := _pending_logs.duplicate(true)
	_pending_logs.clear()
	_pending_log_mutex.unlock()
	_send_message("logs", [logs])


func _capture_debugger_message(message: String, data: Array) -> bool:
	match message:
		"screenshot":
			if data.size() != 2 or not data[1] is Dictionary:
				return true
			var request_id := str(data[0]).strip_edges()
			if request_id.is_empty() or request_id.length() > 128:
				return true
			_pending_screenshots.append({"request_id": request_id, "options": data[1]})
			return true
		"input":
			if data.size() != 2 or not data[1] is Array:
				return true
			var request_id := str(data[0]).strip_edges()
			if request_id.is_empty() or request_id.length() > 128:
				return true
			_handle_input(request_id, data[1])
			return true
		"audio_control":
			if data.size() != 2 or not data[1] is Dictionary:
				return true
			var audio_request_id := str(data[0]).strip_edges()
			if audio_request_id.is_empty() or audio_request_id.length() > 128:
				return true
			_handle_audio_control(audio_request_id, data[1])
			return true
		"performance_sample":
			if data.size() != 2 or not data[1] is Dictionary:
				return true
			var performance_request_id := str(data[0]).strip_edges()
			if performance_request_id.is_empty() or performance_request_id.length() > 128:
				return true
			_request_performance_sample(performance_request_id, data[1])
			return true
		"tween_start":
			if data.size() != 2 or not data[1] is Dictionary:
				return true
			var tween_request_id := str(data[0]).strip_edges()
			if tween_request_id.is_empty() or tween_request_id.length() > 128:
				return true
			_handle_tween_start(tween_request_id, data[1])
			return true
		"tween_stop":
			if data.size() != 1:
				return true
			var tween_stop_request_id := str(data[0]).strip_edges()
			if tween_stop_request_id.is_empty() or tween_stop_request_id.length() > 128:
				return true
			_handle_tween_stop(tween_stop_request_id)
			return true
	return false


func _request_performance_sample(request_id: String, options: Dictionary) -> void:
	for field in options:
		if field != "duration_seconds":
			_send_performance_sample_error(
				request_id,
				"INVALID_PERFORMANCE_SAMPLE_REQUEST",
				"performance sampling only accepts duration_seconds"
			)
			return
	var raw_duration: Variant = options.get("duration_seconds", null)
	if not (raw_duration is int or raw_duration is float) or not is_finite(float(raw_duration)) \
		or float(raw_duration) < MIN_PERFORMANCE_SAMPLE_SECONDS \
		or float(raw_duration) > MAX_PERFORMANCE_SAMPLE_SECONDS:
		_send_performance_sample_error(
			request_id,
			"INVALID_PERFORMANCE_SAMPLE_DURATION",
			"duration_seconds must be a finite number between %.1f and %.1f" \
				% [MIN_PERFORMANCE_SAMPLE_SECONDS, MAX_PERFORMANCE_SAMPLE_SECONDS]
		)
		return
	if _pending_performance_samples.size() >= MAX_PENDING_PERFORMANCE_SAMPLES:
		_send_performance_sample_error(
			request_id,
			"PERFORMANCE_SAMPLE_QUEUE_FULL",
			"At most %d performance samples may run at once" % MAX_PENDING_PERFORMANCE_SAMPLES
		)
		return
	_pending_performance_samples.append(
		{
			"request_id": request_id,
			"duration_seconds": float(raw_duration),
			"elapsed_seconds": 0.0,
			"frame_count": 0,
			"delta_total_msec": 0.0,
			"delta_min_msec": INF,
			"delta_max_msec": 0.0,
		}
	)


func _update_performance_samples(delta: float) -> void:
	if _pending_performance_samples.is_empty():
		return
	var delta_msec := maxf(0.0, _safe_runtime_number(delta) * 1000.0)
	for index in range(_pending_performance_samples.size() - 1, -1, -1):
		var sample: Dictionary = _pending_performance_samples[index]
		sample["elapsed_seconds"] = float(sample["elapsed_seconds"]) + delta_msec / 1000.0
		sample["frame_count"] = int(sample["frame_count"]) + 1
		sample["delta_total_msec"] = float(sample["delta_total_msec"]) + delta_msec
		sample["delta_min_msec"] = minf(float(sample["delta_min_msec"]), delta_msec)
		sample["delta_max_msec"] = maxf(float(sample["delta_max_msec"]), delta_msec)
		if float(sample["elapsed_seconds"]) < float(sample["duration_seconds"]):
			_pending_performance_samples[index] = sample
			continue
		_pending_performance_samples.remove_at(index)
		var actual_duration := maxf(float(sample["elapsed_seconds"]), 0.000001)
		var frame_count := int(sample["frame_count"])
		_send_message(
			"performance_sample_result",
			[
				sample["request_id"],
				{
					"ok": true,
					"requested_duration_seconds": sample["duration_seconds"],
					"actual_duration_seconds": actual_duration,
					"frame_count": frame_count,
					"estimated_fps": frame_count / actual_duration,
					"process_frame_delta_msec": {
						"min": _safe_runtime_number(float(sample["delta_min_msec"])),
						"mean": _safe_runtime_number(float(sample["delta_total_msec"]) / frame_count),
						"max": _safe_runtime_number(float(sample["delta_max_msec"])),
					},
					"monitors": {
						"time_fps": _safe_performance_monitor(Performance.TIME_FPS),
						"memory_static_bytes": _safe_performance_monitor(Performance.MEMORY_STATIC),
						"object_count": _safe_performance_monitor(Performance.OBJECT_COUNT),
						"draw_calls_in_frame": _safe_performance_monitor(
							Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME
						),
					},
				},
			]
		)


func _safe_performance_monitor(monitor: Performance.Monitor) -> float:
	return _safe_runtime_number(Performance.get_monitor(monitor))


func _send_performance_sample_error(request_id: String, code: String, message: String) -> void:
	_send_message("performance_sample_result", [request_id, {"ok": false, "code": code, "message": message}])


func _handle_tween_start(request_id: String, request: Dictionary) -> void:
	if _active_tweens.has(request_id):
		_send_tween_error(request_id, "RUNTIME_TWEEN_DUPLICATE_REQUEST", "A tween with this request_id is already active")
		return
	if _active_tweens.size() >= MAX_ACTIVE_TWEENS:
		_send_tween_error(
			request_id,
			"RUNTIME_TWEEN_QUEUE_FULL",
			"At most %d runtime tweens may be active at once" % MAX_ACTIVE_TWEENS
		)
		return
	var settings_result := _parse_tween_settings(request)
	if settings_result.has("error"):
		_send_tween_error(request_id, settings_result["code"], settings_result["error"])
		return
	var raw_path: Variant = request.get("path", null)
	if not raw_path is String:
		_send_tween_error(
			request_id, "RUNTIME_TWEEN_PATH_INVALID", "path must be a bounded absolute scene node path"
		)
		return
	var path: String = raw_path.strip_edges()
	var path_result := _resolve_runtime_tween_node(path)
	if path_result.has("error"):
		_send_tween_error(request_id, path_result["code"], path_result["error"])
		return
	var node: Node = path_result["node"]
	if not node is CanvasItem:
		_send_tween_error(
			request_id,
			"RUNTIME_TWEEN_CANVAS_ITEM_REQUIRED",
			"Node '%s' is %s, not a 2D CanvasItem" % [node.name, node.get_class()]
		)
		return
	var tracks_result := _parse_tween_tracks(request.get("tracks", null), node)
	if tracks_result.has("error"):
		_send_tween_error(request_id, tracks_result["code"], tracks_result["error"])
		return
	var settings: Dictionary = settings_result["settings"]
	var tracks: Array = tracks_result["tracks"]
	var tween: Tween = node.create_tween()
	if tween == null or not tween.is_valid():
		_send_tween_error(request_id, "RUNTIME_TWEEN_CREATE_FAILED", "Godot could not create a runtime Tween")
		return
	tween.set_parallel(bool(settings["parallel"]))
	tween.set_loops(int(settings["loops"]))
	tween.set_process_mode(int(settings["process_mode"]))
	tween.set_pause_mode(int(settings["pause_mode"]))
	tween.set_ignore_time_scale(bool(settings["ignore_time_scale"]))
	for track_value in tracks:
		var track: Dictionary = track_value
		var tweener := tween.tween_property(
			node,
			NodePath(str(track["property"])),
			track["to"],
			float(track["duration_seconds"])
		)
		if tweener == null:
			tween.kill()
			_send_tween_error(
				request_id,
				"RUNTIME_TWEEN_PROPERTY_REJECTED",
				"Godot rejected the tween property '%s'" % str(track["property"])
			)
			return
		if track.has("from"):
			tweener.from(track["from"])
		if bool(track["relative"]):
			tweener.as_relative()
		tweener.set_delay(float(track["delay_seconds"]))
		tweener.set_trans(int(track["transition"]))
		tweener.set_ease(int(track["ease"]))
	_active_tweens[request_id] = {
		"tween": tween,
		"path": path,
		"track_count": tracks.size(),
		"loops": int(settings["loops"]),
		"started_msec": Time.get_ticks_msec(),
	}
	tween.finished.connect(_on_runtime_tween_finished.bind(request_id), CONNECT_ONE_SHOT)


func _handle_tween_stop(request_id: String) -> void:
	if not _active_tweens.has(request_id):
		_send_tween_error(
			request_id,
			"RUNTIME_TWEEN_NOT_ACTIVE",
			"No active runtime tween exists with this request_id"
		)
		return
	var entry: Dictionary = _active_tweens[request_id]
	var tween_value: Variant = entry.get("tween", null)
	if tween_value is Tween:
		var tween := tween_value as Tween
		if tween.is_valid():
			tween.kill()
	_finish_runtime_tween(request_id, "cancelled")


func _parse_tween_settings(request: Dictionary) -> Dictionary:
	for field in request:
		if field not in ["path", "tracks", "parallel", "loops", "process_mode", "pause_mode", "ignore_time_scale"]:
			return {
				"code": "INVALID_RUNTIME_TWEEN_REQUEST",
				"error": "Runtime tween requests contain an unsupported field: %s" % str(field),
			}
	var raw_parallel: Variant = request.get("parallel", true)
	if not raw_parallel is bool:
		return {"code": "RUNTIME_TWEEN_PARALLEL_INVALID", "error": "parallel must be a boolean"}
	var raw_loops: Variant = request.get("loops", 1)
	if not (raw_loops is int or raw_loops is float) or raw_loops is bool \
		or not is_finite(float(raw_loops)) or float(raw_loops) != floorf(float(raw_loops)) \
		or int(raw_loops) < 0 or int(raw_loops) > MAX_TWEEN_LOOPS:
		return {
			"code": "RUNTIME_TWEEN_LOOPS_INVALID",
			"error": "loops must be an integer between 0 and %d" % MAX_TWEEN_LOOPS,
		}
	var process_mode_result := _parse_tween_enum(
		request.get("process_mode", "idle"), TWEEN_PROCESS_MODES, "process_mode"
	)
	if process_mode_result.has("error"):
		return process_mode_result
	var pause_mode_result := _parse_tween_enum(
		request.get("pause_mode", "bound"), TWEEN_PAUSE_MODES, "pause_mode"
	)
	if pause_mode_result.has("error"):
		return pause_mode_result
	var raw_ignore_time_scale: Variant = request.get("ignore_time_scale", false)
	if not raw_ignore_time_scale is bool:
		return {
			"code": "RUNTIME_TWEEN_IGNORE_TIME_SCALE_INVALID",
			"error": "ignore_time_scale must be a boolean",
		}
	return {
		"settings": {
			"parallel": raw_parallel,
			"loops": int(raw_loops),
			"process_mode": process_mode_result["value"],
			"pause_mode": pause_mode_result["value"],
			"ignore_time_scale": raw_ignore_time_scale,
		}
	}


func _parse_tween_tracks(raw_tracks: Variant, node: Node) -> Dictionary:
	if not raw_tracks is Array or raw_tracks.is_empty() or raw_tracks.size() > MAX_TWEEN_TRACKS:
		return {
			"code": "RUNTIME_TWEEN_TRACKS_INVALID",
			"error": "tracks must contain between 1 and %d entries" % MAX_TWEEN_TRACKS,
		}
	var tracks: Array[Dictionary] = []
	var used_properties: Dictionary = {}
	for index in range(raw_tracks.size()):
		var raw_track_value: Variant = raw_tracks[index]
		if not raw_track_value is Dictionary:
			return _tween_track_error(index, "each track must be an object")
		var raw_track: Dictionary = raw_track_value
		for field in raw_track:
			if field not in ["property", "to", "from", "duration_seconds", "delay_seconds", "transition", "ease", "relative"]:
				return _tween_track_error(index, "track contains an unsupported field: %s" % str(field))
		if not raw_track.has("property") or not raw_track.has("to") or not raw_track.has("duration_seconds"):
			return _tween_track_error(index, "each track requires property, to, and duration_seconds")
		if not raw_track["property"] is String:
			return _tween_track_error(index, "property must be a string")
		var property: String = str(raw_track["property"]).strip_edges()
		var property_result := _resolve_runtime_tween_property(node, property)
		if property_result.has("error"):
			return _tween_track_error(index, property_result["error"], property_result["code"])
		if used_properties.has(property):
			return _tween_track_error(index, "tracks cannot target the same property more than once")
		var raw_duration: Variant = raw_track["duration_seconds"]
		if not (raw_duration is int or raw_duration is float) or not is_finite(float(raw_duration)) \
			or float(raw_duration) <= 0.0 or float(raw_duration) > MAX_TWEEN_DURATION_SECONDS:
			return _tween_track_error(
				index,
				"duration_seconds must be a finite number greater than 0 and at most %.0f" % MAX_TWEEN_DURATION_SECONDS
			)
		var raw_delay: Variant = raw_track.get("delay_seconds", 0.0)
		if not (raw_delay is int or raw_delay is float) or not is_finite(float(raw_delay)) \
			or float(raw_delay) < 0.0 or float(raw_delay) > MAX_TWEEN_DELAY_SECONDS:
			return _tween_track_error(
				index,
				"delay_seconds must be a finite number between 0 and %.0f" % MAX_TWEEN_DELAY_SECONDS
			)
		var transition_result := _parse_tween_enum(
			raw_track.get("transition", "linear"), TWEEN_TRANSITIONS, "transition"
		)
		if transition_result.has("error"):
			return _tween_track_error(index, transition_result["error"], transition_result["code"])
		var ease_result := _parse_tween_enum(raw_track.get("ease", "in_out"), TWEEN_EASES, "ease")
		if ease_result.has("error"):
			return _tween_track_error(index, ease_result["error"], ease_result["code"])
		var raw_relative: Variant = raw_track.get("relative", false)
		if not raw_relative is bool:
			return _tween_track_error(index, "relative must be a boolean")
		var property_info: Dictionary = property_result["property_info"].duplicate(true)
		property_info["type"] = int(property_result["value_type"])
		var current_value: Variant = node.get_indexed(NodePath(property))
		var decoded_to := VariantCodec.decode(raw_track["to"], property_info, current_value)
		if decoded_to.has("_error"):
			return _tween_track_error(
				index,
				"to %s" % str((decoded_to["_error"] as Dictionary).get("message", "is invalid")),
				"RUNTIME_TWEEN_VALUE_INVALID"
			)
		if not _is_finite_tween_value(decoded_to["value"]):
			return _tween_track_error(index, "to must contain only finite numeric values")
		var track := {
			"property": property,
			"to": decoded_to["value"],
			"duration_seconds": float(raw_duration),
			"delay_seconds": float(raw_delay),
			"transition": transition_result["value"],
			"ease": ease_result["value"],
			"relative": raw_relative,
		}
		if raw_track.has("from"):
			var decoded_from := VariantCodec.decode(raw_track["from"], property_info, current_value)
			if decoded_from.has("_error"):
				return _tween_track_error(
					index,
					"from %s" % str((decoded_from["_error"] as Dictionary).get("message", "is invalid")),
					"RUNTIME_TWEEN_VALUE_INVALID"
				)
			if not _is_finite_tween_value(decoded_from["value"]):
				return _tween_track_error(index, "from must contain only finite numeric values")
			track["from"] = decoded_from["value"]
		tracks.append(track)
		used_properties[property] = true
	return {"tracks": tracks}


func _parse_tween_enum(value: Variant, choices: Dictionary, label: String) -> Dictionary:
	if not value is String:
		return {
			"code": "RUNTIME_TWEEN_%s_INVALID" % label.to_upper(),
			"error": "%s must be a supported string value" % label,
		}
	var normalized: String = str(value).strip_edges().to_lower()
	if not choices.has(normalized):
		return {
			"code": "RUNTIME_TWEEN_%s_INVALID" % label.to_upper(),
			"error": "%s is not supported" % label,
		}
	return {"value": choices[normalized]}


func _tween_track_error(index: int, message: String, code: String = "RUNTIME_TWEEN_TRACK_INVALID") -> Dictionary:
	return {"code": code, "error": "tracks[%d] %s" % [index, message]}


func _resolve_runtime_tween_property(node: Node, property_path: String) -> Dictionary:
	if property_path.is_empty() or property_path.length() > 256 or property_path.contains("/"):
		return {"code": "RUNTIME_TWEEN_PROPERTY_INVALID", "error": "property must be a bounded property path"}
	var parts := property_path.split(":", false)
	if parts.size() < 1 or parts.size() > 2 or parts[0].is_empty():
		return {
			"code": "RUNTIME_TWEEN_PROPERTY_INVALID",
			"error": "property must name one native property or one supported component",
		}
	for part in parts:
		if part.is_empty() or part.length() > 128:
			return {"code": "RUNTIME_TWEEN_PROPERTY_INVALID", "error": "property path contains an empty segment"}
	var property_name: String = parts[0]
	if TWEEN_PROTECTED_PROPERTIES.has(property_name):
		return {
			"code": "RUNTIME_TWEEN_PROPERTY_PROTECTED",
			"error": "Property '%s' cannot be tweened" % property_name,
		}
	for property_info_value in ClassDB.class_get_property_list(StringName(node.get_class())):
		var property_info: Dictionary = property_info_value
		if str(property_info.get("name", "")) != property_name:
			continue
		var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
		if bool(usage & PROPERTY_USAGE_READ_ONLY) \
			or not bool(usage & (PROPERTY_USAGE_EDITOR | PROPERTY_USAGE_STORAGE)):
			return {
				"code": "RUNTIME_TWEEN_PROPERTY_NOT_WRITABLE",
				"error": "Property '%s' is not public and writable" % property_name,
			}
		var property_type := int(property_info.get("type", TYPE_NIL))
		if not TWEEN_SUPPORTED_VALUE_TYPES.has(property_type):
			return {
				"code": "RUNTIME_TWEEN_PROPERTY_TYPE_UNSUPPORTED",
				"error": "Property '%s' has unsupported tween type %s" % [property_name, type_string(property_type)],
			}
		if parts.size() == 1:
			return {"property_info": property_info, "value_type": property_type}
		var component: String = parts[1]
		if not TWEEN_COMPONENTS_BY_TYPE.has(property_type) \
			or not TWEEN_COMPONENTS_BY_TYPE[property_type].has(component):
			return {
				"code": "RUNTIME_TWEEN_COMPONENT_UNSUPPORTED",
				"error": "Property '%s' does not expose tween component '%s'" % [property_name, component],
			}
		return {"property_info": property_info, "value_type": TYPE_FLOAT}
	return {
		"code": "RUNTIME_TWEEN_PROPERTY_NOT_FOUND",
		"error": "Property '%s' is not a native property of %s" % [property_name, node.get_class()],
	}


func _is_finite_tween_value(value: Variant) -> bool:
	match typeof(value):
		TYPE_INT, TYPE_STRING, TYPE_STRING_NAME:
			return true
		TYPE_FLOAT:
			return is_finite(float(value))
		TYPE_VECTOR2:
			return is_finite(value.x) and is_finite(value.y)
		TYPE_VECTOR2I:
			return true
		TYPE_RECT2:
			return _is_finite_tween_value(value.position) and _is_finite_tween_value(value.size)
		TYPE_RECT2I:
			return true
		TYPE_TRANSFORM2D:
			return _is_finite_tween_value(value.x) and _is_finite_tween_value(value.y) \
				and _is_finite_tween_value(value.origin)
		TYPE_COLOR:
			return is_finite(value.r) and is_finite(value.g) and is_finite(value.b) and is_finite(value.a)
	return false


func _on_runtime_tween_finished(request_id: String) -> void:
	_finish_runtime_tween(request_id, "completed")


func _finish_runtime_tween(request_id: String, state: String) -> void:
	if not _active_tweens.has(request_id):
		return
	var entry: Dictionary = _active_tweens[request_id]
	_active_tweens.erase(request_id)
	var elapsed_msec := maxi(0, Time.get_ticks_msec() - int(entry.get("started_msec", 0)))
	_send_message(
		"tween_result",
		[
			request_id,
			{
				"ok": true,
				"state": state,
				"path": str(entry.get("path", "")),
				"track_count": int(entry.get("track_count", 0)),
				"loops": int(entry.get("loops", 1)),
				"elapsed_seconds": float(elapsed_msec) / 1000.0,
			},
		]
	)


func _sweep_active_tweens() -> void:
	for request_id_value in _active_tweens.keys():
		var request_id := str(request_id_value)
		if not _active_tweens.has(request_id):
			continue
		var entry: Dictionary = _active_tweens[request_id]
		var tween_value: Variant = entry.get("tween", null)
		if tween_value is Tween and (tween_value as Tween).is_valid():
			continue
		_active_tweens.erase(request_id)
		_send_tween_error(
			request_id,
			"RUNTIME_TWEEN_INVALIDATED",
			"The runtime tween was invalidated before it completed; its target may have left the scene"
		)


func _clear_active_tweens() -> void:
	for entry_value in _active_tweens.values():
		var entry: Dictionary = entry_value
		var tween_value: Variant = entry.get("tween", null)
		if tween_value is Tween and (tween_value as Tween).is_valid():
			(tween_value as Tween).kill()
	_active_tweens.clear()


func _resolve_runtime_tween_node(path: String) -> Dictionary:
	return _resolve_runtime_scene_node_with_prefix(path, "RUNTIME_TWEEN")


func _send_tween_error(request_id: String, code: String, message: String) -> void:
	_send_message("tween_result", [request_id, {"ok": false, "code": code, "message": message}])


func _capture_screenshot(request_id: String, options: Dictionary) -> void:
	var format := str(options.get("format", "png")).to_lower()
	if format not in ["png", "jpeg"]:
		_send_screenshot_error(request_id, "INVALID_SCREENSHOT_FORMAT", "format must be png or jpeg")
		return
	var max_width := int(options.get("max_width", 640))
	var max_height := int(options.get("max_height", 640))
	if max_width < 1 or max_height < 1 or max_width > MAX_SCREENSHOT_DIMENSION \
		or max_height > MAX_SCREENSHOT_DIMENSION:
		_send_screenshot_error(request_id, "INVALID_SCREENSHOT_SIZE", "Screenshot bounds are invalid")
		return
	var quality := float(options.get("quality", 0.85))
	if quality < 0.1 or quality > 1.0:
		_send_screenshot_error(request_id, "INVALID_SCREENSHOT_QUALITY", "quality must be between 0.1 and 1.0")
		return

	var texture := get_viewport().get_texture()
	var image := texture.get_image()
	if image == null or image.is_empty():
		_send_screenshot_error(request_id, "SCREENSHOT_UNAVAILABLE", "The game viewport did not return an image")
		return
	var size := image.get_size()
	var scale := minf(float(max_width) / float(size.x), float(max_height) / float(size.y))
	if scale < 1.0:
		var resized_width := maxi(1, int(round(float(size.x) * scale)))
		var resized_height := maxi(1, int(round(float(size.y) * scale)))
		image.resize(resized_width, resized_height, Image.INTERPOLATE_LANCZOS)
	var encoded: PackedByteArray = image.save_png_to_buffer() if format == "png" else image.save_jpg_to_buffer(quality)
	if encoded.is_empty():
		_send_screenshot_error(request_id, "SCREENSHOT_ENCODE_FAILED", "Godot could not encode the viewport image")
		return
	if encoded.size() > MAX_SCREENSHOT_BYTES:
		_send_screenshot_error(
			request_id,
			"SCREENSHOT_TOO_LARGE",
			"Screenshot exceeds the 1,000,000-byte transport limit; reduce the requested bounds."
		)
		return
	_send_message(
		"screenshot_result",
		[
			request_id,
			{
				"ok": true,
				"mime_type": "image/png" if format == "png" else "image/jpeg",
				"width": image.get_width(),
				"height": image.get_height(),
				"byte_size": encoded.size(),
				"data_base64": Marshalls.raw_to_base64(encoded),
			},
		]
	)


func _send_screenshot_error(request_id: String, code: String, message: String) -> void:
	_send_message("screenshot_result", [request_id, {"ok": false, "code": code, "message": message}])


func _handle_input(request_id: String, events: Array) -> void:
	if events.is_empty() or events.size() > MAX_INPUT_EVENTS:
		_send_message(
			"input_result",
			[request_id, {"ok": false, "code": "INVALID_INPUT_EVENTS", "message": "events must contain 1 to 64 items"}]
		)
		return
	var applied := 0
	for index in events.size():
		var decoded := _decode_input_event(events[index])
		if decoded.has("error"):
			_send_message(
				"input_result",
				[
					request_id,
					{
						"ok": false,
						"code": "INVALID_INPUT_EVENT",
						"message": decoded["error"],
						"event_index": index,
					},
				]
			)
			return
		Input.parse_input_event(decoded["event"])
		applied += 1
	_send_message("input_result", [request_id, {"ok": true, "applied": applied}])


func _handle_audio_control(request_id: String, request: Dictionary) -> void:
	for field in request:
		if field not in ["path", "action", "position_seconds"]:
			_send_audio_control_error(
				request_id,
				"INVALID_RUNTIME_AUDIO_REQUEST",
				"Runtime audio control only accepts path, action, and position_seconds"
			)
			return
	var raw_path: Variant = request.get("path", null)
	if not raw_path is String:
		_send_audio_control_error(
			request_id, "RUNTIME_AUDIO_PATH_INVALID", "path must be a bounded absolute scene node path"
		)
		return
	var path: String = raw_path.strip_edges()
	var path_result := _resolve_runtime_scene_node(path)
	if path_result.has("error"):
		_send_audio_control_error(request_id, path_result["code"], path_result["error"])
		return
	var node: Node = path_result["node"]
	if not node is AudioStreamPlayer2D:
		_send_audio_control_error(
			request_id,
			"RUNTIME_AUDIO_STREAM_PLAYER_2D_REQUIRED",
			"Node '%s' is %s, not AudioStreamPlayer2D" % [node.name, node.get_class()]
		)
		return
	var raw_action: Variant = request.get("action", null)
	if not raw_action is String:
		_send_audio_control_error(
			request_id, "RUNTIME_AUDIO_ACTION_INVALID", "action must be get, play, stop, or seek"
		)
		return
	var action: String = raw_action.strip_edges().to_lower()
	if action not in ["get", "play", "stop", "seek"]:
		_send_audio_control_error(
			request_id, "RUNTIME_AUDIO_ACTION_INVALID", "action must be get, play, stop, or seek"
		)
		return
	var player := node as AudioStreamPlayer2D
	var position_seconds: Variant = null
	if action in ["get", "stop"]:
		if request.has("position_seconds"):
			_send_audio_control_error(
				request_id,
				"RUNTIME_AUDIO_POSITION_UNEXPECTED",
				"position_seconds is only accepted for play or seek"
			)
			return
	elif action == "seek":
		var seek_position := _parse_audio_position(request, true)
		if seek_position.has("error"):
			_send_audio_control_error(request_id, seek_position["code"], seek_position["error"])
			return
		position_seconds = seek_position["position_seconds"]
	else:
		var play_position := _parse_audio_position(request, false)
		if play_position.has("error"):
			_send_audio_control_error(request_id, play_position["code"], play_position["error"])
			return
		position_seconds = play_position["position_seconds"]

	if action in ["play", "seek"] and player.get_stream() == null:
		_send_audio_control_error(
			request_id,
			"RUNTIME_AUDIO_STREAM_MISSING",
			"AudioStreamPlayer2D must have a stream before play or seek"
		)
		return
	match action:
		"play":
			player.play(float(position_seconds))
		"stop":
			player.stop()
		"seek":
			player.seek(float(position_seconds))
	var result := {"ok": true, "action": action, "player": _audio_player_state(player, path)}
	if action in ["play", "seek"]:
		result["requested_position_seconds"] = position_seconds
	_send_message("audio_control_result", [request_id, result])


func _parse_audio_position(request: Dictionary, required: bool) -> Dictionary:
	if not request.has("position_seconds"):
		if required:
			return {
				"code": "RUNTIME_AUDIO_POSITION_REQUIRED",
				"error": "seek requires position_seconds"
			}
		return {"position_seconds": 0.0}
	var value: Variant = request["position_seconds"]
	if not (value is int or value is float) or not is_finite(float(value)) \
		or float(value) < 0.0 or float(value) > MAX_AUDIO_POSITION_SECONDS:
		return {
			"code": "RUNTIME_AUDIO_POSITION_INVALID",
			"error": "position_seconds must be a finite number between 0 and %.0f" % MAX_AUDIO_POSITION_SECONDS
		}
	return {"position_seconds": float(value)}


func _resolve_runtime_scene_node(path: String) -> Dictionary:
	return _resolve_runtime_scene_node_with_prefix(path, "RUNTIME_AUDIO")


func _resolve_runtime_scene_node_with_prefix(path: String, error_prefix: String) -> Dictionary:
	if path.is_empty() or path.length() > MAX_RUNTIME_NODE_PATH_LENGTH or not path.begins_with("/") \
		or path.contains("//"):
		return {
			"code": "%s_PATH_INVALID" % error_prefix,
			"error": "path must be a bounded absolute scene node path"
		}
	var segments := path.trim_prefix("/").split("/", false)
	if segments.is_empty() or segments[0].is_empty():
		return {
			"code": "%s_PATH_INVALID" % error_prefix,
			"error": "path must name the running scene root"
		}
	for segment in segments:
		if segment in [".", ".."]:
			return {
				"code": "%s_PATH_INVALID" % error_prefix,
				"error": "path cannot contain . or .. segments"
			}
	var scene_root := get_tree().current_scene
	if scene_root == null:
		return {
			"code": "%s_SCENE_UNAVAILABLE" % error_prefix,
			"error": "The running game does not expose a current scene"
		}
	if str(segments[0]) != scene_root.name:
		return {
			"code": "%s_SCENE_ROOT_MISMATCH" % error_prefix,
			"error": "path must begin with the running scene root '%s'" % scene_root.name
		}
	var node: Node = scene_root
	for index in range(1, segments.size()):
		var child := node.get_node_or_null(NodePath(str(segments[index])))
		if child == null:
			return {
				"code": "%s_NODE_NOT_FOUND" % error_prefix,
				"error": "No runtime node exists at path: %s" % path
			}
		node = child
	return {"node": node}


func _audio_player_state(player: AudioStreamPlayer2D, path: String) -> Dictionary:
	var stream := player.get_stream()
	var stream_length := 0.0 if stream == null else stream.get_length()
	return {
		"path": path,
		"name": str(player.name),
		"is_playing": player.is_playing(),
		"playback_position_seconds": _safe_runtime_number(player.get_playback_position()),
		"stream_path": "" if stream == null else stream.resource_path,
		"stream_type": "" if stream == null else stream.get_class(),
		"stream_length_seconds": _safe_runtime_number(stream_length),
	}


func _safe_runtime_number(value: float) -> float:
	return value if is_finite(value) else 0.0


func _send_audio_control_error(request_id: String, code: String, message: String) -> void:
	_send_message("audio_control_result", [request_id, {"ok": false, "code": code, "message": message}])


func _decode_input_event(value) -> Dictionary:
	if not value is Dictionary:
		return {"error": "Each input event must be an object"}
	var event_type := str(value.get("type", "")).strip_edges().to_lower()
	if event_type == "action":
		var action := str(value.get("action", "")).strip_edges()
		if action.is_empty() or action.length() > 256 or not value.get("pressed", null) is bool:
			return {"error": "action events require action and boolean pressed"}
		var action_event := InputEventAction.new()
		action_event.action = StringName(action)
		action_event.pressed = value["pressed"]
		return {"event": action_event}
	if event_type == "key":
		if not value.get("pressed", null) is bool:
			return {"error": "key events require boolean pressed"}
		var key_fields := ["keycode", "physical_keycode", "unicode"]
		var supplied := 0
		for field in key_fields:
			if value.has(field):
				supplied += 1
		if supplied != 1:
			return {"error": "key events require exactly one of keycode, physical_keycode, or unicode"}
		var key_event := InputEventKey.new()
		for field in key_fields:
			if not value.has(field):
				continue
			if not _is_valid_key_value(value[field]):
				return {"error": "%s must be a valid non-negative key value" % field}
			key_event.set(field, int(value[field]))
		key_event.pressed = value["pressed"]
		key_event.echo = bool(value.get("echo", false))
		key_event.shift_pressed = bool(value.get("shift", false))
		key_event.alt_pressed = bool(value.get("alt", false))
		key_event.ctrl_pressed = bool(value.get("ctrl", false))
		key_event.meta_pressed = bool(value.get("meta", false))
		return {"event": key_event}
	if event_type == "mouse_button":
		if not value.get("pressed", null) is bool or not _is_valid_mouse_button(value.get("button", 0)):
			return {"error": "mouse_button events require button 1 through 8 and boolean pressed"}
		var position_result := _decode_position(value.get("position", {}), "position")
		if position_result.has("error"):
			return position_result
		var button_event := InputEventMouseButton.new()
		button_event.button_index = int(value["button"])
		button_event.pressed = value["pressed"]
		button_event.double_click = bool(value.get("double_click", false))
		button_event.position = position_result["position"]
		button_event.global_position = position_result["position"]
		return {"event": button_event}
	if event_type == "mouse_motion":
		var motion_position := _decode_position(value.get("position", {}), "position")
		if motion_position.has("error"):
			return motion_position
		var relative_result := _decode_position(value.get("relative", {}), "relative")
		if relative_result.has("error"):
			return relative_result
		var motion_event := InputEventMouseMotion.new()
		motion_event.position = motion_position["position"]
		motion_event.global_position = motion_position["position"]
		motion_event.relative = relative_result["position"]
		return {"event": motion_event}
	if event_type == "screen_touch":
		return _decode_screen_touch_event(value)
	if event_type == "screen_drag":
		return _decode_screen_drag_event(value)
	return {"error": "type must be action, key, mouse_button, mouse_motion, screen_touch, or screen_drag"}


func _decode_screen_touch_event(value: Dictionary) -> Dictionary:
	var fields_error := _input_event_fields_error(
		value, ["type", "index", "position", "pressed", "double_tap", "canceled"]
	)
	if not fields_error.is_empty():
		return {"error": fields_error}
	if not _is_valid_touch_index(value.get("index", null)):
		return {"error": "screen_touch events require index between 0 and %d" % MAX_TOUCH_INDEX}
	if not value.get("pressed", null) is bool:
		return {"error": "screen_touch events require boolean pressed"}
	var position_result := _decode_position(value.get("position", {}), "position")
	if position_result.has("error"):
		return position_result
	if value.has("double_tap") and not value["double_tap"] is bool:
		return {"error": "double_tap must be a boolean"}
	if value.has("canceled") and not value["canceled"] is bool:
		return {"error": "canceled must be a boolean"}
	var touch_event := InputEventScreenTouch.new()
	touch_event.index = int(value["index"])
	touch_event.position = position_result["position"]
	touch_event.pressed = value["pressed"]
	touch_event.double_tap = bool(value.get("double_tap", false))
	touch_event.canceled = bool(value.get("canceled", false))
	return {"event": touch_event}


func _decode_screen_drag_event(value: Dictionary) -> Dictionary:
	var fields_error := _input_event_fields_error(
		value,
		[
			"type", "index", "position", "relative", "screen_relative", "pressure", "tilt",
			"pen_inverted",
		]
	)
	if not fields_error.is_empty():
		return {"error": fields_error}
	if not _is_valid_touch_index(value.get("index", null)):
		return {"error": "screen_drag events require index between 0 and %d" % MAX_TOUCH_INDEX}
	var position_result := _decode_position(value.get("position", {}), "position")
	if position_result.has("error"):
		return position_result
	var relative_result := _decode_position(value.get("relative", {}), "relative")
	if relative_result.has("error"):
		return relative_result
	if value.has("pressure") and not _is_valid_touch_pressure(value["pressure"]):
		return {"error": "pressure must be a finite number between 0 and %.1f" % MAX_TOUCH_PRESSURE}
	var tilt_result: Dictionary = {}
	if value.has("tilt"):
		tilt_result = _decode_touch_tilt(value["tilt"])
		if tilt_result.has("error"):
			return tilt_result
	if value.has("pen_inverted") and not value["pen_inverted"] is bool:
		return {"error": "pen_inverted must be a boolean"}
	var drag_event := InputEventScreenDrag.new()
	drag_event.index = int(value["index"])
	drag_event.position = position_result["position"]
	drag_event.relative = relative_result["position"]
	for field in ["screen_relative"]:
		if not value.has(field):
			continue
		var vector_result := _decode_position(value[field], field)
		if vector_result.has("error"):
			return vector_result
		drag_event.set(field, vector_result["position"])
	if value.has("pressure"):
		drag_event.pressure = float(value["pressure"])
	if value.has("tilt"):
		drag_event.tilt = tilt_result["position"]
	if value.has("pen_inverted"):
		drag_event.pen_inverted = value["pen_inverted"]
	return {"event": drag_event}


func _input_event_fields_error(value: Dictionary, allowed: Array[String]) -> String:
	for field in value:
		if str(field) not in allowed:
			return "input event contains unsupported field: %s" % str(field)
	return ""


func _decode_position(value, name: String) -> Dictionary:
	if not value is Dictionary or not _is_valid_coordinate(value.get("x", null)) \
		or not _is_valid_coordinate(value.get("y", null)):
		return {"error": "%s must contain finite x and y coordinates" % name}
	return {"position": Vector2(float(value["x"]), float(value["y"]))}


func _is_valid_coordinate(value) -> bool:
	if not (value is int or value is float):
		return false
	return absf(float(value)) <= MAX_COORDINATE


func _decode_touch_tilt(value) -> Dictionary:
	var tilt_result := _decode_position(value, "tilt")
	if tilt_result.has("error"):
		return tilt_result
	var tilt: Vector2 = tilt_result["position"]
	if absf(tilt.x) > MAX_TOUCH_TILT or absf(tilt.y) > MAX_TOUCH_TILT:
		return {"error": "tilt coordinates must be between -1 and 1"}
	return tilt_result


func _is_valid_touch_index(value) -> bool:
	if not (value is int or value is float) or value is bool:
		return false
	var numeric_value := float(value)
	return is_finite(numeric_value) and numeric_value >= 0.0 and numeric_value <= MAX_TOUCH_INDEX \
		and is_equal_approx(numeric_value, roundf(numeric_value))


func _is_valid_touch_pressure(value) -> bool:
	return (value is int or value is float) and not (value is bool) and is_finite(float(value)) \
		and float(value) >= 0.0 and float(value) <= MAX_TOUCH_PRESSURE


func _is_valid_key_value(value) -> bool:
	return value is int and not (value is bool) and value >= 0 and value <= 0x7FFFFFFF


func _is_valid_mouse_button(value) -> bool:
	return value is int and not (value is bool) and value >= 1 and value <= 8


func _send_message(message: String, data: Array) -> void:
	if _debugger_active and EngineDebugger.is_active():
		EngineDebugger.send_message("%s:%s" % [CAPTURE_NAME, message], data)

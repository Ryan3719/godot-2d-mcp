extends Node

const CAPTURE_NAME := "godot_2d_mcp"
const MAX_LOG_ENTRY_LENGTH := 2048
const MAX_PENDING_LOGS := 512
const MAX_SCREENSHOT_BYTES := 1_000_000
const MAX_SCREENSHOT_DIMENSION := 1024
const MAX_INPUT_EVENTS := 64
const MAX_COORDINATE := 100_000.0
const MAX_RUNTIME_NODE_PATH_LENGTH := 4096
const MAX_AUDIO_POSITION_SECONDS := 3600.0

var _logger: Logger
var _pending_logs: Array[Dictionary] = []
var _pending_log_mutex := Mutex.new()
var _pending_screenshots: Array[Dictionary] = []
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
		[{"protocol_version": 1, "capabilities": ["logs", "screenshot", "input", "audio_stream_player_2d"]}]
	)


func _exit_tree() -> void:
	if _logger != null:
		OS.remove_logger(_logger)
		_logger = null
	if _debugger_active and EngineDebugger.has_capture(CAPTURE_NAME):
		EngineDebugger.unregister_message_capture(CAPTURE_NAME)


func _process(_delta: float) -> void:
	_flush_logs()
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
	return false


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
	if path.is_empty() or path.length() > MAX_RUNTIME_NODE_PATH_LENGTH or not path.begins_with("/") \
		or path.contains("//"):
		return {
			"code": "RUNTIME_AUDIO_PATH_INVALID",
			"error": "path must be a bounded absolute scene node path"
		}
	var segments := path.trim_prefix("/").split("/", false)
	if segments.is_empty() or segments[0].is_empty():
		return {
			"code": "RUNTIME_AUDIO_PATH_INVALID",
			"error": "path must name the running scene root"
		}
	for segment in segments:
		if segment in [".", ".."]:
			return {
				"code": "RUNTIME_AUDIO_PATH_INVALID",
				"error": "path cannot contain . or .. segments"
			}
	var scene_root := get_tree().current_scene
	if scene_root == null:
		return {
			"code": "RUNTIME_AUDIO_SCENE_UNAVAILABLE",
			"error": "The running game does not expose a current scene"
		}
	if str(segments[0]) != scene_root.name:
		return {
			"code": "RUNTIME_AUDIO_SCENE_ROOT_MISMATCH",
			"error": "path must begin with the running scene root '%s'" % scene_root.name
		}
	var node: Node = scene_root
	for index in range(1, segments.size()):
		var child := node.get_node_or_null(NodePath(str(segments[index])))
		if child == null:
			return {
				"code": "RUNTIME_AUDIO_NODE_NOT_FOUND",
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
	return {"error": "type must be action, key, mouse_button, or mouse_motion"}


func _decode_position(value, name: String) -> Dictionary:
	if not value is Dictionary or not _is_valid_coordinate(value.get("x", null)) \
		or not _is_valid_coordinate(value.get("y", null)):
		return {"error": "%s must contain finite x and y coordinates" % name}
	return {"position": Vector2(float(value["x"]), float(value["y"]))}


func _is_valid_coordinate(value) -> bool:
	if not (value is int or value is float):
		return false
	return absf(float(value)) <= MAX_COORDINATE


func _is_valid_key_value(value) -> bool:
	return value is int and not (value is bool) and value >= 0 and value <= 0x7FFFFFFF


func _is_valid_mouse_button(value) -> bool:
	return value is int and not (value is bool) and value >= 1 and value <= 8


func _send_message(message: String, data: Array) -> void:
	if _debugger_active and EngineDebugger.is_active():
		EngineDebugger.send_message("%s:%s" % [CAPTURE_NAME, message], data)

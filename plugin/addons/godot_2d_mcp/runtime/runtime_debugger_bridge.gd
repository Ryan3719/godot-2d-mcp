@tool
extends EditorDebuggerPlugin

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")

const CAPTURE_NAME := "godot_2d_mcp"
const MAX_LOG_ENTRIES := 1000
const MAX_SCREENSHOT_RESULTS := 8
const MAX_INPUT_RESULTS := 32
const MAX_AUDIO_CONTROL_RESULTS := 32
const MAX_PERFORMANCE_SAMPLE_RESULTS := 16
const MAX_TWEEN_RESULTS := 32

var _autoload_status: Dictionary = {"available": false, "reason": "not_configured"}
var _session_states: Dictionary = {}
var _logs: Array[Dictionary] = []
var _next_log_sequence := 1
var _next_request_number := 1
var _screenshot_requests: Dictionary = {}
var _screenshot_order: Array[String] = []
var _input_requests: Dictionary = {}
var _input_order: Array[String] = []
var _audio_control_requests: Dictionary = {}
var _audio_control_order: Array[String] = []
var _performance_sample_requests: Dictionary = {}
var _performance_sample_order: Array[String] = []
var _tween_requests: Dictionary = {}
var _tween_order: Array[String] = []


func configure_autoload(status: Dictionary) -> void:
	_autoload_status = status.duplicate(true)


func _has_capture(capture: String) -> bool:
	return capture == CAPTURE_NAME


func _setup_session(session_id: int) -> void:
	var session := get_session(session_id)
	_session_states[session_id] = {"ready": false, "started": session.is_active()}
	session.started.connect(_on_session_started.bind(session_id))
	session.stopped.connect(_on_session_stopped.bind(session_id))


func _capture(message: String, data: Array, session_id: int) -> bool:
	var command := message.trim_prefix("%s:" % CAPTURE_NAME)
	match command:
		"ready":
			if data.size() != 1 or not data[0] is Dictionary:
				return true
			var payload: Dictionary = data[0]
			if int(payload.get("protocol_version", 0)) != 1:
				return true
			var state: Dictionary = _session_states.get(session_id, {})
			state["ready"] = true
			state["started"] = true
			state["capabilities"] = payload.get("capabilities", [])
			_session_states[session_id] = state
			return true
		"logs":
			if data.size() == 1 and data[0] is Array:
				_append_logs(data[0], session_id)
			return true
		"screenshot_result":
			if data.size() == 2 and data[1] is Dictionary:
				_store_screenshot_result(str(data[0]), data[1], session_id)
			return true
		"input_result":
			if data.size() == 2 and data[1] is Dictionary:
				_store_input_result(str(data[0]), data[1], session_id)
			return true
		"audio_control_result":
			if data.size() == 2 and data[1] is Dictionary:
				_store_audio_control_result(str(data[0]), data[1], session_id)
			return true
		"performance_sample_result":
			if data.size() == 2 and data[1] is Dictionary:
				_store_performance_sample_result(str(data[0]), data[1], session_id)
			return true
		"tween_result":
			if data.size() == 2 and data[1] is Dictionary:
				_store_tween_result(str(data[0]), data[1], session_id)
			return true
	return false


func get_runtime_state(_params: Dictionary) -> Dictionary:
	var active_session := _active_session_id()
	return {
		"autoload": _autoload_status.duplicate(true),
		"connected": active_session >= 0,
		"active_session_id": active_session if active_session >= 0 else null,
		"log_count": _logs.size(),
		"latest_log_sequence": _next_log_sequence - 1,
		"pending_screenshots": _pending_count(_screenshot_requests),
		"pending_inputs": _pending_count(_input_requests),
		"pending_audio_controls": _pending_count(_audio_control_requests),
		"pending_performance_samples": _pending_count(_performance_sample_requests),
		"pending_tweens": _pending_count(_tween_requests),
	}


func get_logs(params: Dictionary) -> Dictionary:
	var after_sequence := maxi(0, int(params.get("after_sequence", 0)))
	var limit := clampi(int(params.get("limit", 100)), 1, 200)
	var entries: Array[Dictionary] = []
	for entry in _logs:
		if int(entry["sequence"]) <= after_sequence:
			continue
		entries.append(entry.duplicate(true))
		if entries.size() >= limit:
			break
	var next_sequence: Variant = null
	if not entries.is_empty():
		next_sequence = entries.back()["sequence"]
	return {
		"entries": entries,
		"after_sequence": after_sequence,
		"next_sequence": next_sequence,
		"latest_sequence": _next_log_sequence - 1,
		"has_more": next_sequence != null and int(next_sequence) < _next_log_sequence - 1,
	}


func request_screenshot(params: Dictionary) -> Dictionary:
	var session_result := _active_session_result()
	if session_result.has("_error"):
		return session_result
	var request_id := _new_request_id("screenshot")
	_screenshot_requests[request_id] = {"status": "pending", "session_id": session_result["session_id"]}
	(session_result["session"] as EditorDebuggerSession).send_message(
		"%s:screenshot" % CAPTURE_NAME,
		[
			request_id,
			{
				"format": str(params.get("format", "png")),
				"max_width": int(params.get("max_width", 640)),
				"max_height": int(params.get("max_height", 640)),
				"quality": float(params.get("quality", 0.85)),
			},
		]
	)
	return {"request_id": request_id, "status": "pending"}


func get_screenshot(params: Dictionary) -> Dictionary:
	var request_id := str(params.get("request_id", "")).strip_edges()
	if not _screenshot_requests.has(request_id):
		return Errors.make(
			"RUNTIME_SCREENSHOT_NOT_FOUND",
			"No runtime screenshot request exists with this request_id",
			false,
			"Call runtime_screenshot_request first and retain its request_id."
		)
	var result: Dictionary = _screenshot_requests[request_id]
	return {"request_id": request_id, "status": result["status"], "result": result.get("result", {})}


func send_input(params: Dictionary) -> Dictionary:
	var session_result := _active_session_result()
	if session_result.has("_error"):
		return session_result
	var request_id := _new_request_id("input")
	_input_requests[request_id] = {"status": "pending", "session_id": session_result["session_id"]}
	(session_result["session"] as EditorDebuggerSession).send_message(
		"%s:input" % CAPTURE_NAME, [request_id, params["events"]]
	)
	return {"request_id": request_id, "status": "pending"}


func get_input_result(params: Dictionary) -> Dictionary:
	var request_id := str(params.get("request_id", "")).strip_edges()
	if not _input_requests.has(request_id):
		return Errors.make(
			"RUNTIME_INPUT_NOT_FOUND",
			"No runtime input request exists with this request_id",
			false,
			"Call runtime_input_send first and retain its request_id."
		)
	var result: Dictionary = _input_requests[request_id]
	return {"request_id": request_id, "status": result["status"], "result": result.get("result", {})}


func request_audio_stream_player_2d_control(params: Dictionary) -> Dictionary:
	var session_result := _active_session_result()
	if session_result.has("_error"):
		return session_result
	var request_id := _new_request_id("audio")
	_audio_control_requests[request_id] = {
		"status": "pending", "session_id": session_result["session_id"]
	}
	(session_result["session"] as EditorDebuggerSession).send_message(
		"%s:audio_control" % CAPTURE_NAME, [request_id, params.duplicate(true)]
	)
	return {"request_id": request_id, "status": "pending"}


func get_audio_stream_player_2d_control_result(params: Dictionary) -> Dictionary:
	var request_id := str(params.get("request_id", "")).strip_edges()
	if not _audio_control_requests.has(request_id):
		return Errors.make(
			"RUNTIME_AUDIO_CONTROL_NOT_FOUND",
			"No runtime audio control request exists with this request_id",
			false,
			"Call runtime_audio_stream_player_2d_control first and retain its request_id."
		)
	var result: Dictionary = _audio_control_requests[request_id]
	return {"request_id": request_id, "status": result["status"], "result": result.get("result", {})}


func request_performance_sample(params: Dictionary) -> Dictionary:
	var session_result := _active_session_result()
	if session_result.has("_error"):
		return session_result
	var request_id := _new_request_id("performance")
	_performance_sample_requests[request_id] = {
		"status": "pending",
		"session_id": session_result["session_id"],
	}
	(session_result["session"] as EditorDebuggerSession).send_message(
		"%s:performance_sample" % CAPTURE_NAME, [request_id, {"duration_seconds": float(params["duration_seconds"])}]
	)
	return {"request_id": request_id, "status": "pending"}


func get_performance_sample_result(params: Dictionary) -> Dictionary:
	var request_id := str(params.get("request_id", "")).strip_edges()
	if not _performance_sample_requests.has(request_id):
		return Errors.make(
			"RUNTIME_PERFORMANCE_SAMPLE_NOT_FOUND",
			"No runtime performance sample exists with this request_id",
			false,
			"Call runtime_performance_sample_request first and retain its request_id."
		)
	var result: Dictionary = _performance_sample_requests[request_id]
	return {"request_id": request_id, "status": result["status"], "result": result.get("result", {})}


func request_tween_start(params: Dictionary) -> Dictionary:
	var session_result := _active_session_result()
	if session_result.has("_error"):
		return session_result
	var request_id := _new_request_id("tween")
	_tween_requests[request_id] = {"status": "pending", "session_id": session_result["session_id"]}
	(session_result["session"] as EditorDebuggerSession).send_message(
		"%s:tween_start" % CAPTURE_NAME, [request_id, params.duplicate(true)]
	)
	return {"request_id": request_id, "status": "pending"}


func get_tween_result(params: Dictionary) -> Dictionary:
	var request_id := str(params.get("request_id", "")).strip_edges()
	if not _tween_requests.has(request_id):
		return Errors.make(
			"RUNTIME_TWEEN_NOT_FOUND",
			"No runtime tween request exists with this request_id",
			false,
			"Call runtime_tween_start first and retain its request_id."
		)
	var result: Dictionary = _tween_requests[request_id]
	return {"request_id": request_id, "status": result["status"], "result": result.get("result", {})}


func request_tween_stop(params: Dictionary) -> Dictionary:
	var request_id := str(params.get("request_id", "")).strip_edges()
	if not _tween_requests.has(request_id):
		return Errors.make(
			"RUNTIME_TWEEN_NOT_FOUND",
			"No runtime tween request exists with this request_id",
			false,
			"Call runtime_tween_start first and retain its request_id."
		)
	var request: Dictionary = _tween_requests[request_id]
	if str(request.get("status", "")) != "pending":
		return Errors.make(
			"RUNTIME_TWEEN_NOT_ACTIVE",
			"The runtime tween is no longer active",
			false,
			"Only a pending runtime tween can be stopped."
		)
	var session_result := _active_session_result()
	if session_result.has("_error"):
		return session_result
	if int(request.get("session_id", -1)) != int(session_result["session_id"]):
		return Errors.make(
			"RUNTIME_TWEEN_SESSION_MISMATCH",
			"The active runtime session does not own this tween request",
			true,
			"Activate the Godot editor session that started the tween before stopping it."
		)
	(session_result["session"] as EditorDebuggerSession).send_message(
		"%s:tween_stop" % CAPTURE_NAME, [request_id]
	)
	return {"request_id": request_id, "status": "cancellation_requested"}


func _on_session_started(session_id: int) -> void:
	var state: Dictionary = _session_states.get(session_id, {})
	state["started"] = true
	_session_states[session_id] = state


func _on_session_stopped(session_id: int) -> void:
	var state: Dictionary = _session_states.get(session_id, {})
	state["started"] = false
	state["ready"] = false
	_session_states[session_id] = state
	for request_id_value in _tween_requests.keys():
		var request_id := str(request_id_value)
		var request: Dictionary = _tween_requests[request_id]
		if int(request.get("session_id", -1)) != session_id or str(request.get("status", "")) != "pending":
			continue
		request["status"] = "error"
		request["result"] = {
			"ok": false,
			"code": "RUNTIME_TWEEN_SESSION_STOPPED",
			"message": "The game session stopped before the runtime tween completed",
		}
		_tween_requests[request_id] = request
		_tween_order.erase(request_id)
		_tween_order.append(request_id)
	_trim_results(_tween_requests, _tween_order, MAX_TWEEN_RESULTS)


func _append_logs(entries: Array, session_id: int) -> void:
	for raw_entry in entries:
		if not raw_entry is Dictionary:
			continue
		var message := str(raw_entry.get("message", "")).left(2048)
		if message.is_empty():
			continue
		_logs.append(
			{
				"sequence": _next_log_sequence,
				"session_id": session_id,
				"level": "error" if str(raw_entry.get("level", "")) == "error" else "info",
				"message": message,
			}
		)
		_next_log_sequence += 1
		if _logs.size() > MAX_LOG_ENTRIES:
			_logs.pop_front()


func _store_screenshot_result(request_id: String, result: Dictionary, session_id: int) -> void:
	if not _screenshot_requests.has(request_id):
		return
	var request: Dictionary = _screenshot_requests[request_id]
	if int(request.get("session_id", -1)) != session_id:
		return
	request["status"] = "ready" if bool(result.get("ok", false)) else "error"
	request["result"] = result.duplicate(true)
	_screenshot_requests[request_id] = request
	_screenshot_order.erase(request_id)
	_screenshot_order.append(request_id)
	_trim_results(_screenshot_requests, _screenshot_order, MAX_SCREENSHOT_RESULTS)


func _store_input_result(request_id: String, result: Dictionary, session_id: int) -> void:
	if not _input_requests.has(request_id):
		return
	var request: Dictionary = _input_requests[request_id]
	if int(request.get("session_id", -1)) != session_id:
		return
	request["status"] = "ready" if bool(result.get("ok", false)) else "error"
	request["result"] = result.duplicate(true)
	_input_requests[request_id] = request
	_input_order.erase(request_id)
	_input_order.append(request_id)
	_trim_results(_input_requests, _input_order, MAX_INPUT_RESULTS)


func _store_audio_control_result(request_id: String, result: Dictionary, session_id: int) -> void:
	if not _audio_control_requests.has(request_id):
		return
	var request: Dictionary = _audio_control_requests[request_id]
	if int(request.get("session_id", -1)) != session_id:
		return
	request["status"] = "ready" if bool(result.get("ok", false)) else "error"
	request["result"] = result.duplicate(true)
	_audio_control_requests[request_id] = request
	_audio_control_order.erase(request_id)
	_audio_control_order.append(request_id)
	_trim_results(_audio_control_requests, _audio_control_order, MAX_AUDIO_CONTROL_RESULTS)


func _store_performance_sample_result(request_id: String, result: Dictionary, session_id: int) -> void:
	if not _performance_sample_requests.has(request_id):
		return
	var request: Dictionary = _performance_sample_requests[request_id]
	if int(request.get("session_id", -1)) != session_id:
		return
	request["status"] = "ready" if bool(result.get("ok", false)) else "error"
	request["result"] = result.duplicate(true)
	_performance_sample_requests[request_id] = request
	_performance_sample_order.erase(request_id)
	_performance_sample_order.append(request_id)
	_trim_results(
		_performance_sample_requests, _performance_sample_order, MAX_PERFORMANCE_SAMPLE_RESULTS
	)


func _store_tween_result(request_id: String, result: Dictionary, session_id: int) -> void:
	if not _tween_requests.has(request_id):
		return
	var request: Dictionary = _tween_requests[request_id]
	if int(request.get("session_id", -1)) != session_id:
		return
	request["status"] = "ready" if bool(result.get("ok", false)) else "error"
	request["result"] = result.duplicate(true)
	_tween_requests[request_id] = request
	_tween_order.erase(request_id)
	_tween_order.append(request_id)
	_trim_results(_tween_requests, _tween_order, MAX_TWEEN_RESULTS)


func _active_session_result() -> Dictionary:
	if not bool(_autoload_status.get("available", false)):
		return Errors.make(
			"RUNTIME_BRIDGE_UNAVAILABLE",
			"The Godot 2D MCP runtime autoload is unavailable",
			false,
			str(_autoload_status.get("hint", "Resolve the configured runtime autoload before running the scene.")),
			_autoload_status
		)
	var session_id := _active_session_id()
	if session_id < 0:
		return Errors.make(
			"RUNTIME_NOT_CONNECTED",
			"No running Godot scene has connected the runtime bridge",
			true,
			"Start a scene with editor_run and wait for runtime_get_state to report connected: true."
		)
	return {"session_id": session_id, "session": get_session(session_id)}


func _active_session_id() -> int:
	for raw_session_id in _session_states:
		var session_id := int(raw_session_id)
		var state: Dictionary = _session_states[session_id]
		if not bool(state.get("ready", false)):
			continue
		var session := get_session(session_id)
		if session != null and session.is_active():
			return session_id
	return -1


func _new_request_id(kind: String) -> String:
	var request_id := "%s-%x-%d" % [kind, Time.get_ticks_usec(), _next_request_number]
	_next_request_number += 1
	return request_id


func _pending_count(requests: Dictionary) -> int:
	var count := 0
	for request_id in requests:
		if str((requests[request_id] as Dictionary).get("status", "")) == "pending":
			count += 1
	return count


func _trim_results(requests: Dictionary, order: Array[String], maximum: int) -> void:
	while order.size() > maximum:
		requests.erase(order.pop_front())

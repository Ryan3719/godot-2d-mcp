@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")

const DEFAULT_FRAME_BUDGET_MS := 4
const MAX_QUEUED_COMMANDS := 256

var _handlers: Dictionary = {}
var _queue: Array[Dictionary] = []


func register(command: String, handler: Callable) -> void:
	_handlers[command] = handler


func enqueue(command: Dictionary) -> Dictionary:
	if _queue.size() >= MAX_QUEUED_COMMANDS:
		return Errors.make(
			"QUEUE_FULL",
			"Godot command queue is full",
			true,
			"Retry after the editor finishes pending work."
		)
	_queue.append(command)
	return {}


func tick(meta: Dictionary, budget_ms: int = DEFAULT_FRAME_BUDGET_MS) -> Array[Dictionary]:
	var responses: Array[Dictionary] = []
	var started := Time.get_ticks_msec()
	while not _queue.is_empty() and Time.get_ticks_msec() - started < budget_ms:
		var command: Dictionary = _queue.pop_front()
		responses.append(_dispatch(command, meta))
	return responses


func clear() -> void:
	_handlers.clear()
	_queue.clear()


func _dispatch(message: Dictionary, meta: Dictionary) -> Dictionary:
	var request_id: String = str(message.get("request_id", ""))
	var command: String = str(message.get("command", ""))
	var params = message.get("params", {})
	if request_id.is_empty() or command.is_empty() or not params is Dictionary:
		return _response(
			request_id,
			Errors.make("INVALID_REQUEST", "Command message is missing required fields"),
			meta
		)
	if not _handlers.has(command):
		return _response(
			request_id,
			Errors.make("UNKNOWN_COMMAND", "Unknown Godot command: %s" % command),
			meta
		)

	var result = (_handlers[command] as Callable).call(params)
	if not result is Dictionary:
		result = Errors.make("INTERNAL_ERROR", "Command handler returned an invalid result")
	var scene_mutated := bool(result.get("_scene_mutated", false))
	result.erase("_scene_mutated")
	var response := _response(request_id, result, meta)
	if scene_mutated and response["status"] == "ok":
		response["_scene_mutated"] = true
	return response


func _response(request_id: String, result: Dictionary, meta: Dictionary) -> Dictionary:
	if result.has("_error"):
		return {
			"type": "response",
			"request_id": request_id,
			"status": "error",
			"data": {},
			"error": result["_error"],
			"meta": meta,
		}
	return {
		"type": "response",
		"request_id": request_id,
		"status": "ok",
		"data": result,
		"meta": meta,
	}

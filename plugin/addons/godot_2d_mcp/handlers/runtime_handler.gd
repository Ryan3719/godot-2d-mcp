@tool
extends RefCounted


var _runtime_bridge: RefCounted


func _init(runtime_bridge: RefCounted) -> void:
	_runtime_bridge = runtime_bridge


func get_runtime_state(params: Dictionary) -> Dictionary:
	return _runtime_bridge.get_runtime_state(params)


func get_runtime_logs(params: Dictionary) -> Dictionary:
	return _runtime_bridge.get_logs(params)


func request_runtime_screenshot(params: Dictionary) -> Dictionary:
	return _runtime_bridge.request_screenshot(params)


func get_runtime_screenshot(params: Dictionary) -> Dictionary:
	return _runtime_bridge.get_screenshot(params)


func send_runtime_input(params: Dictionary) -> Dictionary:
	return _runtime_bridge.send_input(params)


func get_runtime_input_result(params: Dictionary) -> Dictionary:
	return _runtime_bridge.get_input_result(params)

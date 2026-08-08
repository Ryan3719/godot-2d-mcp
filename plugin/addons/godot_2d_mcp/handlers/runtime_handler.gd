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


func request_runtime_audio_stream_player_2d_control(params: Dictionary) -> Dictionary:
	return _runtime_bridge.request_audio_stream_player_2d_control(params)


func get_runtime_audio_stream_player_2d_control_result(params: Dictionary) -> Dictionary:
	return _runtime_bridge.get_audio_stream_player_2d_control_result(params)


func request_runtime_performance_sample(params: Dictionary) -> Dictionary:
	return _runtime_bridge.request_performance_sample(params)


func get_runtime_performance_sample_result(params: Dictionary) -> Dictionary:
	return _runtime_bridge.get_performance_sample_result(params)


func request_runtime_tween_start(params: Dictionary) -> Dictionary:
	return _runtime_bridge.request_tween_start(params)


func get_runtime_tween_result(params: Dictionary) -> Dictionary:
	return _runtime_bridge.get_tween_result(params)


func request_runtime_tween_stop(params: Dictionary) -> Dictionary:
	return _runtime_bridge.request_tween_stop(params)

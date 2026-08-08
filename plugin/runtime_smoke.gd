extends Node2D

@export var tween_script_value := 0.0


func _ready() -> void:
	print("GODOT_2D_MCP_RUNTIME_SMOKE_READY")


func _input(event: InputEvent) -> void:
	if event is InputEventAction and event.action == &"godot_2d_mcp_smoke":
		print("GODOT_2D_MCP_RUNTIME_INPUT_RECEIVED")
	elif event is InputEventScreenTouch:
		var touch := event as InputEventScreenTouch
		if touch.index != 1:
			return
		if touch.pressed and touch.double_tap and touch.position.is_equal_approx(Vector2(32.0, 48.0)):
			print("GODOT_2D_MCP_RUNTIME_TOUCH_PRESS_RECEIVED")
		elif not touch.pressed and touch.canceled and touch.position.is_equal_approx(Vector2(64.0, 96.0)):
			print("GODOT_2D_MCP_RUNTIME_TOUCH_RELEASE_RECEIVED")
	elif event is InputEventScreenDrag:
		var drag := event as InputEventScreenDrag
		if drag.index == 1 \
				and drag.position.is_equal_approx(Vector2(64.0, 96.0)) \
				and drag.relative.is_equal_approx(Vector2(32.0, 48.0)) \
				and drag.screen_relative.is_equal_approx(Vector2(64.0, 96.0)) \
				and is_equal_approx(drag.pressure, 0.5) \
				and drag.tilt.is_equal_approx(Vector2(0.25, -0.25)) \
				and drag.pen_inverted:
			print("GODOT_2D_MCP_RUNTIME_TOUCH_DRAG_RECEIVED")

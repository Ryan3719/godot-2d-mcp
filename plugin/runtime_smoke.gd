extends Node2D


func _ready() -> void:
	print("GODOT_2D_MCP_RUNTIME_SMOKE_READY")


func _input(event: InputEvent) -> void:
	if event is InputEventAction and event.action == &"godot_2d_mcp_smoke":
		print("GODOT_2D_MCP_RUNTIME_INPUT_RECEIVED")

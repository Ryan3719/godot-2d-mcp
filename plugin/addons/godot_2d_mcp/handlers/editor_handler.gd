@tool
extends RefCounted

const EditorState := preload("res://addons/godot_2d_mcp/utils/editor_state.gd")


func get_state(_params: Dictionary) -> Dictionary:
	var state := EditorState.snapshot()
	state["capabilities"] = {
		"protocol_version": 1,
		"minimum_godot_version": "4.7",
		"domains": ["editor", "scene", "class"],
		"write_tools": false,
	}
	return state

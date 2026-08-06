@tool
extends RefCounted

const EditorState := preload("res://addons/godot_2d_mcp/utils/editor_state.gd")
const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")


func get_state(_params: Dictionary) -> Dictionary:
	var state := EditorState.snapshot()
	state["capabilities"] = {
		"protocol_version": 1,
		"minimum_godot_version": "4.7",
		"domains": ["editor", "scene", "class"],
		"write_tools": true,
	}
	return state


func run(params: Dictionary) -> Dictionary:
	if EditorState.readiness() == "importing":
		return Errors.make(
			"EDITOR_IMPORTING",
			"The editor cannot start a scene while project resources are importing",
			true,
			"Wait for editor_get_state to report readiness 'ready' and retry."
		)
	if EditorInterface.is_playing_scene():
		return Errors.make(
			"SCENE_ALREADY_PLAYING",
			"A scene is already running",
			false,
			"Call editor_stop and wait for editor_get_state to report 'stopped' before starting another scene.",
			{"playing_scene": EditorInterface.get_playing_scene()}
		)

	var mode := str(params.get("mode", "current")).strip_edges().to_lower()
	if mode not in ["current", "main", "custom"]:
		return Errors.make(
			"INVALID_RUN_MODE",
			"mode must be current, main, or custom",
			false,
			"Use current for the edited scene, main for the project's main scene, or custom with scene_file."
		)

	var requested_scene := ""
	match mode:
		"current":
			var scene_root := EditorInterface.get_edited_scene_root()
			if scene_root == null:
				return Errors.make(
					"NO_EDITED_SCENE", "No scene is open in the Godot editor", false,
					"Open a saved scene or use mode 'main' or 'custom'."
				)
			requested_scene = scene_root.scene_file_path
			if requested_scene.is_empty():
				return Errors.make(
					"SCENE_HAS_NO_PATH",
					"The current scene has never been saved",
					false,
					"Save the scene once in Godot before running it."
				)
			EditorInterface.play_current_scene()
		"main":
			requested_scene = str(ProjectSettings.get_setting("application/run/main_scene", ""))
			var main_scene_result := _validate_packed_scene(requested_scene, "MAIN_SCENE_NOT_CONFIGURED")
			if main_scene_result.has("_error"):
				return main_scene_result
			EditorInterface.play_main_scene()
		"custom":
			requested_scene = str(params.get("scene_file", "")).strip_edges()
			if requested_scene.is_empty():
				return Errors.make(
					"CUSTOM_SCENE_REQUIRED",
					"scene_file is required when mode is custom",
					false,
					"Supply an existing PackedScene under res://."
				)
			var custom_scene_result := _validate_packed_scene(requested_scene, "RUN_SCENE_NOT_FOUND")
			if custom_scene_result.has("_error"):
				return custom_scene_result
			EditorInterface.play_custom_scene(requested_scene)

	var state := EditorState.snapshot()
	return {
		"requested": true,
		"mode": mode,
		"requested_scene": requested_scene,
		"play_state": state["play_state"],
		"playing_scene": state["playing_scene"],
		"state_may_be_starting": not EditorInterface.is_playing_scene(),
	}


func stop(_params: Dictionary) -> Dictionary:
	var was_playing := EditorInterface.is_playing_scene()
	var stopped_scene := EditorInterface.get_playing_scene()
	if was_playing:
		EditorInterface.stop_playing_scene()
	var state := EditorState.snapshot()
	return {
		"requested": was_playing,
		"was_playing": was_playing,
		"stopped_scene": stopped_scene,
		"play_state": state["play_state"],
		"playing_scene": state["playing_scene"],
		"state_may_be_stopping": was_playing and EditorInterface.is_playing_scene(),
	}


func _validate_packed_scene(scene_file: String, error_code: String) -> Dictionary:
	if not scene_file.begins_with("res://") or scene_file.length() > 4096 \
		or scene_file.contains("/../") or scene_file.ends_with("/.."):
		return Errors.make(
			error_code,
			"Scene file must be an existing PackedScene under res://",
			false,
			"Use a project-relative scene path such as res://scenes/game.tscn.",
			{"scene_file": scene_file}
		)
	var resource := ResourceLoader.load(scene_file, "PackedScene")
	if not resource is PackedScene:
		return Errors.make(
			error_code,
			"Scene file is not an existing PackedScene: %s" % scene_file,
			false,
			"Check the path with editor_get_state or use an existing .tscn file.",
			{"scene_file": scene_file}
		)
	return {}

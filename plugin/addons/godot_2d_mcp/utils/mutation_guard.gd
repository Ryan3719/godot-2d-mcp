@tool
extends RefCounted

const EditorState := preload("res://addons/godot_2d_mcp/utils/editor_state.gd")
const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")


static func require_scene(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var scene_root := EditorInterface.get_edited_scene_root()
	if scene_root == null:
		return Errors.make(
			"NO_EDITED_SCENE", "No scene is open in the Godot editor", false, "Open a scene first."
		)

	if require_writable:
		var readiness := EditorState.readiness()
		if readiness != "ready":
			return Errors.make(
				"EDITOR_NOT_WRITABLE",
				"The editor is not writable while its state is '%s'" % readiness,
				readiness == "importing",
				"Wait for imports to finish and stop the running scene before editing.",
				{"readiness": readiness}
			)

	var expected_scene_file := str(params.get("scene_file", "")).strip_edges()
	if not expected_scene_file.is_empty() and expected_scene_file != scene_root.scene_file_path:
		return Errors.make(
			"EDITED_SCENE_MISMATCH",
			"The active scene changed before the command was applied",
			false,
			"Read editor_get_state again and target the active scene explicitly.",
			{"expected": expected_scene_file, "actual": scene_root.scene_file_path}
		)

	return {"scene_root": scene_root}

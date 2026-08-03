@tool
extends RefCounted


static func readiness() -> String:
	var filesystem := EditorInterface.get_resource_filesystem()
	if filesystem != null and filesystem.is_scanning():
		return "importing"
	if EditorInterface.is_playing_scene():
		return "playing"
	if EditorInterface.get_edited_scene_root() == null:
		return "no_scene"
	return "ready"


static func snapshot() -> Dictionary:
	var scene_root := EditorInterface.get_edited_scene_root()
	var current_scene := ""
	if scene_root != null:
		current_scene = scene_root.scene_file_path
	var version_info := Engine.get_version_info()
	return {
		"project_name": str(ProjectSettings.get_setting("application/config/name", "Godot Project")),
		"project_path": ProjectSettings.globalize_path("res://").trim_suffix("/"),
		"godot_version": str(version_info.get("string", Engine.get_version_info())),
		"readiness": readiness(),
		"current_scene": current_scene,
		"open_scenes": Array(EditorInterface.get_open_scenes()),
		"play_state": "playing" if EditorInterface.is_playing_scene() else "stopped",
		"playing_scene": EditorInterface.get_playing_scene(),
	}

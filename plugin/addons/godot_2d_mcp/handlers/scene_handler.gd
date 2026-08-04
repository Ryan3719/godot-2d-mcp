@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const TypePolicy := preload("res://addons/godot_2d_mcp/utils/type_policy.gd")

const MAX_SCANNED_NODES := 10000

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_hierarchy(params: Dictionary) -> Dictionary:
	var scene_root := EditorInterface.get_edited_scene_root()
	if scene_root == null:
		return Errors.make(
			"NO_EDITED_SCENE", "No scene is open in the Godot editor", false, "Open a scene first."
		)

	var root_path := str(params.get("root_path", ""))
	var requested_root := ScenePath.resolve(root_path, scene_root)
	if requested_root == null:
		return Errors.make(
			"NODE_NOT_FOUND",
			"Hierarchy root not found: %s" % root_path,
			false,
			"Use an absolute scene path such as /%s/UI." % scene_root.name
		)

	var max_depth := clampi(int(params.get("max_depth", 8)), 0, 64)
	var offset := maxi(0, int(params.get("offset", 0)))
	var limit := clampi(int(params.get("limit", 200)), 1, 1000)
	var items: Array[Dictionary] = []
	var stack: Array[Dictionary] = [{"node": requested_root, "depth": 0}]
	var scanned := 0

	while not stack.is_empty() and scanned < MAX_SCANNED_NODES:
		var entry: Dictionary = stack.pop_back()
		var node: Node = entry["node"]
		var depth: int = entry["depth"]
		items.append(_serialize_node(node, scene_root, depth))
		scanned += 1
		if depth >= max_depth:
			continue
		var children := node.get_children(false)
		for index in range(children.size() - 1, -1, -1):
			stack.append({"node": children[index], "depth": depth + 1})

	var end := mini(offset + limit, items.size())
	var page: Array[Dictionary] = []
	if offset < items.size():
		page.assign(items.slice(offset, end))
	return {
		"scene_file": scene_root.scene_file_path,
		"root_path": ScenePath.from_node(requested_root, scene_root),
		"nodes": page,
		"total": items.size(),
		"offset": offset,
		"limit": limit,
		"has_more": end < items.size(),
		"scan_truncated": not stack.is_empty(),
	}


func save_scene(params: Dictionary) -> Dictionary:
	var guarded := MutationGuard.require_scene(params)
	if guarded.has("_error"):
		return guarded
	var scene_root: Node = guarded["scene_root"]
	if scene_root.scene_file_path.is_empty():
		return Errors.make(
			"SCENE_HAS_NO_PATH",
			"The current scene has never been saved",
			false,
			"Save the scene once in Godot before calling scene_save."
		)
	var error := EditorInterface.save_scene()
	if error != OK:
		return Errors.make(
			"SCENE_SAVE_FAILED",
			"Godot failed to save the current scene: %s" % error_string(error),
			false,
			"Check editor output and project file permissions.",
			{"error": error, "error_name": error_string(error)}
		)
	return {
		"scene_file": scene_root.scene_file_path,
		"saved": true,
		"undoable": false,
	}


func undo_scene(params: Dictionary) -> Dictionary:
	var history_result := _get_scene_history(params)
	if history_result.has("_error"):
		return history_result
	var history: UndoRedo = history_result["history"]
	if not history.has_undo():
		return _history_response(history, false, "")
	var action_name := history.get_current_action_name()
	var changed := history.undo()
	var response := _history_response(history, changed, action_name)
	if changed:
		response["_scene_mutated"] = true
	return response


func redo_scene(params: Dictionary) -> Dictionary:
	var history_result := _get_scene_history(params)
	if history_result.has("_error"):
		return history_result
	var history: UndoRedo = history_result["history"]
	if not history.has_redo():
		return _history_response(history, false, "")
	var next_action := history.get_current_action() + 1
	var action_name := history.get_action_name(next_action)
	var changed := history.redo()
	var response := _history_response(history, changed, action_name)
	if changed:
		response["_scene_mutated"] = true
	return response


func _get_scene_history(params: Dictionary) -> Dictionary:
	var guarded := MutationGuard.require_scene(params)
	if guarded.has("_error"):
		return guarded
	var scene_root: Node = guarded["scene_root"]
	var history_id := _undo_redo.get_object_history_id(scene_root)
	var history := _undo_redo.get_history_undo_redo(history_id)
	if history == null:
		return Errors.make("UNDO_HISTORY_UNAVAILABLE", "No undo history exists for the edited scene")
	return {"history": history}


func _history_response(history: UndoRedo, changed: bool, action_name: String) -> Dictionary:
	return {
		"changed": changed,
		"action": action_name,
		"has_undo": history.has_undo(),
		"has_redo": history.has_redo(),
		"version": history.get_version(),
	}


func _serialize_node(node: Node, scene_root: Node, depth: int) -> Dictionary:
	var script_path := ""
	var script := node.get_script()
	if script is Script:
		script_path = script.resource_path
	var owner_path := ""
	if node.owner != null:
		owner_path = ScenePath.from_node(node.owner, scene_root)
	return {
		"path": ScenePath.from_node(node, scene_root),
		"name": String(node.name),
		"type": node.get_class(),
		"depth": depth,
		"child_count": node.get_child_count(false),
		"owner_path": owner_path,
		"script_path": script_path,
		"groups": Array(node.get_groups()),
		"supported_2d": TypePolicy.is_supported_node_class(node.get_class()),
	}

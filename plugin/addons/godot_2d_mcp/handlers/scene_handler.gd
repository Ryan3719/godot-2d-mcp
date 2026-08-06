@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const EditorState := preload("res://addons/godot_2d_mcp/utils/editor_state.gd")
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


func create_scene(params: Dictionary) -> Dictionary:
	var writable := _require_scene_switchable()
	if writable != null:
		return writable
	var scene_path := str(params.get("scene_path", "")).strip_edges()
	var path_error := _validate_new_scene_path(scene_path)
	if path_error != null:
		return path_error
	if FileAccess.file_exists(scene_path) or ResourceLoader.exists(scene_path):
		return Errors.make(
			"SCENE_PATH_EXISTS",
			"Refusing to overwrite existing scene: %s" % scene_path,
			false,
			"Choose a new project-local .tscn path."
		)

	var root_type := str(params.get("root_type", "Node2D")).strip_edges()
	if not TypePolicy.is_supported_node_class(StringName(root_type)):
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"Scene root type is not allowed by the 2D policy: %s" % root_type,
			false,
			"Use class_search to select a supported 2D or UI node type."
		)
	var root_object := ClassDB.instantiate(StringName(root_type))
	if not root_object is Node:
		if root_object != null:
			root_object.free()
		return Errors.make("INSTANTIATION_FAILED", "Failed to instantiate scene root type: %s" % root_type)
	var root: Node = root_object
	var root_name := str(params.get("root_name", "")).strip_edges()
	if root_name.is_empty():
		root_name = root_type
	if root_name.length() > 256 or root_name.validate_node_name() != root_name:
		root.free()
		return Errors.make("INVALID_NODE_NAME", "Invalid scene root name: %s" % root_name)
	root.name = root_name

	var directory_error := DirAccess.make_dir_recursive_absolute(
		ProjectSettings.globalize_path(scene_path.get_base_dir())
	)
	if directory_error != OK:
		root.free()
		return Errors.make(
			"SCENE_DIRECTORY_CREATE_FAILED",
			"Godot could not create the scene directory: %s" % scene_path.get_base_dir(),
			false,
			"Check project directory permissions.",
			{"error": directory_error, "error_name": error_string(directory_error)}
		)
	var packed_scene := PackedScene.new()
	var pack_error := packed_scene.pack(root)
	root.free()
	if pack_error != OK:
		return Errors.make(
			"SCENE_PACK_FAILED",
			"Godot could not pack the new scene: %s" % error_string(pack_error),
			false,
			"Choose a supported built-in 2D or UI root type.",
			{"error": pack_error, "error_name": error_string(pack_error)}
		)
	var save_error := ResourceSaver.save(packed_scene, scene_path)
	if save_error != OK:
		return Errors.make(
			"SCENE_CREATE_FAILED",
			"Godot could not save the new scene: %s" % error_string(save_error),
			false,
			"Check project directory permissions and choose a valid .tscn path.",
			{"error": save_error, "error_name": error_string(save_error)}
		)
	return _open_scene_path(scene_path, true)


func open_scene(params: Dictionary) -> Dictionary:
	var writable := _require_scene_switchable()
	if writable != null:
		return writable
	var scene_path := str(params.get("scene_path", "")).strip_edges()
	var path_error := _validate_existing_scene_path(scene_path)
	if path_error != null:
		return path_error
	var audited := _load_supported_scene(scene_path)
	if audited.has("_error"):
		return audited
	return _open_scene_path(scene_path, false)


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


func _require_scene_switchable() -> Variant:
	var readiness := EditorState.readiness()
	if readiness == "importing" or readiness == "playing":
		return Errors.make(
			"EDITOR_NOT_WRITABLE",
			"The editor cannot switch scenes while its state is '%s'" % readiness,
			readiness == "importing",
			"Wait for imports to finish and stop the running scene before switching scenes.",
			{"readiness": readiness}
		)
	return null


func _validate_new_scene_path(scene_path: String) -> Variant:
	var path_error := _validate_scene_path(scene_path)
	if path_error != null:
		return path_error
	if not scene_path.ends_with(".tscn"):
		return Errors.make(
			"INVALID_SCENE_PATH",
			"New scenes must use a .tscn path: %s" % scene_path,
			false,
			"Pass a project-local path such as res://scenes/main.tscn."
		)
	return null


func _validate_existing_scene_path(scene_path: String) -> Variant:
	var path_error := _validate_scene_path(scene_path)
	if path_error != null:
		return path_error
	if not ResourceLoader.exists(scene_path):
		return Errors.make(
			"SCENE_NOT_FOUND",
			"Scene path does not exist: %s" % scene_path,
			false,
			"Pass an existing project-local .tscn or .scn path."
		)
	return null


func _validate_scene_path(scene_path: String) -> Variant:
	if (
		scene_path.is_empty()
		or scene_path.length() > 4096
		or not scene_path.begins_with("res://")
		or scene_path.contains("/../")
		or scene_path.ends_with("/..")
		or scene_path.contains("\\")
	):
		return Errors.make(
			"INVALID_SCENE_PATH",
			"scene_path must be a bounded project-local res:// path",
			false,
			"Pass a path such as res://scenes/main.tscn."
		)
	return null


func _load_supported_scene(scene_path: String) -> Dictionary:
	var resource := ResourceLoader.load(scene_path)
	if not resource is PackedScene:
		return Errors.make(
			"SCENE_TYPE_MISMATCH",
			"scene_path does not load a PackedScene: %s" % scene_path,
			false,
			"Pass a .tscn or .scn resource whose complete tree uses supported 2D and UI nodes."
		)
	var instance := (resource as PackedScene).instantiate()
	if instance == null:
		return Errors.make("SCENE_INSTANTIATION_FAILED", "Godot could not open scene: %s" % scene_path)
	var unsupported_type := ""
	for descendant in _collect_subtree(instance):
		if not TypePolicy.is_supported_node_class(descendant.get_class()):
			unsupported_type = descendant.get_class()
			break
	instance.free()
	if not unsupported_type.is_empty():
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"Scene '%s' contains unsupported node type %s" % [scene_path, unsupported_type],
			false,
			"Open scenes whose complete tree uses supported 2D and UI node types."
		)
	return {}


func _open_scene_path(scene_path: String, created: bool) -> Dictionary:
	EditorInterface.open_scene_from_path(scene_path)
	var scene_root := EditorInterface.get_edited_scene_root()
	if scene_root == null or scene_root.scene_file_path != scene_path:
		return Errors.make(
			"SCENE_OPEN_FAILED",
			"Godot did not switch to scene: %s" % scene_path,
			true,
			"Wait for the editor to become ready, then retry scene_open.",
			{
				"expected": scene_path,
				"actual": "" if scene_root == null else scene_root.scene_file_path,
			}
		)
	return {
		"scene_file": scene_path,
		"root_path": ScenePath.from_node(scene_root, scene_root),
		"root_name": String(scene_root.name),
		"root_type": scene_root.get_class(),
		"created": created,
		"opened": true,
		"undoable": false,
	}


func _collect_subtree(root: Node) -> Array[Node]:
	var nodes: Array[Node] = []
	var stack: Array[Node] = [root]
	while not stack.is_empty():
		var node := stack.pop_back()
		nodes.append(node)
		for child in node.get_children(false):
			stack.append(child)
	return nodes


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

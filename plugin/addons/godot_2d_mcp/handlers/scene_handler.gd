@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const TypePolicy := preload("res://addons/godot_2d_mcp/utils/type_policy.gd")

const MAX_SCANNED_NODES := 10000


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

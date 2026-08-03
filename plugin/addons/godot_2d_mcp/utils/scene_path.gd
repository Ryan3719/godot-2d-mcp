@tool
extends RefCounted


static func from_node(node: Node, scene_root: Node) -> String:
	if node == scene_root:
		return "/%s" % scene_root.name
	return "/%s/%s" % [scene_root.name, scene_root.get_path_to(node)]


static func resolve(path: String, scene_root: Node) -> Node:
	var clean_path := path.strip_edges().trim_suffix("/")
	var root_path := "/%s" % scene_root.name
	if clean_path.is_empty() or clean_path == "/" or clean_path == root_path:
		return scene_root
	if clean_path.begins_with(root_path + "/"):
		clean_path = clean_path.trim_prefix(root_path + "/")
	elif clean_path.begins_with("/"):
		return null
	return scene_root.get_node_or_null(NodePath(clean_path))

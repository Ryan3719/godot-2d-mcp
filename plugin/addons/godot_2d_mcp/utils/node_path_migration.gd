@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")


static func plan(
	scene_root: Node, moved_node: Node, new_parent: Node, new_name: String
) -> Dictionary:
	var property_records: Array[Dictionary] = []
	var track_records: Array[Dictionary] = []
	var nodes := _collect_scene_nodes(scene_root)
	for base_node in nodes:
		if not _is_locally_owned(base_node, scene_root):
			continue
		for property_info_value in base_node.get_property_list():
			var property_info: Dictionary = property_info_value
			if int(property_info.get("type", TYPE_NIL)) != TYPE_NODE_PATH:
				continue
			var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
			if not bool(usage & (PROPERTY_USAGE_STORAGE | PROPERTY_USAGE_EDITOR)):
				continue
			var property_name := str(property_info.get("name", ""))
			var old_path = base_node.get(property_name)
			if not old_path is NodePath or old_path.is_empty() or old_path.get_name_count() == 0:
				continue
			var old_node_path: NodePath = old_path
			var target := base_node.get_node_or_null(old_node_path)
			if target == null:
				continue
			var migration := _migrate_path(
				old_node_path, base_node, target, scene_root, moved_node, new_parent, new_name
			)
			if migration.has("_error"):
				return migration
			if migration["changed"]:
				property_records.append(
					{
						"object": base_node,
						"property": property_name,
						"old_path": old_node_path,
						"new_path": migration["new_path"],
					}
				)

	var track_result := _plan_animation_tracks(
		nodes, scene_root, moved_node, new_parent, new_name
	)
	if track_result.has("_error"):
		return track_result
	track_records.assign(track_result["track_records"])
	return {"property_records": property_records, "track_records": track_records}


static func validate_removal(scene_root: Node, removed_node: Node) -> Dictionary:
	var nodes := _collect_scene_nodes(scene_root)
	for base_node in nodes:
		if not _is_locally_owned(base_node, scene_root) or _is_affected(base_node, removed_node):
			continue
		for property_info_value in base_node.get_property_list():
			var property_info: Dictionary = property_info_value
			if int(property_info.get("type", TYPE_NIL)) != TYPE_NODE_PATH:
				continue
			var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
			if not bool(usage & (PROPERTY_USAGE_STORAGE | PROPERTY_USAGE_EDITOR)):
				continue
			var property_name := str(property_info.get("name", ""))
			var node_path = base_node.get(property_name)
			if not node_path is NodePath or node_path.is_empty() or node_path.get_name_count() == 0:
				continue
			var target := base_node.get_node_or_null(node_path)
			if target != null and _is_affected(target, removed_node):
				return Errors.make(
					"NODE_PATH_TARGET_DELETED",
					"Cannot delete '%s' because %s.%s references it" % [
						removed_node.name, base_node.name, property_name
					],
					false,
					"Remove or retarget the NodePath reference before deleting this node."
				)

	for player_node in nodes:
		if not player_node is AnimationPlayer or _is_affected(player_node, removed_node):
			continue
		var player: AnimationPlayer = player_node
		var animation_root := _animation_root(player)
		if animation_root == null:
			continue
		for animation_name in player.get_animation_list():
			var animation := player.get_animation(animation_name)
			if animation == null:
				continue
			for track_index in animation.get_track_count():
				var track_path := animation.track_get_path(track_index)
				if track_path.is_empty() or track_path.get_name_count() == 0:
					continue
				var target := animation_root.get_node_or_null(track_path)
				if target != null and _is_affected(target, removed_node):
					return Errors.make(
						"ANIMATION_TARGET_DELETED",
						"Cannot delete '%s' because animation track %d on '%s' references it"
						% [removed_node.name, track_index, player.name],
						false,
						"Remove or retarget the animation track before deleting this node."
					)
	return {}


static func _plan_animation_tracks(
	nodes: Array[Node], scene_root: Node, moved_node: Node, new_parent: Node, new_name: String
) -> Dictionary:
	var records: Array[Dictionary] = []
	var seen_tracks: Dictionary = {}
	for player_node in nodes:
		if not player_node is AnimationPlayer:
			continue
		var player: AnimationPlayer = player_node
		var animation_root := _animation_root(player)
		if animation_root == null:
			continue
		for animation_name in player.get_animation_list():
			var animation := player.get_animation(animation_name)
			if animation == null:
				continue
			for track_index in animation.get_track_count():
				var old_path := animation.track_get_path(track_index)
				if old_path.is_empty() or old_path.get_name_count() == 0:
					continue
				var target := animation_root.get_node_or_null(old_path)
				if target == null:
					continue
				var migration := _migrate_path(
					old_path,
					animation_root,
					target,
					scene_root,
					moved_node,
					new_parent,
					new_name
				)
				if migration.has("_error"):
					return migration
				if not migration["changed"]:
					continue
				if not animation.is_built_in():
					return Errors.make(
						"EXTERNAL_ANIMATION_REFERENCE",
						"Cannot migrate a track in external animation resource: %s"
						% animation.resource_path,
						false,
						"Move or rename the node from the animation resource's source scene."
					)
				var track_key := "%d:%d" % [animation.get_instance_id(), track_index]
				if seen_tracks.has(track_key):
					if seen_tracks[track_key] != migration["new_path"]:
						return Errors.make(
							"ANIMATION_TRACK_CONFLICT",
							"The same animation track resolves from multiple incompatible roots"
						)
					continue
				seen_tracks[track_key] = migration["new_path"]
				records.append(
					{
						"animation": animation,
						"track_index": track_index,
						"old_path": old_path,
						"new_path": migration["new_path"],
					}
				)
	return {"track_records": records}


static func _migrate_path(
	old_path: NodePath,
	base_node: Node,
	target_node: Node,
	scene_root: Node,
	moved_node: Node,
	new_parent: Node,
	new_name: String
) -> Dictionary:
	var base_affected := _is_affected(base_node, moved_node)
	var target_affected := _is_affected(target_node, moved_node)
	if not base_affected and not target_affected:
		return {"changed": false}
	if old_path.is_absolute():
		if target_affected:
			return Errors.make(
				"ABSOLUTE_NODE_PATH_REFERENCE",
				"Cannot safely migrate absolute NodePath reference: %s" % old_path,
				false,
				"Replace the absolute reference with a scene-relative NodePath before moving the node."
			)
		return {"changed": false}
	if not _is_inside_scene(target_node, scene_root):
		return Errors.make(
			"EXTERNAL_NODE_PATH_REFERENCE",
			"Cannot safely migrate a relative NodePath that targets outside the edited scene",
			false,
			"Use a scene-local reference or keep the referencing node in place."
		)

	var new_base_parts := _virtual_scene_parts(base_node, scene_root, moved_node, new_parent, new_name)
	var new_target_parts := _virtual_scene_parts(target_node, scene_root, moved_node, new_parent, new_name)
	var relative_path := _relative_path(new_base_parts, new_target_parts)
	var new_path := _with_original_subnames(relative_path, old_path)
	return {"changed": new_path != old_path, "new_path": new_path}


static func _animation_root(player: AnimationPlayer) -> Node:
	var root_path: NodePath = player.root_node
	if root_path.is_empty():
		return player
	return player.get_node_or_null(root_path)


static func _collect_scene_nodes(scene_root: Node) -> Array[Node]:
	var nodes: Array[Node] = []
	var stack: Array[Node] = [scene_root]
	while not stack.is_empty():
		var node: Node = stack.pop_back()
		nodes.append(node)
		var children := node.get_children(false)
		for index in range(children.size() - 1, -1, -1):
			stack.append(children[index])
	return nodes


static func _virtual_scene_parts(
	node: Node, scene_root: Node, moved_node: Node, new_parent: Node, new_name: String
) -> Array[String]:
	if not _is_affected(node, moved_node):
		return _scene_parts(node, scene_root)
	var moved_parts := _scene_parts(moved_node, scene_root)
	var node_parts := _scene_parts(node, scene_root)
	var result := _scene_parts(new_parent, scene_root)
	result.append(new_name)
	for part in node_parts.slice(moved_parts.size()):
		result.append(part)
	return result


static func _scene_parts(node: Node, scene_root: Node) -> Array[String]:
	var result: Array[String] = []
	var current: Node = node
	while current != scene_root:
		result.push_front(String(current.name))
		current = current.get_parent()
	return result


static func _relative_path(base_parts: Array[String], target_parts: Array[String]) -> String:
	var shared := 0
	while shared < base_parts.size() and shared < target_parts.size():
		if base_parts[shared] != target_parts[shared]:
			break
		shared += 1
	var result: Array[String] = []
	for _index in range(shared, base_parts.size()):
		result.append("..")
	for part in target_parts.slice(shared):
		result.append(part)
	return "." if result.is_empty() else "/".join(result)


static func _with_original_subnames(node_path: String, original_path: NodePath) -> NodePath:
	if original_path.get_subname_count() == 0:
		return NodePath(node_path)
	var subnames := String(original_path.get_concatenated_subnames())
	return NodePath("%s:%s" % [node_path, subnames])


static func _is_affected(node: Node, moved_node: Node) -> bool:
	return node == moved_node or moved_node.is_ancestor_of(node)


static func _is_inside_scene(node: Node, scene_root: Node) -> bool:
	return node == scene_root or scene_root.is_ancestor_of(node)


static func _is_locally_owned(node: Node, scene_root: Node) -> bool:
	return node == scene_root or node.owner == scene_root

@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const TypePolicy := preload("res://addons/godot_2d_mcp/utils/type_policy.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_ANIMATIONS := 256
const MAX_TRACKS := 128
const MAX_KEYS_PER_TRACK := 512
const MAX_ANIMATION_LENGTH := 3600.0
const PROTECTED_PROPERTIES := {
	"owner": true,
	"scene_file_path": true,
	"script": true,
}
const INTERPOLATION_BY_NAME := {
	"nearest": Animation.INTERPOLATION_NEAREST,
	"linear": Animation.INTERPOLATION_LINEAR,
	"cubic": Animation.INTERPOLATION_CUBIC,
	"linear_angle": Animation.INTERPOLATION_LINEAR_ANGLE,
	"cubic_angle": Animation.INTERPOLATION_CUBIC_ANGLE,
}
const UPDATE_MODE_BY_NAME := {
	"continuous": Animation.UPDATE_CONTINUOUS,
	"discrete": Animation.UPDATE_DISCRETE,
	"capture": Animation.UPDATE_CAPTURE,
}
const LOOP_MODE_BY_NAME := {
	"none": Animation.LOOP_NONE,
	"linear": Animation.LOOP_LINEAR,
	"pingpong": Animation.LOOP_PINGPONG,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func list_animations(params: Dictionary) -> Dictionary:
	var resolved := _resolve_player(params, false)
	if resolved.has("_error"):
		return resolved
	var player: AnimationPlayer = resolved["player"]
	var scene_root: Node = resolved["scene_root"]
	var libraries: Array[Dictionary] = []
	var library_names: Array[String] = []
	for library_name_value in player.get_animation_library_list():
		library_names.append(str(library_name_value))
	library_names.sort()
	var truncated := false
	for library_name in library_names:
		if libraries.size() >= MAX_ANIMATIONS:
			truncated = true
			break
		var library := player.get_animation_library(StringName(library_name))
		if library == null:
			continue
		var animation_names: Array[String] = []
		for animation_name_value in library.get_animation_list():
			animation_names.append(str(animation_name_value))
		animation_names.sort()
		var animations: Array[Dictionary] = []
		var animations_truncated := false
		for animation_name in animation_names:
			if animations.size() >= MAX_ANIMATIONS:
				animations_truncated = true
				break
			var animation := library.get_animation(StringName(animation_name))
			if animation == null:
				continue
			animations.append(_serialize_animation_summary(animation_name, animation))
		libraries.append(
			{
				"name": library_name,
				"editable": library.is_built_in(),
				"resource_path": library.resource_path,
				"animations": animations,
				"count": animations.size(),
				"truncated": animations_truncated,
			}
		)
	return {
		"player_path": ScenePath.from_node(player, scene_root),
		"libraries": libraries,
		"count": libraries.size(),
		"truncated": truncated,
	}


func get_animation(params: Dictionary) -> Dictionary:
	var resolved := _resolve_player(params, false)
	if resolved.has("_error"):
		return resolved
	var player: AnimationPlayer = resolved["player"]
	var scene_root: Node = resolved["scene_root"]
	var library_result := _resolve_library(player, params)
	if library_result.has("_error"):
		return library_result
	var animation_name_result := _animation_name_from_params(params)
	if animation_name_result.has("_error"):
		return animation_name_result
	var animation_name: String = animation_name_result["name"]
	var library: AnimationLibrary = library_result["library"]
	if not library.has_animation(StringName(animation_name)):
		return _animation_not_found_error(animation_name, library_result["name"])
	var animation := library.get_animation(StringName(animation_name))
	if animation == null:
		return _animation_not_found_error(animation_name, library_result["name"])
	var animation_root_result := _resolve_animation_root(player, scene_root)
	if animation_root_result.has("_error"):
		return animation_root_result
	return {
		"player_path": ScenePath.from_node(player, scene_root),
		"library": library_result["name"],
		"editable": library.is_built_in() and animation.is_built_in(),
		"animation": _serialize_animation(
			animation_name, animation, animation_root_result["root"], scene_root
		),
	}


func create_animation(params: Dictionary) -> Dictionary:
	var resolved := _resolve_player(params)
	if resolved.has("_error"):
		return resolved
	var player: AnimationPlayer = resolved["player"]
	var scene_root: Node = resolved["scene_root"]
	var library_name_result := _library_name_from_params(params)
	if library_name_result.has("_error"):
		return library_name_result
	var animation_name_result := _animation_name_from_params(params)
	if animation_name_result.has("_error"):
		return animation_name_result
	var length_result := _parse_length(params.get("length", 0.2))
	if length_result.has("_error"):
		return length_result
	var loop_mode_result := _parse_loop_mode(params.get("loop_mode", "none"))
	if loop_mode_result.has("_error"):
		return loop_mode_result
	var library_name: String = library_name_result["name"]
	var library: AnimationLibrary
	var created_library := false
	if player.has_animation_library(StringName(library_name)):
		library = player.get_animation_library(StringName(library_name))
		var library_editability := _require_editable_library(library)
		if library_editability != null:
			return library_editability
	else:
		library = AnimationLibrary.new()
		created_library = true
	var animation_name: String = animation_name_result["name"]
	if library.has_animation(StringName(animation_name)):
		return Errors.make(
			"ANIMATION_NAME_CONFLICT",
			"Animation '%s' already exists in library '%s'" % [animation_name, library_name],
			false,
			"Choose a unique animation name or update the existing animation tracks."
		)
	var animation := Animation.new()
	animation.resource_name = animation_name
	animation.length = length_result["length"]
	animation.loop_mode = loop_mode_result["loop_mode"]
	_commit_animation_replacement(
		scene_root,
		player,
		library,
		library_name,
		animation_name,
		null,
		animation,
		created_library,
		"Godot 2D MCP: Create animation %s" % animation_name
	)
	return {
		"player_path": ScenePath.from_node(player, scene_root),
		"library": library_name,
		"animation": _serialize_animation_summary(animation_name, animation),
		"undoable": true,
		"_scene_mutated": true,
	}


func delete_animation(params: Dictionary) -> Dictionary:
	var resolved := _resolve_player(params)
	if resolved.has("_error"):
		return resolved
	var player: AnimationPlayer = resolved["player"]
	var scene_root: Node = resolved["scene_root"]
	var library_result := _resolve_library(player, params)
	if library_result.has("_error"):
		return library_result
	var library: AnimationLibrary = library_result["library"]
	var library_editability := _require_editable_library(library)
	if library_editability != null:
		return library_editability
	var animation_name_result := _animation_name_from_params(params)
	if animation_name_result.has("_error"):
		return animation_name_result
	var animation_name: String = animation_name_result["name"]
	if not library.has_animation(StringName(animation_name)):
		return _animation_not_found_error(animation_name, library_result["name"])
	var animation := library.get_animation(StringName(animation_name))
	if animation == null:
		return _animation_not_found_error(animation_name, library_result["name"])
	var animation_editability := _require_editable_animation(animation)
	if animation_editability != null:
		return animation_editability
	var animation_root_result := _resolve_animation_root(player, scene_root)
	if animation_root_result.has("_error"):
		return animation_root_result
	var scope_check := _require_2d_value_track_scope(
		animation, animation_root_result["root"], scene_root
	)
	if scope_check != null:
		return scope_check
	_undo_redo.create_action(
		"Godot 2D MCP: Delete animation %s" % animation_name,
		UndoRedo.MERGE_DISABLE,
		scene_root
	)
	_undo_redo.add_do_method(library, "remove_animation", StringName(animation_name))
	_undo_redo.add_undo_method(library, "add_animation", StringName(animation_name), animation)
	_undo_redo.add_undo_reference(animation)
	_undo_redo.commit_action()
	return {
		"player_path": ScenePath.from_node(player, scene_root),
		"library": library_result["name"],
		"name": animation_name,
		"undoable": true,
		"_scene_mutated": true,
	}


func upsert_value_track(params: Dictionary) -> Dictionary:
	var resolved := _resolve_player(params)
	if resolved.has("_error"):
		return resolved
	var player: AnimationPlayer = resolved["player"]
	var scene_root: Node = resolved["scene_root"]
	var library_result := _resolve_library(player, params)
	if library_result.has("_error"):
		return library_result
	var library: AnimationLibrary = library_result["library"]
	var library_editability := _require_editable_library(library)
	if library_editability != null:
		return library_editability
	var animation_result := _resolve_editable_animation(library, params)
	if animation_result.has("_error"):
		return animation_result
	var animation: Animation = animation_result["animation"]
	var target_result := _resolve_local_target(scene_root, str(params.get("target_path", "")))
	if target_result.has("_error"):
		return target_result
	var target: Node = target_result["node"]
	var property_result := _resolve_writable_property(target, str(params.get("property", "")))
	if property_result.has("_error"):
		return property_result
	var animation_root_result := _resolve_animation_root(player, scene_root)
	if animation_root_result.has("_error"):
		return animation_root_result
	var track_path := _make_track_path(animation_root_result["root"], target, property_result["name"])
	var keys_result := _parse_value_keys(
		params.get("keys", []), property_result["property_info"], target.get(property_result["name"]), animation.length
	)
	if keys_result.has("_error"):
		return keys_result
	var configuration_result := _parse_track_configuration(params)
	if configuration_result.has("_error"):
		return configuration_result
	var existing_index := animation.find_track(track_path, Animation.TYPE_VALUE)
	if existing_index >= 0 and animation.track_is_imported(existing_index):
		return Errors.make(
			"IMPORTED_ANIMATION_TRACK",
			"Cannot replace imported animation track %d" % existing_index,
			false,
			"Edit the source animation instead of an imported track."
		)
	var replacement := _duplicate_animation(animation)
	if replacement == null:
		return Errors.make("ANIMATION_DUPLICATE_FAILED", "Godot failed to duplicate the animation resource")
	var track_index := existing_index
	if existing_index >= 0:
		replacement.remove_track(existing_index)
	track_index = replacement.add_track(Animation.TYPE_VALUE, existing_index)
	replacement.track_set_path(track_index, track_path)
	replacement.track_set_enabled(track_index, configuration_result["enabled"])
	replacement.track_set_interpolation_type(track_index, configuration_result["interpolation"])
	replacement.track_set_interpolation_loop_wrap(track_index, configuration_result["loop_wrap"])
	replacement.value_track_set_update_mode(track_index, configuration_result["update_mode"])
	for key in keys_result["keys"]:
		replacement.track_insert_key(track_index, key["time"], key["value"], key["transition"])
	_commit_animation_replacement(
		scene_root,
		player,
		library,
		library_result["name"],
		animation_result["name"],
		animation,
		replacement,
		false,
		"Godot 2D MCP: Update animation track"
	)
	return {
		"player_path": ScenePath.from_node(player, scene_root),
		"library": library_result["name"],
		"animation": animation_result["name"],
		"track": _serialize_track(replacement, track_index, animation_root_result["root"], scene_root),
		"replaced_existing": existing_index >= 0,
		"undoable": true,
		"_scene_mutated": true,
	}


func delete_track(params: Dictionary) -> Dictionary:
	var resolved := _resolve_player(params)
	if resolved.has("_error"):
		return resolved
	var player: AnimationPlayer = resolved["player"]
	var scene_root: Node = resolved["scene_root"]
	var library_result := _resolve_library(player, params)
	if library_result.has("_error"):
		return library_result
	var library: AnimationLibrary = library_result["library"]
	var library_editability := _require_editable_library(library)
	if library_editability != null:
		return library_editability
	var animation_result := _resolve_editable_animation(library, params)
	if animation_result.has("_error"):
		return animation_result
	var animation: Animation = animation_result["animation"]
	var track_index_result := _track_index_from_params(params, animation)
	if track_index_result.has("_error"):
		return track_index_result
	var track_index: int = track_index_result["index"]
	if animation.track_get_type(track_index) != Animation.TYPE_VALUE:
		return Errors.make(
			"UNSUPPORTED_ANIMATION_TRACK",
			"animation_track_delete currently supports 2D/UI property value tracks only",
			false,
			"Method, audio, nested-animation, and 3D tracks are not editable in this release."
		)
	if animation.track_is_imported(track_index):
		return Errors.make(
			"IMPORTED_ANIMATION_TRACK",
			"Cannot delete imported animation track %d" % track_index,
			false,
			"Edit the source animation instead of an imported track."
		)
	var animation_root_result := _resolve_animation_root(player, scene_root)
	if animation_root_result.has("_error"):
		return animation_root_result
	var property_result := _resolve_track_property(
		animation, track_index, animation_root_result["root"], scene_root
	)
	if property_result.has("_error"):
		return property_result
	var replacement := _duplicate_animation(animation)
	if replacement == null:
		return Errors.make("ANIMATION_DUPLICATE_FAILED", "Godot failed to duplicate the animation resource")
	replacement.remove_track(track_index)
	_commit_animation_replacement(
		scene_root,
		player,
		library,
		library_result["name"],
		animation_result["name"],
		animation,
		replacement,
		false,
		"Godot 2D MCP: Delete animation track"
	)
	return {
		"player_path": ScenePath.from_node(player, scene_root),
		"library": library_result["name"],
		"animation": animation_result["name"],
		"track_index": track_index,
		"undoable": true,
		"_scene_mutated": true,
	}


func upsert_key(params: Dictionary) -> Dictionary:
	var resolved := _resolve_player(params)
	if resolved.has("_error"):
		return resolved
	var player: AnimationPlayer = resolved["player"]
	var scene_root: Node = resolved["scene_root"]
	var library_result := _resolve_library(player, params)
	if library_result.has("_error"):
		return library_result
	var library: AnimationLibrary = library_result["library"]
	var library_editability := _require_editable_library(library)
	if library_editability != null:
		return library_editability
	var animation_result := _resolve_editable_animation(library, params)
	if animation_result.has("_error"):
		return animation_result
	var animation: Animation = animation_result["animation"]
	var track_index_result := _track_index_from_params(params, animation)
	if track_index_result.has("_error"):
		return track_index_result
	var track_index: int = track_index_result["index"]
	if animation.track_get_type(track_index) != Animation.TYPE_VALUE:
		return Errors.make(
			"UNSUPPORTED_ANIMATION_TRACK",
			"animation_key_upsert currently supports property value tracks only",
			false,
			"Use animation_track_upsert to create a value track."
		)
	if animation.track_is_imported(track_index):
		return Errors.make(
			"IMPORTED_ANIMATION_TRACK",
			"Cannot edit imported animation track %d" % track_index,
			false,
			"Edit the source animation instead of an imported track."
		)
	var animation_root_result := _resolve_animation_root(player, scene_root)
	if animation_root_result.has("_error"):
		return animation_root_result
	var property_result := _resolve_track_property(
		animation, track_index, animation_root_result["root"], scene_root
	)
	if property_result.has("_error"):
		return property_result
	var key_result := _parse_value_key(
		params,
		property_result["property_info"],
		property_result["node"].get(property_result["name"]),
		animation.length
	)
	if key_result.has("_error"):
		return key_result
	var replacement := _duplicate_animation(animation)
	if replacement == null:
		return Errors.make("ANIMATION_DUPLICATE_FAILED", "Godot failed to duplicate the animation resource")
	var existing_key := replacement.track_find_key(
		track_index, key_result["time"], Animation.FIND_MODE_APPROX
	)
	var key_index: int
	if existing_key >= 0:
		replacement.track_set_key_value(track_index, existing_key, key_result["value"])
		replacement.track_set_key_transition(track_index, existing_key, key_result["transition"])
		key_index = existing_key
	else:
		key_index = replacement.track_insert_key(
			track_index, key_result["time"], key_result["value"], key_result["transition"]
		)
	_commit_animation_replacement(
		scene_root,
		player,
		library,
		library_result["name"],
		animation_result["name"],
		animation,
		replacement,
		false,
		"Godot 2D MCP: Update animation key"
	)
	return {
		"player_path": ScenePath.from_node(player, scene_root),
		"library": library_result["name"],
		"animation": animation_result["name"],
		"track_index": track_index,
		"key_index": key_index,
		"replaced_existing": existing_key >= 0,
		"key": _serialize_key(replacement, track_index, key_index),
		"undoable": true,
		"_scene_mutated": true,
	}


func delete_key(params: Dictionary) -> Dictionary:
	var resolved := _resolve_player(params)
	if resolved.has("_error"):
		return resolved
	var player: AnimationPlayer = resolved["player"]
	var scene_root: Node = resolved["scene_root"]
	var library_result := _resolve_library(player, params)
	if library_result.has("_error"):
		return library_result
	var library: AnimationLibrary = library_result["library"]
	var library_editability := _require_editable_library(library)
	if library_editability != null:
		return library_editability
	var animation_result := _resolve_editable_animation(library, params)
	if animation_result.has("_error"):
		return animation_result
	var animation: Animation = animation_result["animation"]
	var track_index_result := _track_index_from_params(params, animation)
	if track_index_result.has("_error"):
		return track_index_result
	var track_index: int = track_index_result["index"]
	if animation.track_get_type(track_index) != Animation.TYPE_VALUE:
		return Errors.make(
			"UNSUPPORTED_ANIMATION_TRACK",
			"animation_key_delete currently supports property value tracks only",
			false,
			"Use animation_track_delete to remove a non-value track."
		)
	if animation.track_is_imported(track_index):
		return Errors.make(
			"IMPORTED_ANIMATION_TRACK",
			"Cannot edit imported animation track %d" % track_index,
			false,
			"Edit the source animation instead of an imported track."
		)
	var animation_root_result := _resolve_animation_root(player, scene_root)
	if animation_root_result.has("_error"):
		return animation_root_result
	var property_result := _resolve_track_property(
		animation, track_index, animation_root_result["root"], scene_root
	)
	if property_result.has("_error"):
		return property_result
	var time_result := _parse_key_time(params.get("time", null), animation.length)
	if time_result.has("_error"):
		return time_result
	var key_index := animation.track_find_key(
		track_index, time_result["time"], Animation.FIND_MODE_APPROX
	)
	if key_index < 0:
		return Errors.make(
			"ANIMATION_KEY_NOT_FOUND",
			"No key exists at time %s on track %d" % [time_result["time"], track_index],
			false,
			"Call animation_get to inspect the current track keys."
		)
	var replacement := _duplicate_animation(animation)
	if replacement == null:
		return Errors.make("ANIMATION_DUPLICATE_FAILED", "Godot failed to duplicate the animation resource")
	replacement.track_remove_key(track_index, key_index)
	_commit_animation_replacement(
		scene_root,
		player,
		library,
		library_result["name"],
		animation_result["name"],
		animation,
		replacement,
		false,
		"Godot 2D MCP: Delete animation key"
	)
	return {
		"player_path": ScenePath.from_node(player, scene_root),
		"library": library_result["name"],
		"animation": animation_result["name"],
		"track_index": track_index,
		"key_index": key_index,
		"time": time_result["time"],
		"undoable": true,
		"_scene_mutated": true,
	}


func _commit_animation_replacement(
	scene_root: Node,
	player: AnimationPlayer,
	library: AnimationLibrary,
	library_name: String,
	animation_name: String,
	old_animation: Animation,
	replacement: Animation,
	created_library: bool,
	action_name: String
) -> void:
	_undo_redo.create_action(action_name, UndoRedo.MERGE_DISABLE, scene_root, true)
	if created_library:
		_undo_redo.add_do_method(player, "add_animation_library", StringName(library_name), library)
		_undo_redo.add_do_reference(library)
		_undo_redo.add_undo_method(player, "remove_animation_library", StringName(library_name))
		_undo_redo.add_undo_reference(library)
	if old_animation != null:
		_undo_redo.add_do_method(library, "remove_animation", StringName(animation_name))
		_undo_redo.add_undo_method(library, "add_animation", StringName(animation_name), old_animation)
		_undo_redo.add_undo_reference(old_animation)
	_undo_redo.add_do_method(library, "add_animation", StringName(animation_name), replacement)
	_undo_redo.add_do_reference(replacement)
	_undo_redo.add_undo_method(library, "remove_animation", StringName(animation_name))
	_undo_redo.add_undo_reference(replacement)
	_undo_redo.commit_action()


func _resolve_player(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var guarded := MutationGuard.require_scene(params, require_writable)
	if guarded.has("_error"):
		return guarded
	var scene_root: Node = guarded["scene_root"]
	var player_path := str(params.get("player_path", "")).strip_edges()
	if player_path.is_empty():
		return Errors.make("MISSING_PARAMETER", "player_path is required")
	var player_node := ScenePath.resolve(player_path, scene_root)
	if player_node == null:
		return Errors.make(
			"NODE_NOT_FOUND",
			"AnimationPlayer not found: %s" % player_path,
			false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if not player_node is AnimationPlayer:
		return Errors.make(
			"ANIMATION_PLAYER_REQUIRED",
			"Node '%s' is %s, not AnimationPlayer" % [player_node.name, player_node.get_class()],
			false,
			"Create or target an AnimationPlayer node."
		)
	var player: AnimationPlayer = player_node
	if player != scene_root and player.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit animations on '%s' because it belongs to an instanced scene" % player.name,
			false,
			"Edit the source PackedScene or target a locally owned AnimationPlayer."
		)
	return {"player": player, "scene_root": scene_root}


func _resolve_library(player: AnimationPlayer, params: Dictionary) -> Dictionary:
	var name_result := _library_name_from_params(params)
	if name_result.has("_error"):
		return name_result
	var library_name: String = name_result["name"]
	if not player.has_animation_library(StringName(library_name)):
		return Errors.make(
			"ANIMATION_LIBRARY_NOT_FOUND",
			"Animation library '%s' does not exist" % library_name,
			false,
			"Call animation_list to inspect the player's animation libraries."
		)
	var library := player.get_animation_library(StringName(library_name))
	if library == null:
		return Errors.make("ANIMATION_LIBRARY_NOT_FOUND", "Animation library is unavailable")
	return {"name": library_name, "library": library}


func _resolve_editable_animation(library: AnimationLibrary, params: Dictionary) -> Dictionary:
	var animation_name_result := _animation_name_from_params(params)
	if animation_name_result.has("_error"):
		return animation_name_result
	var animation_name: String = animation_name_result["name"]
	if not library.has_animation(StringName(animation_name)):
		return _animation_not_found_error(animation_name, "")
	var animation := library.get_animation(StringName(animation_name))
	if animation == null:
		return _animation_not_found_error(animation_name, "")
	var editability := _require_editable_animation(animation)
	if editability != null:
		return editability
	return {"name": animation_name, "animation": animation}


func _resolve_animation_root(player: AnimationPlayer, scene_root: Node) -> Dictionary:
	var root_path: NodePath = player.root_node
	var animation_root: Node = player if root_path.is_empty() else player.get_node_or_null(root_path)
	if animation_root == null:
		return Errors.make(
			"ANIMATION_ROOT_NOT_FOUND",
			"AnimationPlayer root_node cannot be resolved: %s" % root_path,
			false,
			"Set AnimationPlayer.root_node to a node in the edited scene."
		)
	if animation_root != scene_root and not scene_root.is_ancestor_of(animation_root):
		return Errors.make(
			"ANIMATION_ROOT_OUTSIDE_SCENE",
			"AnimationPlayer root_node points outside the edited scene",
			false,
			"Use a scene-local AnimationPlayer.root_node."
		)
	return {"root": animation_root}


func _resolve_local_target(scene_root: Node, target_path: String) -> Dictionary:
	var clean_path := target_path.strip_edges()
	if clean_path.is_empty():
		return Errors.make("MISSING_PARAMETER", "target_path is required")
	var target := ScenePath.resolve(clean_path, scene_root)
	if target == null:
		return Errors.make(
			"NODE_NOT_FOUND",
			"Animation target not found: %s" % clean_path,
			false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if target != scene_root and target.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot animate '%s' because it belongs to an instanced scene" % target.name,
			false,
			"Edit the source PackedScene or target a locally owned node."
		)
	if not TypePolicy.is_supported_node_class(target.get_class()):
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"Animation target is outside the supported 2D policy: %s" % target.get_class(),
			false,
			"Use a CanvasItem, Node2D, Control, or other supported 2D node."
		)
	return {"node": target}


func _resolve_writable_property(node: Node, property_name: String) -> Dictionary:
	var clean_name := property_name.strip_edges()
	if clean_name.is_empty() or clean_name.length() > 256 or clean_name.contains(":"):
		return Errors.make("INVALID_PROPERTY", "property must be a single public property name")
	if PROTECTED_PROPERTIES.has(clean_name):
		return Errors.make("PROPERTY_NOT_ANIMATABLE", "Property '%s' cannot be animated" % clean_name)
	for property_info_value in node.get_property_list():
		var property_info: Dictionary = property_info_value
		if str(property_info.get("name", "")) != clean_name:
			continue
		var usage := int(property_info.get("usage", PROPERTY_USAGE_NONE))
		if not _is_writable_public_property(usage):
			return Errors.make(
				"PROPERTY_NOT_ANIMATABLE",
				"Property '%s' is not public and writable" % clean_name,
				false,
				"Call node_get_properties to inspect supported properties."
			)
		return {"name": clean_name, "property_info": property_info}
	return Errors.make(
		"PROPERTY_NOT_FOUND",
		"Property '%s' does not exist on %s" % [clean_name, node.get_class()],
		false,
		"Call node_get_properties to inspect the target node."
	)


func _resolve_track_property(
	animation: Animation, track_index: int, animation_root: Node, scene_root: Node
) -> Dictionary:
	var track_path := animation.track_get_path(track_index)
	if track_path.get_subname_count() != 1:
		return Errors.make(
			"UNSUPPORTED_ANIMATION_TRACK_PATH",
			"Key editing requires a track that targets exactly one node property",
			false,
			"Use animation_track_upsert for a direct property track."
		)
	var target := animation_root.get_node_or_null(track_path)
	if target == null:
		return Errors.make(
			"ANIMATION_TARGET_NOT_FOUND",
			"Animation track %d target no longer exists" % track_index,
			false,
			"Repair or replace the track with animation_track_upsert."
		)
	if target != scene_root and target.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit a track targeting instanced node '%s'" % target.name,
			false,
			"Edit the source PackedScene or replace the track with a local target."
		)
	if not TypePolicy.is_supported_node_class(target.get_class()):
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"Animation track %d targets unsupported type %s" % [track_index, target.get_class()],
			false,
			"Use animation_track_upsert with a supported 2D target."
		)
	return _resolve_writable_property(target, str(track_path.get_subname(0))).merged({"node": target})


func _require_2d_value_track_scope(
	animation: Animation, animation_root: Node, scene_root: Node
) -> Variant:
	for track_index in animation.get_track_count():
		if animation.track_get_type(track_index) != Animation.TYPE_VALUE:
			return Errors.make(
				"UNSUPPORTED_ANIMATION_TRACK",
				"Animation contains a non-property track at index %d" % track_index,
				false,
				"Only local 2D/UI property value tracks are editable in this release."
			)
		var track_path := animation.track_get_path(track_index)
		if track_path.get_subname_count() != 1:
			return Errors.make(
				"UNSUPPORTED_ANIMATION_TRACK_PATH",
				"Animation track %d does not target a single node property" % track_index,
				false,
				"Remove unsupported tracks in Godot before editing this animation through MCP."
			)
		var target := animation_root.get_node_or_null(track_path)
		if target == null or (target != scene_root and not scene_root.is_ancestor_of(target)):
			return Errors.make(
				"ANIMATION_TARGET_NOT_FOUND",
				"Animation track %d target cannot be resolved in the edited scene" % track_index
			)
		if not TypePolicy.is_supported_node_class(target.get_class()):
			return Errors.make(
				"UNSUPPORTED_2D_TYPE",
				"Animation track %d targets unsupported type %s" % [track_index, target.get_class()]
			)
	return null


func _make_track_path(animation_root: Node, target: Node, property_name: String) -> NodePath:
	var target_path := str(animation_root.get_path_to(target))
	if target_path.is_empty():
		target_path = "."
	return NodePath("%s:%s" % [target_path, property_name])


func _parse_value_keys(
	raw_keys: Variant, property_info: Dictionary, current_value: Variant, animation_length: float
) -> Dictionary:
	if not raw_keys is Array or raw_keys.is_empty():
		return Errors.make("MISSING_PARAMETER", "keys must be a non-empty array")
	if raw_keys.size() > MAX_KEYS_PER_TRACK:
		return Errors.make(
			"REQUEST_LIMIT_EXCEEDED",
			"A track can contain at most %d keys" % MAX_KEYS_PER_TRACK
		)
	var parsed: Array[Dictionary] = []
	for raw_key in raw_keys:
		if not raw_key is Dictionary:
			return Errors.make("INVALID_ANIMATION_KEY", "Every key must be an object")
		var parsed_key := _parse_value_key(raw_key, property_info, current_value, animation_length)
		if parsed_key.has("_error"):
			return parsed_key
		for existing_key in parsed:
			if is_equal_approx(existing_key["time"], parsed_key["time"]):
				return Errors.make(
					"DUPLICATE_ANIMATION_KEY",
					"A track cannot contain more than one key at the same time"
				)
		parsed.append(parsed_key)
	return {"keys": parsed}


func _parse_value_key(
	raw_key: Dictionary, property_info: Dictionary, current_value: Variant, animation_length: float
) -> Dictionary:
	if not raw_key.has("time") or not raw_key.has("value"):
		return Errors.make("INVALID_ANIMATION_KEY", "Each key requires time and value")
	var time_result := _parse_key_time(raw_key["time"], animation_length)
	if time_result.has("_error"):
		return time_result
	var decoded := VariantCodec.decode(raw_key["value"], property_info, current_value)
	if decoded.has("_error"):
		return Errors.make(
			"INVALID_ANIMATION_KEY_VALUE",
			decoded["_error"]["message"],
			false,
			"Use a JSON value compatible with the target property type."
		)
	var transition_result := _parse_transition(raw_key.get("transition", 1.0))
	if transition_result.has("_error"):
		return transition_result
	return {
		"time": time_result["time"],
		"value": decoded["value"],
		"transition": transition_result["transition"],
	}


func _parse_key_time(raw_time: Variant, animation_length: float) -> Dictionary:
	if not _is_finite_number(raw_time):
		return Errors.make("INVALID_ANIMATION_TIME", "time must be a finite number")
	var time := float(raw_time)
	if time < 0.0 or time > animation_length:
		return Errors.make(
			"INVALID_ANIMATION_TIME",
			"time must be between 0 and the animation length (%s)" % animation_length
		)
	return {"time": time}


func _parse_transition(raw_transition: Variant) -> Dictionary:
	if not _is_finite_number(raw_transition):
		return Errors.make("INVALID_ANIMATION_TRANSITION", "transition must be a finite number")
	return {"transition": float(raw_transition)}


func _parse_length(raw_length: Variant) -> Dictionary:
	if not _is_finite_number(raw_length):
		return Errors.make("INVALID_ANIMATION_LENGTH", "length must be a finite number")
	var length := float(raw_length)
	if length <= 0.0 or length > MAX_ANIMATION_LENGTH:
		return Errors.make(
			"INVALID_ANIMATION_LENGTH",
			"length must be greater than 0 and no more than %s seconds" % MAX_ANIMATION_LENGTH
		)
	return {"length": length}


func _parse_loop_mode(raw_loop_mode: Variant) -> Dictionary:
	if not raw_loop_mode is String:
		return Errors.make("INVALID_LOOP_MODE", "loop_mode must be none, linear, or pingpong")
	var loop_mode_name: String = raw_loop_mode.to_lower().strip_edges()
	if not LOOP_MODE_BY_NAME.has(loop_mode_name):
		return Errors.make("INVALID_LOOP_MODE", "loop_mode must be none, linear, or pingpong")
	return {"loop_mode": LOOP_MODE_BY_NAME[loop_mode_name]}


func _parse_track_configuration(params: Dictionary) -> Dictionary:
	var interpolation_name := str(params.get("interpolation", "linear")).to_lower().strip_edges()
	if not INTERPOLATION_BY_NAME.has(interpolation_name):
		return Errors.make(
			"INVALID_INTERPOLATION",
			"interpolation must be nearest, linear, cubic, linear_angle, or cubic_angle"
		)
	var update_mode_name := str(params.get("update_mode", "continuous")).to_lower().strip_edges()
	if not UPDATE_MODE_BY_NAME.has(update_mode_name):
		return Errors.make(
			"INVALID_UPDATE_MODE", "update_mode must be continuous, discrete, or capture"
		)
	var enabled = params.get("enabled", true)
	var loop_wrap = params.get("loop_wrap", true)
	if not enabled is bool or not loop_wrap is bool:
		return Errors.make("INVALID_PARAMETER", "enabled and loop_wrap must be booleans")
	return {
		"interpolation": INTERPOLATION_BY_NAME[interpolation_name],
		"update_mode": UPDATE_MODE_BY_NAME[update_mode_name],
		"enabled": enabled,
		"loop_wrap": loop_wrap,
	}


func _library_name_from_params(params: Dictionary) -> Dictionary:
	var library_name = params.get("library", "")
	if not library_name is String:
		return Errors.make("INVALID_ANIMATION_LIBRARY", "library must be a string")
	var clean_name: String = library_name.strip_edges()
	if clean_name.length() > 256 or clean_name.contains("/"):
		return Errors.make(
			"INVALID_ANIMATION_LIBRARY",
			"library cannot exceed 256 characters or contain '/'"
		)
	return {"name": clean_name}


func _animation_name_from_params(params: Dictionary) -> Dictionary:
	var animation_name = params.get("animation", "")
	if not animation_name is String:
		return Errors.make("INVALID_ANIMATION_NAME", "animation must be a string")
	var clean_name: String = animation_name.strip_edges()
	if clean_name.is_empty() or clean_name.length() > 256 or clean_name.contains("/"):
		return Errors.make(
			"INVALID_ANIMATION_NAME",
			"animation must contain 1 to 256 characters and cannot contain '/'"
		)
	return {"name": clean_name}


func _track_index_from_params(params: Dictionary, animation: Animation) -> Dictionary:
	var raw_index = params.get("track_index", -1)
	if not _is_integral_number(raw_index):
		return Errors.make(
			"ANIMATION_TRACK_NOT_FOUND",
			"track_index must identify an existing animation track",
			false,
			"Call animation_get to inspect the current track indexes."
		)
	var track_index := int(raw_index)
	if track_index < 0 or track_index >= animation.get_track_count():
		return Errors.make(
			"ANIMATION_TRACK_NOT_FOUND",
			"track_index must identify an existing animation track",
			false,
			"Call animation_get to inspect the current track indexes."
		)
	return {"index": track_index}


func _require_editable_library(library: AnimationLibrary) -> Variant:
	if library != null and library.is_built_in():
		return null
	var resource_path := "" if library == null else library.resource_path
	return Errors.make(
		"EXTERNAL_ANIMATION_LIBRARY",
		"Only scene-embedded AnimationLibrary resources are editable: %s" % resource_path,
		false,
		"Edit the source resource or use an embedded AnimationLibrary."
	)


func _require_editable_animation(animation: Animation) -> Variant:
	if animation != null and animation.is_built_in():
		return null
	var resource_path := "" if animation == null else animation.resource_path
	return Errors.make(
		"EXTERNAL_ANIMATION_RESOURCE",
		"Only scene-embedded Animation resources are editable: %s" % resource_path,
		false,
		"Edit the source resource or use an embedded Animation."
	)


func _duplicate_animation(animation: Animation) -> Animation:
	var duplicated := animation.duplicate(true)
	return duplicated as Animation


func _serialize_animation_summary(animation_name: String, animation: Animation) -> Dictionary:
	return {
		"name": animation_name,
		"length": _safe_float(animation.length),
		"loop_mode": _loop_mode_name(animation.loop_mode),
		"track_count": animation.get_track_count(),
	}


func _serialize_animation(
	animation_name: String, animation: Animation, animation_root: Node, scene_root: Node
) -> Dictionary:
	var tracks: Array[Dictionary] = []
	var truncated := false
	for track_index in animation.get_track_count():
		if tracks.size() >= MAX_TRACKS:
			truncated = true
			break
		tracks.append(_serialize_track(animation, track_index, animation_root, scene_root))
	var result := _serialize_animation_summary(animation_name, animation)
	result["tracks"] = tracks
	result["tracks_truncated"] = truncated
	return result


func _serialize_track(
	animation: Animation, track_index: int, animation_root: Node, scene_root: Node
) -> Dictionary:
	var track_path := animation.track_get_path(track_index)
	var target_path := ""
	var target_type := ""
	var target := animation_root.get_node_or_null(track_path)
	if target != null and (target == scene_root or scene_root.is_ancestor_of(target)):
		target_path = ScenePath.from_node(target, scene_root)
		target_type = target.get_class()
	var key_count := animation.track_get_key_count(track_index)
	var keys: Array[Dictionary] = []
	var keys_truncated := false
	for key_index in key_count:
		if keys.size() >= MAX_KEYS_PER_TRACK:
			keys_truncated = true
			break
		keys.append(_serialize_key(animation, track_index, key_index))
	var result := {
		"index": track_index,
		"type": _track_type_name(animation.track_get_type(track_index)),
		"path": str(track_path),
		"target_path": target_path,
		"target_type": target_type,
		"property": _track_property_name(track_path),
		"enabled": animation.track_is_enabled(track_index),
		"imported": animation.track_is_imported(track_index),
		"interpolation": _interpolation_name(animation.track_get_interpolation_type(track_index)),
		"loop_wrap": animation.track_get_interpolation_loop_wrap(track_index),
		"keys": keys,
		"key_count": key_count,
		"keys_truncated": keys_truncated,
	}
	if animation.track_get_type(track_index) == Animation.TYPE_VALUE:
		result["update_mode"] = _update_mode_name(animation.value_track_get_update_mode(track_index))
	return result


func _serialize_key(animation: Animation, track_index: int, key_index: int) -> Dictionary:
	return {
		"index": key_index,
		"time": _safe_float(animation.track_get_key_time(track_index, key_index)),
		"transition": _safe_float(animation.track_get_key_transition(track_index, key_index)),
		"value": VariantCodec.serialize(animation.track_get_key_value(track_index, key_index)),
	}


func _animation_not_found_error(animation_name: String, library_name: String) -> Dictionary:
	var suffix := "" if library_name.is_empty() else " in library '%s'" % library_name
	return Errors.make(
		"ANIMATION_NOT_FOUND",
		"Animation '%s' does not exist%s" % [animation_name, suffix],
		false,
		"Call animation_list to inspect available animations."
	)


func _is_writable_public_property(usage: int) -> bool:
	return (
		bool(usage & (PROPERTY_USAGE_STORAGE | PROPERTY_USAGE_EDITOR))
		and not bool(usage & PROPERTY_USAGE_READ_ONLY)
	)


func _is_finite_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


func _is_integral_number(value: Variant) -> bool:
	return _is_finite_number(value) and is_equal_approx(float(value), round(float(value)))


func _safe_float(value: float) -> Variant:
	return value if is_finite(value) else null


func _track_property_name(track_path: NodePath) -> String:
	return str(track_path.get_subname(0)) if track_path.get_subname_count() == 1 else ""


func _track_type_name(track_type: int) -> String:
	match track_type:
		Animation.TYPE_VALUE:
			return "value"
		Animation.TYPE_METHOD:
			return "method"
		Animation.TYPE_BEZIER:
			return "bezier"
		Animation.TYPE_AUDIO:
			return "audio"
		Animation.TYPE_ANIMATION:
			return "animation"
	return "unsupported"


func _interpolation_name(interpolation: int) -> String:
	for name in INTERPOLATION_BY_NAME:
		if INTERPOLATION_BY_NAME[name] == interpolation:
			return name
	return "unknown"


func _update_mode_name(update_mode: int) -> String:
	for name in UPDATE_MODE_BY_NAME:
		if UPDATE_MODE_BY_NAME[name] == update_mode:
			return name
	return "unknown"


func _loop_mode_name(loop_mode: int) -> String:
	for name in LOOP_MODE_BY_NAME:
		if LOOP_MODE_BY_NAME[name] == loop_mode:
			return name
	return "unknown"

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
const MAX_BEZIER_VALUE := 1000000.0
const MAX_BEZIER_HANDLE := 3600.0
const AUDIO_KEY_FIELDS := {
	"time": true,
	"stream_path": true,
	"start_offset": true,
	"end_offset": true,
}
const BEZIER_KEY_FIELDS := {
	"time": true,
	"value": true,
	"in_handle": true,
	"out_handle": true,
}
const METHOD_KEY_FIELDS := {
	"time": true,
	"method": true,
	"args": true,
}
const NESTED_ANIMATION_KEY_FIELDS := {
	"time": true,
	"animation": true,
}
const NESTED_ANIMATION_STOP := "[stop]"
const BEZIER_COMPONENTS_BY_TYPE := {
	TYPE_VECTOR2: {"x": true, "y": true},
	TYPE_COLOR: {"r": true, "g": true, "b": true, "a": true},
}
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
	var scope_check := _require_2d_animation_track_scope(
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


func upsert_audio_track(params: Dictionary) -> Dictionary:
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
	if not target is AudioStreamPlayer2D:
		return Errors.make(
			"AUDIO_STREAM_PLAYER_2D_REQUIRED",
			"Audio animation tracks must target AudioStreamPlayer2D, not %s" % target.get_class(),
			false,
			"Create or target a scene-local AudioStreamPlayer2D node."
		)
	var animation_root_result := _resolve_animation_root(player, scene_root)
	if animation_root_result.has("_error"):
		return animation_root_result
	var track_path := _make_node_track_path(animation_root_result["root"], target)
	var keys_result := _parse_audio_track_keys(params.get("keys", []), animation.length)
	if keys_result.has("_error"):
		return keys_result
	var configuration_result := _parse_audio_track_configuration(params)
	if configuration_result.has("_error"):
		return configuration_result
	var existing_index := animation.find_track(track_path, Animation.TYPE_AUDIO)
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
	track_index = replacement.add_track(Animation.TYPE_AUDIO, existing_index)
	replacement.track_set_path(track_index, track_path)
	replacement.track_set_enabled(track_index, configuration_result["enabled"])
	replacement.audio_track_set_use_blend(track_index, configuration_result["use_blend"])
	for key in keys_result["keys"]:
		replacement.audio_track_insert_key(
			track_index,
			key["time"],
			key["stream"],
			key["start_offset"],
			key["end_offset"]
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
		"Godot 2D MCP: Update animation audio track"
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


func upsert_bezier_track(params: Dictionary) -> Dictionary:
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
	var property_result := _resolve_bezier_property(target, str(params.get("property", "")))
	if property_result.has("_error"):
		return property_result
	var animation_root_result := _resolve_animation_root(player, scene_root)
	if animation_root_result.has("_error"):
		return animation_root_result
	var track_path := _make_track_path(animation_root_result["root"], target, property_result["name"])
	var keys_result := _parse_bezier_track_keys(params.get("keys", []), animation.length)
	if keys_result.has("_error"):
		return keys_result
	var enabled = params.get("enabled", true)
	if not enabled is bool:
		return Errors.make("INVALID_PARAMETER", "enabled must be a boolean")
	var existing_index := animation.find_track(track_path, Animation.TYPE_BEZIER)
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
	track_index = replacement.add_track(Animation.TYPE_BEZIER, existing_index)
	replacement.track_set_path(track_index, track_path)
	replacement.track_set_enabled(track_index, enabled)
	for key in keys_result["keys"]:
		replacement.bezier_track_insert_key(
			track_index, key["time"], key["value"], key["in_handle"], key["out_handle"]
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
		"Godot 2D MCP: Update animation Bezier track"
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


func upsert_method_track(params: Dictionary) -> Dictionary:
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
	var target_result := _resolve_safe_method_track_target(
		scene_root, str(params.get("target_path", ""))
	)
	if target_result.has("_error"):
		return target_result
	var target: Node = target_result["node"]
	var animation_root_result := _resolve_animation_root(player, scene_root)
	if animation_root_result.has("_error"):
		return animation_root_result
	var keys_result := _parse_method_track_keys(params.get("keys", []), animation.length, target)
	if keys_result.has("_error"):
		return keys_result
	var enabled = params.get("enabled", true)
	if not enabled is bool:
		return Errors.make("INVALID_PARAMETER", "enabled must be a boolean")
	var track_path := _make_node_track_path(animation_root_result["root"], target)
	var existing_index := animation.find_track(track_path, Animation.TYPE_METHOD)
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
	track_index = replacement.add_track(Animation.TYPE_METHOD, existing_index)
	replacement.track_set_path(track_index, track_path)
	replacement.track_set_enabled(track_index, enabled)
	for key in keys_result["keys"]:
		replacement.track_insert_key(
			track_index,
			key["time"],
			{"method": StringName(key["method"]), "args": key["args"]}
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
		"Godot 2D MCP: Update animation method track"
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


func upsert_nested_animation_track(params: Dictionary) -> Dictionary:
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
	var target_result := _resolve_safe_nested_animation_track_target(
		scene_root, str(params.get("target_path", ""))
	)
	if target_result.has("_error"):
		return target_result
	var target: AnimationPlayer = target_result["player"]
	var animation_root_result := _resolve_animation_root(player, scene_root)
	if animation_root_result.has("_error"):
		return animation_root_result
	var keys_result := _parse_nested_animation_track_keys(
		params.get("keys", []), animation.length, target, player, animation, scene_root
	)
	if keys_result.has("_error"):
		return keys_result
	var enabled = params.get("enabled", true)
	if not enabled is bool:
		return Errors.make("INVALID_PARAMETER", "enabled must be a boolean")
	var track_path := _make_node_track_path(animation_root_result["root"], target)
	var existing_index := animation.find_track(track_path, Animation.TYPE_ANIMATION)
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
	track_index = replacement.add_track(Animation.TYPE_ANIMATION, existing_index)
	replacement.track_set_path(track_index, track_path)
	replacement.track_set_enabled(track_index, enabled)
	for key in keys_result["keys"]:
		replacement.animation_track_insert_key(track_index, key["time"], StringName(key["animation"]))
	_commit_animation_replacement(
		scene_root,
		player,
		library,
		library_result["name"],
		animation_result["name"],
		animation,
		replacement,
		false,
		"Godot 2D MCP: Update nested animation track"
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
	var track_type := animation.track_get_type(track_index)
	if track_type != Animation.TYPE_VALUE and track_type != Animation.TYPE_AUDIO \
		and track_type != Animation.TYPE_BEZIER and track_type != Animation.TYPE_METHOD \
		and track_type != Animation.TYPE_ANIMATION:
		return Errors.make(
			"UNSUPPORTED_ANIMATION_TRACK",
			"animation_track_delete supports local 2D/UI value, Bezier, audio, safe method, and nested animation tracks only",
			false,
			"3D tracks are not editable in this release."
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
	var track_scope_result: Dictionary = {}
	if track_type == Animation.TYPE_VALUE:
		track_scope_result = _resolve_track_property(
			animation, track_index, animation_root_result["root"], scene_root
		)
	elif track_type == Animation.TYPE_AUDIO:
		track_scope_result = _resolve_audio_track_target(
			animation, track_index, animation_root_result["root"], scene_root
		)
	elif track_type == Animation.TYPE_METHOD:
		track_scope_result = _resolve_safe_method_track(
			animation, track_index, animation_root_result["root"], scene_root
		)
	elif track_type == Animation.TYPE_ANIMATION:
		track_scope_result = _resolve_safe_nested_animation_track(
			animation, track_index, animation_root_result["root"], scene_root
		)
	else:
		track_scope_result = _resolve_bezier_track_property(
			animation, track_index, animation_root_result["root"], scene_root
		)
	if track_scope_result.has("_error"):
		return track_scope_result
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


func _resolve_safe_method_track_target(scene_root: Node, target_path: String) -> Dictionary:
	var target_result := _resolve_local_target(scene_root, target_path)
	if target_result.has("_error"):
		return target_result
	var safety_check := _require_safe_method_track_target(target_result["node"])
	if safety_check != null:
		return safety_check
	return target_result


func _require_safe_method_track_target(target: Node) -> Variant:
	if target.get_script() != null:
		return Errors.make(
			"SCRIPTED_METHOD_TRACK_TARGET",
			"Method tracks cannot target scripted node '%s'" % target.name,
			false,
			"Target an un-scripted built-in 2D node so every method call remains within the safe whitelist."
		)
	if target is CanvasItem or target is AnimationPlayer or target is AudioStreamPlayer2D:
		return null
	return Errors.make(
		"UNSAFE_ANIMATION_METHOD_TARGET",
		"Method tracks do not support target type %s" % target.get_class(),
		false,
		"Target a CanvasItem, AnimationPlayer, AudioStreamPlayer2D, AnimatedSprite2D, or 2D particle node."
	)


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


func _resolve_bezier_property(node: Node, property_path: String) -> Dictionary:
	var clean_path := property_path.strip_edges()
	if clean_path.is_empty() or clean_path.length() > 256:
		return Errors.make("INVALID_PROPERTY", "property must contain 1 to 256 characters")
	var parts := clean_path.split(":")
	if parts.size() < 1 or parts.size() > 2:
		return Errors.make(
			"INVALID_BEZIER_PROPERTY",
			"Bezier properties must be a float property or one Vector2/Color component",
			false,
			"Use a float property, position:x, position:y, or modulate:r/g/b/a."
		)
	for part in parts:
		if part.is_empty() or part.length() > 128:
			return Errors.make("INVALID_BEZIER_PROPERTY", "property path contains an empty or oversized segment")
	var property_result := _resolve_writable_property(node, parts[0])
	if property_result.has("_error"):
		return property_result
	var property_type := int(property_result["property_info"].get("type", TYPE_NIL))
	if parts.size() == 1:
		if property_type != TYPE_FLOAT:
			return Errors.make(
				"BEZIER_PROPERTY_TYPE_UNSUPPORTED",
				"Bezier tracks require a float property or Vector2/Color component, not %s"
					% type_string(property_type),
				false,
				"Target a float property or a supported :x, :y, :r, :g, :b, or :a component."
			)
		return {"name": clean_path, "property_info": property_result["property_info"]}
	var component: String = parts[1]
	if not BEZIER_COMPONENTS_BY_TYPE.has(property_type) \
		or not BEZIER_COMPONENTS_BY_TYPE[property_type].has(component):
		return Errors.make(
			"BEZIER_PROPERTY_TYPE_UNSUPPORTED",
			"Property '%s' does not expose Bezier component '%s'" % [parts[0], component],
			false,
			"Use :x or :y for Vector2, or :r, :g, :b, or :a for Color."
		)
	return {"name": clean_path, "property_info": property_result["property_info"]}


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


func _resolve_bezier_track_property(
	animation: Animation, track_index: int, animation_root: Node, scene_root: Node
) -> Dictionary:
	var track_path := animation.track_get_path(track_index)
	if track_path.get_subname_count() < 1 or track_path.get_subname_count() > 2:
		return Errors.make(
			"UNSUPPORTED_ANIMATION_TRACK_PATH",
			"Bezier track %d must target one float property or Vector2/Color component" % track_index,
			false,
			"Use animation_bezier_track_upsert with a supported local property."
		)
	var target := animation_root.get_node_or_null(track_path)
	if target == null:
		return Errors.make(
			"ANIMATION_TARGET_NOT_FOUND",
			"Animation track %d target no longer exists" % track_index,
			false,
			"Repair or replace the track with animation_bezier_track_upsert."
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
			"Use animation_bezier_track_upsert with a supported 2D target."
		)
	var property_path := str(track_path.get_subname(0))
	if track_path.get_subname_count() == 2:
		property_path += ":%s" % track_path.get_subname(1)
	return _resolve_bezier_property(target, property_path).merged({"node": target})


func _resolve_audio_track_target(
	animation: Animation, track_index: int, animation_root: Node, scene_root: Node
) -> Dictionary:
	var track_path := animation.track_get_path(track_index)
	if track_path.get_subname_count() != 0:
		return Errors.make(
			"UNSUPPORTED_ANIMATION_TRACK_PATH",
			"Audio track %d must target an AudioStreamPlayer2D node directly" % track_index,
			false,
			"Use animation_audio_track_upsert with a scene-local AudioStreamPlayer2D path."
		)
	var target := animation_root.get_node_or_null(track_path)
	if target == null:
		return Errors.make(
			"ANIMATION_TARGET_NOT_FOUND",
			"Animation track %d target no longer exists" % track_index,
			false,
			"Repair or replace the track with animation_audio_track_upsert."
		)
	if target != scene_root and target.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit a track targeting instanced node '%s'" % target.name,
			false,
			"Edit the source PackedScene or replace the track with a local target."
		)
	if not target is AudioStreamPlayer2D:
		return Errors.make(
			"AUDIO_STREAM_PLAYER_2D_REQUIRED",
			"Audio track %d targets %s, not AudioStreamPlayer2D" % [track_index, target.get_class()],
			false,
			"Use animation_audio_track_upsert with a scene-local AudioStreamPlayer2D path."
		)
	return {"node": target}


func _resolve_safe_method_track(
	animation: Animation, track_index: int, animation_root: Node, scene_root: Node
) -> Dictionary:
	var track_path := animation.track_get_path(track_index)
	if track_path.get_subname_count() != 0:
		return Errors.make(
			"UNSUPPORTED_ANIMATION_TRACK_PATH",
			"Method track %d must target a node directly" % track_index,
			false,
			"Use animation_method_track_upsert with a scene-local target path."
		)
	var target := animation_root.get_node_or_null(track_path)
	if target == null:
		return Errors.make(
			"ANIMATION_TARGET_NOT_FOUND",
			"Animation track %d target no longer exists" % track_index,
			false,
			"Repair or replace the track with animation_method_track_upsert."
		)
	if target != scene_root and target.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit a method track targeting instanced node '%s'" % target.name,
			false,
			"Edit the source PackedScene or replace the track with a local target."
		)
	if not TypePolicy.is_supported_node_class(target.get_class()):
		return Errors.make(
			"UNSUPPORTED_2D_TYPE",
			"Method track %d targets unsupported type %s" % [track_index, target.get_class()],
			false,
			"Use animation_method_track_upsert with a supported 2D target."
		)
	var safety_check := _require_safe_method_track_target(target)
	if safety_check != null:
		return safety_check
	for key_index in animation.track_get_key_count(track_index):
		var key_check := _parse_safe_method_track_call(
			target,
			str(animation.method_track_get_name(track_index, key_index)),
			animation.method_track_get_params(track_index, key_index)
		)
		if key_check.has("_error"):
			return key_check
	return {"node": target}


func _resolve_safe_nested_animation_track_target(
	scene_root: Node, target_path: String
) -> Dictionary:
	var target_result := _resolve_local_target(scene_root, target_path)
	if target_result.has("_error"):
		return target_result
	var target: Node = target_result["node"]
	if not target is AnimationPlayer:
		return Errors.make(
			"ANIMATION_PLAYER_REQUIRED",
			"Nested animation tracks must target AnimationPlayer, not %s" % target.get_class(),
			false,
			"Create or target a scene-local un-scripted AnimationPlayer node."
		)
	var safety_check := _require_safe_method_track_target(target)
	if safety_check != null:
		return safety_check
	return {"player": target as AnimationPlayer}


func _resolve_safe_nested_animation_track(
	animation: Animation, track_index: int, animation_root: Node, scene_root: Node
) -> Dictionary:
	var track_path := animation.track_get_path(track_index)
	if track_path.get_subname_count() != 0:
		return Errors.make(
			"UNSUPPORTED_ANIMATION_TRACK_PATH",
			"Nested animation track %d must target an AnimationPlayer node directly" % track_index,
			false,
			"Use animation_nested_track_upsert with a scene-local AnimationPlayer path."
		)
	var target := animation_root.get_node_or_null(track_path)
	if target == null:
		return Errors.make(
			"ANIMATION_TARGET_NOT_FOUND",
			"Animation track %d target no longer exists" % track_index,
			false,
			"Repair or replace the track with animation_nested_track_upsert."
		)
	if target != scene_root and target.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit a nested track targeting instanced node '%s'" % target.name,
			false,
			"Edit the source PackedScene or replace the track with a local target."
		)
	if not target is AnimationPlayer:
		return Errors.make(
			"ANIMATION_PLAYER_REQUIRED",
			"Nested track %d targets %s, not AnimationPlayer" % [track_index, target.get_class()],
			false,
			"Use animation_nested_track_upsert with a scene-local AnimationPlayer path."
		)
	var safety_check := _require_safe_method_track_target(target)
	if safety_check != null:
		return safety_check
	var target_player := target as AnimationPlayer
	for key_index in animation.track_get_key_count(track_index):
		var key_check := _resolve_nested_animation_key(
			target_player,
			str(animation.animation_track_get_key_animation(track_index, key_index)),
			scene_root
		)
		if key_check.has("_error"):
			return key_check
	return {"player": target_player}


func _require_2d_animation_track_scope(
	animation: Animation, animation_root: Node, scene_root: Node, allow_nested: bool = true
) -> Variant:
	for track_index in animation.get_track_count():
		var track_type := animation.track_get_type(track_index)
		if track_type == Animation.TYPE_VALUE:
			var property_result := _resolve_track_property(
				animation, track_index, animation_root, scene_root
			)
			if property_result.has("_error"):
				return property_result
			continue
		if track_type == Animation.TYPE_AUDIO:
			var audio_result := _resolve_audio_track_target(
				animation, track_index, animation_root, scene_root
			)
			if audio_result.has("_error"):
				return audio_result
			continue
		if track_type == Animation.TYPE_BEZIER:
			var bezier_result := _resolve_bezier_track_property(
				animation, track_index, animation_root, scene_root
			)
			if bezier_result.has("_error"):
				return bezier_result
			continue
		if track_type == Animation.TYPE_METHOD:
			var method_result := _resolve_safe_method_track(
				animation, track_index, animation_root, scene_root
			)
			if method_result.has("_error"):
				return method_result
			continue
		if track_type == Animation.TYPE_ANIMATION:
			if not allow_nested:
				return Errors.make(
					"NESTED_ANIMATION_RECURSION",
					"Nested target animations cannot contain further nested animation tracks",
					false,
					"Flatten this animation level into property, audio, Bezier, or safe method tracks."
				)
			var nested_result := _resolve_safe_nested_animation_track(
				animation, track_index, animation_root, scene_root
			)
			if nested_result.has("_error"):
				return nested_result
			continue
		return Errors.make(
			"UNSUPPORTED_ANIMATION_TRACK",
			"Animation contains an unsupported track at index %d" % track_index,
			false,
			"Only local 2D/UI property value, Bezier, safe method, one-level nested animation, and AudioStreamPlayer2D audio tracks are editable."
		)
	return null


func _make_track_path(animation_root: Node, target: Node, property_name: String) -> NodePath:
	return NodePath("%s:%s" % [str(_make_node_track_path(animation_root, target)), property_name])


func _make_node_track_path(animation_root: Node, target: Node) -> NodePath:
	var target_path := str(animation_root.get_path_to(target))
	if target_path.is_empty():
		target_path = "."
	return NodePath(target_path)


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


func _parse_audio_track_keys(raw_keys: Variant, animation_length: float) -> Dictionary:
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
			return Errors.make("INVALID_AUDIO_ANIMATION_KEY", "Every audio key must be an object")
		for field in raw_key:
			if not field is String or not AUDIO_KEY_FIELDS.has(field):
				return Errors.make(
					"INVALID_AUDIO_ANIMATION_KEY",
					"Audio keys allow only time, stream_path, start_offset, and end_offset"
				)
		if not raw_key.has("time") or not raw_key.has("stream_path"):
			return Errors.make(
				"INVALID_AUDIO_ANIMATION_KEY", "Each audio key requires time and stream_path"
			)
		var time_result := _parse_key_time(raw_key["time"], animation_length)
		if time_result.has("_error"):
			return time_result
		var stream_result := _load_audio_track_stream(raw_key["stream_path"])
		if stream_result.has("_error"):
			return stream_result
		var start_offset_result := _parse_audio_track_offset(
			raw_key.get("start_offset", 0.0), "start_offset"
		)
		if start_offset_result.has("_error"):
			return start_offset_result
		var end_offset_result := _parse_audio_track_offset(
			raw_key.get("end_offset", 0.0), "end_offset"
		)
		if end_offset_result.has("_error"):
			return end_offset_result
		for existing_key in parsed:
			if is_equal_approx(existing_key["time"], time_result["time"]):
				return Errors.make(
					"DUPLICATE_ANIMATION_KEY",
					"A track cannot contain more than one key at the same time"
				)
		parsed.append(
			{
				"time": time_result["time"],
				"stream": stream_result["stream"],
				"start_offset": start_offset_result["offset"],
				"end_offset": end_offset_result["offset"],
			}
		)
	return {"keys": parsed}


func _load_audio_track_stream(raw_stream_path: Variant) -> Dictionary:
	if not raw_stream_path is String:
		return Errors.make("INVALID_AUDIO_STREAM_PATH", "stream_path must be a non-empty res:// string")
	var stream_path: String = raw_stream_path.strip_edges()
	if stream_path.is_empty() or stream_path.length() > 4096 or not stream_path.begins_with("res://") \
		or stream_path.contains("/../") or stream_path.ends_with("/.."):
		return Errors.make("INVALID_AUDIO_STREAM_PATH", "stream_path must remain inside the Godot project res:// directory")
	if not ResourceLoader.exists(stream_path):
		return Errors.make("RESOURCE_NOT_FOUND", "stream_path does not exist: %s" % stream_path)
	var stream := ResourceLoader.load(stream_path)
	if not stream is AudioStream:
		return Errors.make("RESOURCE_TYPE_MISMATCH", "stream_path does not load an AudioStream resource")
	return {"stream": stream as AudioStream}


func _parse_audio_track_offset(raw_offset: Variant, label: String) -> Dictionary:
	if not _is_finite_number(raw_offset):
		return Errors.make("INVALID_AUDIO_ANIMATION_KEY", "%s must be a finite number" % label)
	var offset := float(raw_offset)
	if offset < 0.0 or offset > MAX_ANIMATION_LENGTH:
		return Errors.make(
			"INVALID_AUDIO_ANIMATION_KEY",
			"%s must be between 0 and %s seconds" % [label, MAX_ANIMATION_LENGTH]
		)
	return {"offset": offset}


func _parse_method_track_keys(
	raw_keys: Variant, animation_length: float, target: Node
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
			return Errors.make("INVALID_METHOD_ANIMATION_KEY", "Every method key must be an object")
		for field in raw_key:
			if not field is String or not METHOD_KEY_FIELDS.has(field):
				return Errors.make(
					"INVALID_METHOD_ANIMATION_KEY",
					"Method keys allow only time, method, and args"
				)
		if not raw_key.has("time") or not raw_key.has("method"):
			return Errors.make(
				"INVALID_METHOD_ANIMATION_KEY", "Each method key requires time and method"
			)
		var time_result := _parse_key_time(raw_key["time"], animation_length)
		if time_result.has("_error"):
			return time_result
		var call_result := _parse_safe_method_track_call(
			target, raw_key["method"], raw_key.get("args", [])
		)
		if call_result.has("_error"):
			return call_result
		for existing_key in parsed:
			if is_equal_approx(existing_key["time"], time_result["time"]):
				return Errors.make(
					"DUPLICATE_ANIMATION_KEY",
					"A track cannot contain more than one key at the same time"
				)
		parsed.append(
			{
				"time": time_result["time"],
				"method": call_result["method"],
				"args": call_result["args"],
			}
		)
	return {"keys": parsed}


func _parse_nested_animation_track_keys(
	raw_keys: Variant,
	animation_length: float,
	target: AnimationPlayer,
	source_player: AnimationPlayer,
	source_animation: Animation,
	scene_root: Node
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
			return Errors.make("INVALID_NESTED_ANIMATION_KEY", "Every nested animation key must be an object")
		for field in raw_key:
			if not field is String or not NESTED_ANIMATION_KEY_FIELDS.has(field):
				return Errors.make(
					"INVALID_NESTED_ANIMATION_KEY", "Nested keys allow only time and animation"
				)
		if not raw_key.has("time") or not raw_key.has("animation"):
			return Errors.make(
				"INVALID_NESTED_ANIMATION_KEY", "Each nested animation key requires time and animation"
			)
		var time_result := _parse_key_time(raw_key["time"], animation_length)
		if time_result.has("_error"):
			return time_result
		var animation_check := _resolve_nested_animation_key(
			target, raw_key["animation"], scene_root
		)
		if animation_check.has("_error"):
			return animation_check
		if target == source_player and animation_check.get("resource", null) == source_animation:
			return Errors.make(
				"NESTED_ANIMATION_RECURSION",
				"Animation cannot target itself through a nested animation track",
				false,
				"Target a different AnimationPlayer animation or use property tracks directly."
			)
		for existing_key in parsed:
			if is_equal_approx(existing_key["time"], time_result["time"]):
				return Errors.make(
					"DUPLICATE_ANIMATION_KEY",
					"A track cannot contain more than one key at the same time"
				)
		parsed.append({"time": time_result["time"], "animation": animation_check["name"]})
	return {"keys": parsed}


func _resolve_nested_animation_key(
	target: AnimationPlayer, raw_animation_name: Variant, scene_root: Node
) -> Dictionary:
	if not raw_animation_name is String:
		return Errors.make("INVALID_NESTED_ANIMATION_KEY", "animation must be a string")
	var animation_name: String = raw_animation_name.strip_edges()
	if animation_name.is_empty() or animation_name.length() > 256:
		return Errors.make(
			"INVALID_NESTED_ANIMATION_KEY", "animation must contain between 1 and 256 characters"
		)
	if animation_name == NESTED_ANIMATION_STOP:
		return {"name": animation_name, "resource": null}
	if not target.has_animation(StringName(animation_name)):
		return Errors.make(
			"ANIMATION_NOT_FOUND",
			"AnimationPlayer '%s' has no animation named '%s'" % [target.name, animation_name],
			false,
			"Call animation_list to inspect the target AnimationPlayer."
		)
	var nested_animation := target.get_animation(StringName(animation_name))
	if nested_animation == null:
		return Errors.make("ANIMATION_NOT_FOUND", "Target AnimationPlayer animation is unavailable")
	var nested_root_result := _resolve_animation_root(target, scene_root)
	if nested_root_result.has("_error"):
		return nested_root_result
	var scope_check := _require_2d_animation_track_scope(
		nested_animation, nested_root_result["root"], scene_root, false
	)
	if scope_check != null:
		return scope_check
	return {"name": animation_name, "resource": nested_animation}


func _parse_safe_method_track_call(
	target: Node, raw_method: Variant, raw_args: Variant
) -> Dictionary:
	if not raw_method is String:
		return Errors.make("INVALID_METHOD_ANIMATION_KEY", "method must be a string")
	var method: String = raw_method.strip_edges()
	if method.is_empty() or method.length() > 256:
		return Errors.make(
			"INVALID_METHOD_ANIMATION_KEY", "method must contain between 1 and 256 characters"
		)
	if not raw_args is Array:
		return Errors.make("INVALID_METHOD_ANIMATION_KEY", "args must be an array")
	var args: Array = raw_args
	if method == "show" or method == "hide":
		if not target is CanvasItem:
			return _unsafe_method_error(target, method)
		return _require_zero_argument_method(method, args)
	if target is AnimationPlayer:
		return _parse_animation_player_method_call(target, method, args)
	if target is AudioStreamPlayer2D:
		return _parse_audio_stream_player_method_call(method, args)
	if target is AnimatedSprite2D:
		return _parse_animated_sprite_method_call(target, method, args)
	if target is GPUParticles2D or target is CPUParticles2D:
		if method == "restart":
			return _require_zero_argument_method(method, args)
	return _unsafe_method_error(target, method)


func _parse_animation_player_method_call(
	target: AnimationPlayer, method: String, args: Array
) -> Dictionary:
	if method == "stop" or method == "pause":
		return _require_zero_argument_method(method, args)
	if method == "play" or method == "play_backwards":
		if args.size() > 1:
			return Errors.make(
				"INVALID_METHOD_ANIMATION_KEY",
				"AnimationPlayer.%s accepts at most one animation name" % method
			)
		if args.is_empty():
			return {"method": method, "args": []}
		var animation_check := _require_known_animation_name(target, args[0], method)
		if animation_check.has("_error"):
			return animation_check
		return {"method": method, "args": [animation_check["name"]]}
	if method == "queue":
		if args.size() != 1:
			return Errors.make(
				"INVALID_METHOD_ANIMATION_KEY", "AnimationPlayer.queue requires one animation name"
			)
		var queue_animation_check := _require_known_animation_name(target, args[0], method)
		if queue_animation_check.has("_error"):
			return queue_animation_check
		if String(queue_animation_check["name"]).is_empty():
			return Errors.make(
				"INVALID_METHOD_ANIMATION_KEY", "AnimationPlayer.queue requires a non-empty animation name"
			)
		return {"method": method, "args": [queue_animation_check["name"]]}
	return _unsafe_method_error(target, method)


func _parse_audio_stream_player_method_call(method: String, args: Array) -> Dictionary:
	if method == "stop":
		return _require_zero_argument_method(method, args)
	if method != "play":
		return _unsafe_method_error(null, method, "AudioStreamPlayer2D")
	if args.size() > 1:
		return Errors.make(
			"INVALID_METHOD_ANIMATION_KEY", "AudioStreamPlayer2D.play accepts at most one start position"
		)
	if args.is_empty():
		return {"method": method, "args": []}
	if not _is_finite_number(args[0]) or float(args[0]) < 0.0 \
		or float(args[0]) > MAX_ANIMATION_LENGTH:
		return Errors.make(
			"INVALID_METHOD_ANIMATION_KEY",
			"AudioStreamPlayer2D.play position must be between 0 and %s seconds" % MAX_ANIMATION_LENGTH
		)
	return {"method": method, "args": [float(args[0])]}


func _parse_animated_sprite_method_call(
	target: AnimatedSprite2D, method: String, args: Array
) -> Dictionary:
	if method == "pause" or method == "stop":
		return _require_zero_argument_method(method, args)
	if method != "play":
		return _unsafe_method_error(target, method)
	if args.size() > 1:
		return Errors.make(
			"INVALID_METHOD_ANIMATION_KEY", "AnimatedSprite2D.play accepts at most one animation name"
		)
	if args.is_empty():
		return {"method": method, "args": []}
	if not args[0] is String:
		return Errors.make(
			"INVALID_METHOD_ANIMATION_KEY", "AnimatedSprite2D.play animation must be a string"
		)
	var animation_name: String = args[0].strip_edges()
	if animation_name.is_empty() or animation_name.length() > 256:
		return Errors.make(
			"INVALID_METHOD_ANIMATION_KEY",
			"AnimatedSprite2D.play animation must contain between 1 and 256 characters"
		)
	var frames := target.sprite_frames
	if frames == null or not frames.has_animation(StringName(animation_name)):
		return Errors.make(
			"ANIMATION_NOT_FOUND",
			"AnimatedSprite2D '%s' has no animation named '%s'" % [target.name, animation_name],
			false,
			"Call sprite_frames_get to inspect the available animations."
		)
	return {"method": method, "args": [animation_name]}


func _require_known_animation_name(
	target: AnimationPlayer, raw_name: Variant, method: String
) -> Dictionary:
	if not raw_name is String:
		return Errors.make(
			"INVALID_METHOD_ANIMATION_KEY", "AnimationPlayer.%s animation must be a string" % method
		)
	var animation_name: String = raw_name.strip_edges()
	if animation_name.length() > 256:
		return Errors.make(
			"INVALID_METHOD_ANIMATION_KEY",
			"AnimationPlayer.%s animation cannot exceed 256 characters" % method
		)
	if not animation_name.is_empty() and not target.has_animation(StringName(animation_name)):
		return Errors.make(
			"ANIMATION_NOT_FOUND",
			"AnimationPlayer '%s' has no animation named '%s'" % [target.name, animation_name],
			false,
			"Call animation_list to inspect the target AnimationPlayer."
		)
	return {"name": animation_name}


func _require_zero_argument_method(method: String, args: Array) -> Dictionary:
	if not args.is_empty():
		return Errors.make(
			"INVALID_METHOD_ANIMATION_KEY", "%s does not accept arguments" % method
		)
	return {"method": method, "args": []}


func _unsafe_method_error(target: Variant, method: String, target_name: String = "") -> Dictionary:
	var type_name: String = target_name
	if type_name.is_empty():
		type_name = target.get_class()
	return Errors.make(
		"UNSAFE_ANIMATION_METHOD",
		"Method '%s' is not allowed for %s animation tracks" % [method, type_name],
		false,
		"Use the supported show/hide, animation playback, audio playback, AnimatedSprite2D playback, or particle restart methods."
	)


func _parse_bezier_track_keys(raw_keys: Variant, animation_length: float) -> Dictionary:
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
			return Errors.make("INVALID_BEZIER_KEY", "Every Bezier key must be an object")
		for field in raw_key:
			if not field is String or not BEZIER_KEY_FIELDS.has(field):
				return Errors.make(
					"INVALID_BEZIER_KEY",
					"Bezier keys allow only time, value, in_handle, and out_handle"
				)
		if not raw_key.has("time") or not raw_key.has("value"):
			return Errors.make("INVALID_BEZIER_KEY", "Each Bezier key requires time and value")
		var time_result := _parse_key_time(raw_key["time"], animation_length)
		if time_result.has("_error"):
			return time_result
		if not _is_finite_number(raw_key["value"]) \
			or absf(float(raw_key["value"])) > MAX_BEZIER_VALUE:
			return Errors.make(
				"INVALID_BEZIER_KEY",
				"value must be a finite number between -%s and %s" % [MAX_BEZIER_VALUE, MAX_BEZIER_VALUE]
			)
		var in_handle_result := _parse_bezier_handle(
			raw_key.get("in_handle", {"x": 0.0, "y": 0.0}), true, "in_handle"
		)
		if in_handle_result.has("_error"):
			return in_handle_result
		var out_handle_result := _parse_bezier_handle(
			raw_key.get("out_handle", {"x": 0.0, "y": 0.0}), false, "out_handle"
		)
		if out_handle_result.has("_error"):
			return out_handle_result
		for existing_key in parsed:
			if is_equal_approx(existing_key["time"], time_result["time"]):
				return Errors.make(
					"DUPLICATE_ANIMATION_KEY",
					"A track cannot contain more than one key at the same time"
				)
		parsed.append(
			{
				"time": time_result["time"],
				"value": float(raw_key["value"]),
				"in_handle": in_handle_result["handle"],
				"out_handle": out_handle_result["handle"],
			}
		)
	return {"keys": parsed}


func _parse_bezier_handle(raw_handle: Variant, is_in_handle: bool, label: String) -> Dictionary:
	if not raw_handle is Dictionary or raw_handle.size() != 2 \
		or not raw_handle.has("x") or not raw_handle.has("y"):
		return Errors.make("INVALID_BEZIER_KEY", "%s must contain finite x and y values" % label)
	if not _is_finite_number(raw_handle["x"]) or not _is_finite_number(raw_handle["y"]):
		return Errors.make("INVALID_BEZIER_KEY", "%s must contain finite x and y values" % label)
	var x := float(raw_handle["x"])
	var y := float(raw_handle["y"])
	if absf(x) > MAX_BEZIER_HANDLE or absf(y) > MAX_BEZIER_VALUE:
		return Errors.make(
			"INVALID_BEZIER_KEY",
			"%s exceeds the supported Bezier handle bounds" % label
		)
	if (is_in_handle and x > 0.0) or (not is_in_handle and x < 0.0):
		return Errors.make(
			"INVALID_BEZIER_KEY",
			"%s.x must be %s 0" % [label, "at most" if is_in_handle else "at least"]
		)
	return {"handle": Vector2(x, y)}


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


func _parse_audio_track_configuration(params: Dictionary) -> Dictionary:
	var enabled = params.get("enabled", true)
	var use_blend = params.get("use_blend", true)
	if not enabled is bool or not use_blend is bool:
		return Errors.make("INVALID_PARAMETER", "enabled and use_blend must be booleans")
	return {"enabled": enabled, "use_blend": use_blend}


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
	elif animation.track_get_type(track_index) == Animation.TYPE_AUDIO:
		result["use_blend"] = animation.audio_track_is_use_blend(track_index)
	return result


func _serialize_key(animation: Animation, track_index: int, key_index: int) -> Dictionary:
	var result := {
		"index": key_index,
		"time": _safe_float(animation.track_get_key_time(track_index, key_index)),
		"transition": _safe_float(animation.track_get_key_transition(track_index, key_index)),
	}
	if animation.track_get_type(track_index) == Animation.TYPE_AUDIO:
		var stream := animation.audio_track_get_key_stream(track_index, key_index)
		result["stream_path"] = "" if stream == null else stream.resource_path
		result["stream_type"] = "" if stream == null else stream.get_class()
		result["start_offset"] = _safe_float(
			animation.audio_track_get_key_start_offset(track_index, key_index)
		)
		result["end_offset"] = _safe_float(
			animation.audio_track_get_key_end_offset(track_index, key_index)
		)
	elif animation.track_get_type(track_index) == Animation.TYPE_BEZIER:
		result["value"] = _safe_float(animation.bezier_track_get_key_value(track_index, key_index))
		result["in_handle"] = VariantCodec.serialize(
			animation.bezier_track_get_key_in_handle(track_index, key_index)
		)
		result["out_handle"] = VariantCodec.serialize(
			animation.bezier_track_get_key_out_handle(track_index, key_index)
		)
	elif animation.track_get_type(track_index) == Animation.TYPE_METHOD:
		result["method"] = str(animation.method_track_get_name(track_index, key_index))
		result["args"] = VariantCodec.serialize(
			animation.method_track_get_params(track_index, key_index)
		)
	elif animation.track_get_type(track_index) == Animation.TYPE_ANIMATION:
		result["animation"] = str(
			animation.animation_track_get_key_animation(track_index, key_index)
		)
	else:
		result["value"] = VariantCodec.serialize(animation.track_get_key_value(track_index, key_index))
	return result


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
	if track_path.get_subname_count() == 1:
		return str(track_path.get_subname(0))
	if track_path.get_subname_count() == 2:
		return "%s:%s" % [track_path.get_subname(0), track_path.get_subname(1)]
	return ""


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

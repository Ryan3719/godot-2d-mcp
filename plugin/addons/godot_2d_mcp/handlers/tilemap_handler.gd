@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_TILEMAP_CELLS := 512
const MAX_ATLAS_TILE_SIZE := 64
const MAX_PAGE_LIMIT := 512
const MAX_TILESET_LAYERS := 64
const MAX_TILESET_TERRAINS := 64
const MAX_TILE_CUSTOM_DATA_VALUES := 16
const MAX_TILESET_NAME_LENGTH := 128
const MAX_TILE_COLLISION_POLYGONS := 128
const MAX_TILE_COLLISION_POLYGON_POINTS := 512
const MAX_TILE_COLLISION_TOTAL_POINTS := 2048
const MAX_TILE_NAVIGATION_POLYGONS := 512
const MAX_TILE_NAVIGATION_INDICES := 2048
const TERRAIN_MODES := {
	"match_corners_and_sides": 0,
	"match_corners": 1,
	"match_sides": 2,
}
const CUSTOM_DATA_TYPES := {
	"bool": TYPE_BOOL,
	"int": TYPE_INT,
	"float": TYPE_FLOAT,
	"string": TYPE_STRING,
	"vector2": TYPE_VECTOR2,
	"vector2i": TYPE_VECTOR2I,
	"color": TYPE_COLOR,
}
const TERRAIN_PEERING_BITS := {
	"right_side": 0,
	"right_corner": 1,
	"bottom_right_side": 2,
	"bottom_right_corner": 3,
	"bottom_side": 4,
	"bottom_corner": 5,
	"bottom_left_side": 6,
	"bottom_left_corner": 7,
	"left_side": 8,
	"left_corner": 9,
	"top_left_side": 10,
	"top_left_corner": 11,
	"top_side": 12,
	"top_corner": 13,
	"top_right_side": 14,
	"top_right_corner": 15,
}

var _undo_redo: EditorUndoRedoManager


func _init(undo_redo: EditorUndoRedoManager) -> void:
	_undo_redo = undo_redo


func get_tile_map_layer(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params, false)
	if resolved.has("_error"):
		return resolved
	return _tile_map_layer_response(resolved["tile_map_layer"], resolved["scene_root"])


func get_tile_map_layer_cells(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params, false)
	if resolved.has("_error"):
		return resolved
	var page_result := _parse_page(params)
	if page_result.has("_error"):
		return page_result
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var used_cells := tile_map_layer.get_used_cells()
	used_cells.sort()
	var offset: int = page_result["offset"]
	var limit: int = page_result["limit"]
	var end := mini(offset + limit, used_cells.size())
	var cells := []
	for index in range(offset, end):
		cells.append(_serialize_cell(tile_map_layer, used_cells[index]))
	return {
		"path": ScenePath.from_node(tile_map_layer, resolved["scene_root"]),
		"type": tile_map_layer.get_class(),
		"cells": cells,
		"total": used_cells.size(),
		"offset": offset,
		"limit": limit,
		"next_offset": end if end < used_cells.size() else null,
	}


func get_tile_set(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params, false)
	if resolved.has("_error"):
		return resolved
	var page_result := _parse_page(params)
	if page_result.has("_error"):
		return page_result
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	return _tile_set_response(
		tile_map_layer,
		resolved["scene_root"],
		page_result["offset"],
		page_result["limit"]
	)


func create_tile_set(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	if tile_map_layer.tile_set != null:
		return Errors.make(
			"TILE_SET_ALREADY_ASSIGNED",
			"TileMapLayer '%s' already has a TileSet resource" % tile_map_layer.name,
			false,
			"Call tile_set_get before editing it, or tile_set_clear before replacing it."
		)
	var tile_size_result := _parse_tile_size(params.get("tile_size", {"x": 16, "y": 16}), "tile_size")
	if tile_size_result.has("_error"):
		return tile_size_result
	var tile_set := TileSet.new()
	tile_set.tile_size = tile_size_result["value"]
	_commit_tile_set(
		tile_map_layer,
		resolved["scene_root"],
		tile_set,
		"Create TileSet on %s" % tile_map_layer.name
	)
	var result := _tile_set_response(tile_map_layer, resolved["scene_root"])
	result["created"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func clear_tile_set(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var current: TileSet = tile_map_layer.tile_set
	if current == null:
		return _tile_set_required(tile_map_layer)
	_undo_redo.create_action(
		"Godot 2D MCP: Clear TileSet on %s" % tile_map_layer.name,
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	_undo_redo.add_do_property(tile_map_layer, "tile_set", null)
	_undo_redo.add_undo_property(tile_map_layer, "tile_set", current)
	_undo_redo.add_undo_reference(current)
	_undo_redo.commit_action()
	var result := _tile_set_response(tile_map_layer, resolved["scene_root"])
	result["cleared"] = true
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func create_tile_set_atlas_source(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var current: TileSet = tile_map_layer.tile_set
	if current == null:
		return _tile_set_required(tile_map_layer)
	var texture_result := _load_atlas_texture(params.get("texture_path", null))
	if texture_result.has("_error"):
		return texture_result
	var raw_region_size: Variant = params.get("texture_region_size", null)
	var region_size: Vector2i
	if raw_region_size == null:
		region_size = current.tile_size
	else:
		var region_size_result := _parse_tile_size(raw_region_size, "texture_region_size")
		if region_size_result.has("_error"):
			return region_size_result
		region_size = region_size_result["value"]
	if region_size.x < current.tile_size.x or region_size.y < current.tile_size.y:
		return Errors.make(
			"INVALID_TILESET_ATLAS",
			"texture_region_size must be at least the TileSet tile_size"
		)
	var raw_margins: Variant = params.get("margins", null)
	if raw_margins == null:
		raw_margins = {"x": 0, "y": 0}
	var margins_result := _parse_nonnegative_vector2i(raw_margins, "margins")
	if margins_result.has("_error"):
		return margins_result
	var raw_separation: Variant = params.get("separation", null)
	if raw_separation == null:
		raw_separation = {"x": 0, "y": 0}
	var separation_result := _parse_nonnegative_vector2i(raw_separation, "separation")
	if separation_result.has("_error"):
		return separation_result
	var source_id_result := _parse_source_id(params, current)
	if source_id_result.has("_error"):
		return source_id_result
	var replacement_result := _duplicate_tile_set(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: TileSet = replacement_result["tile_set"]
	var atlas_source := TileSetAtlasSource.new()
	atlas_source.texture = texture_result["texture"]
	atlas_source.texture_region_size = region_size
	atlas_source.margins = margins_result["value"]
	atlas_source.separation = separation_result["value"]
	replacement.add_source(atlas_source, source_id_result["source_id"])
	_commit_tile_set(
		tile_map_layer,
		resolved["scene_root"],
		replacement,
		"Create TileSet atlas source on %s" % tile_map_layer.name
	)
	var result := _tile_set_response(tile_map_layer, resolved["scene_root"])
	result["source_id"] = source_id_result["source_id"]
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func create_tile_set_atlas_tile(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var current: TileSet = tile_map_layer.tile_set
	if current == null:
		return _tile_set_required(tile_map_layer)
	var source_result := _resolve_atlas_source(params, current)
	if source_result.has("_error"):
		return source_result
	var atlas_coords_result := _parse_nonnegative_vector2i(params.get("atlas_coords", null), "atlas_coords")
	if atlas_coords_result.has("_error"):
		return atlas_coords_result
	var size_result := _parse_tile_size(params.get("size", {"x": 1, "y": 1}), "size")
	if size_result.has("_error"):
		return size_result
	var atlas_source: TileSetAtlasSource = source_result["atlas_source"]
	var atlas_coords: Vector2i = atlas_coords_result["value"]
	var size: Vector2i = size_result["value"]
	if size.x > MAX_ATLAS_TILE_SIZE or size.y > MAX_ATLAS_TILE_SIZE:
		return Errors.make("INVALID_TILESET_ATLAS", "size exceeds the supported atlas tile limit")
	if atlas_source.has_tile(atlas_coords):
		return Errors.make("ATLAS_TILE_ALREADY_EXISTS", "A tile already exists at atlas_coords")
	if not atlas_source.has_room_for_tile(atlas_coords, size, 0, Vector2i.ZERO, 1):
		return Errors.make(
			"INVALID_TILESET_ATLAS",
			"The requested atlas tile does not fit in the texture or overlaps another tile"
		)
	var replacement_result := _duplicate_tile_set(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: TileSet = replacement_result["tile_set"]
	var replacement_source := replacement.get_source(source_result["source_id"]) as TileSetAtlasSource
	if replacement_source == null:
		return Errors.make("TILE_SET_COPY_FAILED", "Duplicated TileSet lost its atlas source")
	replacement_source.create_tile(atlas_coords, size)
	_commit_tile_set(
		tile_map_layer,
		resolved["scene_root"],
		replacement,
		"Create TileSet atlas tile on %s" % tile_map_layer.name
	)
	var result := _tile_set_response(tile_map_layer, resolved["scene_root"])
	result["source_id"] = source_result["source_id"]
	result["atlas_coords"] = VariantCodec.serialize(atlas_coords)
	result["size"] = VariantCodec.serialize(size)
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_tile_map_layer_cells(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var tile_set: TileSet = tile_map_layer.tile_set
	if tile_set == null:
		return _tile_set_required(tile_map_layer)
	var cells_result := _parse_cells(params.get("cells", null))
	if cells_result.has("_error"):
		return cells_result
	var validity := _validate_cells_against_tile_set(cells_result["cells"], tile_set)
	if validity.has("_error"):
		return validity
	var changed := []
	for cell in cells_result["cells"]:
		var previous := _read_cell(tile_map_layer, cell["coords"])
		if _cells_match(previous, cell):
			continue
		changed.append({"previous": previous, "next": cell})
	if changed.is_empty():
		var unchanged := _tile_map_layer_response(tile_map_layer, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Set TileMapLayer cells on %s" % tile_map_layer.name,
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	for change in changed:
		var next: Dictionary = change["next"]
		_undo_redo.add_do_method(
			tile_map_layer,
			"set_cell",
			next["coords"],
			next["source_id"],
			next["atlas_coords"],
			next["alternative_tile"]
		)
		_add_undo_cell_change(tile_map_layer, change["previous"])
	_undo_redo.commit_action()
	var result := _tile_map_layer_response(tile_map_layer, resolved["scene_root"])
	result["changed_cells"] = changed.size()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func clear_tile_map_layer_cells(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var coordinates_result := _parse_cell_coordinates(params.get("coords", null))
	if coordinates_result.has("_error"):
		return coordinates_result
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var changed := []
	for coords in coordinates_result["coords"]:
		var previous := _read_cell(tile_map_layer, coords)
		if int(previous["source_id"]) < 0:
			continue
		changed.append(previous)
	if changed.is_empty():
		var unchanged := _tile_map_layer_response(tile_map_layer, resolved["scene_root"])
		unchanged["changed"] = false
		unchanged["undoable"] = false
		return unchanged
	_undo_redo.create_action(
		"Godot 2D MCP: Clear TileMapLayer cells on %s" % tile_map_layer.name,
		UndoRedo.MERGE_DISABLE,
		resolved["scene_root"],
		true
	)
	for previous in changed:
		_undo_redo.add_do_method(tile_map_layer, "erase_cell", previous["coords"])
		_add_undo_cell_change(tile_map_layer, previous)
	_undo_redo.commit_action()
	var result := _tile_map_layer_response(tile_map_layer, resolved["scene_root"])
	result["cleared_cells"] = changed.size()
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func get_tile_set_layers(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params, false)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var tile_set: TileSet = tile_map_layer.tile_set
	if tile_set == null:
		return _tile_set_required(tile_map_layer)
	return _tile_set_layers_response(tile_map_layer, resolved["scene_root"])


func get_tile_set_atlas_tile(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params, false)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var tile_set: TileSet = tile_map_layer.tile_set
	if tile_set == null:
		return _tile_set_required(tile_map_layer)
	var tile_result := _resolve_atlas_tile(params, tile_set)
	if tile_result.has("_error"):
		return tile_result
	var tile_data: TileData = tile_result["tile_data"]
	var result := _tile_data_response(tile_map_layer, resolved["scene_root"], tile_result)
	result["physics_layers"] = _serialize_tile_collision_layers(tile_set, tile_data)
	result["navigation_layers"] = _serialize_tile_navigation_layers(tile_set, tile_data)
	return result


func create_tile_set_physics_layer(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var current: TileSet = tile_map_layer.tile_set
	if current == null:
		return _tile_set_required(tile_map_layer)
	if current.get_physics_layers_count() >= MAX_TILESET_LAYERS:
		return Errors.make("TILESET_LAYER_LIMIT", "physics layer count exceeds the supported limit")
	var layers_result := _parse_layer_numbers(params.get("layers", [1]), "layers")
	if layers_result.has("_error"):
		return layers_result
	var masks_result := _parse_layer_numbers(params.get("masks", [1]), "masks")
	if masks_result.has("_error"):
		return masks_result
	var priority_result := _parse_nonnegative_float(params.get("priority", 1.0), "priority")
	if priority_result.has("_error"):
		return priority_result
	var replacement_result := _duplicate_tile_set(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: TileSet = replacement_result["tile_set"]
	var layer_index := replacement.get_physics_layers_count()
	replacement.add_physics_layer()
	replacement.set_physics_layer_collision_layer(layer_index, layers_result["mask"])
	replacement.set_physics_layer_collision_mask(layer_index, masks_result["mask"])
	replacement.set_physics_layer_collision_priority(layer_index, priority_result["value"])
	_commit_tile_set(
		tile_map_layer,
		resolved["scene_root"],
		replacement,
		"Create TileSet physics layer on %s" % tile_map_layer.name
	)
	var result := _tile_set_layers_response(tile_map_layer, resolved["scene_root"])
	result["physics_layer_index"] = layer_index
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func create_tile_set_navigation_layer(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var current: TileSet = tile_map_layer.tile_set
	if current == null:
		return _tile_set_required(tile_map_layer)
	if current.get_navigation_layers_count() >= MAX_TILESET_LAYERS:
		return Errors.make("TILESET_LAYER_LIMIT", "navigation layer count exceeds the supported limit")
	var layers_result := _parse_layer_numbers(params.get("layers", [1]), "layers")
	if layers_result.has("_error"):
		return layers_result
	var replacement_result := _duplicate_tile_set(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: TileSet = replacement_result["tile_set"]
	var layer_index := replacement.get_navigation_layers_count()
	replacement.add_navigation_layer()
	replacement.set_navigation_layer_layers(layer_index, layers_result["mask"])
	_commit_tile_set(
		tile_map_layer,
		resolved["scene_root"],
		replacement,
		"Create TileSet navigation layer on %s" % tile_map_layer.name
	)
	var result := _tile_set_layers_response(tile_map_layer, resolved["scene_root"])
	result["navigation_layer_index"] = layer_index
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func create_tile_set_custom_data_layer(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var current: TileSet = tile_map_layer.tile_set
	if current == null:
		return _tile_set_required(tile_map_layer)
	if current.get_custom_data_layers_count() >= MAX_TILESET_LAYERS:
		return Errors.make("TILESET_LAYER_LIMIT", "custom data layer count exceeds the supported limit")
	var name_result := _parse_tile_set_name(params.get("name", null), "name")
	if name_result.has("_error"):
		return name_result
	var name: String = name_result["value"]
	if current.has_custom_data_layer_by_name(name):
		return Errors.make("CUSTOM_DATA_LAYER_EXISTS", "A custom data layer already uses this name")
	var type_result := _parse_custom_data_type(params.get("value_type", null))
	if type_result.has("_error"):
		return type_result
	var replacement_result := _duplicate_tile_set(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: TileSet = replacement_result["tile_set"]
	var layer_index := replacement.get_custom_data_layers_count()
	replacement.add_custom_data_layer()
	replacement.set_custom_data_layer_name(layer_index, name)
	replacement.set_custom_data_layer_type(layer_index, type_result["type"])
	_commit_tile_set(
		tile_map_layer,
		resolved["scene_root"],
		replacement,
		"Create TileSet custom data layer on %s" % tile_map_layer.name
	)
	var result := _tile_set_layers_response(tile_map_layer, resolved["scene_root"])
	result["custom_data_layer_index"] = layer_index
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func create_tile_set_terrain_set(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var current: TileSet = tile_map_layer.tile_set
	if current == null:
		return _tile_set_required(tile_map_layer)
	if current.get_terrain_sets_count() >= MAX_TILESET_TERRAINS:
		return Errors.make("TILESET_TERRAIN_LIMIT", "terrain set count exceeds the supported limit")
	var mode_result := _parse_terrain_mode(params.get("mode", "match_corners_and_sides"))
	if mode_result.has("_error"):
		return mode_result
	var replacement_result := _duplicate_tile_set(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: TileSet = replacement_result["tile_set"]
	var terrain_set := replacement.get_terrain_sets_count()
	replacement.add_terrain_set()
	replacement.set_terrain_set_mode(terrain_set, mode_result["mode"])
	_commit_tile_set(
		tile_map_layer,
		resolved["scene_root"],
		replacement,
		"Create TileSet terrain set on %s" % tile_map_layer.name
	)
	var result := _tile_set_layers_response(tile_map_layer, resolved["scene_root"])
	result["terrain_set"] = terrain_set
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func create_tile_set_terrain(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var current: TileSet = tile_map_layer.tile_set
	if current == null:
		return _tile_set_required(tile_map_layer)
	var terrain_set_result := _parse_existing_terrain_set(params, current)
	if terrain_set_result.has("_error"):
		return terrain_set_result
	var terrain_set: int = terrain_set_result["terrain_set"]
	if current.get_terrains_count(terrain_set) >= MAX_TILESET_TERRAINS:
		return Errors.make("TILESET_TERRAIN_LIMIT", "terrain count exceeds the supported limit")
	var name_result := _parse_optional_tile_set_name(params.get("name", ""), "name")
	if name_result.has("_error"):
		return name_result
	var color_result := _parse_color(params.get("color", null), Color.WHITE)
	if color_result.has("_error"):
		return color_result
	var replacement_result := _duplicate_tile_set(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: TileSet = replacement_result["tile_set"]
	var terrain_index := replacement.get_terrains_count(terrain_set)
	replacement.add_terrain(terrain_set)
	replacement.set_terrain_name(terrain_set, terrain_index, name_result["value"])
	replacement.set_terrain_color(terrain_set, terrain_index, color_result["color"])
	_commit_tile_set(
		tile_map_layer,
		resolved["scene_root"],
		replacement,
		"Create TileSet terrain on %s" % tile_map_layer.name
	)
	var result := _tile_set_layers_response(tile_map_layer, resolved["scene_root"])
	result["terrain_set"] = terrain_set
	result["terrain"] = terrain_index
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func create_tile_set_atlas_alternative(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var current: TileSet = tile_map_layer.tile_set
	if current == null:
		return _tile_set_required(tile_map_layer)
	var base_tile_params := params.duplicate()
	base_tile_params["alternative_tile"] = 0
	var tile_result := _resolve_atlas_tile(base_tile_params, current)
	if tile_result.has("_error"):
		return tile_result
	var alternative_result := _parse_new_alternative_id(params, tile_result["atlas_source"], tile_result["atlas_coords"])
	if alternative_result.has("_error"):
		return alternative_result
	var replacement_result := _duplicate_tile_set(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: TileSet = replacement_result["tile_set"]
	var source := replacement.get_source(tile_result["source_id"]) as TileSetAtlasSource
	if source == null:
		return Errors.make("TILE_SET_COPY_FAILED", "Duplicated TileSet lost its atlas source")
	var alternative_id := source.create_alternative_tile(
		tile_result["atlas_coords"], alternative_result["alternative_id"]
	)
	if alternative_id < 0:
		return Errors.make("ATLAS_ALTERNATIVE_CREATE_FAILED", "Godot could not create the requested alternative tile")
	_commit_tile_set(
		tile_map_layer,
		resolved["scene_root"],
		replacement,
		"Create TileSet atlas alternative on %s" % tile_map_layer.name
	)
	var result := _tile_set_response(tile_map_layer, resolved["scene_root"])
	result["source_id"] = tile_result["source_id"]
	result["atlas_coords"] = VariantCodec.serialize(tile_result["atlas_coords"])
	result["alternative_tile"] = alternative_id
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_tile_set_atlas_tile_terrain(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var current: TileSet = tile_map_layer.tile_set
	if current == null:
		return _tile_set_required(tile_map_layer)
	var tile_result := _resolve_atlas_tile(params, current)
	if tile_result.has("_error"):
		return tile_result
	var terrain_result := _parse_tile_terrain(params, current, tile_result["tile_data"])
	if terrain_result.has("_error"):
		return terrain_result
	var replacement_result := _duplicate_tile_set(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: TileSet = replacement_result["tile_set"]
	var replacement_data_result := _get_replacement_tile_data(replacement, tile_result)
	if replacement_data_result.has("_error"):
		return replacement_data_result
	var tile_data: TileData = replacement_data_result["tile_data"]
	for name in terrain_result["clear_peering_bits"]:
		tile_data.set_terrain_peering_bit(TERRAIN_PEERING_BITS[name], -1)
	tile_data.terrain_set = terrain_result["terrain_set"]
	tile_data.terrain = terrain_result["terrain"]
	for name in terrain_result["peering_bits"]:
		tile_data.set_terrain_peering_bit(TERRAIN_PEERING_BITS[name], terrain_result["peering_bits"][name])
	_commit_tile_set(
		tile_map_layer,
		resolved["scene_root"],
		replacement,
		"Set TileSet atlas terrain on %s" % tile_map_layer.name
	)
	var result := _tile_data_response(tile_map_layer, resolved["scene_root"], tile_result)
	result["terrain_set"] = terrain_result["terrain_set"]
	result["terrain"] = terrain_result["terrain"]
	result["peering_bits"] = terrain_result["peering_bits"]
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_tile_set_atlas_tile_custom_data(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var current: TileSet = tile_map_layer.tile_set
	if current == null:
		return _tile_set_required(tile_map_layer)
	var tile_result := _resolve_atlas_tile(params, current)
	if tile_result.has("_error"):
		return tile_result
	var values_result := _parse_tile_custom_data(params.get("values", null), current, tile_result["tile_data"])
	if values_result.has("_error"):
		return values_result
	var replacement_result := _duplicate_tile_set(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: TileSet = replacement_result["tile_set"]
	var replacement_data_result := _get_replacement_tile_data(replacement, tile_result)
	if replacement_data_result.has("_error"):
		return replacement_data_result
	var tile_data: TileData = replacement_data_result["tile_data"]
	for name in values_result["values"]:
		tile_data.set_custom_data(name, values_result["values"][name])
	_commit_tile_set(
		tile_map_layer,
		resolved["scene_root"],
		replacement,
		"Set TileSet atlas custom data on %s" % tile_map_layer.name
	)
	var result := _tile_data_response(tile_map_layer, resolved["scene_root"], tile_result)
	result["custom_data"] = values_result["serialized"]
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_tile_set_atlas_tile_collision(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var current: TileSet = tile_map_layer.tile_set
	if current == null:
		return _tile_set_required(tile_map_layer)
	var tile_result := _resolve_atlas_tile(params, current)
	if tile_result.has("_error"):
		return tile_result
	var layer_result := _parse_existing_tile_set_layer(
		params.get("physics_layer", null), "physics_layer", current.get_physics_layers_count()
	)
	if layer_result.has("_error"):
		return layer_result
	var polygons_result := _parse_tile_collision_polygons(params.get("polygons", null))
	if polygons_result.has("_error"):
		return polygons_result
	var replacement_result := _duplicate_tile_set(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: TileSet = replacement_result["tile_set"]
	var replacement_data_result := _get_replacement_tile_data(replacement, tile_result)
	if replacement_data_result.has("_error"):
		return replacement_data_result
	var tile_data: TileData = replacement_data_result["tile_data"]
	var physics_layer: int = layer_result["layer"]
	var polygons: Array = polygons_result["polygons"]
	tile_data.set_collision_polygons_count(physics_layer, polygons.size())
	for polygon_index in polygons.size():
		var polygon: Dictionary = polygons[polygon_index]
		tile_data.set_collision_polygon_points(physics_layer, polygon_index, polygon["points"])
		tile_data.set_collision_polygon_one_way(physics_layer, polygon_index, polygon["one_way"])
		tile_data.set_collision_polygon_one_way_margin(
			physics_layer, polygon_index, polygon["one_way_margin"]
		)
	_commit_tile_set(
		tile_map_layer,
		resolved["scene_root"],
		replacement,
		"Set TileSet atlas collision on %s" % tile_map_layer.name
	)
	var result := _tile_data_response(tile_map_layer, resolved["scene_root"], tile_result)
	result["physics_layer"] = physics_layer
	result["collision_polygons"] = _serialize_tile_collision_polygons(tile_data, physics_layer)
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func set_tile_set_atlas_tile_navigation(params: Dictionary) -> Dictionary:
	var resolved := _resolve_tile_map_layer(params)
	if resolved.has("_error"):
		return resolved
	var tile_map_layer: TileMapLayer = resolved["tile_map_layer"]
	var current: TileSet = tile_map_layer.tile_set
	if current == null:
		return _tile_set_required(tile_map_layer)
	var tile_result := _resolve_atlas_tile(params, current)
	if tile_result.has("_error"):
		return tile_result
	var layer_result := _parse_existing_tile_set_layer(
		params.get("navigation_layer", null), "navigation_layer", current.get_navigation_layers_count()
	)
	if layer_result.has("_error"):
		return layer_result
	var clear_result := _parse_tile_navigation_clear(params.get("clear", false))
	if clear_result.has("_error"):
		return clear_result
	var geometry_result := {}
	var agent_radius := 0.0
	if not clear_result["clear"]:
		geometry_result = _parse_tile_navigation_geometry(params)
		if geometry_result.has("_error"):
			return geometry_result
		var radius_result := _parse_nonnegative_float(params.get("agent_radius", 0.0), "agent_radius")
		if radius_result.has("_error"):
			return Errors.make("INVALID_TILE_NAVIGATION", "agent_radius must be a finite number greater than or equal to zero")
		agent_radius = radius_result["value"]
	var replacement_result := _duplicate_tile_set(current)
	if replacement_result.has("_error"):
		return replacement_result
	var replacement: TileSet = replacement_result["tile_set"]
	var replacement_data_result := _get_replacement_tile_data(replacement, tile_result)
	if replacement_data_result.has("_error"):
		return replacement_data_result
	var tile_data: TileData = replacement_data_result["tile_data"]
	var navigation_layer: int = layer_result["layer"]
	if clear_result["clear"]:
		tile_data.set_navigation_polygon(navigation_layer, null)
	else:
		var navigation_polygon := NavigationPolygon.new()
		navigation_polygon.agent_radius = agent_radius
		navigation_polygon.set_vertices(geometry_result["vertices"])
		navigation_polygon.clear_polygons()
		for polygon in geometry_result["polygons"]:
			navigation_polygon.add_polygon(polygon)
		tile_data.set_navigation_polygon(navigation_layer, navigation_polygon)
	_commit_tile_set(
		tile_map_layer,
		resolved["scene_root"],
		replacement,
		"Set TileSet atlas navigation on %s" % tile_map_layer.name
	)
	var result := _tile_data_response(tile_map_layer, resolved["scene_root"], tile_result)
	result["navigation_layer"] = navigation_layer
	result["navigation_polygon"] = _serialize_tile_navigation_polygon(
		tile_data.get_navigation_polygon(navigation_layer)
	)
	result["undoable"] = true
	result["_scene_mutated"] = true
	return result


func _parse_layer_numbers(raw_values: Variant, label: String) -> Dictionary:
	if not raw_values is Array or raw_values.size() > 32:
		return Errors.make("INVALID_TILESET_LAYERS", "%s must contain at most 32 layer numbers" % label)
	var mask := 0
	for raw_value in raw_values:
		if not _is_integral_number(raw_value):
			return Errors.make("INVALID_TILESET_LAYERS", "%s entries must be integers from 1 to 32" % label)
		var layer := int(raw_value)
		if layer < 1 or layer > 32 or mask & (1 << (layer - 1)) != 0:
			return Errors.make(
				"INVALID_TILESET_LAYERS", "%s entries must be unique integers from 1 to 32" % label
			)
		mask |= 1 << (layer - 1)
	return {"mask": mask}


func _mask_to_layer_numbers(mask: int) -> Array[int]:
	var layers: Array[int] = []
	for index in 32:
		if mask & (1 << index) != 0:
			layers.append(index + 1)
	return layers


func _parse_nonnegative_float(raw_value: Variant, label: String) -> Dictionary:
	if not (raw_value is int or raw_value is float) or not is_finite(float(raw_value)):
		return Errors.make("INVALID_TILESET_VALUE", "%s must be a finite number" % label)
	var value := float(raw_value)
	if value < 0.0:
		return Errors.make("INVALID_TILESET_VALUE", "%s must be greater than or equal to zero" % label)
	return {"value": value}


func _parse_tile_set_name(raw_value: Variant, label: String) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_TILESET_NAME", "%s must be a non-empty string" % label)
	var value: String = raw_value.strip_edges()
	if value.is_empty() or value.length() > MAX_TILESET_NAME_LENGTH or "/" in value or ":" in value:
		return Errors.make("INVALID_TILESET_NAME", "%s is not a supported TileSet identifier" % label)
	return {"value": value}


func _parse_optional_tile_set_name(raw_value: Variant, label: String) -> Dictionary:
	if not raw_value is String or raw_value.length() > MAX_TILESET_NAME_LENGTH:
		return Errors.make("INVALID_TILESET_NAME", "%s must be a string with at most 128 characters" % label)
	return {"value": raw_value}


func _parse_custom_data_type(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_CUSTOM_DATA_TYPE", "value_type must be a supported type name")
	var name: String = raw_value.to_lower().strip_edges()
	if not CUSTOM_DATA_TYPES.has(name):
		return Errors.make(
			"INVALID_CUSTOM_DATA_TYPE",
			"value_type must be one of: bool, int, float, string, vector2, vector2i, color"
		)
	return {"name": name, "type": CUSTOM_DATA_TYPES[name]}


func _parse_terrain_mode(raw_value: Variant) -> Dictionary:
	if not raw_value is String:
		return Errors.make("INVALID_TERRAIN_MODE", "mode must be a supported terrain mode name")
	var name: String = raw_value.to_lower().strip_edges()
	if not TERRAIN_MODES.has(name):
		return Errors.make(
			"INVALID_TERRAIN_MODE",
			"mode must be match_corners_and_sides, match_corners, or match_sides"
		)
	return {"mode": TERRAIN_MODES[name]}


func _terrain_mode_name(mode: int) -> String:
	for name in TERRAIN_MODES:
		if int(TERRAIN_MODES[name]) == mode:
			return name
	return "unknown"


func _custom_data_type_name(value_type: int) -> String:
	for name in CUSTOM_DATA_TYPES:
		if int(CUSTOM_DATA_TYPES[name]) == value_type:
			return name
	return type_string(value_type)


func _parse_color(raw_value: Variant, fallback: Color) -> Dictionary:
	if raw_value == null:
		return {"color": fallback}
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_COLOR}, fallback)
	if decoded.has("_error"):
		return Errors.make("INVALID_TILESET_COLOR", "color must be a Color string or numeric r, g, b, a object")
	return {"color": decoded["value"]}


func _parse_existing_terrain_set(params: Dictionary, tile_set: TileSet) -> Dictionary:
	if not params.has("terrain_set") or not _is_integral_number(params["terrain_set"]):
		return Errors.make("MISSING_PARAMETER", "terrain_set must be an existing non-negative integer")
	var terrain_set := int(params["terrain_set"])
	if terrain_set < 0 or terrain_set >= tile_set.get_terrain_sets_count():
		return Errors.make("TERRAIN_SET_NOT_FOUND", "terrain_set does not identify a TileSet terrain set")
	return {"terrain_set": terrain_set}


func _resolve_atlas_tile(params: Dictionary, tile_set: TileSet) -> Dictionary:
	var source_result := _resolve_atlas_source(params, tile_set)
	if source_result.has("_error"):
		return source_result
	var atlas_coords_result := _parse_nonnegative_vector2i(params.get("atlas_coords", null), "atlas_coords")
	if atlas_coords_result.has("_error"):
		return atlas_coords_result
	var atlas_source: TileSetAtlasSource = source_result["atlas_source"]
	var atlas_coords: Vector2i = atlas_coords_result["value"]
	if not atlas_source.has_tile(atlas_coords):
		return Errors.make("ATLAS_TILE_NOT_FOUND", "atlas_coords is not a tile in the selected source")
	var alternative_result := _parse_existing_alternative_id(params, atlas_source, atlas_coords)
	if alternative_result.has("_error"):
		return alternative_result
	var alternative_tile: int = alternative_result["alternative_tile"]
	var tile_data := atlas_source.get_tile_data(atlas_coords, alternative_tile)
	if tile_data == null:
		return Errors.make("ATLAS_TILE_NOT_FOUND", "Godot could not resolve the selected TileData")
	return {
		"source_id": source_result["source_id"],
		"atlas_source": atlas_source,
		"atlas_coords": atlas_coords,
		"alternative_tile": alternative_tile,
		"tile_data": tile_data as TileData,
	}


func _parse_existing_alternative_id(
	params: Dictionary,
	atlas_source: TileSetAtlasSource,
	atlas_coords: Vector2i
) -> Dictionary:
	var raw_value: Variant = params.get("alternative_tile", 0)
	if raw_value == null:
		raw_value = 0
	if not _is_integral_number(raw_value) or int(raw_value) < 0 or int(raw_value) > 4095:
		return Errors.make("INVALID_ATLAS_ALTERNATIVE", "alternative_tile must be an integer from 0 to 4095")
	var alternative_tile := int(raw_value)
	if not atlas_source.has_alternative_tile(atlas_coords, alternative_tile):
		return Errors.make("ATLAS_ALTERNATIVE_NOT_FOUND", "alternative_tile is not defined for atlas_coords")
	return {"alternative_tile": alternative_tile}


func _parse_new_alternative_id(
	params: Dictionary,
	atlas_source: TileSetAtlasSource,
	atlas_coords: Vector2i
) -> Dictionary:
	if not params.has("alternative_tile") or params["alternative_tile"] == null:
		var next_id := atlas_source.get_next_alternative_tile_id(atlas_coords)
		if next_id < 1 or next_id > 4095:
			return Errors.make("INVALID_ATLAS_ALTERNATIVE", "Godot could not allocate a supported alternative tile ID")
		return {"alternative_id": next_id}
	if not _is_integral_number(params["alternative_tile"]):
		return Errors.make("INVALID_ATLAS_ALTERNATIVE", "alternative_tile must be an integer from 1 to 4095")
	var alternative_id := int(params["alternative_tile"])
	if alternative_id < 1 or alternative_id > 4095:
		return Errors.make("INVALID_ATLAS_ALTERNATIVE", "alternative_tile must be an integer from 1 to 4095")
	if atlas_source.has_alternative_tile(atlas_coords, alternative_id):
		return Errors.make("ATLAS_ALTERNATIVE_EXISTS", "alternative_tile already exists for atlas_coords")
	return {"alternative_id": alternative_id}


func _get_replacement_tile_data(replacement: TileSet, tile_result: Dictionary) -> Dictionary:
	var source := replacement.get_source(tile_result["source_id"])
	if not source is TileSetAtlasSource:
		return Errors.make("TILE_SET_COPY_FAILED", "Duplicated TileSet lost its atlas source")
	var tile_data := (source as TileSetAtlasSource).get_tile_data(
		tile_result["atlas_coords"], tile_result["alternative_tile"]
	)
	if tile_data == null:
		return Errors.make("TILE_SET_COPY_FAILED", "Duplicated TileSet lost its TileData")
	return {"tile_data": tile_data as TileData}


func _parse_tile_terrain(params: Dictionary, tile_set: TileSet, tile_data: TileData) -> Dictionary:
	if not params.has("terrain_set") or not params.has("terrain"):
		return Errors.make("MISSING_PARAMETER", "terrain_set and terrain must be supplied")
	if not _is_integral_number(params["terrain_set"]) or not _is_integral_number(params["terrain"]):
		return Errors.make("INVALID_TILE_TERRAIN", "terrain_set and terrain must be integers")
	var terrain_set := int(params["terrain_set"])
	var terrain := int(params["terrain"])
	if terrain_set == -1:
		if terrain != -1:
			return Errors.make("INVALID_TILE_TERRAIN", "terrain must be -1 when terrain_set is -1")
	elif terrain_set < 0 or terrain_set >= tile_set.get_terrain_sets_count():
		return Errors.make("TERRAIN_SET_NOT_FOUND", "terrain_set does not identify a TileSet terrain set")
	elif terrain < 0 or terrain >= tile_set.get_terrains_count(terrain_set):
		return Errors.make("TERRAIN_NOT_FOUND", "terrain does not identify a terrain in terrain_set")
	var peering_bits := {}
	var clear_peering_bits: Array[String] = []
	if terrain_set == -1:
		for name in TERRAIN_PEERING_BITS:
			if tile_data.is_valid_terrain_peering_bit(TERRAIN_PEERING_BITS[name]):
				clear_peering_bits.append(name)
	var raw_peering_bits: Variant = params.get("peering_bits", {})
	if not raw_peering_bits is Dictionary or raw_peering_bits.size() > TERRAIN_PEERING_BITS.size():
		return Errors.make("INVALID_TILE_TERRAIN", "peering_bits must be an object with supported neighbor names")
	for raw_name in raw_peering_bits:
		if not raw_name is String or not TERRAIN_PEERING_BITS.has(raw_name):
			return Errors.make("INVALID_TILE_TERRAIN", "peering_bits contains an unsupported neighbor name")
		if not _is_integral_number(raw_peering_bits[raw_name]):
			return Errors.make("INVALID_TILE_TERRAIN", "peering_bits values must be terrain indices")
		var value := int(raw_peering_bits[raw_name])
		if terrain_set == -1:
			if value != -1:
				return Errors.make("INVALID_TILE_TERRAIN", "cleared terrain_set requires peering_bits values of -1")
		elif value < -1 or value >= tile_set.get_terrains_count(terrain_set):
			return Errors.make("TERRAIN_NOT_FOUND", "peering_bits values must be -1 or terrain indices in terrain_set")
		if terrain_set != -1 and not _is_valid_terrain_peering_bit(
			tile_set, terrain_set, TERRAIN_PEERING_BITS[raw_name]
		):
			return Errors.make("INVALID_TILE_TERRAIN", "peering_bits contains a direction invalid for this TileSet layout")
		peering_bits[raw_name] = value
	return {
		"terrain_set": terrain_set,
		"terrain": terrain,
		"peering_bits": peering_bits,
		"clear_peering_bits": clear_peering_bits,
	}


func _is_valid_terrain_peering_bit(tile_set: TileSet, terrain_set: int, peering_bit: int) -> bool:
	if terrain_set < 0 or terrain_set >= tile_set.get_terrain_sets_count():
		return false
	var mode := tile_set.get_terrain_set_mode(terrain_set)
	var supports_sides := mode == TERRAIN_MODES["match_corners_and_sides"] \
		or mode == TERRAIN_MODES["match_sides"]
	var supports_corners := mode == TERRAIN_MODES["match_corners_and_sides"] \
		or mode == TERRAIN_MODES["match_corners"]
	var side_bits: Array[int] = []
	var corner_bits: Array[int] = []
	if tile_set.tile_shape == TileSet.TILE_SHAPE_SQUARE:
		side_bits.assign([0, 4, 8, 12])
		corner_bits.assign([3, 7, 11, 15])
	elif tile_set.tile_shape == TileSet.TILE_SHAPE_ISOMETRIC:
		side_bits.assign([2, 6, 10, 14])
		corner_bits.assign([1, 5, 9, 13])
	elif tile_set.tile_offset_axis == TileSet.TILE_OFFSET_AXIS_HORIZONTAL:
		side_bits.assign([0, 2, 6, 8, 10, 14])
		corner_bits.assign([3, 5, 7, 11, 13, 15])
	else:
		side_bits.assign([2, 4, 6, 10, 12, 14])
		corner_bits.assign([1, 3, 7, 9, 11, 15])
	return (supports_sides and peering_bit in side_bits) \
		or (supports_corners and peering_bit in corner_bits)


func _parse_tile_custom_data(raw_values: Variant, tile_set: TileSet, tile_data: TileData) -> Dictionary:
	if not raw_values is Dictionary or raw_values.is_empty() or raw_values.size() > MAX_TILE_CUSTOM_DATA_VALUES:
		return Errors.make(
			"INVALID_TILE_CUSTOM_DATA",
			"values must be a non-empty object with at most %d entries" % MAX_TILE_CUSTOM_DATA_VALUES
		)
	var values := {}
	var serialized := {}
	for raw_name in raw_values:
		if not raw_name is String or raw_name.is_empty() or raw_name.length() > MAX_TILESET_NAME_LENGTH:
			return Errors.make("INVALID_TILE_CUSTOM_DATA", "custom data names must be supported TileSet identifiers")
		var layer_index := tile_set.get_custom_data_layer_by_name(raw_name)
		if layer_index < 0:
			return Errors.make("CUSTOM_DATA_LAYER_NOT_FOUND", "values contains a name not defined by this TileSet")
		var decoded := VariantCodec.decode(
			raw_values[raw_name],
			{"type": tile_set.get_custom_data_layer_type(layer_index)},
			tile_data.get_custom_data(raw_name)
		)
		if decoded.has("_error"):
			return Errors.make(
				"INVALID_TILE_CUSTOM_DATA",
				"values.%s does not match the TileSet custom data type" % raw_name
			)
		values[raw_name] = decoded["value"]
		serialized[raw_name] = VariantCodec.serialize(decoded["value"])
	return {"values": values, "serialized": serialized}


func _parse_existing_tile_set_layer(raw_value: Variant, label: String, layer_count: int) -> Dictionary:
	if not _is_integral_number(raw_value):
		return Errors.make("MISSING_PARAMETER", "%s must be an existing non-negative integer" % label)
	var layer := int(raw_value)
	if layer < 0 or layer >= layer_count:
		return Errors.make("TILESET_LAYER_NOT_FOUND", "%s does not identify an existing TileSet layer" % label)
	return {"layer": layer}


func _parse_tile_collision_polygons(raw_value: Variant) -> Dictionary:
	if not raw_value is Array or raw_value.size() > MAX_TILE_COLLISION_POLYGONS:
		return Errors.make(
			"INVALID_TILE_COLLISION",
			"polygons must contain at most %d polygons" % MAX_TILE_COLLISION_POLYGONS
		)
	var polygons: Array = []
	var total_points := 0
	for polygon_index in raw_value.size():
		var raw_polygon: Variant = raw_value[polygon_index]
		if not raw_polygon is Dictionary or not raw_polygon.has("points"):
			return Errors.make("INVALID_TILE_COLLISION", "polygons entries must contain points")
		for name in raw_polygon:
			if name != "points" and name != "one_way" and name != "one_way_margin":
				return Errors.make("INVALID_TILE_COLLISION", "polygons entries contain an unsupported property")
		var points_result := _parse_tile_collision_polygon_points(
			raw_polygon["points"], "polygons[%d].points" % polygon_index
		)
		if points_result.has("_error"):
			return points_result
		var points: PackedVector2Array = points_result["points"]
		total_points += points.size()
		if total_points > MAX_TILE_COLLISION_TOTAL_POINTS:
			return Errors.make("INVALID_TILE_COLLISION", "collision polygon points exceed the supported limit")
		var one_way := false
		if raw_polygon.has("one_way"):
			if not raw_polygon["one_way"] is bool:
				return Errors.make("INVALID_TILE_COLLISION", "polygons[].one_way must be a boolean")
			one_way = raw_polygon["one_way"]
		var one_way_margin := 1.0
		if raw_polygon.has("one_way_margin"):
			var margin_value: Variant = raw_polygon["one_way_margin"]
			if not (margin_value is int or margin_value is float) or not is_finite(float(margin_value)) \
				or float(margin_value) < 0.0:
				return Errors.make(
					"INVALID_TILE_COLLISION",
					"polygons[].one_way_margin must be a finite number greater than or equal to zero"
				)
			one_way_margin = float(margin_value)
		polygons.append({
			"points": points,
			"one_way": one_way,
			"one_way_margin": one_way_margin,
		})
	return {"polygons": polygons}


func _parse_tile_collision_polygon_points(raw_value: Variant, label: String) -> Dictionary:
	var decoded := VariantCodec.decode(
		raw_value, {"type": TYPE_PACKED_VECTOR2_ARRAY}, PackedVector2Array()
	)
	if decoded.has("_error"):
		return Errors.make("INVALID_TILE_COLLISION", "%s must be an array of Vector2 objects" % label)
	var points: PackedVector2Array = decoded["value"]
	if points.size() < 3 or points.size() > MAX_TILE_COLLISION_POLYGON_POINTS:
		return Errors.make(
			"INVALID_TILE_COLLISION",
			"%s must contain between 3 and %d points" % [label, MAX_TILE_COLLISION_POLYGON_POINTS]
		)
	for point_index in points.size():
		if not is_finite(points[point_index].x) or not is_finite(points[point_index].y):
			return Errors.make("INVALID_TILE_COLLISION", "%s points must be finite" % label)
		for later_index in range(point_index + 1, points.size()):
			if points[point_index].is_equal_approx(points[later_index]):
				return Errors.make("INVALID_TILE_COLLISION", "%s points must be unique" % label)
	var signed_area := 0.0
	for point_index in points.size():
		var next_index := (point_index + 1) % points.size()
		signed_area += points[point_index].cross(points[next_index])
	if is_zero_approx(signed_area):
		return Errors.make("INVALID_TILE_COLLISION", "%s must enclose a non-zero area" % label)
	if Geometry2D.decompose_polygon_in_convex(points).is_empty():
		return Errors.make("INVALID_TILE_COLLISION", "%s must describe a valid simple polygon" % label)
	return {"points": points}


func _parse_tile_navigation_clear(raw_value: Variant) -> Dictionary:
	if not raw_value is bool:
		return Errors.make("INVALID_TILE_NAVIGATION", "clear must be a boolean")
	return {"clear": raw_value}


func _parse_tile_navigation_geometry(params: Dictionary) -> Dictionary:
	if not params.has("vertices") or not params.has("polygons") \
		or params["vertices"] == null or params["polygons"] == null:
		return Errors.make("MISSING_PARAMETER", "vertices and polygons must be supplied unless clear is true")
	var vertices_result := _parse_tile_navigation_points(params["vertices"], "vertices")
	if vertices_result.has("_error"):
		return vertices_result
	var vertices: PackedVector2Array = vertices_result["points"]
	var raw_polygons: Variant = params["polygons"]
	if not raw_polygons is Array or raw_polygons.size() > MAX_TILE_NAVIGATION_POLYGONS:
		return Errors.make(
			"INVALID_TILE_NAVIGATION",
			"polygons must contain at most %d polygons" % MAX_TILE_NAVIGATION_POLYGONS
		)
	if vertices.size() < 3:
		return Errors.make("INVALID_TILE_NAVIGATION", "vertices must contain at least three points")
	if raw_polygons.is_empty():
		return Errors.make("INVALID_TILE_NAVIGATION", "polygons must contain at least one polygon")
	var polygons: Array[PackedInt32Array] = []
	var total_indices := 0
	for polygon_index in raw_polygons.size():
		var polygon_result := _parse_tile_navigation_indices(
			raw_polygons[polygon_index], vertices, polygon_index, total_indices
		)
		if polygon_result.has("_error"):
			return polygon_result
		var polygon: PackedInt32Array = polygon_result["polygon"]
		total_indices += polygon.size()
		polygons.append(polygon)
	return {"vertices": vertices, "polygons": polygons}


func _parse_tile_navigation_points(raw_value: Variant, label: String) -> Dictionary:
	var decoded := VariantCodec.decode(
		raw_value, {"type": TYPE_PACKED_VECTOR2_ARRAY}, PackedVector2Array()
	)
	if decoded.has("_error"):
		return Errors.make("INVALID_TILE_NAVIGATION", "%s must be an array of Vector2 objects" % label)
	var points: PackedVector2Array = decoded["value"]
	if points.size() > MAX_TILE_COLLISION_POLYGON_POINTS:
		return Errors.make("INVALID_TILE_NAVIGATION", "%s exceeds the supported point limit" % label)
	for point_index in points.size():
		if not is_finite(points[point_index].x) or not is_finite(points[point_index].y):
			return Errors.make("INVALID_TILE_NAVIGATION", "%s points must be finite" % label)
		for later_index in range(point_index + 1, points.size()):
			if points[point_index].is_equal_approx(points[later_index]):
				return Errors.make("INVALID_TILE_NAVIGATION", "%s points must be unique" % label)
	return {"points": points}


func _parse_tile_navigation_indices(
	raw_polygon: Variant,
	vertices: PackedVector2Array,
	polygon_index: int,
	total_indices: int
) -> Dictionary:
	if not raw_polygon is Array or raw_polygon.size() < 3:
		return Errors.make(
			"INVALID_TILE_NAVIGATION",
			"polygons[%d] must contain at least three vertex indices" % polygon_index
		)
	if raw_polygon.size() > MAX_TILE_COLLISION_POLYGON_POINTS \
		or total_indices + raw_polygon.size() > MAX_TILE_NAVIGATION_INDICES:
		return Errors.make("INVALID_TILE_NAVIGATION", "polygon indices exceed the supported limit")
	var polygon := PackedInt32Array()
	var seen := {}
	for raw_index in raw_polygon:
		if not _is_integral_number(raw_index):
			return Errors.make("INVALID_TILE_NAVIGATION", "polygon indices must be integers")
		var vertex_index := int(raw_index)
		if vertex_index < 0 or vertex_index >= vertices.size():
			return Errors.make("INVALID_TILE_NAVIGATION", "polygon index is outside the vertices array")
		if seen.has(vertex_index):
			return Errors.make("INVALID_TILE_NAVIGATION", "polygon indices must not repeat a vertex")
		seen[vertex_index] = true
		polygon.append(vertex_index)
	var polygon_points := PackedVector2Array()
	for vertex_index in polygon:
		polygon_points.append(vertices[vertex_index])
	var validity := _validate_tile_navigation_face(polygon_points, polygon_index)
	if validity.has("_error"):
		return validity
	return {"polygon": polygon}


func _validate_tile_navigation_face(points: PackedVector2Array, polygon_index: int) -> Dictionary:
	var winding := 0.0
	for point_index in points.size():
		var next_index := (point_index + 1) % points.size()
		var after_next_index := (point_index + 2) % points.size()
		var cross := (points[next_index] - points[point_index]).cross(
			points[after_next_index] - points[next_index]
		)
		if is_zero_approx(cross):
			return Errors.make(
				"INVALID_TILE_NAVIGATION",
				"polygons[%d] cannot contain collinear edges" % polygon_index
			)
		if is_zero_approx(winding):
			winding = sign(cross)
		elif sign(cross) != winding:
			return Errors.make(
				"INVALID_TILE_NAVIGATION",
				"polygons[%d] must be convex and ordered" % polygon_index
			)
	return {}


func _serialize_tile_collision_layers(tile_set: TileSet, tile_data: TileData) -> Array:
	var layers := []
	for layer_index in tile_set.get_physics_layers_count():
		layers.append({
			"index": layer_index,
			"collision_polygons": _serialize_tile_collision_polygons(tile_data, layer_index),
		})
	return layers


func _serialize_tile_collision_polygons(tile_data: TileData, physics_layer: int) -> Array:
	var polygons := []
	for polygon_index in tile_data.get_collision_polygons_count(physics_layer):
		polygons.append({
			"points": VariantCodec.serialize(
				tile_data.get_collision_polygon_points(physics_layer, polygon_index)
			),
			"one_way": tile_data.is_collision_polygon_one_way(physics_layer, polygon_index),
			"one_way_margin": tile_data.get_collision_polygon_one_way_margin(
				physics_layer, polygon_index
			),
		})
	return polygons


func _serialize_tile_navigation_layers(tile_set: TileSet, tile_data: TileData) -> Array:
	var layers := []
	for layer_index in tile_set.get_navigation_layers_count():
		layers.append({
			"index": layer_index,
			"navigation_polygon": _serialize_tile_navigation_polygon(
				tile_data.get_navigation_polygon(layer_index)
			),
		})
	return layers


func _serialize_tile_navigation_polygon(navigation_polygon: NavigationPolygon) -> Variant:
	if navigation_polygon == null:
		return null
	var polygons := []
	for polygon_index in navigation_polygon.get_polygon_count():
		polygons.append(VariantCodec.serialize(navigation_polygon.get_polygon(polygon_index)))
	return {
		"agent_radius": navigation_polygon.agent_radius,
		"vertices": VariantCodec.serialize(navigation_polygon.get_vertices()),
		"polygons": polygons,
	}


func _tile_set_layers_response(tile_map_layer: TileMapLayer, scene_root: Node) -> Dictionary:
	var response := _tile_map_layer_response(tile_map_layer, scene_root)
	var tile_set: TileSet = tile_map_layer.tile_set
	var physics_layers := []
	for index in mini(tile_set.get_physics_layers_count(), MAX_TILESET_LAYERS):
		physics_layers.append({
			"index": index,
			"layers": _mask_to_layer_numbers(tile_set.get_physics_layer_collision_layer(index)),
			"masks": _mask_to_layer_numbers(tile_set.get_physics_layer_collision_mask(index)),
			"priority": tile_set.get_physics_layer_collision_priority(index),
		})
	var navigation_layers := []
	for index in mini(tile_set.get_navigation_layers_count(), MAX_TILESET_LAYERS):
		navigation_layers.append({
			"index": index,
			"layers": _mask_to_layer_numbers(tile_set.get_navigation_layer_layers(index)),
		})
	var custom_data_layers := []
	for index in mini(tile_set.get_custom_data_layers_count(), MAX_TILESET_LAYERS):
		custom_data_layers.append({
			"index": index,
			"name": tile_set.get_custom_data_layer_name(index),
			"value_type": _custom_data_type_name(tile_set.get_custom_data_layer_type(index)),
		})
	var terrain_sets := []
	for terrain_set in mini(tile_set.get_terrain_sets_count(), MAX_TILESET_TERRAINS):
		var terrains := []
		for terrain in mini(tile_set.get_terrains_count(terrain_set), MAX_TILESET_TERRAINS):
			terrains.append({
				"index": terrain,
				"name": tile_set.get_terrain_name(terrain_set, terrain),
				"color": VariantCodec.serialize(tile_set.get_terrain_color(terrain_set, terrain)),
			})
		terrain_sets.append({
			"index": terrain_set,
			"mode": _terrain_mode_name(tile_set.get_terrain_set_mode(terrain_set)),
			"terrains": terrains,
			"terrain_total": tile_set.get_terrains_count(terrain_set),
		})
	response["physics_layers"] = physics_layers
	response["physics_layers_total"] = tile_set.get_physics_layers_count()
	response["navigation_layers"] = navigation_layers
	response["navigation_layers_total"] = tile_set.get_navigation_layers_count()
	response["custom_data_layers"] = custom_data_layers
	response["custom_data_layers_total"] = tile_set.get_custom_data_layers_count()
	response["terrain_sets"] = terrain_sets
	response["terrain_sets_total"] = tile_set.get_terrain_sets_count()
	return response


func _tile_data_response(tile_map_layer: TileMapLayer, scene_root: Node, tile_result: Dictionary) -> Dictionary:
	return {
		"path": ScenePath.from_node(tile_map_layer, scene_root),
		"type": tile_map_layer.get_class(),
		"source_id": tile_result["source_id"],
		"atlas_coords": VariantCodec.serialize(tile_result["atlas_coords"]),
		"alternative_tile": tile_result["alternative_tile"],
	}


func _resolve_tile_map_layer(params: Dictionary, require_writable: bool = true) -> Dictionary:
	var guarded := MutationGuard.require_scene(params, require_writable)
	if guarded.has("_error"):
		return guarded
	var scene_root: Node = guarded["scene_root"]
	var path := str(params.get("path", "")).strip_edges()
	if path.is_empty():
		return Errors.make("MISSING_PARAMETER", "path is required")
	var node := ScenePath.resolve(path, scene_root)
	if node == null:
		return Errors.make(
			"NODE_NOT_FOUND",
			"Node not found: %s" % path,
			false,
			"Use scene_get_hierarchy to refresh node paths."
		)
	if not node is TileMapLayer:
		return Errors.make(
			"TILE_MAP_LAYER_REQUIRED",
			"Node '%s' is %s, not TileMapLayer" % [node.name, node.get_class()],
			false,
			"Target a TileMapLayer node."
		)
	if require_writable and node != scene_root and node.owner != scene_root:
		return Errors.make(
			"PACKED_SCENE_BOUNDARY",
			"Cannot edit node '%s' because it belongs to an instanced scene" % node.name,
			false,
			"Edit the source PackedScene or target a locally owned node."
		)
	return {"tile_map_layer": node as TileMapLayer, "scene_root": scene_root}


func _tile_set_required(tile_map_layer: TileMapLayer) -> Dictionary:
	return Errors.make(
		"TILE_SET_NOT_ASSIGNED",
		"TileMapLayer '%s' has no TileSet resource" % tile_map_layer.name,
		false,
		"Call tile_set_create before editing tiles or cells."
	)


func _parse_page(params: Dictionary) -> Dictionary:
	var offset := int(params.get("offset", 0))
	var limit := int(params.get("limit", 100))
	if not _is_integral_number(params.get("offset", 0)) or offset < 0:
		return Errors.make("INVALID_PAGINATION", "offset must be a non-negative integer")
	if not _is_integral_number(params.get("limit", 100)) or limit < 1 or limit > MAX_PAGE_LIMIT:
		return Errors.make("INVALID_PAGINATION", "limit must be an integer from 1 to %d" % MAX_PAGE_LIMIT)
	return {"offset": offset, "limit": limit}


func _parse_tile_size(raw_value: Variant, label: String) -> Dictionary:
	var parsed := _parse_nonnegative_vector2i(raw_value, label)
	if parsed.has("_error"):
		return parsed
	var value: Vector2i = parsed["value"]
	if value.x < 1 or value.y < 1:
		return Errors.make("INVALID_TILESET_ATLAS", "%s.x and %s.y must be greater than zero" % [label, label])
	return parsed


func _parse_nonnegative_vector2i(raw_value: Variant, label: String) -> Dictionary:
	var decoded := VariantCodec.decode(raw_value, {"type": TYPE_VECTOR2I}, Vector2i.ZERO)
	if decoded.has("_error"):
		return Errors.make("INVALID_TILEMAP_COORDINATES", "%s must be a Vector2i object" % label)
	var value: Vector2i = decoded["value"]
	if value.x < 0 or value.y < 0:
		return Errors.make("INVALID_TILEMAP_COORDINATES", "%s must use non-negative coordinates" % label)
	return {"value": value}


func _parse_cell_coordinates(raw_coords: Variant) -> Dictionary:
	if not raw_coords is Array or raw_coords.is_empty() or raw_coords.size() > MAX_TILEMAP_CELLS:
		return Errors.make(
			"INVALID_TILEMAP_CELLS",
			"coords must contain between one and %d cell coordinates" % MAX_TILEMAP_CELLS
		)
	var coords: Array[Vector2i] = []
	var seen := {}
	for raw_coord in raw_coords:
		var decoded := VariantCodec.decode(raw_coord, {"type": TYPE_VECTOR2I}, Vector2i.ZERO)
		if decoded.has("_error"):
			return Errors.make("INVALID_TILEMAP_COORDINATES", "coords must contain Vector2i objects")
		var coord: Vector2i = decoded["value"]
		if seen.has(coord):
			return Errors.make("INVALID_TILEMAP_CELLS", "coords must not contain duplicates")
		seen[coord] = true
		coords.append(coord)
	return {"coords": coords}


func _parse_cells(raw_cells: Variant) -> Dictionary:
	if not raw_cells is Array or raw_cells.is_empty() or raw_cells.size() > MAX_TILEMAP_CELLS:
		return Errors.make(
			"INVALID_TILEMAP_CELLS",
			"cells must contain between one and %d entries" % MAX_TILEMAP_CELLS
		)
	var cells := []
	var seen := {}
	for raw_cell in raw_cells:
		if not raw_cell is Dictionary:
			return Errors.make("INVALID_TILEMAP_CELLS", "each cell must be an object")
		var required := ["coords", "source_id", "atlas_coords", "alternative_tile"]
		if raw_cell.keys().size() != required.size():
			return Errors.make("INVALID_TILEMAP_CELLS", "each cell must contain coords, source_id, atlas_coords, and alternative_tile")
		for name in required:
			if not raw_cell.has(name):
				return Errors.make("INVALID_TILEMAP_CELLS", "each cell must contain coords, source_id, atlas_coords, and alternative_tile")
		var coords_result := VariantCodec.decode(raw_cell["coords"], {"type": TYPE_VECTOR2I}, Vector2i.ZERO)
		if coords_result.has("_error"):
			return Errors.make("INVALID_TILEMAP_COORDINATES", "cells[].coords must be a Vector2i object")
		var atlas_coords_result := _parse_nonnegative_vector2i(raw_cell["atlas_coords"], "cells[].atlas_coords")
		if atlas_coords_result.has("_error"):
			return atlas_coords_result
		if not _is_integral_number(raw_cell["source_id"]) or int(raw_cell["source_id"]) < 0:
			return Errors.make("INVALID_TILEMAP_CELLS", "cells[].source_id must be a non-negative integer")
		if not _is_integral_number(raw_cell["alternative_tile"]) or int(raw_cell["alternative_tile"]) < 0:
			return Errors.make("INVALID_TILEMAP_CELLS", "cells[].alternative_tile must be a non-negative integer")
		var coords: Vector2i = coords_result["value"]
		if seen.has(coords):
			return Errors.make("INVALID_TILEMAP_CELLS", "cells must not contain duplicate coords")
		seen[coords] = true
		cells.append({
			"coords": coords,
			"source_id": int(raw_cell["source_id"]),
			"atlas_coords": atlas_coords_result["value"],
			"alternative_tile": int(raw_cell["alternative_tile"]),
		})
	return {"cells": cells}


func _parse_source_id(params: Dictionary, tile_set: TileSet) -> Dictionary:
	if not params.has("source_id") or params["source_id"] == null:
		return {"source_id": tile_set.get_next_source_id()}
	if not _is_integral_number(params["source_id"]) or int(params["source_id"]) < 0:
		return Errors.make("INVALID_TILESET_SOURCE", "source_id must be a non-negative integer")
	var source_id := int(params["source_id"])
	if tile_set.has_source(source_id):
		return Errors.make("TILESET_SOURCE_ALREADY_EXISTS", "source_id is already present in the TileSet")
	return {"source_id": source_id}


func _resolve_atlas_source(params: Dictionary, tile_set: TileSet) -> Dictionary:
	if not params.has("source_id") or not _is_integral_number(params["source_id"]):
		return Errors.make("MISSING_PARAMETER", "source_id must be a non-negative integer")
	var source_id := int(params["source_id"])
	if source_id < 0 or not tile_set.has_source(source_id):
		return Errors.make("TILESET_SOURCE_NOT_FOUND", "source_id does not identify a TileSet source")
	var source := tile_set.get_source(source_id)
	if not source is TileSetAtlasSource:
		return Errors.make(
			"TILESET_ATLAS_SOURCE_REQUIRED",
			"source_id does not identify a TileSetAtlasSource",
			false,
			"Create an atlas source with tile_set_atlas_source_create first."
		)
	return {"source_id": source_id, "atlas_source": source as TileSetAtlasSource}


func _load_atlas_texture(raw_path: Variant) -> Dictionary:
	if not raw_path is String or raw_path.strip_edges().is_empty():
		return Errors.make("MISSING_PARAMETER", "texture_path must be a non-empty res:// Texture2D path")
	var texture_path: String = raw_path.strip_edges()
	if not texture_path.begins_with("res://"):
		return Errors.make("INVALID_TEXTURE_PATH", "texture_path must remain inside the Godot project res:// directory")
	var texture := ResourceLoader.load(texture_path)
	if not texture is Texture2D:
		return Errors.make(
			"TEXTURE_NOT_FOUND",
			"texture_path does not load a Texture2D resource: %s" % texture_path,
			false,
			"Import the texture into the project and pass its res:// path."
		)
	return {"texture": texture as Texture2D}


func _duplicate_tile_set(tile_set: TileSet) -> Dictionary:
	var duplicate_resource := tile_set.duplicate(true)
	if not duplicate_resource is TileSet:
		return Errors.make("TILE_SET_COPY_FAILED", "Godot failed to duplicate the TileSet resource")
	return {"tile_set": duplicate_resource as TileSet}


func _validate_cells_against_tile_set(cells: Array, tile_set: TileSet) -> Dictionary:
	for cell in cells:
		var source_id: int = cell["source_id"]
		if not tile_set.has_source(source_id):
			return Errors.make("TILESET_SOURCE_NOT_FOUND", "cells[].source_id is not present in this TileSet")
		var source := tile_set.get_source(source_id)
		if not source is TileSetAtlasSource:
			return Errors.make(
				"UNSUPPORTED_TILESET_SOURCE",
				"cells currently support TileSetAtlasSource entries only"
			)
		var atlas_source := source as TileSetAtlasSource
		var atlas_coords: Vector2i = cell["atlas_coords"]
		if not atlas_source.has_tile(atlas_coords):
			return Errors.make("ATLAS_TILE_NOT_FOUND", "cells[].atlas_coords is not a tile in the selected source")
		if not atlas_source.has_alternative_tile(atlas_coords, cell["alternative_tile"]):
			return Errors.make(
				"ATLAS_ALTERNATIVE_NOT_FOUND",
				"cells[].alternative_tile is not defined for the selected atlas tile"
			)
	return {}


func _commit_tile_set(
	tile_map_layer: TileMapLayer,
	scene_root: Node,
	replacement: TileSet,
	action_name: String
) -> void:
	var current: TileSet = tile_map_layer.tile_set
	_undo_redo.create_action("Godot 2D MCP: %s" % action_name, UndoRedo.MERGE_DISABLE, scene_root, true)
	_undo_redo.add_do_property(tile_map_layer, "tile_set", replacement)
	_undo_redo.add_do_reference(replacement)
	_undo_redo.add_undo_property(tile_map_layer, "tile_set", current)
	if current != null:
		_undo_redo.add_undo_reference(current)
	_undo_redo.commit_action()


func _add_undo_cell_change(tile_map_layer: TileMapLayer, previous: Dictionary) -> void:
	if int(previous["source_id"]) < 0:
		_undo_redo.add_undo_method(tile_map_layer, "erase_cell", previous["coords"])
		return
	_undo_redo.add_undo_method(
		tile_map_layer,
		"set_cell",
		previous["coords"],
		previous["source_id"],
		previous["atlas_coords"],
		previous["alternative_tile"]
	)


func _tile_map_layer_response(tile_map_layer: TileMapLayer, scene_root: Node) -> Dictionary:
	return {
		"path": ScenePath.from_node(tile_map_layer, scene_root),
		"type": tile_map_layer.get_class(),
		"used_cells": tile_map_layer.get_used_cells().size(),
		"used_rect": VariantCodec.serialize(tile_map_layer.get_used_rect()),
		"tile_set": _tile_set_summary(tile_map_layer.tile_set),
	}


func _tile_set_response(
	tile_map_layer: TileMapLayer,
	scene_root: Node,
	offset: int = 0,
	limit: int = 100
) -> Dictionary:
	var response := _tile_map_layer_response(tile_map_layer, scene_root)
	var tile_set: TileSet = tile_map_layer.tile_set
	if tile_set == null:
		response["sources"] = []
		response["total"] = 0
		response["offset"] = offset
		response["limit"] = limit
		response["next_offset"] = null
		return response
	var end := mini(offset + limit, tile_set.get_source_count())
	var sources := []
	for index in range(offset, end):
		var source_id := tile_set.get_source_id(index)
		sources.append(_serialize_tile_set_source(source_id, tile_set.get_source(source_id)))
	response["sources"] = sources
	response["total"] = tile_set.get_source_count()
	response["offset"] = offset
	response["limit"] = limit
	response["next_offset"] = end if end < tile_set.get_source_count() else null
	return response


func _tile_set_summary(tile_set: TileSet) -> Variant:
	if tile_set == null:
		return null
	return {
		"resource_type": tile_set.get_class(),
		"resource_path": tile_set.resource_path,
		"resource_name": tile_set.resource_name,
		"built_in": tile_set.is_built_in(),
		"tile_size": VariantCodec.serialize(tile_set.tile_size),
		"source_count": tile_set.get_source_count(),
	}


func _serialize_tile_set_source(source_id: int, source: TileSetSource) -> Dictionary:
	var result := {"source_id": source_id, "type": source.get_class()}
	if source is TileSetAtlasSource:
		var atlas_source := source as TileSetAtlasSource
		var texture: Texture2D = atlas_source.texture
		result["texture_path"] = texture.resource_path if texture != null else ""
		result["texture_region_size"] = VariantCodec.serialize(atlas_source.texture_region_size)
		result["margins"] = VariantCodec.serialize(atlas_source.margins)
		result["separation"] = VariantCodec.serialize(atlas_source.separation)
		result["atlas_grid_size"] = VariantCodec.serialize(atlas_source.get_atlas_grid_size())
		result["tiles_count"] = atlas_source.get_tiles_count()
	return result


func _serialize_cell(tile_map_layer: TileMapLayer, coords: Vector2i) -> Dictionary:
	return _serialize_cell_data(coords, _read_cell(tile_map_layer, coords))


func _read_cell(tile_map_layer: TileMapLayer, coords: Vector2i) -> Dictionary:
	return {
		"coords": coords,
		"source_id": tile_map_layer.get_cell_source_id(coords),
		"atlas_coords": tile_map_layer.get_cell_atlas_coords(coords),
		"alternative_tile": tile_map_layer.get_cell_alternative_tile(coords),
	}


func _serialize_cell_data(coords: Vector2i, cell: Dictionary) -> Dictionary:
	return {
		"coords": VariantCodec.serialize(coords),
		"source_id": cell["source_id"],
		"atlas_coords": VariantCodec.serialize(cell["atlas_coords"]),
		"alternative_tile": cell["alternative_tile"],
	}


func _cells_match(first: Dictionary, second: Dictionary) -> bool:
	return (
		first["source_id"] == second["source_id"]
		and first["atlas_coords"] == second["atlas_coords"]
		and first["alternative_tile"] == second["alternative_tile"]
	)


func _is_integral_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and is_equal_approx(float(value), round(float(value)))

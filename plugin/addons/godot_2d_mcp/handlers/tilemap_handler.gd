@tool
extends RefCounted

const Errors := preload("res://addons/godot_2d_mcp/utils/errors.gd")
const MutationGuard := preload("res://addons/godot_2d_mcp/utils/mutation_guard.gd")
const ScenePath := preload("res://addons/godot_2d_mcp/utils/scene_path.gd")
const VariantCodec := preload("res://addons/godot_2d_mcp/utils/variant_codec.gd")

const MAX_TILEMAP_CELLS := 512
const MAX_ATLAS_TILE_SIZE := 64
const MAX_PAGE_LIMIT := 512

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

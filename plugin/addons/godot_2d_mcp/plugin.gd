@tool
extends EditorPlugin

const PLUGIN_VERSION := "0.20.0"
const WS_PORT_SETTING := "godot_2d_mcp/server/ws_port"

const ConnectionScript := preload("res://addons/godot_2d_mcp/transport/connection.gd")
const DispatcherScript := preload("res://addons/godot_2d_mcp/dispatcher.gd")
const DockScript := preload("res://addons/godot_2d_mcp/ui/mcp_dock.gd")
const EditorHandlerScript := preload("res://addons/godot_2d_mcp/handlers/editor_handler.gd")
const SceneHandlerScript := preload("res://addons/godot_2d_mcp/handlers/scene_handler.gd")
const NodeHandlerScript := preload("res://addons/godot_2d_mcp/handlers/node_handler.gd")
const ClassHandlerScript := preload("res://addons/godot_2d_mcp/handlers/class_handler.gd")
const SignalHandlerScript := preload("res://addons/godot_2d_mcp/handlers/signal_handler.gd")
const AnimationHandlerScript := preload("res://addons/godot_2d_mcp/handlers/animation_handler.gd")
const UiHandlerScript := preload("res://addons/godot_2d_mcp/handlers/ui_handler.gd")
const ThemeHandlerScript := preload("res://addons/godot_2d_mcp/handlers/theme_handler.gd")
const PhysicsHandlerScript := preload("res://addons/godot_2d_mcp/handlers/physics_handler.gd")
const TileMapHandlerScript := preload("res://addons/godot_2d_mcp/handlers/tilemap_handler.gd")
const LightingHandlerScript := preload("res://addons/godot_2d_mcp/handlers/lighting_handler.gd")
const ViewportHandlerScript := preload("res://addons/godot_2d_mcp/handlers/viewport_handler.gd")
const PathHandlerScript := preload("res://addons/godot_2d_mcp/handlers/path_handler.gd")
const SkeletonHandlerScript := preload("res://addons/godot_2d_mcp/handlers/skeleton_handler.gd")

var _connection: Node
var _dispatcher: RefCounted
var _dock: Control
var _handlers: Array[RefCounted] = []


func _enter_tree() -> void:
	var ws_port := _ensure_ws_port_setting()
	_dispatcher = DispatcherScript.new()
	_register_handlers()

	_connection = ConnectionScript.new()
	_connection.name = "Godot2DMcpConnection"
	_connection.dispatcher = _dispatcher
	_connection.plugin_version = PLUGIN_VERSION
	_connection.ws_port = ws_port
	add_child(_connection)

	_dock = DockScript.new()
	_dock.setup(_connection, ws_port)
	add_control_to_dock(DOCK_SLOT_RIGHT_BL, _dock)


func _exit_tree() -> void:
	if _dock != null:
		remove_control_from_docks(_dock)
		_dock.free()
		_dock = null
	if _connection != null:
		_connection.teardown()
		_connection.free()
		_connection = null
	if _dispatcher != null:
		_dispatcher.clear()
		_dispatcher = null
	_handlers.clear()


func _register_handlers() -> void:
	var editor_handler: RefCounted = EditorHandlerScript.new()
	var scene_handler: RefCounted = SceneHandlerScript.new(get_undo_redo())
	var node_handler: RefCounted = NodeHandlerScript.new(get_undo_redo())
	var class_handler: RefCounted = ClassHandlerScript.new()
	var signal_handler: RefCounted = SignalHandlerScript.new(get_undo_redo())
	var animation_handler: RefCounted = AnimationHandlerScript.new(get_undo_redo())
	var ui_handler: RefCounted = UiHandlerScript.new(get_undo_redo())
	var theme_handler: RefCounted = ThemeHandlerScript.new(get_undo_redo())
	var physics_handler: RefCounted = PhysicsHandlerScript.new(get_undo_redo())
	var tile_map_handler: RefCounted = TileMapHandlerScript.new(get_undo_redo())
	var lighting_handler: RefCounted = LightingHandlerScript.new(get_undo_redo())
	var viewport_handler: RefCounted = ViewportHandlerScript.new(get_undo_redo())
	var path_handler: RefCounted = PathHandlerScript.new(get_undo_redo())
	var skeleton_handler: RefCounted = SkeletonHandlerScript.new(get_undo_redo())
	_handlers.assign([
		editor_handler, scene_handler, node_handler, class_handler, signal_handler, animation_handler,
		ui_handler, theme_handler, physics_handler, tile_map_handler, lighting_handler, viewport_handler,
		path_handler, skeleton_handler
	])

	_dispatcher.register("editor_get_state", editor_handler.get_state)
	_dispatcher.register("scene_get_hierarchy", scene_handler.get_hierarchy)
	_dispatcher.register("scene_save", scene_handler.save_scene)
	_dispatcher.register("scene_undo", scene_handler.undo_scene)
	_dispatcher.register("scene_redo", scene_handler.redo_scene)
	_dispatcher.register("node_get_properties", node_handler.get_properties)
	_dispatcher.register("node_get_signals", signal_handler.get_signals)
	_dispatcher.register("animation_list", animation_handler.list_animations)
	_dispatcher.register("animation_get", animation_handler.get_animation)
	_dispatcher.register("control_get_layout", ui_handler.get_layout)
	_dispatcher.register("control_get_styleboxes", ui_handler.get_styleboxes)
	_dispatcher.register("control_theme_get", theme_handler.get_theme)
	_dispatcher.register("collision_shape_get", physics_handler.get_collision_shape)
	_dispatcher.register("collision_object_get_layers", physics_handler.get_collision_layers)
	_dispatcher.register("area_2d_get", physics_handler.get_area)
	_dispatcher.register("physics_body_2d_get", physics_handler.get_physics_body)
	_dispatcher.register("joint_2d_get", physics_handler.get_joint)
	_dispatcher.register("ray_cast_2d_get", physics_handler.get_ray_cast)
	_dispatcher.register("shape_cast_2d_get", physics_handler.get_shape_cast)
	_dispatcher.register("navigation_2d_get", physics_handler.get_navigation_node)
	_dispatcher.register("navigation_polygon_get", physics_handler.get_navigation_polygon)
	_dispatcher.register("camera_2d_get", viewport_handler.get_camera_2d)
	_dispatcher.register("parallax_2d_get", viewport_handler.get_parallax_2d)
	_dispatcher.register("canvas_layer_get", viewport_handler.get_canvas_layer)
	_dispatcher.register("path_2d_get", path_handler.get_path_2d)
	_dispatcher.register("skeleton_2d_get", skeleton_handler.get_skeleton_2d)
	_dispatcher.register("bone_2d_get", skeleton_handler.get_bone_2d)
	_dispatcher.register("light_2d_get", lighting_handler.get_light_2d)
	_dispatcher.register("light_occluder_2d_get", lighting_handler.get_light_occluder_2d)
	_dispatcher.register("tile_map_layer_get", tile_map_handler.get_tile_map_layer)
	_dispatcher.register("tile_map_layer_cells_get", tile_map_handler.get_tile_map_layer_cells)
	_dispatcher.register("tile_set_get", tile_map_handler.get_tile_set)
	_dispatcher.register("tile_set_layers_get", tile_map_handler.get_tile_set_layers)
	_dispatcher.register("tile_set_atlas_tile_get", tile_map_handler.get_tile_set_atlas_tile)
	_dispatcher.register("node_create", node_handler.create_node)
	_dispatcher.register("node_set_properties", node_handler.set_properties)
	_dispatcher.register("node_delete", node_handler.delete_node)
	_dispatcher.register("node_rename", node_handler.rename_node)
	_dispatcher.register("node_duplicate", node_handler.duplicate_node)
	_dispatcher.register("node_reparent", node_handler.reparent_node)
	_dispatcher.register("node_move", node_handler.move_node)
	_dispatcher.register("signal_connect", signal_handler.connect_signal)
	_dispatcher.register("signal_disconnect", signal_handler.disconnect_signal)
	_dispatcher.register("animation_create", animation_handler.create_animation)
	_dispatcher.register("animation_delete", animation_handler.delete_animation)
	_dispatcher.register("animation_track_upsert", animation_handler.upsert_value_track)
	_dispatcher.register("animation_track_delete", animation_handler.delete_track)
	_dispatcher.register("animation_key_upsert", animation_handler.upsert_key)
	_dispatcher.register("animation_key_delete", animation_handler.delete_key)
	_dispatcher.register("control_set_layout", ui_handler.set_layout)
	_dispatcher.register("control_set_layout_preset", ui_handler.set_layout_preset)
	_dispatcher.register("control_stylebox_flat_upsert", ui_handler.upsert_stylebox_flat)
	_dispatcher.register("control_stylebox_override_clear", ui_handler.clear_stylebox_override)
	_dispatcher.register("control_theme_create", theme_handler.create_theme)
	_dispatcher.register("control_theme_assign", theme_handler.assign_theme)
	_dispatcher.register("control_theme_defaults_set", theme_handler.set_defaults)
	_dispatcher.register("control_theme_defaults_clear", theme_handler.clear_defaults)
	_dispatcher.register("control_theme_item_upsert", theme_handler.upsert_item)
	_dispatcher.register("control_theme_item_clear", theme_handler.clear_item)
	_dispatcher.register("collision_shape_set", physics_handler.set_collision_shape)
	_dispatcher.register("collision_shape_clear", physics_handler.clear_collision_shape)
	_dispatcher.register("collision_object_set_layers", physics_handler.set_collision_layers)
	_dispatcher.register("area_2d_set", physics_handler.set_area)
	_dispatcher.register("physics_body_2d_set", physics_handler.set_physics_body)
	_dispatcher.register("joint_2d_set", physics_handler.set_joint)
	_dispatcher.register("ray_cast_2d_set", physics_handler.set_ray_cast)
	_dispatcher.register("shape_cast_2d_set", physics_handler.set_shape_cast)
	_dispatcher.register("shape_cast_2d_shape_clear", physics_handler.clear_shape_cast_shape)
	_dispatcher.register("navigation_2d_set", physics_handler.set_navigation_node)
	_dispatcher.register("navigation_polygon_create", physics_handler.create_navigation_polygon)
	_dispatcher.register("navigation_polygon_geometry_set", physics_handler.set_navigation_polygon_geometry)
	_dispatcher.register("navigation_polygon_outline_set", physics_handler.set_navigation_polygon_outline)
	_dispatcher.register("navigation_polygon_outline_remove", physics_handler.remove_navigation_polygon_outline)
	_dispatcher.register("navigation_polygon_make_from_outlines", physics_handler.make_navigation_polygon_from_outlines)
	_dispatcher.register("navigation_polygon_clear", physics_handler.clear_navigation_polygon)
	_dispatcher.register("camera_2d_set", viewport_handler.set_camera_2d)
	_dispatcher.register("parallax_2d_set", viewport_handler.set_parallax_2d)
	_dispatcher.register("canvas_layer_set", viewport_handler.set_canvas_layer)
	_dispatcher.register("path_2d_curve_set", path_handler.set_path_curve)
	_dispatcher.register("path_2d_curve_point_insert", path_handler.insert_path_curve_point)
	_dispatcher.register("path_2d_curve_point_set", path_handler.set_path_curve_point)
	_dispatcher.register("path_2d_curve_point_remove", path_handler.remove_path_curve_point)
	_dispatcher.register("path_2d_curve_clear", path_handler.clear_path_curve)
	_dispatcher.register("skeleton_2d_bone_create", skeleton_handler.create_skeleton_2d_bone)
	_dispatcher.register("bone_2d_set", skeleton_handler.set_bone_2d)
	_dispatcher.register("skeleton_2d_reset_to_rest", skeleton_handler.reset_skeleton_2d_to_rest)
	_dispatcher.register("skeleton_2d_make_rest_from_current", skeleton_handler.make_skeleton_2d_rest_from_current)
	_dispatcher.register("light_2d_set", lighting_handler.set_light_2d)
	_dispatcher.register("light_occluder_2d_set", lighting_handler.set_light_occluder_2d)
	_dispatcher.register("tile_set_create", tile_map_handler.create_tile_set)
	_dispatcher.register("tile_set_clear", tile_map_handler.clear_tile_set)
	_dispatcher.register("tile_set_atlas_source_create", tile_map_handler.create_tile_set_atlas_source)
	_dispatcher.register("tile_set_atlas_tile_create", tile_map_handler.create_tile_set_atlas_tile)
	_dispatcher.register("tile_map_layer_cells_set", tile_map_handler.set_tile_map_layer_cells)
	_dispatcher.register("tile_map_layer_cells_clear", tile_map_handler.clear_tile_map_layer_cells)
	_dispatcher.register("tile_set_physics_layer_create", tile_map_handler.create_tile_set_physics_layer)
	_dispatcher.register("tile_set_navigation_layer_create", tile_map_handler.create_tile_set_navigation_layer)
	_dispatcher.register("tile_set_occlusion_layer_create", tile_map_handler.create_tile_set_occlusion_layer)
	_dispatcher.register("tile_set_custom_data_layer_create", tile_map_handler.create_tile_set_custom_data_layer)
	_dispatcher.register("tile_set_terrain_set_create", tile_map_handler.create_tile_set_terrain_set)
	_dispatcher.register("tile_set_terrain_create", tile_map_handler.create_tile_set_terrain)
	_dispatcher.register("tile_set_atlas_alternative_create", tile_map_handler.create_tile_set_atlas_alternative)
	_dispatcher.register("tile_set_atlas_tile_terrain_set", tile_map_handler.set_tile_set_atlas_tile_terrain)
	_dispatcher.register("tile_set_atlas_tile_custom_data_set", tile_map_handler.set_tile_set_atlas_tile_custom_data)
	_dispatcher.register("tile_set_atlas_tile_collision_set", tile_map_handler.set_tile_set_atlas_tile_collision)
	_dispatcher.register("tile_set_atlas_tile_navigation_set", tile_map_handler.set_tile_set_atlas_tile_navigation)
	_dispatcher.register("tile_set_atlas_tile_occlusion_set", tile_map_handler.set_tile_set_atlas_tile_occlusion)
	_dispatcher.register("class_search", class_handler.search)


func _ensure_ws_port_setting() -> int:
	var environment_port := OS.get_environment("GODOT_2D_MCP_WS_PORT")
	if environment_port.is_valid_int():
		var parsed_port := int(environment_port)
		if parsed_port >= 1024 and parsed_port <= 65535:
			return parsed_port
	var settings := EditorInterface.get_editor_settings()
	if not settings.has_setting(WS_PORT_SETTING):
		settings.set_setting(WS_PORT_SETTING, 9500)
	settings.add_property_info(
		{
			"name": WS_PORT_SETTING,
			"type": TYPE_INT,
			"hint": PROPERTY_HINT_RANGE,
			"hint_string": "1024,65535,1",
		}
	)
	return int(settings.get_setting(WS_PORT_SETTING))

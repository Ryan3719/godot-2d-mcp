from __future__ import annotations

import pytest

from godot_2d_mcp.server import create_application


@pytest.mark.asyncio
async def test_tool_catalog_exposes_read_and_write_annotations() -> None:
    app = create_application(ws_port=19999)

    tools = await app.mcp.list_tools()

    assert [tool.name for tool in tools] == [
        "session_list",
        "session_activate",
        "editor_get_state",
        "scene_get_hierarchy",
        "class_search",
        "node_get_properties",
        "node_get_signals",
        "animation_list",
        "animation_get",
        "control_get_layout",
        "control_get_styleboxes",
        "control_theme_get",
        "collision_shape_get",
        "collision_object_get_layers",
        "area_2d_get",
        "physics_body_2d_get",
        "joint_2d_get",
        "ray_cast_2d_get",
        "shape_cast_2d_get",
        "navigation_2d_get",
        "navigation_polygon_get",
        "camera_2d_get",
        "parallax_2d_get",
        "canvas_layer_get",
        "path_2d_get",
        "skeleton_2d_get",
        "bone_2d_get",
        "audio_stream_player_2d_get",
        "gpu_particles_2d_get",
        "cpu_particles_2d_get",
        "cpu_particles_2d_curve_get",
        "cpu_particles_2d_gradient_get",
        "particle_process_material_2d_get",
        "particle_process_material_2d_curve_get",
        "particle_process_material_2d_gradient_get",
        "canvas_item_material_get",
        "light_2d_get",
        "light_occluder_2d_get",
        "tile_map_layer_get",
        "tile_map_layer_cells_get",
        "tile_set_get",
        "tile_set_layers_get",
        "tile_set_atlas_tile_get",
        "node_create",
        "node_set_properties",
        "node_delete",
        "node_rename",
        "node_duplicate",
        "node_reparent",
        "node_move",
        "signal_connect",
        "signal_disconnect",
        "animation_create",
        "animation_delete",
        "animation_track_upsert",
        "animation_track_delete",
        "animation_key_upsert",
        "animation_key_delete",
        "control_set_layout",
        "control_set_layout_preset",
        "control_stylebox_flat_upsert",
        "control_stylebox_override_clear",
        "control_theme_create",
        "control_theme_assign",
        "control_theme_defaults_set",
        "control_theme_defaults_clear",
        "control_theme_item_upsert",
        "control_theme_item_clear",
        "collision_shape_set",
        "collision_shape_clear",
        "collision_object_set_layers",
        "area_2d_set",
        "physics_body_2d_set",
        "joint_2d_set",
        "ray_cast_2d_set",
        "shape_cast_2d_set",
        "shape_cast_2d_shape_clear",
        "navigation_2d_set",
        "navigation_polygon_create",
        "navigation_polygon_geometry_set",
        "navigation_polygon_outline_set",
        "navigation_polygon_outline_remove",
        "navigation_polygon_make_from_outlines",
        "navigation_polygon_clear",
        "camera_2d_set",
        "parallax_2d_set",
        "canvas_layer_set",
        "path_2d_curve_set",
        "path_2d_curve_point_insert",
        "path_2d_curve_point_set",
        "path_2d_curve_point_remove",
        "path_2d_curve_clear",
        "skeleton_2d_bone_create",
        "bone_2d_set",
        "skeleton_2d_reset_to_rest",
        "skeleton_2d_make_rest_from_current",
        "audio_stream_player_2d_set",
        "gpu_particles_2d_set",
        "cpu_particles_2d_set",
        "cpu_particles_2d_curve_bind",
        "cpu_particles_2d_curve_set",
        "cpu_particles_2d_curve_clear",
        "cpu_particles_2d_gradient_bind",
        "cpu_particles_2d_gradient_set",
        "cpu_particles_2d_gradient_clear",
        "particle_process_material_2d_create",
        "particle_process_material_2d_set",
        "particle_process_material_2d_curve_bind",
        "particle_process_material_2d_curve_set",
        "particle_process_material_2d_curve_clear",
        "particle_process_material_2d_gradient_bind",
        "particle_process_material_2d_gradient_set",
        "particle_process_material_2d_gradient_clear",
        "canvas_item_material_create",
        "canvas_item_material_bind",
        "canvas_item_material_set",
        "canvas_item_material_clear",
        "light_2d_set",
        "light_occluder_2d_set",
        "tile_set_create",
        "tile_set_clear",
        "tile_set_atlas_source_create",
        "tile_set_atlas_tile_create",
        "tile_set_physics_layer_create",
        "tile_set_navigation_layer_create",
        "tile_set_occlusion_layer_create",
        "tile_set_custom_data_layer_create",
        "tile_set_terrain_set_create",
        "tile_set_terrain_create",
        "tile_set_atlas_alternative_create",
        "tile_set_atlas_tile_terrain_set",
        "tile_set_atlas_tile_custom_data_set",
        "tile_set_atlas_tile_collision_set",
        "tile_set_atlas_tile_navigation_set",
        "tile_set_atlas_tile_occlusion_set",
        "tile_map_layer_cells_set",
        "tile_map_layer_cells_clear",
        "scene_save",
        "scene_undo",
        "scene_redo",
    ]
    assert all(tool.annotations is not None for tool in tools)
    annotations = {tool.name: tool.annotations for tool in tools}
    assert annotations["node_get_properties"].readOnlyHint is True
    assert annotations["node_get_signals"].readOnlyHint is True
    assert annotations["animation_list"].readOnlyHint is True
    assert annotations["animation_get"].readOnlyHint is True
    assert annotations["control_get_layout"].readOnlyHint is True
    assert annotations["control_get_styleboxes"].readOnlyHint is True
    assert annotations["control_theme_get"].readOnlyHint is True
    assert annotations["collision_shape_get"].readOnlyHint is True
    assert annotations["collision_object_get_layers"].readOnlyHint is True
    assert annotations["area_2d_get"].readOnlyHint is True
    assert annotations["physics_body_2d_get"].readOnlyHint is True
    assert annotations["joint_2d_get"].readOnlyHint is True
    assert annotations["ray_cast_2d_get"].readOnlyHint is True
    assert annotations["shape_cast_2d_get"].readOnlyHint is True
    assert annotations["navigation_2d_get"].readOnlyHint is True
    assert annotations["navigation_polygon_get"].readOnlyHint is True
    assert annotations["camera_2d_get"].readOnlyHint is True
    assert annotations["parallax_2d_get"].readOnlyHint is True
    assert annotations["canvas_layer_get"].readOnlyHint is True
    assert annotations["path_2d_get"].readOnlyHint is True
    assert annotations["skeleton_2d_get"].readOnlyHint is True
    assert annotations["bone_2d_get"].readOnlyHint is True
    assert annotations["audio_stream_player_2d_get"].readOnlyHint is True
    assert annotations["gpu_particles_2d_get"].readOnlyHint is True
    assert annotations["cpu_particles_2d_get"].readOnlyHint is True
    assert annotations["cpu_particles_2d_curve_get"].readOnlyHint is True
    assert annotations["cpu_particles_2d_gradient_get"].readOnlyHint is True
    assert annotations["particle_process_material_2d_get"].readOnlyHint is True
    assert annotations["particle_process_material_2d_curve_get"].readOnlyHint is True
    assert annotations["particle_process_material_2d_gradient_get"].readOnlyHint is True
    assert annotations["canvas_item_material_get"].readOnlyHint is True
    assert annotations["light_2d_get"].readOnlyHint is True
    assert annotations["light_occluder_2d_get"].readOnlyHint is True
    assert annotations["tile_map_layer_get"].readOnlyHint is True
    assert annotations["tile_map_layer_cells_get"].readOnlyHint is True
    assert annotations["tile_set_get"].readOnlyHint is True
    assert annotations["tile_set_layers_get"].readOnlyHint is True
    assert annotations["tile_set_atlas_tile_get"].readOnlyHint is True
    assert annotations["node_create"].readOnlyHint is False
    assert annotations["node_delete"].destructiveHint is True
    assert annotations["node_rename"].destructiveHint is False
    assert annotations["node_duplicate"].readOnlyHint is False
    assert annotations["node_reparent"].readOnlyHint is False
    assert annotations["node_move"].readOnlyHint is False
    assert annotations["signal_connect"].readOnlyHint is False
    assert annotations["signal_disconnect"].readOnlyHint is False
    assert annotations["animation_create"].readOnlyHint is False
    assert annotations["animation_delete"].destructiveHint is True
    assert annotations["animation_track_upsert"].readOnlyHint is False
    assert annotations["animation_track_delete"].destructiveHint is True
    assert annotations["animation_key_upsert"].readOnlyHint is False
    assert annotations["animation_key_delete"].destructiveHint is True
    assert annotations["control_set_layout"].readOnlyHint is False
    assert annotations["control_set_layout_preset"].readOnlyHint is False
    assert annotations["control_stylebox_flat_upsert"].readOnlyHint is False
    assert annotations["control_stylebox_override_clear"].destructiveHint is True
    assert annotations["control_theme_create"].readOnlyHint is False
    assert annotations["control_theme_assign"].readOnlyHint is False
    assert annotations["control_theme_defaults_set"].readOnlyHint is False
    assert annotations["control_theme_defaults_clear"].destructiveHint is True
    assert annotations["control_theme_item_upsert"].readOnlyHint is False
    assert annotations["control_theme_item_clear"].destructiveHint is True
    assert annotations["collision_shape_set"].readOnlyHint is False
    assert annotations["collision_shape_clear"].destructiveHint is True
    assert annotations["collision_object_set_layers"].readOnlyHint is False
    assert annotations["area_2d_set"].readOnlyHint is False
    assert annotations["physics_body_2d_set"].readOnlyHint is False
    assert annotations["joint_2d_set"].readOnlyHint is False
    assert annotations["ray_cast_2d_set"].readOnlyHint is False
    assert annotations["shape_cast_2d_set"].readOnlyHint is False
    assert annotations["shape_cast_2d_shape_clear"].destructiveHint is True
    assert annotations["navigation_2d_set"].readOnlyHint is False
    assert annotations["navigation_polygon_create"].readOnlyHint is False
    assert annotations["navigation_polygon_geometry_set"].readOnlyHint is False
    assert annotations["navigation_polygon_outline_set"].readOnlyHint is False
    assert annotations["navigation_polygon_outline_remove"].destructiveHint is True
    assert annotations["navigation_polygon_make_from_outlines"].readOnlyHint is False
    assert annotations["navigation_polygon_clear"].destructiveHint is True
    assert annotations["camera_2d_set"].readOnlyHint is False
    assert annotations["parallax_2d_set"].readOnlyHint is False
    assert annotations["canvas_layer_set"].readOnlyHint is False
    assert annotations["path_2d_curve_set"].readOnlyHint is False
    assert annotations["path_2d_curve_point_insert"].readOnlyHint is False
    assert annotations["path_2d_curve_point_set"].readOnlyHint is False
    assert annotations["path_2d_curve_point_remove"].destructiveHint is True
    assert annotations["path_2d_curve_clear"].destructiveHint is True
    assert annotations["skeleton_2d_bone_create"].readOnlyHint is False
    assert annotations["bone_2d_set"].readOnlyHint is False
    assert annotations["skeleton_2d_reset_to_rest"].readOnlyHint is False
    assert annotations["skeleton_2d_make_rest_from_current"].destructiveHint is True
    assert annotations["audio_stream_player_2d_set"].readOnlyHint is False
    assert annotations["gpu_particles_2d_set"].readOnlyHint is False
    assert annotations["cpu_particles_2d_set"].readOnlyHint is False
    assert annotations["cpu_particles_2d_curve_bind"].readOnlyHint is False
    assert annotations["cpu_particles_2d_curve_set"].readOnlyHint is False
    assert annotations["cpu_particles_2d_curve_clear"].destructiveHint is True
    assert annotations["cpu_particles_2d_gradient_bind"].readOnlyHint is False
    assert annotations["cpu_particles_2d_gradient_set"].readOnlyHint is False
    assert annotations["cpu_particles_2d_gradient_clear"].destructiveHint is True
    assert annotations["particle_process_material_2d_create"].destructiveHint is True
    assert annotations["particle_process_material_2d_set"].readOnlyHint is False
    assert annotations["particle_process_material_2d_curve_bind"].readOnlyHint is False
    assert annotations["particle_process_material_2d_curve_set"].readOnlyHint is False
    assert annotations["particle_process_material_2d_curve_clear"].destructiveHint is True
    assert annotations["particle_process_material_2d_gradient_bind"].readOnlyHint is False
    assert annotations["particle_process_material_2d_gradient_set"].readOnlyHint is False
    assert annotations["particle_process_material_2d_gradient_clear"].destructiveHint is True
    assert annotations["canvas_item_material_create"].destructiveHint is True
    assert annotations["canvas_item_material_bind"].readOnlyHint is False
    assert annotations["canvas_item_material_set"].readOnlyHint is False
    assert annotations["canvas_item_material_clear"].destructiveHint is True
    assert annotations["light_2d_set"].readOnlyHint is False
    assert annotations["light_occluder_2d_set"].readOnlyHint is False
    assert annotations["tile_set_create"].readOnlyHint is False
    assert annotations["tile_set_clear"].destructiveHint is True
    assert annotations["tile_set_atlas_source_create"].readOnlyHint is False
    assert annotations["tile_set_atlas_tile_create"].readOnlyHint is False
    assert annotations["tile_set_physics_layer_create"].readOnlyHint is False
    assert annotations["tile_set_navigation_layer_create"].readOnlyHint is False
    assert annotations["tile_set_occlusion_layer_create"].readOnlyHint is False
    assert annotations["tile_set_custom_data_layer_create"].readOnlyHint is False
    assert annotations["tile_set_terrain_set_create"].readOnlyHint is False
    assert annotations["tile_set_terrain_create"].readOnlyHint is False
    assert annotations["tile_set_atlas_alternative_create"].readOnlyHint is False
    assert annotations["tile_set_atlas_tile_terrain_set"].readOnlyHint is False
    assert annotations["tile_set_atlas_tile_custom_data_set"].readOnlyHint is False
    assert annotations["tile_set_atlas_tile_collision_set"].readOnlyHint is False
    assert annotations["tile_set_atlas_tile_navigation_set"].readOnlyHint is False
    assert annotations["tile_set_atlas_tile_occlusion_set"].readOnlyHint is False
    assert annotations["tile_map_layer_cells_set"].readOnlyHint is False
    assert annotations["tile_map_layer_cells_clear"].destructiveHint is True
    assert annotations["scene_save"].idempotentHint is True

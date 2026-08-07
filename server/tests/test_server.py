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
        "editor_run",
        "editor_stop",
        "runtime_get_state",
        "runtime_logs_get",
        "runtime_screenshot_request",
        "runtime_screenshot_get",
        "runtime_screenshot_view",
        "runtime_input_send",
        "runtime_input_result_get",
        "runtime_audio_stream_player_2d_control",
        "runtime_audio_stream_player_2d_control_result_get",
        "scene_get_hierarchy",
        "scene_create",
        "scene_open",
        "class_search",
        "class_2d_coverage",
        "node_get_properties",
        "node_get_signals",
        "sprite_2d_get",
        "line_2d_get",
        "polygon_2d_get",
        "animated_sprite_2d_get",
        "sprite_frames_get",
        "button_2d_get",
        "button_menu_items_get",
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
        "canvas_item_shader_get",
        "light_2d_get",
        "light_occluder_2d_get",
        "tile_map_layer_get",
        "tile_map_layer_cells_get",
        "tile_set_get",
        "tile_set_layers_get",
        "tile_set_atlas_tile_get",
        "node_create",
        "node_script_bind",
        "node_script_clear",
        "node_instance_scene",
        "node_set_properties",
        "sprite_2d_set",
        "line_2d_set",
        "polygon_2d_set",
        "animated_sprite_2d_set",
        "button_2d_set",
        "button_menu_items_set",
        "button_menu_items_clear",
        "sprite_frames_animation_upsert",
        "sprite_frames_animation_rename",
        "sprite_frames_animation_remove",
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
        "canvas_item_shader_create",
        "canvas_item_shader_bind",
        "canvas_item_shader_set",
        "canvas_item_shader_uniforms_set",
        "canvas_item_shader_uniforms_clear",
        "canvas_item_shader_clear",
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
    assert annotations["editor_run"].readOnlyHint is False
    assert annotations["editor_stop"].idempotentHint is True
    assert annotations["runtime_get_state"].readOnlyHint is True
    assert annotations["runtime_logs_get"].readOnlyHint is True
    assert annotations["runtime_screenshot_request"].readOnlyHint is False
    assert annotations["runtime_screenshot_get"].readOnlyHint is True
    assert annotations["runtime_screenshot_view"].readOnlyHint is True
    assert annotations["runtime_input_send"].readOnlyHint is False
    assert annotations["runtime_input_result_get"].readOnlyHint is True
    assert annotations["runtime_audio_stream_player_2d_control"].readOnlyHint is False
    assert annotations["runtime_audio_stream_player_2d_control_result_get"].readOnlyHint is True
    assert annotations["class_2d_coverage"].readOnlyHint is True
    assert annotations["node_get_properties"].readOnlyHint is True
    assert annotations["node_get_signals"].readOnlyHint is True
    assert annotations["sprite_2d_get"].readOnlyHint is True
    assert annotations["line_2d_get"].readOnlyHint is True
    assert annotations["polygon_2d_get"].readOnlyHint is True
    assert annotations["animated_sprite_2d_get"].readOnlyHint is True
    assert annotations["sprite_frames_get"].readOnlyHint is True
    assert annotations["button_2d_get"].readOnlyHint is True
    assert annotations["button_menu_items_get"].readOnlyHint is True
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
    assert annotations["canvas_item_shader_get"].readOnlyHint is True
    assert annotations["light_2d_get"].readOnlyHint is True
    assert annotations["light_occluder_2d_get"].readOnlyHint is True
    assert annotations["tile_map_layer_get"].readOnlyHint is True
    assert annotations["tile_map_layer_cells_get"].readOnlyHint is True
    assert annotations["tile_set_get"].readOnlyHint is True
    assert annotations["tile_set_layers_get"].readOnlyHint is True
    assert annotations["tile_set_atlas_tile_get"].readOnlyHint is True
    assert annotations["node_create"].readOnlyHint is False
    assert annotations["node_instance_scene"].readOnlyHint is False
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
    assert annotations["canvas_item_shader_create"].destructiveHint is True
    assert annotations["canvas_item_shader_bind"].readOnlyHint is False
    assert annotations["canvas_item_shader_set"].readOnlyHint is False
    assert annotations["canvas_item_shader_uniforms_set"].readOnlyHint is False
    assert annotations["canvas_item_shader_uniforms_clear"].destructiveHint is True
    assert annotations["canvas_item_shader_clear"].destructiveHint is True
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
    assert annotations["scene_create"].destructiveHint is True
    assert annotations["scene_open"].readOnlyHint is False
    assert annotations["node_script_bind"].readOnlyHint is False
    assert annotations["node_script_clear"].destructiveHint is True
    assert annotations["sprite_2d_set"].readOnlyHint is False
    assert annotations["line_2d_set"].readOnlyHint is False
    assert annotations["polygon_2d_set"].readOnlyHint is False
    assert annotations["animated_sprite_2d_set"].readOnlyHint is False
    assert annotations["button_2d_set"].readOnlyHint is False
    assert annotations["button_menu_items_set"].readOnlyHint is False
    assert annotations["button_menu_items_clear"].destructiveHint is True
    assert annotations["sprite_frames_animation_upsert"].readOnlyHint is False
    assert annotations["sprite_frames_animation_rename"].readOnlyHint is False
    assert annotations["sprite_frames_animation_remove"].destructiveHint is True
    assert annotations["scene_save"].idempotentHint is True


@pytest.mark.asyncio
async def test_runtime_screenshot_view_returns_mcp_image_content() -> None:
    app = create_application(ws_port=19999)

    async def runtime_screenshot_get(
        request_id: str, session_id: str | None = None
    ) -> dict[str, object]:
        assert request_id == "screenshot-123"
        assert session_id == "project@a1b2"
        return {
            "status": "ready",
            "result": {
                "ok": True,
                "width": 1,
                "height": 1,
                "byte_size": 1,
                "mime_type": "image/png",
                "data_base64": "AA==",
            },
        }

    app.service.runtime_screenshot_get = runtime_screenshot_get  # type: ignore[method-assign]
    tool = await app.mcp.get_tool("runtime_screenshot_view")

    assert tool is not None
    response = await tool.run({"request_id": "screenshot-123", "session_id": "project@a1b2"})

    assert len(response.content) == 1
    image = response.content[0]
    assert image.type == "image"
    assert image.mimeType == "image/png"
    assert image.data == "AA=="
    assert response.structured_content == {
        "request_id": "screenshot-123",
        "status": "ready",
        "width": 1,
        "height": 1,
        "byte_size": 1,
        "mime_type": "image/png",
    }

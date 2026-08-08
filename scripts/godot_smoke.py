"""Run a real Godot editor against the Python WebSocket bridge."""

from __future__ import annotations

import argparse
import asyncio
import base64
import os
import shutil
import signal
import socket
import struct
import tempfile
import zlib
from collections.abc import Awaitable
from pathlib import Path

from godot_2d_mcp.bridge import GodotCommandError
from godot_2d_mcp.server import create_application

EDITOR_CONNECTION_TIMEOUT_SECONDS = 30.0
EDITOR_CONNECTION_POLL_INTERVAL_SECONDS = 0.1
SMOKE_TRACE_ENABLED = os.environ.get("GODOT_2D_MCP_SMOKE_TRACE") == "1"


def _trace_smoke(message: str) -> None:
    if SMOKE_TRACE_ENABLED:
        print(f"[godot-smoke] {message}", flush=True)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def run_smoke(godot_binary: str, project_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="godot-2d-mcp-smoke-") as temp_dir:
        isolated_project = Path(temp_dir) / "project"
        shutil.copytree(
            project_path,
            isolated_project,
            ignore=shutil.ignore_patterns(".godot"),
        )
        await _run_editor_smoke(godot_binary, isolated_project)


async def _run_editor_smoke(godot_binary: str, project_path: Path) -> None:
    _trace_smoke("starting editor bridge")
    port = free_port()
    app = create_application(ws_port=port, command_timeout=5.0)
    await app.bridge.start()

    environment = dict(os.environ)
    environment["GODOT_2D_MCP_WS_PORT"] = str(port)
    process = await asyncio.create_subprocess_exec(
        godot_binary,
        "--headless",
        "--editor",
        "--path",
        str(project_path),
        "res://test_scene.tscn",
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=os.name != "nt",
    )

    output = b""
    failure: BaseException | None = None
    try:
        for _ in range(
            int(
                EDITOR_CONNECTION_TIMEOUT_SECONDS
                / EDITOR_CONNECTION_POLL_INTERVAL_SECONDS
            )
        ):
            sessions = await app.registry.list_sessions()
            if sessions:
                break
            if process.returncode is not None:
                raise RuntimeError("Godot exited before the plugin connected")
            await asyncio.sleep(EDITOR_CONNECTION_POLL_INTERVAL_SECONDS)
        else:
            raise RuntimeError(
                "Godot plugin did not connect within "
                f"{EDITOR_CONNECTION_TIMEOUT_SECONDS:.0f} seconds"
            )

        state = await _wait_for_editor_ready(app)
        _trace_smoke("editor connected and ready")
        loop_mode = "pingpong" if str(state.get("godot_version", "")).startswith("4.7") else "linear"
        input_action_name = "mcp_smoke_move_left"
        input_events = [
            {"type": "key", "physical_keycode": 65, "shift": True},
            {"type": "mouse_button", "button": 1, "device": -1},
            {"type": "joypad_button", "button": 0, "device": 2},
            {"type": "joypad_motion", "axis": 0, "axis_value": -1.0},
        ]
        input_action_created = await app.service.input_map_action_upsert(
            input_action_name,
            input_events,
            deadzone=0.35,
        )
        input_actions_after_create = await app.service.input_map_get(
            query=input_action_name, limit=20
        )
        created_input_action = next(
            (
                action
                for action in input_actions_after_create.get("actions", [])
                if action.get("action") == input_action_name
            ),
            None,
        )
        if (
            input_action_created.get("created") is not True
            or created_input_action is None
            or abs(float(created_input_action.get("deadzone", -1)) - 0.35) > 0.00001
            or {event.get("type") for event in created_input_action.get("events", [])}
            != {"key", "mouse_button", "joypad_button", "joypad_motion"}
            or input_action_name not in (project_path / "project.godot").read_text(encoding="utf-8")
        ):
            raise RuntimeError(
                "Input Map action creation was incomplete: "
                f"result={input_action_created}, action={created_input_action}"
            )
        input_action_undo_create = await app.service.input_map_undo()
        input_actions_after_undo_create = await app.service.input_map_get(
            query=input_action_name, limit=20
        )
        input_action_redo_create = await app.service.input_map_redo()
        input_actions_after_redo_create = await app.service.input_map_get(
            query=input_action_name, limit=20
        )
        if (
            input_action_undo_create.get("changed") is not True
            or input_actions_after_undo_create.get("total") != 0
            or input_action_redo_create.get("changed") is not True
            or input_actions_after_redo_create.get("total") != 1
        ):
            raise RuntimeError(
                "Input Map creation undo/redo was incomplete: "
                f"undo={input_action_undo_create}, after_undo={input_actions_after_undo_create}, "
                f"redo={input_action_redo_create}, after_redo={input_actions_after_redo_create}"
            )
        input_action_updated = await app.service.input_map_action_upsert(
            input_action_name,
            [{"type": "key", "keycode": 68, "command_or_control_autoremap": True}],
            deadzone=0.5,
            replace_existing=True,
        )
        input_action_undo_update = await app.service.input_map_undo()
        input_action_redo_update = await app.service.input_map_redo()
        input_actions_after_update = await app.service.input_map_get(
            query=input_action_name, limit=20
        )
        updated_input_action = next(
            (
                action
                for action in input_actions_after_update.get("actions", [])
                if action.get("action") == input_action_name
            ),
            None,
        )
        if (
            input_action_updated.get("replaced") is not True
            or input_action_undo_update.get("changed") is not True
            or input_action_redo_update.get("changed") is not True
            or updated_input_action is None
            or abs(float(updated_input_action.get("deadzone", -1)) - 0.5) > 0.00001
            or updated_input_action.get("event_count") != 1
            or updated_input_action.get("events", [{}])[0].get("keycode") != 68
            or updated_input_action.get("events", [{}])[0].get("command_or_control_autoremap")
            is not True
        ):
            raise RuntimeError(
                "Input Map action replacement was incomplete: "
                f"result={input_action_updated}, action={updated_input_action}"
            )
        input_action_deleted = await app.service.input_map_action_delete(
            input_action_name, confirm=True
        )
        input_action_undo_delete = await app.service.input_map_undo()
        input_action_redo_delete = await app.service.input_map_redo()
        input_actions_after_delete = await app.service.input_map_get(
            query=input_action_name, limit=20
        )
        if (
            input_action_deleted.get("deleted") is not True
            or input_action_undo_delete.get("changed") is not True
            or input_action_redo_delete.get("changed") is not True
            or input_actions_after_delete.get("total") != 0
            or input_action_name in (project_path / "project.godot").read_text(encoding="utf-8")
        ):
            raise RuntimeError(
                "Input Map action deletion was incomplete: "
                f"delete={input_action_deleted}, undo={input_action_undo_delete}, "
                f"redo={input_action_redo_delete}, after_delete={input_actions_after_delete}"
            )
        resource_path = "res://generated/agent_gradient.tres"
        await _expect_godot_error(
            app.service.resource_create("Shader", "res://generated/rejected_shader.tres"),
            "UNSUPPORTED_2D_RESOURCE",
        )
        created_resource = await app.service.resource_create(
            "Gradient",
            resource_path,
            {
                "offsets": [0.0, 1.0],
                "colors": [
                    {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0},
                    {"r": 0.8, "g": 0.7, "b": 0.6, "a": 1.0},
                ],
            },
        )
        created_resource_data = await app.service.resource_get(
            resource_path, fields=["offsets", "colors"]
        )
        created_offsets = _property_value(created_resource_data, "offsets")
        created_colors = _property_value(created_resource_data, "colors")
        if (
            created_resource.get("created") is not True
            or created_resource.get("saved") is not True
            or created_resource_data.get("resource_type") != "Gradient"
            or created_offsets != [0.0, 1.0]
            or not isinstance(created_colors, list)
            or len(created_colors) != 2
            or not _color_matches(
                created_colors[0], {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0}
            )
        ):
            raise RuntimeError(
                "Generic resource creation was incomplete: "
                f"created={created_resource}, resource={created_resource_data}"
            )
        updated_resource = await app.service.resource_set_properties(
            resource_path,
            {"offsets": [0.0, 0.75]},
        )
        undone_resource = await app.service.resource_undo(resource_path)
        after_undo_resource = await app.service.resource_get(resource_path, fields=["offsets"])
        redone_resource = await app.service.resource_redo(resource_path)
        saved_resource = await app.service.resource_save(resource_path)
        after_redo_resource = await app.service.resource_get(resource_path, fields=["offsets"])
        saved_resource_file = project_path / "generated" / "agent_gradient.tres"
        if (
            updated_resource.get("updated", {}).get("offsets") != [0.0, 0.75]
            or undone_resource.get("changed") is not True
            or _property_value(after_undo_resource, "offsets") != [0.0, 1.0]
            or redone_resource.get("changed") is not True
            or saved_resource.get("saved") is not True
            or _property_value(after_redo_resource, "offsets") != [0.0, 0.75]
            or not saved_resource_file.is_file()
            or "Gradient" not in saved_resource_file.read_text(encoding="utf-8")
        ):
            raise RuntimeError(
                "Generic resource update, undo/redo, or save was incomplete: "
                f"updated={updated_resource}, undone={undone_resource}, "
                f"after_undo={after_undo_resource}, redone={redone_resource}, "
                f"saved={saved_resource}, after_redo={after_redo_resource}"
            )
        hierarchy = await app.service.scene_get_hierarchy(limit=20)
        classes = await app.service.class_search(query="Button", limit=20)
        button_overview = await app.service.class_2d_describe("Button")
        button_properties = await app.service.class_2d_describe(
            "Button", section="properties", limit=500
        )
        button_methods = await app.service.class_2d_describe(
            "Button", section="methods", limit=500
        )
        button_methods_tail = await app.service.class_2d_describe(
            "Button", section="methods", offset=500, limit=100
        )
        button_signals = await app.service.class_2d_describe(
            "Button", section="signals", limit=500
        )
        button_enums = await app.service.class_2d_describe(
            "Button", section="enums", limit=500
        )
        navigation_polygon_properties = await app.service.class_2d_describe(
            "NavigationPolygon", section="properties", limit=500
        )
        coverage = await app.service.class_2d_coverage(
            query="Button", scope="node", limit=20
        )
        resource_coverage = await app.service.class_2d_coverage(
            query="TileSet", scope="resource", limit=20
        )
        gradient_coverage = await app.service.class_2d_coverage(
            query="Gradient", scope="resource", limit=20
        )
        navigation_polygon_coverage = await app.service.class_2d_coverage(
            query="NavigationPolygon", scope="resource", limit=20
        )
        draw_coverage = await app.service.class_2d_coverage(
            query="Sprite2D", scope="node", limit=20
        )
        draw_resource_coverage = await app.service.class_2d_coverage(
            query="Curve", scope="resource", limit=20
        )
        sprite_frames_coverage = await app.service.class_2d_coverage(
            query="SpriteFrames", scope="resource", limit=20
        )
        texture_button_coverage = await app.service.class_2d_coverage(
            query="TextureButton", scope="node", limit=20
        )
        link_button_coverage = await app.service.class_2d_coverage(
            query="LinkButton", scope="node", limit=20
        )
        container_coverage = await app.service.class_2d_coverage(
            query="Container", scope="node", limit=40
        )

        if hierarchy.get("total") != 5:
            raise RuntimeError(f"Unexpected scene node count: {hierarchy.get('total')}")
        if classes.get("total", 0) < 4:
            raise RuntimeError("2D class search returned too few Button types")
        if (
            button_overview.get("kind") != "node"
            or button_overview.get("api_type") != "core"
            or {"Button", "BaseButton", "Control"}
            - set(button_overview.get("inheritance", []))
            or not any(item.get("name") == "text" for item in button_properties.get("items", []))
            or button_methods.get("has_more") is not True
            or not any(
                item.get("name") == "set_text" for item in button_methods_tail.get("items", [])
            )
            or not any(item.get("name") == "pressed" for item in button_signals.get("items", []))
            or button_enums.get("total", 0) < 1
            or navigation_polygon_properties.get("kind") != "resource"
            or not any(
                item.get("name") == "agent_radius"
                for item in navigation_polygon_properties.get("items", [])
            )
        ):
            raise RuntimeError(
                "ClassDB 2D reflection details were incomplete: "
                f"overview={button_overview}, properties={button_properties}, "
                f"methods={button_methods}, methods_tail={button_methods_tail}, "
                f"signals={button_signals}, enums={button_enums}, "
                f"navigation_polygon_properties={navigation_polygon_properties}"
            )
        button_coverage = next(
            (
                entry
                for entry in coverage.get("entries", [])
                if entry.get("name") == "Button"
            ),
            None,
        )
        option_button_coverage = next(
            (
                entry
                for entry in coverage.get("entries", [])
                if entry.get("name") == "OptionButton"
            ),
            None,
        )
        menu_button_coverage = next(
            (
                entry
                for entry in coverage.get("entries", [])
                if entry.get("name") == "MenuButton"
            ),
            None,
        )
        if (
            coverage.get("audit_version") != 1
            or coverage.get("scope") != "node"
            or button_coverage is None
            or button_coverage.get("kind") != "node"
            or button_coverage.get("base_support", {}).get("create") is not True
            or "control_get_layout" not in button_coverage.get("semantic_tools", [])
            or {"button_2d_get", "button_2d_set"}
            - set(button_coverage.get("semantic_tools", []))
            or button_coverage.get("test_status") != "semantic_smoke"
        ):
            raise RuntimeError(f"Button coverage audit was incomplete: {coverage}")
        for entry, class_name in (
            (option_button_coverage, "OptionButton"),
            (menu_button_coverage, "MenuButton"),
        ):
            if (
                entry is None
                or {
                    "button_menu_items_get",
                    "button_menu_items_set",
                    "button_menu_items_clear",
                }
                - set(entry.get("semantic_tools", []))
                or entry.get("test_status") != "semantic_smoke"
            ):
                raise RuntimeError(f"{class_name} coverage audit was incomplete: {coverage}")
        tile_set_coverage = next(
            (
                entry
                for entry in resource_coverage.get("entries", [])
                if entry.get("name") == "TileSet"
            ),
            None,
        )
        if (
            resource_coverage.get("scope") != "resource"
            or tile_set_coverage is None
            or tile_set_coverage.get("kind") != "resource"
            or tile_set_coverage.get("category") != "tile_map"
            or {
                "tile_set_create",
                "tile_set_layer_set",
                "tile_set_layer_remove",
                "tile_set_terrain_set_remove",
                "tile_set_terrain_remove",
            }
            - set(tile_set_coverage.get("semantic_tools", []))
        ):
            raise RuntimeError(
                f"TileSet coverage audit was incomplete: {resource_coverage}"
            )
        gradient_coverage_entry = next(
            (
                entry
                for entry in gradient_coverage.get("entries", [])
                if entry.get("name") == "Gradient"
            ),
            None,
        )
        if (
            gradient_coverage_entry is None
            or {
                "resource_get",
                "resource_create",
                "resource_set_properties",
                "resource_save",
                "resource_undo",
                "resource_redo",
            }
            - set(gradient_coverage_entry.get("semantic_tools", []))
            or gradient_coverage_entry.get("test_status") != "semantic_smoke"
        ):
            raise RuntimeError(
                f"Gradient resource coverage audit was incomplete: {gradient_coverage}"
            )
        navigation_polygon_coverage_entry = next(
            (
                entry
                for entry in navigation_polygon_coverage.get("entries", [])
                if entry.get("name") == "NavigationPolygon"
            ),
            None,
        )
        if (
            navigation_polygon_coverage.get("scope") != "resource"
            or navigation_polygon_coverage_entry is None
            or {
                "navigation_polygon_get",
                "navigation_polygon_bake_request",
                "navigation_polygon_bake_result_get",
            }
            - set(navigation_polygon_coverage_entry.get("semantic_tools", []))
            or navigation_polygon_coverage_entry.get("test_status") != "semantic_smoke"
        ):
            raise RuntimeError(
                "NavigationPolygon coverage audit was incomplete: "
                f"{navigation_polygon_coverage}"
            )
        sprite_coverage = next(
            (
                entry
                for entry in draw_coverage.get("entries", [])
                if entry.get("name") == "Sprite2D"
            ),
            None,
        )
        curve_coverage = next(
            (
                entry
                for entry in draw_resource_coverage.get("entries", [])
                if entry.get("name") == "Curve"
            ),
            None,
        )
        animated_sprite_coverage = next(
            (
                entry
                for entry in draw_coverage.get("entries", [])
                if entry.get("name") == "AnimatedSprite2D"
            ),
            None,
        )
        frames_coverage = next(
            (
                entry
                for entry in sprite_frames_coverage.get("entries", [])
                if entry.get("name") == "SpriteFrames"
            ),
            None,
        )
        texture_button_entry = next(
            (
                entry
                for entry in texture_button_coverage.get("entries", [])
                if entry.get("name") == "TextureButton"
            ),
            None,
        )
        link_button_entry = next(
            (
                entry
                for entry in link_button_coverage.get("entries", [])
                if entry.get("name") == "LinkButton"
            ),
            None,
        )
        container_entries = {
            entry.get("name"): entry for entry in container_coverage.get("entries", [])
        }
        if (
            sprite_coverage is None
            or {"sprite_2d_get", "sprite_2d_set"}
            - set(sprite_coverage.get("semantic_tools", []))
            or sprite_coverage.get("test_status") != "semantic_smoke"
            or curve_coverage is None
            or {"line_2d_get", "line_2d_set"}
            - set(curve_coverage.get("semantic_tools", []))
            or animated_sprite_coverage is None
            or {"animated_sprite_2d_get", "sprite_frames_animation_upsert"}
            - set(animated_sprite_coverage.get("semantic_tools", []))
            or animated_sprite_coverage.get("test_status") != "semantic_smoke"
            or frames_coverage is None
            or {"sprite_frames_get", "sprite_frames_animation_remove"}
            - set(frames_coverage.get("semantic_tools", []))
            or texture_button_entry is None
            or {"button_2d_get", "button_2d_set"}
            - set(texture_button_entry.get("semantic_tools", []))
            or texture_button_entry.get("test_status") != "semantic_smoke"
            or link_button_entry is None
            or {"button_2d_get", "button_2d_set"}
            - set(link_button_entry.get("semantic_tools", []))
            or link_button_entry.get("test_status") != "semantic_smoke"
        ):
            raise RuntimeError("2D drawing coverage audit was incomplete")
        for class_name in (
            "HBoxContainer",
            "GridContainer",
            "AspectRatioContainer",
            "HFlowContainer",
            "HSplitContainer",
            "ScrollContainer",
            "TabContainer",
            "SubViewportContainer",
        ):
            container_entry = container_entries.get(class_name)
            required_tools = {
                "container_2d_get",
                "container_2d_set",
                "container_child_layout_set",
            }
            if class_name == "TabContainer":
                required_tools.update({"tab_container_items_get", "tab_container_item_set"})
            if (
                container_entry is None
                or required_tools - set(container_entry.get("semantic_tools", []))
                or container_entry.get("test_status") != "semantic_smoke"
            ):
                raise RuntimeError(
                    f"{class_name} container coverage audit was incomplete: "
                    f"{container_coverage}"
                )

        scene_file = state.get("current_scene", "")
        coverage_snapshot = await app.service.class_2d_coverage_snapshot()
        coverage_diff = await app.service.class_2d_coverage_diff(coverage_snapshot)
        if (
            coverage_snapshot.get("snapshot_version") != 1
            or coverage_snapshot.get("total", 0) < 40
            or coverage_snapshot.get("total") != len(coverage_snapshot.get("entries", []))
            or coverage_diff.get("summary") != {
                "added": 0,
                "removed": 0,
                "changed": 0,
                "breaking": 0,
            }
        ):
            raise RuntimeError(
                "2D coverage snapshot or same-build diff was incomplete: "
                f"snapshot={coverage_snapshot}, diff={coverage_diff}"
            )
        await _smoke_generic_2d_node_lifecycle(app, scene_file, coverage_snapshot)

        created_scene_file = "res://generated/agent_created_ui.tscn"
        await _expect_godot_error(
            app.service.scene_create(
                scene_path="res://generated/rejected_3d.tscn",
                root_type="Node3D",
            ),
            "UNSUPPORTED_2D_TYPE",
        )
        created_scene = await app.service.scene_create(
            scene_path=created_scene_file,
            root_type="Control",
            root_name="AgentCreatedUI",
        )
        if (
            not created_scene.get("created")
            or created_scene.get("scene_file") != created_scene_file
            or created_scene.get("root_type") != "Control"
        ):
            raise RuntimeError("scene_create returned an unexpected scene root")
        await _expect_godot_error(
            app.service.scene_create(scene_path=created_scene_file),
            "SCENE_PATH_EXISTS",
        )
        created_hierarchy = await app.service.scene_get_hierarchy(limit=20)
        if (
            created_hierarchy.get("scene_file") != created_scene_file
            or created_hierarchy.get("total") != 1
            or created_hierarchy["nodes"][0].get("name") != "AgentCreatedUI"
        ):
            raise RuntimeError("scene_create did not open the generated 2D scene")
        created_button = await app.service.node_create(
            type_name="Button",
            name="AgentCreatedButton",
            parent_path="/AgentCreatedUI",
            scene_file=created_scene_file,
        )
        if created_button.get("type") != "Button":
            raise RuntimeError("Newly created scene did not accept 2D child nodes")
        created_save = await app.service.scene_save(scene_file=created_scene_file)
        if not created_save.get("saved"):
            raise RuntimeError("Newly created scene could not be saved")
        generated_scene = (
            project_path / "generated" / "agent_created_ui.tscn"
        ).read_text(encoding="utf-8")
        if (
            "AgentCreatedUI" not in generated_scene
            or "AgentCreatedButton" not in generated_scene
        ):
            raise RuntimeError("Newly created scene was not persisted")
        await _expect_godot_error(
            app.service.scene_open("res://packed_scene_3d.tscn"),
            "UNSUPPORTED_2D_TYPE",
        )
        reopened_scene = await app.service.scene_open(scene_file)
        if (
            not reopened_scene.get("opened")
            or reopened_scene.get("scene_file") != scene_file
        ):
            raise RuntimeError("scene_open did not return to the original scene")
        reopened_hierarchy = await app.service.scene_get_hierarchy(limit=20)
        if (
            reopened_hierarchy.get("scene_file") != scene_file
            or reopened_hierarchy.get("total") != 5
        ):
            raise RuntimeError("scene_open did not restore the original scene")
        initial_revision = state["meta"]["scene_revision"]
        await _expect_godot_error(
            app.service.node_create(type_name="Node3D", scene_file=scene_file),
            "UNSUPPORTED_2D_TYPE",
        )
        await _expect_godot_error(
            app.service.node_create(
                type_name="Node2D",
                name="RejectedToolScript",
                parent_path="/Main",
                script_path="res://test_tool_node_2d.gd",
                scene_file=scene_file,
            ),
            "TOOL_SCRIPT_NOT_SUPPORTED",
        )
        await _expect_godot_error(
            app.service.node_create(
                type_name="Button",
                name="RejectedScriptBase",
                parent_path="/Main",
                script_path="res://test_node_2d.gd",
                scene_file=scene_file,
            ),
            "SCRIPT_BASE_TYPE_MISMATCH",
        )
        scripted_node = await app.service.node_create(
            type_name="Node2D",
            name="AgentScriptedNode",
            parent_path="/Main",
            script_path="res://test_node_2d.gd",
            scene_file=scene_file,
        )
        if scripted_node["script"] != {
            "resource_path": "res://test_node_2d.gd",
            "base_type": "Node2D",
            "global_name": "",
            "is_tool": False,
        }:
            raise RuntimeError("node_create did not attach the requested 2D script")
        scripted_path = scripted_node["path"]
        scripted_hierarchy = await app.service.scene_get_hierarchy(limit=20)
        if not any(
            item["path"] == scripted_path
            and item["script_path"] == "res://test_node_2d.gd"
            for item in scripted_hierarchy["nodes"]
        ):
            raise RuntimeError("Scripted node was not persisted in the scene hierarchy")
        cleared_script = await app.service.node_script_clear(
            scripted_path, scene_file=scene_file
        )
        if not cleared_script.get("cleared"):
            raise RuntimeError("node_script_clear did not detach the script")
        undone_script_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undone_script_clear.get("changed"):
            raise RuntimeError("node_script_clear was not undoable")
        restored_script_hierarchy = await app.service.scene_get_hierarchy(limit=20)
        if not any(
            item["path"] == scripted_path
            and item["script_path"] == "res://test_node_2d.gd"
            for item in restored_script_hierarchy["nodes"]
        ):
            raise RuntimeError("Undo did not restore the detached script")
        typed_container_properties = await app.service.node_get_properties(
            scripted_path,
            fields=["accent_colors", "color_labels", "color_lookup", "icon_textures"],
            scene_file=scene_file,
        )
        if (
            _property_data(typed_container_properties, "accent_colors").get(
                "container_type"
            )
            != {"kind": "array", "element": {"type": "Color"}}
            or _property_data(typed_container_properties, "color_labels").get(
                "container_type"
            )
            != {
                "kind": "dictionary",
                "key": {"type": "String"},
                "value": {"type": "Color"},
            }
            or _property_data(typed_container_properties, "color_lookup").get(
                "container_type"
            )
            != {
                "kind": "dictionary",
                "key": {"type": "Color"},
                "value": {"type": "String"},
            }
            or _property_data(typed_container_properties, "icon_textures").get(
                "container_type"
            )
            != {
                "kind": "array",
                "element": {"type": "Object", "class_name": "Texture2D"},
            }
        ):
            raise RuntimeError("Typed container metadata was not reported")
        typed_container_update = await app.service.node_set_properties(
            scripted_path,
            {
                "accent_colors": [
                    {"r": 0.1, "g": 0.2, "b": 0.3, "a": 0.4},
                    {"r": 0.8, "g": 0.7, "b": 0.6, "a": 1.0},
                ],
                "color_labels": {"primary": {"r": 0.2, "g": 0.4, "b": 0.6, "a": 1.0}},
                "color_lookup": {
                    "entries": [
                        {
                            "key": {"r": 0.9, "g": 0.1, "b": 0.2, "a": 1.0},
                            "value": "danger",
                        }
                    ]
                },
                "icon_textures": [{"resource_path": "res://test_icon.svg"}],
            },
            scene_file=scene_file,
        )
        if not typed_container_update.get("updated"):
            raise RuntimeError("Typed container properties were not updated")
        typed_container_values = await app.service.node_get_properties(
            scripted_path,
            fields=["accent_colors", "color_labels", "color_lookup", "icon_textures"],
            scene_file=scene_file,
        )
        accent_colors = _property_value(typed_container_values, "accent_colors")
        color_labels = _property_value(typed_container_values, "color_labels")
        color_lookup = _property_value(typed_container_values, "color_lookup")
        icon_textures = _property_value(typed_container_values, "icon_textures")
        color_lookup_entries = (
            color_lookup.get("entries") if isinstance(color_lookup, dict) else None
        )
        if (
            not isinstance(accent_colors, list)
            or len(accent_colors) != 2
            or not _color_matches(
                accent_colors[0], {"r": 0.1, "g": 0.2, "b": 0.3, "a": 0.4}
            )
            or not isinstance(color_labels, dict)
            or not _color_matches(
                color_labels.get("primary"), {"r": 0.2, "g": 0.4, "b": 0.6, "a": 1.0}
            )
            or not isinstance(color_lookup_entries, list)
            or len(color_lookup_entries) != 1
            or not _color_matches(
                color_lookup_entries[0].get("key"),
                {"r": 0.9, "g": 0.1, "b": 0.2, "a": 1.0},
            )
            or color_lookup_entries[0].get("value") != "danger"
            or not isinstance(icon_textures, list)
            or icon_textures[0].get("resource_path") != "res://test_icon.svg"
        ):
            raise RuntimeError("Typed container values were not serialized correctly")
        await _expect_godot_error(
            app.service.node_set_properties(
                scripted_path,
                {
                    "accent_colors": [{"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}],
                    "node_references": [{"resource_path": "res://test_icon.svg"}],
                },
                scene_file=scene_file,
            ),
            "PROPERTY_TYPE_MISMATCH",
        )
        unchanged_accent_colors = _property_value(
            await app.service.node_get_properties(
                scripted_path,
                fields=["accent_colors"],
                scene_file=scene_file,
            ),
            "accent_colors",
        )
        if unchanged_accent_colors != accent_colors:
            raise RuntimeError(
                "Invalid typed container batch partially changed an earlier property"
            )
        undo_typed_containers = await app.service.scene_undo(scene_file=scene_file)
        if not undo_typed_containers.get("changed"):
            raise RuntimeError("Typed container update was not undoable")
        if (
            _property_value(
                await app.service.node_get_properties(
                    scripted_path,
                    fields=[
                        "accent_colors",
                        "color_labels",
                        "color_lookup",
                        "icon_textures",
                    ],
                    scene_file=scene_file,
                ),
                "accent_colors",
            )
            != []
        ):
            raise RuntimeError("Undo did not restore typed container defaults")
        redo_typed_containers = await app.service.scene_redo(scene_file=scene_file)
        if not redo_typed_containers.get("changed"):
            raise RuntimeError("Typed container update was not redoable")
        await _expect_godot_error(
            app.service.node_get_properties("/Main/..", scene_file=scene_file),
            "NODE_NOT_FOUND",
        )
        marker = await app.service.node_create(
            type_name="Node2D",
            name="AgentMarker",
            parent_path="/Main",
            scene_file=scene_file,
        )
        marker_path = marker["path"]
        bound_script = await app.service.node_script_bind(
            path=marker_path,
            script_path="res://test_node_2d.gd",
            scene_file=scene_file,
        )
        if (
            not bound_script.get("changed")
            or bound_script["script"]["resource_path"] != "res://test_node_2d.gd"
        ):
            raise RuntimeError("node_script_bind did not attach a compatible script")
        unchanged_script = await app.service.node_script_bind(
            path=marker_path,
            script_path="res://test_node_2d.gd",
            scene_file=scene_file,
        )
        if unchanged_script.get("changed"):
            raise RuntimeError("Binding the same script should be idempotent")
        await _expect_godot_error(
            app.service.node_script_bind(
                path=marker_path,
                script_path="res://test_node_2d_alternate.gd",
                scene_file=scene_file,
            ),
            "SCRIPT_ALREADY_ATTACHED",
        )
        replaced_script = await app.service.node_script_bind(
            path=marker_path,
            script_path="res://test_node_2d_alternate.gd",
            replace_existing=True,
            scene_file=scene_file,
        )
        if (
            replaced_script["script"]["resource_path"]
            != "res://test_node_2d_alternate.gd"
        ):
            raise RuntimeError("node_script_bind did not replace the existing script")
        undo_script_replace = await app.service.scene_undo(scene_file=scene_file)
        if not undo_script_replace.get("changed"):
            raise RuntimeError("Script replacement was not undoable")
        undo_replace_hierarchy = await app.service.scene_get_hierarchy(limit=20)
        if not any(
            item["path"] == marker_path
            and item["script_path"] == "res://test_node_2d.gd"
            for item in undo_replace_hierarchy["nodes"]
        ):
            raise RuntimeError("Undo did not restore the previous script")
        redo_script_replace = await app.service.scene_redo(scene_file=scene_file)
        if not redo_script_replace.get("changed"):
            raise RuntimeError("Script replacement was not redoable")
        if marker["meta"]["scene_revision"] <= initial_revision:
            raise RuntimeError("Node creation did not advance scene_revision")
        await _expect_godot_error(
            app.service.node_set_properties(
                marker_path,
                {"visible": False, "position": {"x": 42}},
                scene_file=scene_file,
            ),
            "PROPERTY_TYPE_MISMATCH",
        )
        marker_visibility = await app.service.node_get_properties(
            marker_path,
            fields=["visible"],
            scene_file=scene_file,
        )
        if _property_value(marker_visibility, "visible") is not True:
            raise RuntimeError("Invalid batch partially changed an earlier property")
        marker_update = await app.service.node_set_properties(
            marker_path,
            {"position": {"x": 42, "y": 24}},
            scene_file=scene_file,
        )
        if marker_update["meta"]["scene_revision"] <= marker["meta"]["scene_revision"]:
            raise RuntimeError("Property update did not advance scene_revision")
        marker_properties = await app.service.node_get_properties(
            marker_path,
            fields=["position"],
            scene_file=scene_file,
        )
        if _property_value(marker_properties, "position") != {"x": 42.0, "y": 24.0}:
            raise RuntimeError("Node2D position was not applied")

        undo_update = await app.service.scene_undo(scene_file=scene_file)
        if not undo_update.get("changed"):
            raise RuntimeError("Property update was not undoable")
        marker_properties = await app.service.node_get_properties(
            marker_path,
            fields=["position"],
            scene_file=scene_file,
        )
        if _property_value(marker_properties, "position") != {"x": 0.0, "y": 0.0}:
            raise RuntimeError("Undo did not restore the Node2D position")

        redo_update = await app.service.scene_redo(scene_file=scene_file)
        if not redo_update.get("changed"):
            raise RuntimeError("Property update was not redoable")

        await _expect_godot_error(
            app.service.node_instance_scene(
                "res://packed_scene_3d.tscn",
                parent_path="/Main",
                scene_file=scene_file,
            ),
            "UNSUPPORTED_2D_TYPE",
        )
        packed_instance = await app.service.node_instance_scene(
            "res://packed_scene_2d.tscn",
            name="AgentPackedVisual",
            parent_path="/Main",
            scene_file=scene_file,
        )
        packed_instance_path = packed_instance["path"]
        if (
            packed_instance["scene_path"] != "res://packed_scene_2d.tscn"
            or packed_instance["subtree_node_count"] != 2
            or packed_instance["type"] != "Node2D"
        ):
            raise RuntimeError(
                "PackedScene instance metadata was not reported correctly"
            )
        undo_packed_instance = await app.service.scene_undo(scene_file=scene_file)
        if not undo_packed_instance.get("changed"):
            raise RuntimeError("PackedScene instance was not undoable")
        hierarchy_after_packed_undo = await app.service.scene_get_hierarchy(limit=20)
        if _has_node(hierarchy_after_packed_undo, packed_instance_path):
            raise RuntimeError("Undo did not remove the PackedScene instance root")
        redo_packed_instance = await app.service.scene_redo(scene_file=scene_file)
        if not redo_packed_instance.get("changed"):
            raise RuntimeError("PackedScene instance was not redoable")
        packed_instance_details = await app.service.packed_scene_instance_get(
            packed_instance_path, scene_file=scene_file
        )
        if (
            packed_instance_details.get("scene_path") != "res://packed_scene_2d.tscn"
            or packed_instance_details.get("editable_children") is not False
            or packed_instance_details.get("local_override_node_count") != 0
        ):
            raise RuntimeError(
                f"PackedScene instance inspection was incomplete: {packed_instance_details}"
            )
        packed_internal_sprite_path = f"{packed_instance_path}/PackedSceneInternalSprite"
        await _expect_godot_error(
            app.service.node_set_properties(
                packed_internal_sprite_path,
                {"position": {"x": 18, "y": 30}},
                scene_file=scene_file,
            ),
            "PACKED_SCENE_EDITABLE_CHILDREN_REQUIRED",
        )
        packed_editable = await app.service.packed_scene_instance_editable_children_enable(
            packed_instance_path, scene_file=scene_file
        )
        if (
            packed_editable.get("changed") is not True
            or packed_editable.get("editable_children") is not True
        ):
            raise RuntimeError(f"Editable Children was not enabled: {packed_editable}")
        undo_packed_editable = await app.service.scene_undo(scene_file=scene_file)
        if not undo_packed_editable.get("changed"):
            raise RuntimeError("Editable Children enable was not undoable")
        packed_after_editable_undo = await app.service.packed_scene_instance_get(
            packed_instance_path, scene_file=scene_file
        )
        if packed_after_editable_undo.get("editable_children") is not False:
            raise RuntimeError("Undo did not disable Editable Children")
        redo_packed_editable = await app.service.scene_redo(scene_file=scene_file)
        if not redo_packed_editable.get("changed"):
            raise RuntimeError("Editable Children enable was not redoable")
        packed_internal_update = await app.service.node_set_properties(
            packed_internal_sprite_path,
            {"position": {"x": 18, "y": 30}},
            scene_file=scene_file,
        )
        if packed_internal_update.get("updated", {}).get("position") != {"x": 18.0, "y": 30.0}:
            raise RuntimeError(
                f"PackedScene internal property override was not applied: {packed_internal_update}"
            )
        deleted_packed_instance = await app.service.node_delete(
            packed_instance_path, scene_file=scene_file
        )
        if not deleted_packed_instance.get("deleted"):
            raise RuntimeError("PackedScene instance root was not deletable")
        undo_packed_delete = await app.service.scene_undo(scene_file=scene_file)
        if not undo_packed_delete.get("changed"):
            raise RuntimeError("PackedScene instance deletion was not undoable")
        packed_parent = await app.service.node_create(
            type_name="Node2D",
            name="PackedInstanceContainer",
            parent_path="/Main",
            scene_file=scene_file,
        )
        packed_parent_path = packed_parent["path"]
        reparented_packed_instance = await app.service.node_reparent(
            packed_instance_path,
            packed_parent_path,
            scene_file=scene_file,
        )
        packed_instance_path = reparented_packed_instance["path"]
        if (
            not reparented_packed_instance.get("packed_scene_instance")
            or reparented_packed_instance.get("migrated_animation_tracks") != 0
        ):
            raise RuntimeError(
                "PackedScene instance reparenting lost its instance boundary"
            )
        undo_packed_reparent = await app.service.scene_undo(scene_file=scene_file)
        if not undo_packed_reparent.get("changed"):
            raise RuntimeError("PackedScene instance reparenting was not undoable")
        redo_packed_reparent = await app.service.scene_redo(scene_file=scene_file)
        if not redo_packed_reparent.get("changed"):
            raise RuntimeError("PackedScene instance reparenting was not redoable")
        packed_override = await app.service.node_create(
            type_name="Node2D",
            name="AgentPackedOverride",
            parent_path=packed_instance_path,
            scene_file=scene_file,
        )
        if packed_override.get("parent_path") != packed_instance_path:
            raise RuntimeError("PackedScene local override child was not created")
        packed_after_override = await app.service.packed_scene_instance_get(
            packed_instance_path, scene_file=scene_file
        )
        if packed_after_override.get("local_override_node_count") != 1:
            raise RuntimeError(
                f"PackedScene local override was not reported: {packed_after_override}"
            )
        renamed_packed_instance = await app.service.node_rename(
            packed_instance_path,
            "AgentPackedVisualRenamed",
            scene_file=scene_file,
        )
        old_packed_instance_path = packed_instance_path
        packed_instance_path = renamed_packed_instance["path"]
        if (
            renamed_packed_instance.get("old_path") != old_packed_instance_path
            or packed_instance_path == old_packed_instance_path
        ):
            raise RuntimeError("PackedScene instance rename did not return stable paths")
        undo_packed_rename = await app.service.scene_undo(scene_file=scene_file)
        if not undo_packed_rename.get("changed"):
            raise RuntimeError("PackedScene instance rename was not undoable")
        hierarchy_after_packed_rename_undo = await app.service.scene_get_hierarchy(limit=200)
        if not _has_node(hierarchy_after_packed_rename_undo, old_packed_instance_path):
            raise RuntimeError("Undo did not restore the PackedScene instance name")
        redo_packed_rename = await app.service.scene_redo(scene_file=scene_file)
        if not redo_packed_rename.get("changed"):
            raise RuntimeError("PackedScene instance rename was not redoable")
        hierarchy_after_packed_rename_redo = await app.service.scene_get_hierarchy(limit=200)
        if not _has_node(hierarchy_after_packed_rename_redo, packed_instance_path):
            raise RuntimeError("Redo did not restore the PackedScene instance name")
        packed_instance_copy = await app.service.node_duplicate(
            packed_instance_path,
            name="AgentPackedVisualCopy",
            scene_file=scene_file,
        )
        packed_instance_copy_path = packed_instance_copy["path"]
        if (
            not packed_instance_copy.get("packed_scene_instance")
            or packed_instance_copy.get("scene_path") != "res://packed_scene_2d.tscn"
            or packed_instance_copy.get("copied_node_count") != 3
        ):
            raise RuntimeError(
                "PackedScene instance duplication did not preserve the source boundary"
            )
        packed_copy_hierarchy = await app.service.scene_get_hierarchy(limit=200)
        if not _has_node(
            packed_copy_hierarchy, f"{packed_instance_copy_path}/AgentPackedOverride"
        ):
            raise RuntimeError("PackedScene duplication lost the local override child")
        await _expect_godot_error(
            app.service.node_duplicate(
                f"{packed_instance_path}/PackedSceneInternalSprite",
                scene_file=scene_file,
            ),
            "PACKED_SCENE_BOUNDARY",
        )
        moved_packed_copy = await app.service.node_reparent(
            packed_instance_copy_path,
            "/Main",
            scene_file=scene_file,
        )
        if not moved_packed_copy.get("packed_scene_instance"):
            raise RuntimeError(
                "Duplicated PackedScene instance could not be reparented"
            )

        transform_parent = await app.service.node_create(
            type_name="Node2D",
            name="TransformParent",
            parent_path="/Main",
            scene_file=scene_file,
        )
        transform_parent_path = transform_parent["path"]
        await app.service.node_set_properties(
            transform_parent_path,
            {"position": {"x": 100, "y": 50}},
            scene_file=scene_file,
        )
        reparented_marker = await app.service.node_reparent(
            marker_path,
            transform_parent_path,
            scene_file=scene_file,
        )
        marker_path = reparented_marker["path"]
        marker_properties = await app.service.node_get_properties(
            marker_path,
            fields=["position"],
            scene_file=scene_file,
        )
        if _property_value(marker_properties, "position") != {"x": -58.0, "y": -26.0}:
            raise RuntimeError("Reparent did not preserve the Node2D global position")

        follower = await app.service.node_create(
            type_name="RemoteTransform2D",
            name="TargetFollower",
            parent_path="/Main",
            scene_file=scene_file,
        )
        follower_path = follower["path"]
        await app.service.node_set_properties(
            follower_path,
            {"remote_path": "../UI/Panel/StartButton"},
            scene_file=scene_file,
        )
        renamed_button = await app.service.node_rename(
            "/Main/UI/Panel/StartButton",
            "RenamedButton",
            scene_file=scene_file,
        )
        renamed_button_path = renamed_button["path"]
        if renamed_button_path != "/Main/UI/Panel/RenamedButton":
            raise RuntimeError(f"Unexpected renamed path: {renamed_button_path}")
        if (
            renamed_button["migrated_node_paths"] < 1
            or renamed_button["migrated_animation_tracks"] < 1
        ):
            raise RuntimeError(
                f"Rename did not migrate NodePath and animation references: {renamed_button!r}"
            )
        follower_properties = await app.service.node_get_properties(
            follower_path,
            fields=["remote_path"],
            scene_file=scene_file,
        )
        if (
            _property_value(follower_properties, "remote_path")
            != "../UI/Panel/RenamedButton"
        ):
            raise RuntimeError("Rename did not update the RemoteTransform2D path")

        undo_rename = await app.service.scene_undo(scene_file=scene_file)
        if not undo_rename.get("changed"):
            raise RuntimeError("Rename was not undoable")
        follower_properties = await app.service.node_get_properties(
            follower_path,
            fields=["remote_path"],
            scene_file=scene_file,
        )
        if (
            _property_value(follower_properties, "remote_path")
            != "../UI/Panel/StartButton"
        ):
            raise RuntimeError("Undo did not restore the renamed NodePath")
        redo_rename = await app.service.scene_redo(scene_file=scene_file)
        if not redo_rename.get("changed"):
            raise RuntimeError("Rename was not redoable")

        reparented_button = await app.service.node_reparent(
            renamed_button_path,
            "/Main/UI",
            scene_file=scene_file,
        )
        reparented_button_path = reparented_button["path"]
        if reparented_button_path != "/Main/UI/RenamedButton":
            raise RuntimeError(f"Unexpected reparented path: {reparented_button_path}")
        if not reparented_button.get("kept_global_transform"):
            raise RuntimeError(
                "Reparent did not preserve the default global transform policy"
            )
        if (
            reparented_button["migrated_node_paths"] < 1
            or reparented_button["migrated_animation_tracks"] < 1
        ):
            raise RuntimeError(
                "Reparent did not migrate NodePath and animation references: "
                f"{reparented_button!r}"
            )
        follower_properties = await app.service.node_get_properties(
            follower_path,
            fields=["remote_path"],
            scene_file=scene_file,
        )
        if _property_value(follower_properties, "remote_path") != "../UI/RenamedButton":
            raise RuntimeError("Reparent did not update the RemoteTransform2D path")
        await app.service.scene_save(scene_file=scene_file)
        saved_scene = (project_path / "test_scene.tscn").read_text(encoding="utf-8")
        if 'NodePath("UI/RenamedButton:modulate")' not in saved_scene:
            raise RuntimeError("Reparent did not update the animation track path")

        undo_reparent = await app.service.scene_undo(scene_file=scene_file)
        if not undo_reparent.get("changed"):
            raise RuntimeError("Reparent was not undoable")
        follower_properties = await app.service.node_get_properties(
            follower_path,
            fields=["remote_path"],
            scene_file=scene_file,
        )
        if (
            _property_value(follower_properties, "remote_path")
            != "../UI/Panel/RenamedButton"
        ):
            raise RuntimeError("Undo did not restore the reparented NodePath")
        redo_reparent = await app.service.scene_redo(scene_file=scene_file)
        if not redo_reparent.get("changed"):
            raise RuntimeError("Reparent was not redoable")

        animation_list = await app.service.animation_list(
            "/Main/ButtonAnimations", scene_file=scene_file
        )
        if not _has_animation(animation_list, "", "button_pulse"):
            raise RuntimeError("Existing button animation was not listed")
        existing_animation = await app.service.animation_get(
            "/Main/ButtonAnimations", "button_pulse", scene_file=scene_file
        )
        if not _has_animation_track(
            existing_animation["animation"], reparented_button_path, "modulate"
        ):
            raise RuntimeError(
                "Animation track target was not resolved after reparenting"
            )
        await _expect_godot_error(
            app.service.animation_track_upsert(
                player_path="/Main/ButtonAnimations",
                animation="button_pulse",
                target_path=reparented_button_path,
                property="not_a_property",
                keys=[{"time": 0.0, "value": 1}],
                scene_file=scene_file,
            ),
            "PROPERTY_NOT_FOUND",
        )
        created_animation = await app.service.animation_create(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            length=0.2,
            loop_mode="pingpong",
            scene_file=scene_file,
        )
        if created_animation["animation"]["name"] != "button_hover":
            raise RuntimeError("Animation creation returned an unexpected name")
        track_update = await app.service.animation_track_upsert(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            target_path=reparented_button_path,
            property="scale",
            keys=[
                {"time": 0.0, "value": {"x": 1.0, "y": 1.0}},
                {"time": 0.2, "value": {"x": 1.08, "y": 1.08}, "transition": 0.5},
            ],
            interpolation="cubic",
            loop_wrap=False,
            scene_file=scene_file,
        )
        hover_track_index = track_update["track"]["index"]
        if track_update["track"]["target_path"] != reparented_button_path:
            raise RuntimeError("Animation track targeted the wrong node")
        if track_update["track"]["property"] != "scale":
            raise RuntimeError("Animation track targeted the wrong property")
        hover_animation = await app.service.animation_get(
            "/Main/ButtonAnimations", "button_hover", scene_file=scene_file
        )
        hover_track = _animation_track(
            hover_animation["animation"], reparented_button_path, "scale"
        )
        if hover_track["key_count"] != 2 or hover_track["interpolation"] != "cubic":
            raise RuntimeError(
                "Animation track did not retain its keyframe configuration"
            )
        key_update = await app.service.animation_key_upsert(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            track_index=hover_track_index,
            time=0.1,
            value={"x": 1.04, "y": 1.04},
            scene_file=scene_file,
        )
        if key_update["replaced_existing"]:
            raise RuntimeError("Animation key upsert unexpectedly replaced a new key")
        undo_key_update = await app.service.scene_undo(scene_file=scene_file)
        if not undo_key_update.get("changed"):
            raise RuntimeError("Animation key upsert was not undoable")
        hover_animation = await app.service.animation_get(
            "/Main/ButtonAnimations", "button_hover", scene_file=scene_file
        )
        hover_track = _animation_track(
            hover_animation["animation"], reparented_button_path, "scale"
        )
        if hover_track["key_count"] != 2:
            raise RuntimeError("Undo did not restore animation keys")
        redo_key_update = await app.service.scene_redo(scene_file=scene_file)
        if not redo_key_update.get("changed"):
            raise RuntimeError("Animation key upsert was not redoable")
        key_delete = await app.service.animation_key_delete(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            track_index=hover_track_index,
            time=0.1,
            scene_file=scene_file,
        )
        if key_delete["key_index"] < 0:
            raise RuntimeError("Animation key delete returned an invalid key index")
        undo_key_delete = await app.service.scene_undo(scene_file=scene_file)
        if not undo_key_delete.get("changed"):
            raise RuntimeError("Animation key delete was not undoable")
        track_delete = await app.service.animation_track_delete(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            track_index=hover_track_index,
            scene_file=scene_file,
        )
        if track_delete["track_index"] != hover_track_index:
            raise RuntimeError("Animation track delete returned an unexpected index")
        undo_track_delete = await app.service.scene_undo(scene_file=scene_file)
        if not undo_track_delete.get("changed"):
            raise RuntimeError("Animation track delete was not undoable")
        animation_delete = await app.service.animation_delete(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            scene_file=scene_file,
        )
        if animation_delete["name"] != "button_hover":
            raise RuntimeError("Animation delete returned an unexpected name")
        undo_animation_delete = await app.service.scene_undo(scene_file=scene_file)
        if not undo_animation_delete.get("changed"):
            raise RuntimeError("Animation delete was not undoable")
        await app.service.scene_save(scene_file=scene_file)
        saved_scene = (project_path / "test_scene.tscn").read_text(encoding="utf-8")
        if 'resource_name = "button_hover"' not in saved_scene:
            raise RuntimeError("Created animation was not saved in the scene")

        styled_button = await app.service.node_create(
            type_name="Button",
            name="StyledButton",
            parent_path="/Main/UI",
            scene_file=scene_file,
        )
        styled_button_path = styled_button["path"]
        await app.service.node_set_properties(
            styled_button_path,
            {"text": "Styled"},
            scene_file=scene_file,
        )
        initial_layout = await app.service.control_get_layout(
            styled_button_path,
            scene_file=scene_file,
        )
        if initial_layout["layout"]["container_managed"]:
            raise RuntimeError("Styled button should not be Container-managed")
        managed_button = await app.service.node_create(
            type_name="Button",
            name="ManagedButton",
            parent_path="/Main/UI/Panel",
            scene_file=scene_file,
        )
        await _expect_godot_error(
            app.service.control_set_layout(
                managed_button["path"],
                anchors={"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0},
                scene_file=scene_file,
            ),
            "CONTAINER_LAYOUT_MANAGED",
        )
        await app.service.node_delete(managed_button["path"], scene_file=scene_file)
        preset_layout = await app.service.control_set_layout_preset(
            styled_button_path,
            preset="full_rect",
            resize_mode="keep_size",
            margin=4,
            scene_file=scene_file,
        )
        if not _layout_sides_match(
            preset_layout["layout"]["anchors"],
            {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0},
        ):
            raise RuntimeError("Layout preset did not update anchors")
        undo_layout_preset = await app.service.scene_undo(scene_file=scene_file)
        if not undo_layout_preset.get("changed"):
            raise RuntimeError("Layout preset was not undoable")
        redo_layout_preset = await app.service.scene_redo(scene_file=scene_file)
        if not redo_layout_preset.get("changed"):
            raise RuntimeError("Layout preset was not redoable")
        exact_layout = await app.service.control_set_layout(
            styled_button_path,
            anchors={"left": 0.1, "top": 0.2, "right": 0.9, "bottom": 0.8},
            offsets={"left": 8.0, "top": 12.0, "right": -8.0, "bottom": -12.0},
            scene_file=scene_file,
        )
        if not _layout_sides_match(
            exact_layout["layout"]["anchors"],
            {"left": 0.1, "top": 0.2, "right": 0.9, "bottom": 0.8},
        ):
            raise RuntimeError("Exact layout did not retain requested anchors")
        if not _layout_sides_match(
            exact_layout["layout"]["offsets"],
            {"left": 8.0, "top": 12.0, "right": -8.0, "bottom": -12.0},
        ):
            raise RuntimeError("Exact layout did not retain requested offsets")
        undo_exact_layout = await app.service.scene_undo(scene_file=scene_file)
        if not undo_exact_layout.get("changed"):
            raise RuntimeError("Exact layout was not undoable")
        redo_exact_layout = await app.service.scene_redo(scene_file=scene_file)
        if not redo_exact_layout.get("changed"):
            raise RuntimeError("Exact layout was not redoable")
        styles_before = await app.service.control_get_styleboxes(
            styled_button_path,
            scene_file=scene_file,
        )
        if _stylebox_state(styles_before, "normal") is None:
            raise RuntimeError("Button normal style state was not returned")
        style_update = await app.service.control_stylebox_flat_upsert(
            styled_button_path,
            state="normal",
            properties={
                "bg_color": {"r": 0.08, "g": 0.3, "b": 0.55, "a": 1.0},
                "border_color": {"r": 0.25, "g": 0.75, "b": 1.0, "a": 1.0},
                "border_width_left": 2,
                "border_width_top": 2,
                "border_width_right": 2,
                "border_width_bottom": 2,
                "corner_radius_top_left": 10,
                "corner_radius_top_right": 10,
                "corner_radius_bottom_left": 10,
                "corner_radius_bottom_right": 10,
            },
            scene_file=scene_file,
        )
        normal_style = style_update["style"]
        if normal_style["effective_type"] != "StyleBoxFlat" or not _color_matches(
            normal_style["flat_properties"].get("bg_color"),
            {"r": 0.08, "g": 0.3, "b": 0.55, "a": 1.0},
        ):
            raise RuntimeError(
                "StyleBoxFlat override did not retain requested properties"
            )
        undo_style = await app.service.scene_undo(scene_file=scene_file)
        if not undo_style.get("changed"):
            raise RuntimeError("StyleBoxFlat update was not undoable")
        styles_after_undo = await app.service.control_get_styleboxes(
            styled_button_path,
            scene_file=scene_file,
        )
        if _stylebox_state(styles_after_undo, "normal").get("has_override"):
            raise RuntimeError("Undo did not remove the new StyleBoxFlat override")
        redo_style = await app.service.scene_redo(scene_file=scene_file)
        if not redo_style.get("changed"):
            raise RuntimeError("StyleBoxFlat update was not redoable")
        await app.service.control_stylebox_override_clear(
            styled_button_path,
            state="normal",
            scene_file=scene_file,
        )
        undo_style_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_style_clear.get("changed"):
            raise RuntimeError("StyleBoxFlat override clear was not undoable")
        await app.service.scene_save(scene_file=scene_file)
        saved_scene = (project_path / "test_scene.tscn").read_text(encoding="utf-8")
        if 'sub_resource type="StyleBoxFlat"' not in saved_scene:
            raise RuntimeError("StyleBoxFlat override was not saved in the scene")

        theme_before = await app.service.control_theme_get(
            styled_button_path,
            scene_file=scene_file,
        )
        if theme_before["theme"] is not None:
            raise RuntimeError("Styled button unexpectedly started with a local Theme")
        created_theme = await app.service.control_theme_create(
            styled_button_path,
            resource_name="SmokeUiTheme",
            scene_file=scene_file,
        )
        if (
            not created_theme["theme"]["built_in"]
            or created_theme["theme"]["resource_name"] != "SmokeUiTheme"
        ):
            raise RuntimeError("Embedded Theme creation returned an invalid resource")
        await app.service.control_theme_defaults_set(
            styled_button_path,
            font={"source": "system", "families": ["sans-serif"]},
            font_size=18,
            base_scale=1.25,
            scene_file=scene_file,
        )
        themed_state = await app.service.control_theme_get(
            styled_button_path, scene_file=scene_file
        )
        defaults = themed_state["theme"]["defaults"]
        if (
            defaults["font"]["resource_type"] != "SystemFont"
            or defaults["font_size"] != 18
            or not _is_close(defaults["base_scale"], 1.25)
        ):
            raise RuntimeError("Theme defaults did not retain system font settings")
        undo_theme_defaults = await app.service.scene_undo(scene_file=scene_file)
        if not undo_theme_defaults.get("changed"):
            raise RuntimeError("Theme default settings were not undoable")
        themed_state = await app.service.control_theme_get(
            styled_button_path, scene_file=scene_file
        )
        if any(
            value is not None for value in themed_state["theme"]["defaults"].values()
        ):
            raise RuntimeError("Undo did not clear newly-created Theme defaults")
        redo_theme_defaults = await app.service.scene_redo(scene_file=scene_file)
        if not redo_theme_defaults.get("changed"):
            raise RuntimeError("Theme default settings were not redoable")
        theme_color = await app.service.control_theme_item_upsert(
            styled_button_path,
            item_type="color",
            theme_type="Button",
            name="font_color",
            value={"r": 0.1, "g": 0.7, "b": 0.95, "a": 1.0},
            scene_file=scene_file,
        )
        if not _color_matches(
            theme_color["item"]["value"], {"r": 0.1, "g": 0.7, "b": 0.95, "a": 1.0}
        ):
            raise RuntimeError("Theme color item did not retain the requested value")
        theme_constant = await app.service.control_theme_item_upsert(
            styled_button_path,
            item_type="constant",
            theme_type="Button",
            name="outline_size",
            value=2,
            scene_file=scene_file,
        )
        if theme_constant["item"]["value"] != 2:
            raise RuntimeError("Theme constant item did not retain the requested value")
        theme_font_size = await app.service.control_theme_item_upsert(
            styled_button_path,
            item_type="font_size",
            theme_type="Button",
            name="font_size",
            value=20,
            scene_file=scene_file,
        )
        if theme_font_size["item"]["value"] != 20:
            raise RuntimeError(
                "Theme font size item did not retain the requested value"
            )
        theme_font = await app.service.control_theme_item_upsert(
            styled_button_path,
            item_type="font",
            theme_type="Button",
            name="font",
            value={"source": "system", "families": ["sans-serif"]},
            scene_file=scene_file,
        )
        if theme_font["item"]["value"]["resource_type"] != "SystemFont":
            raise RuntimeError("Theme font item did not create a SystemFont resource")
        theme_icon = await app.service.control_theme_item_upsert(
            styled_button_path,
            item_type="icon",
            theme_type="Button",
            name="icon",
            value="res://test_icon.svg",
            scene_file=scene_file,
        )
        if theme_icon["item"]["value"]["resource_type"] != "CompressedTexture2D":
            raise RuntimeError("Theme icon item did not load the project texture")
        theme_style = await app.service.control_theme_item_upsert(
            styled_button_path,
            item_type="stylebox_flat",
            theme_type="Button",
            name="normal",
            value={
                "bg_color": {"r": 0.04, "g": 0.12, "b": 0.22, "a": 1.0},
                "corner_radius_top_left": 6,
                "corner_radius_top_right": 6,
                "corner_radius_bottom_left": 6,
                "corner_radius_bottom_right": 6,
            },
            scene_file=scene_file,
        )
        if theme_style["item"]["value"]["resource"]["resource_type"] != "StyleBoxFlat":
            raise RuntimeError("Theme StyleBoxFlat item was not created")
        themed_state = await app.service.control_theme_get(
            styled_button_path, scene_file=scene_file
        )
        if (
            _theme_item(themed_state, "colors", "Button", "font_color") is None
            or _theme_item(themed_state, "constants", "Button", "outline_size") is None
            or _theme_item(themed_state, "font_sizes", "Button", "font_size") is None
            or _theme_item(themed_state, "fonts", "Button", "font") is None
            or _theme_item(themed_state, "icons", "Button", "icon") is None
            or _theme_item(themed_state, "styleboxes", "Button", "normal") is None
        ):
            raise RuntimeError("Theme inspection did not return all local Theme items")
        cleared_theme_color = await app.service.control_theme_item_clear(
            styled_button_path,
            item_type="color",
            theme_type="Button",
            name="font_color",
            scene_file=scene_file,
        )
        if cleared_theme_color["item_type"] != "color":
            raise RuntimeError("Theme item clear returned the wrong item type")
        undo_theme_item_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_theme_item_clear.get("changed"):
            raise RuntimeError("Theme item clear was not undoable")
        await app.service.control_theme_defaults_clear(
            styled_button_path,
            defaults=["font", "font_size", "base_scale"],
            scene_file=scene_file,
        )
        undo_theme_defaults_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_theme_defaults_clear.get("changed"):
            raise RuntimeError("Theme default clear was not undoable")
        external_theme = await app.service.control_theme_assign(
            styled_button_path,
            theme_path="res://test_theme.tres",
            scene_file=scene_file,
        )
        if external_theme["theme"]["resource_path"] != "res://test_theme.tres":
            raise RuntimeError(
                "External Theme assignment did not retain its project path"
            )
        await _expect_godot_error(
            app.service.control_theme_defaults_set(
                styled_button_path,
                font_size=20,
                scene_file=scene_file,
            ),
            "EXTERNAL_THEME_READ_ONLY",
        )
        undo_external_theme = await app.service.scene_undo(scene_file=scene_file)
        if not undo_external_theme.get("changed"):
            raise RuntimeError("External Theme assignment was not undoable")
        restored_theme = await app.service.control_theme_get(
            styled_button_path, scene_file=scene_file
        )
        if restored_theme["theme"]["resource_name"] != "SmokeUiTheme":
            raise RuntimeError("Undo did not restore the embedded Theme assignment")
        cleared_theme_assignment = await app.service.control_theme_assign(
            styled_button_path,
            theme_path="",
            scene_file=scene_file,
        )
        if cleared_theme_assignment["theme"] is not None:
            raise RuntimeError("Empty Theme path did not clear the local assignment")
        undo_theme_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_theme_clear.get("changed"):
            raise RuntimeError("Theme assignment clear was not undoable")
        await app.service.scene_save(scene_file=scene_file)
        saved_scene = (project_path / "test_scene.tscn").read_text(encoding="utf-8")
        if (
            "SmokeUiTheme" not in saved_scene
            or 'theme = SubResource("Theme_' not in saved_scene
        ):
            raise RuntimeError("Embedded Theme was not saved in the scene")

        button_signals = await app.service.node_get_signals(
            reparented_button_path,
            scene_file=scene_file,
        )
        if _signal_data(button_signals, "pressed") is None:
            raise RuntimeError("Button pressed signal was not returned")
        await _expect_godot_error(
            app.service.signal_connect(
                source_path=reparented_button_path,
                signal="pressed",
                target_path="/Main/ButtonAnimations",
                method="not_a_method",
                scene_file=scene_file,
            ),
            "TARGET_METHOD_NOT_FOUND",
        )
        signal_connection = await app.service.signal_connect(
            source_path=reparented_button_path,
            signal="pressed",
            target_path="/Main/ButtonAnimations",
            method="play",
            binds=["button_pulse"],
            deferred=True,
            one_shot=True,
            scene_file=scene_file,
        )
        if (
            not signal_connection.get("persistent")
            or not signal_connection.get("deferred")
            or not signal_connection.get("one_shot")
        ):
            raise RuntimeError("Signal connection was not persistent")
        button_signals = await app.service.node_get_signals(
            reparented_button_path,
            scene_file=scene_file,
        )
        if not _has_signal_connection(
            button_signals,
            "pressed",
            "/Main/ButtonAnimations",
            "play",
            ["button_pulse"],
        ):
            raise RuntimeError("Signal connection was not returned by node_get_signals")
        pressed_signal = _signal_data(button_signals, "pressed")
        if not any(
            connection.get("target_path") == "/Main/ButtonAnimations"
            and connection.get("method") == "play"
            and connection.get("deferred")
            and connection.get("one_shot")
            for connection in pressed_signal.get("connections", [])
        ):
            raise RuntimeError(
                "Signal connection flags were not returned by node_get_signals"
            )
        undo_connect = await app.service.scene_undo(scene_file=scene_file)
        if not undo_connect.get("changed"):
            raise RuntimeError("Signal connection was not undoable")
        button_signals = await app.service.node_get_signals(
            reparented_button_path,
            scene_file=scene_file,
        )
        if _has_signal_connection(
            button_signals,
            "pressed",
            "/Main/ButtonAnimations",
            "play",
            ["button_pulse"],
        ):
            raise RuntimeError("Undo did not remove the signal connection")
        redo_connect = await app.service.scene_redo(scene_file=scene_file)
        if not redo_connect.get("changed"):
            raise RuntimeError("Signal connection was not redoable")
        await app.service.signal_disconnect(
            source_path=reparented_button_path,
            signal="pressed",
            target_path="/Main/ButtonAnimations",
            method="play",
            scene_file=scene_file,
        )
        undo_disconnect = await app.service.scene_undo(scene_file=scene_file)
        if not undo_disconnect.get("changed"):
            raise RuntimeError("Signal disconnection was not undoable")
        await app.service.scene_save(scene_file=scene_file)
        saved_scene = (project_path / "test_scene.tscn").read_text(encoding="utf-8")
        if (
            'connection signal="pressed" from="UI/RenamedButton" to="ButtonAnimations"'
            ' method="play"' not in saved_scene
        ):
            raise RuntimeError("Persistent signal connection was not saved")

        child_label = await app.service.node_create(
            type_name="Label",
            name="MarkerLabel",
            parent_path=marker_path,
            scene_file=scene_file,
        )
        child_label_path = child_label["path"]
        await app.service.node_set_properties(
            child_label_path,
            {"text": "Nested node"},
            scene_file=scene_file,
        )

        marker_copy = await app.service.node_duplicate(
            marker_path,
            name="AgentMarkerCopy",
            scene_file=scene_file,
        )
        marker_copy_path = marker_copy["path"]
        marker_copy_label_path = f"{marker_copy_path}/MarkerLabel"
        if marker_copy["copied_node_count"] != 2:
            raise RuntimeError("Duplicate did not copy the whole local subtree")
        copy_label_properties = await app.service.node_get_properties(
            marker_copy_label_path,
            fields=["text"],
            scene_file=scene_file,
        )
        if _property_value(copy_label_properties, "text") != "Nested node":
            raise RuntimeError("Duplicate did not retain child properties")
        await _expect_godot_error(
            app.service.node_rename(
                marker_copy_path, "AgentMarker", scene_file=scene_file
            ),
            "NODE_NAME_CONFLICT",
        )
        await _expect_godot_error(
            app.service.node_reparent(
                marker_path,
                child_label_path,
                scene_file=scene_file,
            ),
            "NODE_CYCLE",
        )
        moved_copy = await app.service.node_move(
            marker_copy_path, index=0, scene_file=scene_file
        )
        if moved_copy.get("index") != 0:
            raise RuntimeError("Move did not report the requested sibling index")
        reordered = await app.service.scene_get_hierarchy(limit=30)
        reordered_marker_paths = [
            node["path"]
            for node in reordered["nodes"]
            if node.get("path") in {marker_path, marker_copy_path}
        ]
        if reordered_marker_paths != [marker_copy_path, marker_path]:
            raise RuntimeError("Move did not update sibling order")
        await _expect_godot_error(
            app.service.node_delete(reparented_button_path, scene_file=scene_file),
            "NODE_PATH_TARGET_DELETED",
        )

        button = await app.service.node_create(
            type_name="Button",
            name="AgentButton",
            parent_path="/Main/UI",
            scene_file=scene_file,
        )
        button_path = button["path"]
        await app.service.node_set_properties(
            button_path,
            {
                "text": "Created by MCP",
                "offset_left": 260.0,
                "offset_top": 24.0,
                "offset_right": 420.0,
                "offset_bottom": 72.0,
                "modulate": {"r": 0.8, "g": 0.9, "b": 1.0, "a": 1.0},
            },
            scene_file=scene_file,
        )
        button_properties = await app.service.node_get_properties(
            button_path,
            fields=["text", "modulate"],
            scene_file=scene_file,
        )
        if _property_value(button_properties, "text") != "Created by MCP":
            raise RuntimeError("Button text was not applied")
        actual_modulate = _property_value(button_properties, "modulate")
        if not _color_matches(
            actual_modulate,
            {
                "r": 0.8,
                "g": 0.9,
                "b": 1.0,
                "a": 1.0,
            },
        ):
            raise RuntimeError(f"Button color was not applied: {actual_modulate!r}")

        await app.service.node_delete(marker_path, scene_file=scene_file)
        undo_delete = await app.service.scene_undo(scene_file=scene_file)
        restored = await app.service.scene_get_hierarchy(limit=20)
        if (
            not undo_delete.get("changed")
            or not _has_node(restored, marker_path)
            or not _has_node(restored, child_label_path)
        ):
            raise RuntimeError("Deleted node subtree was not restored by undo")
        if _node_data(restored, child_label_path).get("owner_path") != "/Main":
            raise RuntimeError("Undo did not restore nested node ownership")
        redo_delete = await app.service.scene_redo(scene_file=scene_file)
        if not redo_delete.get("changed"):
            raise RuntimeError("Deleted node was not removable by redo")

        wall = await app.service.node_create(
            type_name="StaticBody2D",
            name="AgentWall",
            parent_path="/Main",
            scene_file=scene_file,
        )
        wall_path = wall["path"]
        wall_shape = await app.service.node_create(
            type_name="CollisionShape2D",
            name="AgentWallShape",
            parent_path=wall_path,
            scene_file=scene_file,
        )
        wall_shape_path = wall_shape["path"]
        initial_wall_shape = await app.service.collision_shape_get(
            wall_shape_path,
            scene_file=scene_file,
        )
        if initial_wall_shape["shape"] is not None:
            raise RuntimeError(
                "New CollisionShape2D unexpectedly had a Shape2D resource"
            )
        await _expect_godot_error(
            app.service.collision_shape_set(
                wall_shape_path,
                shape_type="circle",
                properties={"radius": 0.0},
                scene_file=scene_file,
            ),
            "INVALID_SHAPE_GEOMETRY",
        )
        shape_specs = [
            ("circle", {"radius": 12.0}, "CircleShape2D"),
            ("rectangle", {"size": {"x": 96.0, "y": 32.0}}, "RectangleShape2D"),
            (
                "capsule",
                {"radius": 8.0, "height": 32.0},
                "CapsuleShape2D",
            ),
            (
                "segment",
                {"a": {"x": -12.0, "y": 0.0}, "b": {"x": 12.0, "y": 0.0}},
                "SegmentShape2D",
            ),
            (
                "separation_ray",
                {"length": 24.0, "slide_on_slope": True},
                "SeparationRayShape2D",
            ),
            (
                "world_boundary",
                {"normal": {"x": 0.0, "y": -1.0}, "distance": 16.0},
                "WorldBoundaryShape2D",
            ),
            (
                "convex_polygon",
                {
                    "points": [
                        {"x": -12.0, "y": 8.0},
                        {"x": 0.0, "y": -12.0},
                        {"x": 12.0, "y": 8.0},
                    ]
                },
                "ConvexPolygonShape2D",
            ),
            (
                "concave_polygon",
                {
                    "segments": [
                        {"x": -12.0, "y": 0.0},
                        {"x": 12.0, "y": 0.0},
                        {"x": 0.0, "y": -12.0},
                        {"x": 0.0, "y": 12.0},
                    ]
                },
                "ConcavePolygonShape2D",
            ),
        ]
        for shape_type, shape_properties, expected_type in shape_specs:
            shape_update = await app.service.collision_shape_set(
                wall_shape_path,
                shape_type=shape_type,
                properties=shape_properties,
                scene_file=scene_file,
            )
            if shape_update["shape"]["resource_type"] != expected_type:
                raise RuntimeError(f"{shape_type} did not create {expected_type}")
        cleared_shape = await app.service.collision_shape_clear(
            wall_shape_path, scene_file=scene_file
        )
        if not cleared_shape["cleared"]:
            raise RuntimeError("CollisionShape2D clear did not report a change")
        undo_shape_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_shape_clear.get("changed"):
            raise RuntimeError("Collision shape clear was not undoable")
        restored_wall_shape = await app.service.collision_shape_get(
            wall_shape_path,
            scene_file=scene_file,
        )
        if restored_wall_shape["shape"]["resource_type"] != "ConcavePolygonShape2D":
            raise RuntimeError("Undo did not restore the collision shape resource")
        initial_layers = await app.service.collision_object_get_layers(
            wall_path, scene_file=scene_file
        )
        if initial_layers["layers"] != [1] or initial_layers["masks"] != [1]:
            raise RuntimeError("StaticBody2D did not expose default collision layers")
        updated_layers = await app.service.collision_object_set_layers(
            wall_path,
            layers=[2, 5],
            masks=[1, 3],
            scene_file=scene_file,
        )
        if updated_layers["layers"] != [2, 5] or updated_layers["masks"] != [1, 3]:
            raise RuntimeError("Collision layer number lists were not applied")
        undo_layers = await app.service.scene_undo(scene_file=scene_file)
        if not undo_layers.get("changed"):
            raise RuntimeError("Collision layer update was not undoable")
        restored_layers = await app.service.collision_object_get_layers(
            wall_path, scene_file=scene_file
        )
        if restored_layers["layers"] != [1] or restored_layers["masks"] != [1]:
            raise RuntimeError("Undo did not restore collision layer values")
        redo_layers = await app.service.scene_redo(scene_file=scene_file)
        if not redo_layers.get("changed"):
            raise RuntimeError("Collision layer update was not redoable")

        area = await app.service.node_create(
            type_name="Area2D",
            name="AgentGravityZone",
            parent_path="/Main",
            scene_file=scene_file,
        )
        area_path = area["path"]
        initial_area = await app.service.area_2d_get(area_path, scene_file=scene_file)
        if initial_area["configuration"]["gravity_space_override"] != "disabled":
            raise RuntimeError("Area2D did not expose readable gravity override names")
        await _expect_godot_error(
            app.service.area_2d_set(
                area_path,
                {"gravity_space_override": "not_a_mode"},
                scene_file=scene_file,
            ),
            "INVALID_PHYSICS_ENUM",
        )
        area_update = await app.service.area_2d_set(
            area_path,
            {
                "monitoring": False,
                "priority": 12,
                "gravity_space_override": "replace",
                "gravity_point": True,
                "gravity_point_center": {"x": 16.0, "y": -8.0},
                "gravity_point_unit_distance": 32.0,
                "gravity_direction": {"x": 0.0, "y": 1.0},
                "gravity": 420.0,
                "linear_damp_space_override": "combine_replace",
                "linear_damp": 2.0,
                "angular_damp_space_override": "replace_combine",
                "angular_damp": 3.0,
            },
            scene_file=scene_file,
        )
        if (
            area_update["configuration"]["gravity_space_override"] != "replace"
            or area_update["configuration"]["gravity"] != 420.0
            or area_update["configuration"]["monitoring"] is not False
        ):
            raise RuntimeError("Area2D semantic configuration was not applied")

        static_update = await app.service.physics_body_2d_set(
            wall_path,
            {
                "constant_linear_velocity": {"x": 24.0, "y": 0.0},
                "constant_angular_velocity": 0.5,
            },
            scene_file=scene_file,
        )
        if static_update["body_kind"] != "StaticBody2D" or static_update[
            "configuration"
        ]["constant_linear_velocity"] != {"x": 24.0, "y": 0.0}:
            raise RuntimeError("StaticBody2D configuration was not applied")
        static_state = await app.service.physics_body_2d_get(
            wall_path, scene_file=scene_file
        )
        if static_state["configuration"]["constant_angular_velocity"] != 0.5:
            raise RuntimeError(
                "physics_body_2d_get did not return the current StaticBody2D configuration"
            )

        animated_body = await app.service.node_create(
            type_name="AnimatableBody2D",
            name="AgentPlatform",
            parent_path="/Main",
            scene_file=scene_file,
        )
        animated_body_path = animated_body["path"]
        animated_update = await app.service.physics_body_2d_set(
            animated_body_path,
            {
                "constant_linear_velocity": {"x": 0.0, "y": 32.0},
                "sync_to_physics": False,
            },
            scene_file=scene_file,
        )
        if animated_update["configuration"]["sync_to_physics"] is not False:
            raise RuntimeError("AnimatableBody2D configuration was not applied")

        character_body = await app.service.node_create(
            type_name="CharacterBody2D",
            name="AgentCharacter",
            parent_path="/Main",
            scene_file=scene_file,
        )
        character_body_path = character_body["path"]
        character_update = await app.service.physics_body_2d_set(
            character_body_path,
            {
                "motion_mode": "grounded",
                "up_direction": {"x": 0.0, "y": -1.0},
                "velocity": {"x": 160.0, "y": 0.0},
                "max_slides": 6,
                "floor_snap_length": 8.0,
                "platform_on_leave": "add_upward_velocity",
                "platform_floor_layers": [1, 3],
                "platform_wall_layers": [2],
                "safe_margin": 0.08,
            },
            scene_file=scene_file,
        )
        character_configuration = character_update.get("configuration")
        if (
            not isinstance(character_configuration, dict)
            or character_configuration["platform_floor_layers"] != [1, 3]
            or character_configuration["platform_on_leave"] != "add_upward_velocity"
        ):
            raise RuntimeError(
                f"CharacterBody2D semantic configuration was not applied: {character_update!r}"
            )

        rigid_body = await app.service.node_create(
            type_name="RigidBody2D",
            name="AgentRigidBody",
            parent_path="/Main",
            scene_file=scene_file,
        )
        rigid_body_path = rigid_body["path"]
        rigid_update = await app.service.physics_body_2d_set(
            rigid_body_path,
            {
                "mass": 2.5,
                "gravity_scale": 0.5,
                "center_of_mass_mode": "custom",
                "center_of_mass": {"x": 4.0, "y": -2.0},
                "freeze_mode": "kinematic",
                "continuous_cd": "cast_shape",
                "contact_monitor": True,
                "max_contacts_reported": 8,
                "linear_damp_mode": "replace",
                "linear_damp": 0.5,
                "angular_damp_mode": "combine",
                "angular_damp": 0.25,
            },
            scene_file=scene_file,
        )
        if (
            rigid_update["body_kind"] != "RigidBody2D"
            or rigid_update["configuration"]["center_of_mass_mode"] != "custom"
            or rigid_update["configuration"]["continuous_cd"] != "cast_shape"
        ):
            raise RuntimeError("RigidBody2D semantic configuration was not applied")

        pin_joint = await app.service.node_create(
            type_name="PinJoint2D",
            name="AgentPinJoint",
            parent_path="/Main",
            scene_file=scene_file,
        )
        pin_joint_path = pin_joint["path"]
        await _expect_godot_error(
            app.service.joint_2d_set(
                pin_joint_path,
                node_a_path=area_path,
                scene_file=scene_file,
            ),
            "JOINT_ENDPOINT_BODY_REQUIRED",
        )
        pin_update = await app.service.joint_2d_set(
            pin_joint_path,
            properties={
                "bias": 0.2,
                "softness": 0.5,
                "angular_limit_enabled": True,
                "angular_limit_lower": -0.5,
                "angular_limit_upper": 0.5,
                "motor_enabled": True,
                "motor_target_velocity": 1.0,
            },
            node_a_path=rigid_body_path,
            node_b_path=wall_path,
            scene_file=scene_file,
        )
        if (
            pin_update["node_a_path"] != rigid_body_path
            or pin_update["node_b_path"] != wall_path
            or pin_update["configuration"]["angular_limit_enabled"] is not True
        ):
            raise RuntimeError(
                "PinJoint2D configuration or endpoint path was not applied"
            )
        pin_state = await app.service.joint_2d_get(
            pin_joint_path, scene_file=scene_file
        )
        if (
            pin_state["node_a_path"] != rigid_body_path
            or pin_state["configuration"]["softness"] != 0.5
        ):
            raise RuntimeError(
                "joint_2d_get did not return the current PinJoint2D configuration"
            )

        groove_joint = await app.service.node_create(
            type_name="GrooveJoint2D",
            name="AgentGrooveJoint",
            parent_path="/Main",
            scene_file=scene_file,
        )
        groove_update = await app.service.joint_2d_set(
            groove_joint["path"],
            properties={"bias": 0.3, "length": 96.0, "initial_offset": 24.0},
            node_a_path=character_body_path,
            node_b_path=wall_path,
            scene_file=scene_file,
        )
        if groove_update["configuration"]["length"] != 96.0:
            raise RuntimeError("GrooveJoint2D configuration was not applied")

        spring_joint = await app.service.node_create(
            type_name="DampedSpringJoint2D",
            name="AgentSpringJoint",
            parent_path="/Main",
            scene_file=scene_file,
        )
        spring_joint_path = spring_joint["path"]
        spring_update = await app.service.joint_2d_set(
            spring_joint_path,
            properties={
                "bias": 0.4,
                "length": 80.0,
                "rest_length": 60.0,
                "stiffness": 12.0,
                "damping": 0.8,
            },
            node_a_path=rigid_body_path,
            node_b_path=animated_body_path,
            scene_file=scene_file,
        )
        if spring_update["configuration"]["stiffness"] != 12.0:
            raise RuntimeError("DampedSpringJoint2D configuration was not applied")
        undo_spring = await app.service.scene_undo(scene_file=scene_file)
        if not undo_spring.get("changed"):
            raise RuntimeError("Joint configuration was not undoable")
        redo_spring = await app.service.scene_redo(scene_file=scene_file)
        if not redo_spring.get("changed"):
            raise RuntimeError("Joint configuration was not redoable")

        ray_cast = await app.service.node_create(
            type_name="RayCast2D",
            name="AgentGroundRay",
            parent_path="/Main",
            scene_file=scene_file,
        )
        ray_cast_path = ray_cast["path"]
        initial_ray_cast = await app.service.ray_cast_2d_get(
            ray_cast_path, scene_file=scene_file
        )
        if initial_ray_cast["masks"] != [1]:
            raise RuntimeError("RayCast2D did not expose its default collision mask")
        ray_cast_update = await app.service.ray_cast_2d_set(
            ray_cast_path,
            properties={
                "enabled": True,
                "exclude_parent": False,
                "target_position": {"x": 96.0, "y": 24.0},
                "hit_from_inside": True,
                "collide_with_areas": True,
                "collide_with_bodies": True,
            },
            masks=[2, 4],
            scene_file=scene_file,
        )
        if (
            ray_cast_update["masks"] != [2, 4]
            or ray_cast_update["configuration"]["target_position"]
            != {"x": 96.0, "y": 24.0}
            or ray_cast_update["configuration"]["hit_from_inside"] is not True
        ):
            raise RuntimeError("RayCast2D configuration was not applied")

        shape_cast = await app.service.node_create(
            type_name="ShapeCast2D",
            name="AgentShapeCast",
            parent_path="/Main",
            scene_file=scene_file,
        )
        shape_cast_path = shape_cast["path"]
        initial_shape_cast = await app.service.shape_cast_2d_get(
            shape_cast_path, scene_file=scene_file
        )
        if initial_shape_cast["shape"] is not None:
            raise RuntimeError("New ShapeCast2D unexpectedly had a Shape2D resource")
        await _expect_godot_error(
            app.service.shape_cast_2d_set(
                shape_cast_path,
                shape_type="circle",
                shape_properties={"radius": 0.0},
                scene_file=scene_file,
            ),
            "INVALID_SHAPE_GEOMETRY",
        )
        shape_cast_update = await app.service.shape_cast_2d_set(
            shape_cast_path,
            properties={
                "enabled": True,
                "target_position": {"x": 48.0, "y": 0.0},
                "margin": 1.5,
                "max_results": 12,
                "collide_with_areas": True,
            },
            masks=[1, 3],
            shape_type="circle",
            shape_properties={"radius": 16.0},
            scene_file=scene_file,
        )
        if (
            shape_cast_update["shape"]["resource_type"] != "CircleShape2D"
            or shape_cast_update["masks"] != [1, 3]
            or shape_cast_update["configuration"]["max_results"] != 12
        ):
            raise RuntimeError("ShapeCast2D configuration or Shape2D was not applied")
        cleared_shape_cast = await app.service.shape_cast_2d_shape_clear(
            shape_cast_path, scene_file=scene_file
        )
        if not cleared_shape_cast["cleared"]:
            raise RuntimeError("ShapeCast2D clear did not report a change")
        undo_shape_cast_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_shape_cast_clear.get("changed"):
            raise RuntimeError("ShapeCast2D clear was not undoable")
        restored_shape_cast = await app.service.shape_cast_2d_get(
            shape_cast_path, scene_file=scene_file
        )
        if restored_shape_cast["shape"]["resource_type"] != "CircleShape2D":
            raise RuntimeError("Undo did not restore the ShapeCast2D Shape2D resource")

        navigation_region = await app.service.node_create(
            type_name="NavigationRegion2D",
            name="AgentNavigationRegion",
            parent_path="/Main",
            scene_file=scene_file,
        )
        navigation_region_path = navigation_region["path"]
        region_update = await app.service.navigation_2d_set(
            navigation_region_path,
            {
                "enabled": True,
                "use_edge_connections": False,
                "navigation_layers": [1, 3],
                "enter_cost": 2.0,
                "travel_cost": 1.5,
            },
            scene_file=scene_file,
        )
        if (
            region_update["navigation_kind"] != "NavigationRegion2D"
            or region_update["configuration"]["navigation_layers"] != [1, 3]
            or region_update["configuration"]["travel_cost"] != 1.5
        ):
            raise RuntimeError("NavigationRegion2D configuration was not applied")
        navigation_polygon_vertices = [
            {"x": 0.0, "y": 0.0},
            {"x": 192.0, "y": 0.0},
            {"x": 192.0, "y": 96.0},
            {"x": 0.0, "y": 96.0},
        ]
        initial_navigation_polygon = await app.service.navigation_polygon_get(
            navigation_region_path, scene_file=scene_file
        )
        if initial_navigation_polygon["navigation_polygon"] is not None:
            raise RuntimeError(
                "New NavigationRegion2D unexpectedly had a NavigationPolygon resource"
            )
        await _expect_godot_error(
            app.service.navigation_polygon_geometry_set(
                navigation_region_path,
                navigation_polygon_vertices,
                [[0, 1, 2, 3]],
                scene_file=scene_file,
            ),
            "NAVIGATION_POLYGON_NOT_ASSIGNED",
        )
        created_navigation_polygon = await app.service.navigation_polygon_create(
            navigation_region_path, agent_radius=12.0, scene_file=scene_file
        )
        if created_navigation_polygon["navigation_polygon"]["agent_radius"] != 12.0:
            raise RuntimeError("NavigationPolygon creation did not set agent_radius")
        await _expect_godot_error(
            app.service.navigation_polygon_bake_request(
                navigation_region_path, scene_file=scene_file
            ),
            "NAVIGATION_POLYGON_OUTLINES_REQUIRED",
        )
        direct_navigation_polygon = await app.service.navigation_polygon_geometry_set(
            navigation_region_path,
            navigation_polygon_vertices,
            [[0, 1, 2, 3]],
            agent_radius=8.0,
            scene_file=scene_file,
        )
        if direct_navigation_polygon["navigation_polygon"][
            "agent_radius"
        ] != 8.0 or direct_navigation_polygon["navigation_polygon"]["polygons"] != [
            [0, 1, 2, 3]
        ]:
            raise RuntimeError("NavigationPolygon direct geometry was not applied")
        outlined_navigation_polygon = await app.service.navigation_polygon_outline_set(
            navigation_region_path, navigation_polygon_vertices, scene_file=scene_file
        )
        if outlined_navigation_polygon["outline_index"] != 0:
            raise RuntimeError("NavigationPolygon outline was not appended")
        baked_navigation_polygon = (
            await app.service.navigation_polygon_make_from_outlines(
                navigation_region_path, scene_file=scene_file
            )
        )
        if not baked_navigation_polygon["navigation_polygon"]["polygons"]:
            raise RuntimeError("NavigationPolygon did not build polygons from outlines")
        removed_outline = await app.service.navigation_polygon_outline_remove(
            navigation_region_path, 0, scene_file=scene_file
        )
        if removed_outline["navigation_polygon"]["outlines"]:
            raise RuntimeError("NavigationPolygon outline was not removed")
        undo_outline_remove = await app.service.scene_undo(scene_file=scene_file)
        if not undo_outline_remove.get("changed"):
            raise RuntimeError("NavigationPolygon outline removal was not undoable")
        restored_outline = await app.service.navigation_polygon_get(
            navigation_region_path, scene_file=scene_file
        )
        if len(restored_outline["navigation_polygon"]["outlines"]) != 1:
            raise RuntimeError("Undo did not restore the NavigationPolygon outline")
        redo_outline_remove = await app.service.scene_redo(scene_file=scene_file)
        if not redo_outline_remove.get("changed"):
            raise RuntimeError("NavigationPolygon outline removal was not redoable")
        cleared_navigation_polygon = await app.service.navigation_polygon_clear(
            navigation_region_path, scene_file=scene_file
        )
        if cleared_navigation_polygon["navigation_polygon"] is not None:
            raise RuntimeError("NavigationPolygon resource was not detached")
        undo_navigation_polygon_clear = await app.service.scene_undo(
            scene_file=scene_file
        )
        if not undo_navigation_polygon_clear.get("changed"):
            raise RuntimeError("NavigationPolygon clear was not undoable")
        restored_navigation_polygon = await app.service.navigation_polygon_get(
            navigation_region_path, scene_file=scene_file
        )
        if not restored_navigation_polygon["navigation_polygon"]["polygons"]:
            raise RuntimeError("Undo did not restore the NavigationPolygon resource")
        bake_outline = await app.service.navigation_polygon_outline_set(
            navigation_region_path, navigation_polygon_vertices, scene_file=scene_file
        )
        if bake_outline["outline_index"] != 0:
            raise RuntimeError("NavigationPolygon bake outline was not appended")
        navigation_bake_settings = {
            "agent_radius": 4.0,
            "cell_size": 2.0,
            "border_size": 4.0,
            "baking_rect": {
                "position": {"x": 0.0, "y": 0.0},
                "size": {"x": 192.0, "y": 96.0},
            },
            "baking_rect_offset": {"x": 0.0, "y": 0.0},
            "sample_partition_type": "triangulate",
            "parsed_geometry_type": "static_colliders",
            "parsed_collision_layers": [2, 5],
        }
        navigation_bake_request = await app.service.navigation_polygon_bake_request(
            navigation_region_path,
            source_root_path=wall_path,
            settings=navigation_bake_settings,
            scene_file=scene_file,
        )
        if (
            navigation_bake_request.get("status") not in {"pending", "ready"}
            or navigation_bake_request.get("source_root_path") != wall_path
            or navigation_bake_request.get("source_geometry", {}).get("obstruction_outline_count", 0)
            < 1
            or navigation_bake_request.get("source_geometry", {})
            .get("bounds", {})
            .get("size", {})
            .get("x", 0.0)
            <= 0.0
        ):
            raise RuntimeError(
                f"NavigationPolygon source geometry bake was not started: {navigation_bake_request}"
            )
        navigation_bake_result = await _wait_for_navigation_polygon_bake(
            app, navigation_bake_request["request_id"]
        )
        baked_result_polygon = navigation_bake_result.get("result", {}).get(
            "navigation_polygon", {}
        )
        if (
            navigation_bake_result.get("status") != "ready"
            or not baked_result_polygon.get("polygons")
            or baked_result_polygon.get("agent_radius") != 4.0
            or baked_result_polygon.get("bake_settings", {}).get("cell_size") != 2.0
            or baked_result_polygon.get("bake_settings", {}).get("border_size") != 4.0
            or baked_result_polygon.get("bake_settings", {}).get("baking_rect")
            != navigation_bake_settings["baking_rect"]
            or baked_result_polygon.get("bake_settings", {}).get("baking_rect_offset")
            != navigation_bake_settings["baking_rect_offset"]
            or baked_result_polygon.get("bake_settings", {}).get("sample_partition_type")
            != "triangulate"
            or baked_result_polygon.get("bake_settings", {}).get("parsed_geometry_type")
            != "static_colliders"
            or baked_result_polygon.get("bake_settings", {}).get("parsed_collision_layers")
            != [2, 5]
        ):
            raise RuntimeError(
                f"NavigationPolygon source geometry bake did not complete: {navigation_bake_result}"
            )
        undo_navigation_bake = await app.service.scene_undo(scene_file=scene_file)
        if not undo_navigation_bake.get("changed"):
            raise RuntimeError("NavigationPolygon source geometry bake was not undoable")
        navigation_before_bake_redo = await app.service.navigation_polygon_get(
            navigation_region_path, scene_file=scene_file
        )
        if navigation_before_bake_redo["navigation_polygon"]["agent_radius"] != 8.0:
            raise RuntimeError("Undo did not restore the pre-bake NavigationPolygon")
        redo_navigation_bake = await app.service.scene_redo(scene_file=scene_file)
        if not redo_navigation_bake.get("changed"):
            raise RuntimeError("NavigationPolygon source geometry bake was not redoable")
        navigation_after_bake_redo = await app.service.navigation_polygon_get(
            navigation_region_path, scene_file=scene_file
        )
        if navigation_after_bake_redo["navigation_polygon"]["agent_radius"] != 4.0:
            raise RuntimeError("Redo did not restore the baked NavigationPolygon")

        navigation_agent = await app.service.node_create(
            type_name="NavigationAgent2D",
            name="AgentNavigationAgent",
            parent_path="/Main",
            scene_file=scene_file,
        )
        navigation_agent_path = navigation_agent["path"]
        agent_update = await app.service.navigation_2d_set(
            navigation_agent_path,
            {
                "target_position": {"x": 320.0, "y": 160.0},
                "path_desired_distance": 8.0,
                "target_desired_distance": 6.0,
                "path_max_distance": 160.0,
                "navigation_layers": [1],
                "pathfinding_algorithm": "astar",
                "path_postprocessing": "edge_centered",
                "simplify_path": True,
                "simplify_epsilon": 1.5,
                "avoidance_enabled": True,
                "radius": 12.0,
                "neighbor_distance": 120.0,
                "max_neighbors": 8,
                "time_horizon_agents": 1.5,
                "max_speed": 240.0,
                "avoidance_layers": [2],
                "avoidance_mask": [1, 3],
                "avoidance_priority": 0.5,
            },
            scene_file=scene_file,
        )
        if (
            agent_update["configuration"]["path_postprocessing"] != "edge_centered"
            or agent_update["configuration"]["avoidance_layers"] != [2]
            or agent_update["configuration"]["avoidance_mask"] != [1, 3]
        ):
            raise RuntimeError("NavigationAgent2D configuration was not applied")

        navigation_obstacle = await app.service.node_create(
            type_name="NavigationObstacle2D",
            name="AgentNavigationObstacle",
            parent_path="/Main",
            scene_file=scene_file,
        )
        obstacle_update = await app.service.navigation_2d_set(
            navigation_obstacle["path"],
            {
                "radius": 16.0,
                "vertices": [
                    {"x": -12.0, "y": -12.0},
                    {"x": 12.0, "y": -12.0},
                    {"x": 12.0, "y": 12.0},
                    {"x": -12.0, "y": 12.0},
                ],
                "affect_navigation_mesh": True,
                "carve_navigation_mesh": True,
                "avoidance_enabled": True,
                "velocity": {"x": 20.0, "y": 0.0},
                "avoidance_layers": [2],
            },
            scene_file=scene_file,
        )
        if obstacle_update["configuration"]["radius"] != 16.0 or obstacle_update[
            "configuration"
        ]["avoidance_layers"] != [2]:
            raise RuntimeError("NavigationObstacle2D configuration was not applied")

        navigation_link = await app.service.node_create(
            type_name="NavigationLink2D",
            name="AgentNavigationLink",
            parent_path="/Main",
            scene_file=scene_file,
        )
        navigation_link_path = navigation_link["path"]
        link_update = await app.service.navigation_2d_set(
            navigation_link_path,
            {
                "enabled": True,
                "bidirectional": False,
                "navigation_layers": [1, 4],
                "start_position": {"x": 0.0, "y": 0.0},
                "end_position": {"x": 128.0, "y": 32.0},
                "enter_cost": 1.0,
                "travel_cost": 2.0,
            },
            scene_file=scene_file,
        )
        if (
            link_update["configuration"]["navigation_layers"] != [1, 4]
            or link_update["configuration"]["bidirectional"] is not False
        ):
            raise RuntimeError("NavigationLink2D configuration was not applied")
        navigation_link_state = await app.service.navigation_2d_get(
            navigation_link_path, scene_file=scene_file
        )
        if navigation_link_state["configuration"]["end_position"] != {
            "x": 128.0,
            "y": 32.0,
        }:
            raise RuntimeError(
                "navigation_2d_get did not return the current NavigationLink2D configuration"
            )
        undo_navigation_link = await app.service.scene_undo(scene_file=scene_file)
        if not undo_navigation_link.get("changed"):
            raise RuntimeError("NavigationLink2D configuration was not undoable")
        redo_navigation_link = await app.service.scene_redo(scene_file=scene_file)
        if not redo_navigation_link.get("changed"):
            raise RuntimeError("NavigationLink2D configuration was not redoable")

        patrol_path = await app.service.node_create(
            type_name="Path2D",
            name="AgentPatrolPath",
            parent_path="/Main",
            scene_file=scene_file,
        )
        patrol_path_path = patrol_path["path"]
        initial_patrol_path = await app.service.path_2d_get(
            patrol_path_path, scene_file=scene_file
        )
        if (
            initial_patrol_path["curve"] is not None
            or initial_patrol_path["total_points"] != 0
        ):
            raise RuntimeError("New Path2D unexpectedly had a Curve2D resource")
        patrol_points = [
            {
                "position": {"x": 0.0, "y": 0.0},
                "out": {"x": 32.0, "y": 0.0},
            },
            {
                "position": {"x": 128.0, "y": 64.0},
                "in": {"x": -32.0, "y": 0.0},
            },
            {"position": {"x": 256.0, "y": 0.0}},
        ]
        patrol_curve = await app.service.path_2d_curve_set(
            patrol_path_path,
            patrol_points,
            bake_interval=2.5,
            scene_file=scene_file,
        )
        if (
            patrol_curve["curve"] is None
            or patrol_curve["curve"]["embedded"] is not True
            or not _is_close(patrol_curve["curve"]["bake_interval"], 2.5)
            or patrol_curve["total_points"] != 3
            or patrol_curve["points"][1]["in"] != {"x": -32.0, "y": 0.0}
        ):
            raise RuntimeError("Path2D Curve2D was not created")
        paged_patrol_path = await app.service.path_2d_get(
            patrol_path_path, offset=1, limit=1, scene_file=scene_file
        )
        if (
            paged_patrol_path["points"]
            != [
                {
                    "index": 1,
                    "position": {"x": 128.0, "y": 64.0},
                    "in": {"x": -32.0, "y": 0.0},
                    "out": {"x": 0.0, "y": 0.0},
                }
            ]
            or paged_patrol_path["truncated"] is not True
        ):
            raise RuntimeError("path_2d_get did not return a stable Curve2D point page")
        inserted_patrol_point = await app.service.path_2d_curve_point_insert(
            patrol_path_path,
            {"position": {"x": 64.0, "y": 16.0}},
            index=1,
            scene_file=scene_file,
        )
        if (
            inserted_patrol_point["point_index"] != 1
            or inserted_patrol_point["total_points"] != 4
        ):
            raise RuntimeError("Path2D Curve2D point insertion was not applied")
        updated_patrol_point = await app.service.path_2d_curve_point_set(
            patrol_path_path,
            2,
            {
                "position": {"x": 144.0, "y": 72.0},
                "in": {"x": -24.0, "y": -8.0},
                "out": {"x": 16.0, "y": 12.0},
            },
            scene_file=scene_file,
        )
        if updated_patrol_point["points"][2]["out"] != {"x": 16.0, "y": 12.0}:
            raise RuntimeError("Path2D Curve2D point update was not applied")
        await _expect_godot_error(
            app.service.path_2d_curve_point_remove(
                patrol_path_path, 4, scene_file=scene_file
            ),
            "PATH_CURVE_POINT_NOT_FOUND",
        )
        removed_patrol_point = await app.service.path_2d_curve_point_remove(
            patrol_path_path, 0, scene_file=scene_file
        )
        if (
            removed_patrol_point["removed_point_index"] != 0
            or removed_patrol_point["total_points"] != 3
        ):
            raise RuntimeError("Path2D Curve2D point removal was not applied")
        undo_patrol_point_remove = await app.service.scene_undo(scene_file=scene_file)
        if not undo_patrol_point_remove.get("changed"):
            raise RuntimeError("Path2D Curve2D point removal was not undoable")
        restored_patrol_path = await app.service.path_2d_get(
            patrol_path_path, scene_file=scene_file
        )
        if restored_patrol_path["total_points"] != 4:
            raise RuntimeError("Undo did not restore the Path2D Curve2D point")
        redo_patrol_point_remove = await app.service.scene_redo(scene_file=scene_file)
        if not redo_patrol_point_remove.get("changed"):
            raise RuntimeError("Path2D Curve2D point removal was not redoable")
        cleared_patrol_curve = await app.service.path_2d_curve_clear(
            patrol_path_path, scene_file=scene_file
        )
        if cleared_patrol_curve["curve"] is not None:
            raise RuntimeError("Path2D Curve2D was not cleared")
        undo_patrol_curve_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_patrol_curve_clear.get("changed"):
            raise RuntimeError("Path2D Curve2D clear was not undoable")
        restored_patrol_curve = await app.service.path_2d_get(
            patrol_path_path, scene_file=scene_file
        )
        if (
            restored_patrol_curve["curve"] is None
            or restored_patrol_curve["total_points"] != 3
        ):
            raise RuntimeError("Undo did not restore the Path2D Curve2D resource")

        skeleton = await app.service.node_create(
            type_name="Skeleton2D",
            name="AgentSkeleton",
            parent_path="/Main",
            scene_file=scene_file,
        )
        skeleton_path = skeleton["path"]
        empty_skeleton = await app.service.skeleton_2d_get(
            skeleton_path, scene_file=scene_file
        )
        if empty_skeleton["bone_count"] != 0 or empty_skeleton["bones"]:
            raise RuntimeError("New Skeleton2D did not report an empty bone hierarchy")
        root_bone = await app.service.skeleton_2d_bone_create(
            skeleton_path,
            name="AgentRootBone",
            scene_file=scene_file,
        )
        root_bone_path = root_bone["path"]
        child_bone = await app.service.skeleton_2d_bone_create(
            skeleton_path,
            name="AgentChildBone",
            parent_bone_path=root_bone_path,
            rest={
                "x": {"x": 1.0, "y": 0.0},
                "y": {"x": 0.0, "y": 1.0},
                "origin": {"x": 48.0, "y": 0.0},
            },
            scene_file=scene_file,
        )
        child_bone_path = child_bone["path"]
        initial_skeleton = await app.service.skeleton_2d_get(
            skeleton_path, scene_file=scene_file
        )
        if initial_skeleton["bone_count"] != 2 or {
            bone["path"] for bone in initial_skeleton["bones"]
        } != {root_bone_path, child_bone_path}:
            raise RuntimeError("Skeleton2D did not discover its Bone2D hierarchy")
        initial_root_bone = await app.service.bone_2d_get(
            root_bone_path, scene_file=scene_file
        )
        if (
            not initial_root_bone["valid_hierarchy"]
            or initial_root_bone["skeleton_path"] != skeleton_path
        ):
            raise RuntimeError("Bone2D hierarchy metadata was not resolved")
        root_rest = {
            "x": {"x": 1.0, "y": 0.0},
            "y": {"x": 0.0, "y": 1.0},
            "origin": {"x": 32.0, "y": 8.0},
        }
        root_bone_update = await app.service.bone_2d_set(
            root_bone_path,
            {
                "rest": root_rest,
                "auto_calculate_length_and_angle": False,
                "length": 48.0,
                "angle_degrees": 15.0,
            },
            scene_file=scene_file,
        )
        if (
            root_bone_update["rest"] != root_rest
            or root_bone_update["auto_calculate_length_and_angle"] is not False
            or not _is_close(root_bone_update["length"], 48.0)
            or not _is_close(root_bone_update["angle_degrees"], 15.0)
        ):
            raise RuntimeError("Bone2D semantic configuration was not applied")
        reset_skeleton = await app.service.skeleton_2d_reset_to_rest(
            skeleton_path, scene_file=scene_file
        )
        if not reset_skeleton.get("changed"):
            raise RuntimeError("Skeleton2D reset-to-rest was not applied")
        reset_root_bone = await app.service.bone_2d_get(
            root_bone_path, scene_file=scene_file
        )
        if reset_root_bone["transform"] != root_rest:
            raise RuntimeError(
                "Skeleton2D reset-to-rest did not restore the Bone2D transform"
            )
        undo_skeleton_reset = await app.service.scene_undo(scene_file=scene_file)
        if not undo_skeleton_reset.get("changed"):
            raise RuntimeError("Skeleton2D reset-to-rest was not undoable")
        restored_root_transform = await app.service.bone_2d_get(
            root_bone_path, scene_file=scene_file
        )
        if restored_root_transform["transform"] == root_rest:
            raise RuntimeError(
                "Undo did not restore the Bone2D transform before reset-to-rest"
            )
        redo_skeleton_reset = await app.service.scene_redo(scene_file=scene_file)
        if not redo_skeleton_reset.get("changed"):
            raise RuntimeError("Skeleton2D reset-to-rest was not redoable")
        await app.service.node_set_properties(
            root_bone_path,
            {"position": {"x": 64.0, "y": 16.0}},
            scene_file=scene_file,
        )
        made_rest = await app.service.skeleton_2d_make_rest_from_current(
            skeleton_path, scene_file=scene_file
        )
        if not made_rest.get("changed"):
            raise RuntimeError("Skeleton2D make-rest-from-current was not applied")
        current_rest_root_bone = await app.service.bone_2d_get(
            root_bone_path, scene_file=scene_file
        )
        if current_rest_root_bone["rest"]["origin"] != {"x": 64.0, "y": 16.0}:
            raise RuntimeError(
                "Skeleton2D did not copy the current Bone2D transform to rest"
            )
        undo_make_rest = await app.service.scene_undo(scene_file=scene_file)
        if not undo_make_rest.get("changed"):
            raise RuntimeError("Skeleton2D make-rest-from-current was not undoable")
        restored_rest_root_bone = await app.service.bone_2d_get(
            root_bone_path, scene_file=scene_file
        )
        if restored_rest_root_bone["rest"] != root_rest:
            raise RuntimeError("Undo did not restore the previous Skeleton2D rest pose")
        redo_make_rest = await app.service.scene_redo(scene_file=scene_file)
        if not redo_make_rest.get("changed"):
            raise RuntimeError("Skeleton2D make-rest-from-current was not redoable")

        audio_player = await app.service.node_create(
            type_name="AudioStreamPlayer2D",
            name="AgentSound",
            parent_path="/Main",
            scene_file=scene_file,
        )
        audio_player_path = audio_player["path"]
        initial_audio_player = await app.service.audio_stream_player_2d_get(
            audio_player_path, scene_file=scene_file
        )
        if (
            initial_audio_player["configuration"]["stream_path"] != ""
            or "Master" not in initial_audio_player["available_buses"]
        ):
            raise RuntimeError(
                "New AudioStreamPlayer2D had unexpected stream or bus state"
            )
        await _expect_godot_error(
            app.service.audio_stream_player_2d_set(
                audio_player_path,
                {"stream_path": "res://test_icon.svg"},
                scene_file=scene_file,
            ),
            "RESOURCE_TYPE_MISMATCH",
        )
        audio_update = await app.service.audio_stream_player_2d_set(
            audio_player_path,
            {
                "stream_path": "res://test_audio.tres",
                "volume_db": -6.0,
                "pitch_scale": 1.25,
                "autoplay": True,
                "max_distance": 640.0,
                "attenuation": 1.5,
                "panning_strength": 0.75,
                "max_polyphony": 4,
                "bus": "Master",
                "area_layers": [1, 3],
                "playback_type": "stream",
            },
            scene_file=scene_file,
        )
        audio_configuration = audio_update["configuration"]
        if (
            audio_configuration["stream_path"] != "res://test_audio.tres"
            or audio_configuration["stream_type"] != "AudioStreamGenerator"
            or not _is_close(audio_configuration["volume_db"], -6.0)
            or not _is_close(audio_configuration["pitch_scale"], 1.25)
            or audio_configuration["autoplay"] is not True
            or not _is_close(audio_configuration["max_distance"], 640.0)
            or not _is_close(audio_configuration["attenuation"], 1.5)
            or not _is_close(audio_configuration["panning_strength"], 0.75)
            or audio_configuration["max_polyphony"] != 4
            or audio_configuration["bus"] != "Master"
            or audio_configuration["area_layers"] != [1, 3]
            or audio_configuration["playback_type"] != "stream"
        ):
            raise RuntimeError("AudioStreamPlayer2D configuration was not applied")
        undo_audio_update = await app.service.scene_undo(scene_file=scene_file)
        if not undo_audio_update.get("changed"):
            raise RuntimeError("AudioStreamPlayer2D configuration was not undoable")
        restored_audio_player = await app.service.audio_stream_player_2d_get(
            audio_player_path, scene_file=scene_file
        )
        if restored_audio_player["configuration"]["stream_path"] != "":
            raise RuntimeError(
                "Undo did not clear the AudioStreamPlayer2D stream binding"
            )
        redo_audio_update = await app.service.scene_redo(scene_file=scene_file)
        if not redo_audio_update.get("changed"):
            raise RuntimeError("AudioStreamPlayer2D configuration was not redoable")
        cleared_audio = await app.service.audio_stream_player_2d_set(
            audio_player_path,
            {"stream_path": ""},
            scene_file=scene_file,
        )
        if cleared_audio["configuration"]["stream_path"] != "":
            raise RuntimeError("AudioStreamPlayer2D stream was not cleared")
        undo_audio_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_audio_clear.get("changed"):
            raise RuntimeError("AudioStreamPlayer2D stream clear was not undoable")
        restored_audio_stream = await app.service.audio_stream_player_2d_get(
            audio_player_path, scene_file=scene_file
        )
        if (
            restored_audio_stream["configuration"]["stream_path"]
            != "res://test_audio.tres"
        ):
            raise RuntimeError(
                "Undo did not restore the AudioStreamPlayer2D stream binding"
            )
        await _expect_godot_error(
            app.service.animation_audio_track_upsert(
                player_path="/Main/ButtonAnimations",
                animation="button_hover",
                target_path=reparented_button_path,
                keys=[{"time": 0.0, "stream_path": "res://test_audio.tres"}],
                scene_file=scene_file,
            ),
            "AUDIO_STREAM_PLAYER_2D_REQUIRED",
        )
        await _expect_godot_error(
            app.service.animation_audio_track_upsert(
                player_path="/Main/ButtonAnimations",
                animation="button_hover",
                target_path=audio_player_path,
                keys=[{"time": 0.0, "stream_path": "res://test_icon.svg"}],
                scene_file=scene_file,
            ),
            "RESOURCE_TYPE_MISMATCH",
        )
        audio_track_create = await app.service.animation_audio_track_upsert(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            target_path=audio_player_path,
            keys=[
                {
                    "time": 0.0,
                    "stream_path": "res://test_audio.tres",
                    "start_offset": 0.05,
                    "end_offset": 0.1,
                },
                {"time": 0.15, "stream_path": "res://test_audio.tres"},
            ],
            enabled=True,
            use_blend=True,
            scene_file=scene_file,
        )
        audio_track_index = audio_track_create["track"]["index"]
        if (
            audio_track_create["replaced_existing"]
            or audio_track_create["track"]["type"] != "audio"
            or audio_track_create["track"]["target_path"] != audio_player_path
            or audio_track_create["track"]["property"] != ""
            or audio_track_create["track"].get("use_blend") is not True
            or audio_track_create["track"]["key_count"] != 2
        ):
            raise RuntimeError("Audio animation track creation returned an unexpected result")
        audio_animation = await app.service.animation_get(
            "/Main/ButtonAnimations", "button_hover", scene_file=scene_file
        )
        audio_track = _audio_animation_track(audio_animation["animation"], audio_player_path)
        if (
            audio_track["keys"][0].get("stream_path") != "res://test_audio.tres"
            or not _is_close(audio_track["keys"][0].get("start_offset"), 0.05)
            or not _is_close(audio_track["keys"][0].get("end_offset"), 0.1)
        ):
            raise RuntimeError("Audio animation key data was not serialized correctly")
        audio_track_update = await app.service.animation_audio_track_upsert(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            target_path=audio_player_path,
            keys=[
                {
                    "time": 0.1,
                    "stream_path": "res://test_audio.tres",
                    "start_offset": 0.02,
                    "end_offset": 0.03,
                }
            ],
            enabled=False,
            use_blend=False,
            scene_file=scene_file,
        )
        if (
            audio_track_update["replaced_existing"] is not True
            or audio_track_update["track"]["enabled"] is not False
            or audio_track_update["track"].get("use_blend") is not False
            or audio_track_update["track"]["key_count"] != 1
        ):
            raise RuntimeError("Audio animation track replacement was incomplete")
        undo_audio_track_update = await app.service.scene_undo(scene_file=scene_file)
        if not undo_audio_track_update.get("changed"):
            raise RuntimeError("Audio animation track replacement was not undoable")
        restored_audio_animation = await app.service.animation_get(
            "/Main/ButtonAnimations", "button_hover", scene_file=scene_file
        )
        restored_audio_track = _audio_animation_track(
            restored_audio_animation["animation"], audio_player_path
        )
        if restored_audio_track["key_count"] != 2 or restored_audio_track.get("use_blend") is not True:
            raise RuntimeError("Undo did not restore the audio animation track")
        redo_audio_track_update = await app.service.scene_redo(scene_file=scene_file)
        if not redo_audio_track_update.get("changed"):
            raise RuntimeError("Audio animation track replacement was not redoable")
        audio_track_delete = await app.service.animation_track_delete(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            track_index=audio_track_index,
            scene_file=scene_file,
        )
        if audio_track_delete["track_index"] != audio_track_index:
            raise RuntimeError("Audio animation track delete returned an unexpected index")
        undo_audio_track_delete = await app.service.scene_undo(scene_file=scene_file)
        if not undo_audio_track_delete.get("changed"):
            raise RuntimeError("Audio animation track delete was not undoable")
        redo_audio_track_delete = await app.service.scene_redo(scene_file=scene_file)
        if not redo_audio_track_delete.get("changed"):
            raise RuntimeError("Audio animation track delete was not redoable")
        restore_audio_track_delete = await app.service.scene_undo(scene_file=scene_file)
        if not restore_audio_track_delete.get("changed"):
            raise RuntimeError("Undo did not restore the deleted audio animation track")
        await _expect_godot_error(
            app.service.animation_bezier_track_upsert(
                player_path="/Main/ButtonAnimations",
                animation="button_hover",
                target_path=reparented_button_path,
                property="scale:z",
                keys=[{"time": 0.0, "value": 1.0}],
                scene_file=scene_file,
            ),
            "BEZIER_PROPERTY_TYPE_UNSUPPORTED",
        )
        bezier_track_create = await app.service.animation_bezier_track_upsert(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            target_path=reparented_button_path,
            property="modulate:a",
            keys=[
                {
                    "time": 0.0,
                    "value": 1.0,
                    "in_handle": {"x": 0.0, "y": 0.0},
                    "out_handle": {"x": 0.05, "y": -0.1},
                },
                {
                    "time": 0.2,
                    "value": 0.4,
                    "in_handle": {"x": -0.05, "y": 0.1},
                    "out_handle": {"x": 0.0, "y": 0.0},
                },
            ],
            scene_file=scene_file,
        )
        bezier_track_index = bezier_track_create["track"]["index"]
        if (
            bezier_track_create["replaced_existing"]
            or bezier_track_create["track"]["type"] != "bezier"
            or bezier_track_create["track"]["target_path"] != reparented_button_path
            or bezier_track_create["track"]["property"] != "modulate:a"
            or bezier_track_create["track"]["key_count"] != 2
        ):
            raise RuntimeError("Bezier animation track creation returned an unexpected result")
        bezier_animation = await app.service.animation_get(
            "/Main/ButtonAnimations", "button_hover", scene_file=scene_file
        )
        bezier_track = _bezier_animation_track(
            bezier_animation["animation"], reparented_button_path, "modulate:a"
        )
        if (
            not _is_close(bezier_track["keys"][0].get("value"), 1.0)
            or not _vector2_match(
                bezier_track["keys"][0].get("out_handle"), {"x": 0.05, "y": -0.1}
            )
            or not _vector2_match(
                bezier_track["keys"][1].get("in_handle"), {"x": -0.05, "y": 0.1}
            )
        ):
            raise RuntimeError("Bezier animation key data was not serialized correctly")
        bezier_track_update = await app.service.animation_bezier_track_upsert(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            target_path=reparented_button_path,
            property="modulate:a",
            keys=[
                {
                    "time": 0.1,
                    "value": 0.75,
                    "in_handle": {"x": -0.02, "y": 0.0},
                    "out_handle": {"x": 0.02, "y": 0.0},
                }
            ],
            enabled=False,
            scene_file=scene_file,
        )
        if (
            bezier_track_update["replaced_existing"] is not True
            or bezier_track_update["track"]["enabled"] is not False
            or bezier_track_update["track"]["key_count"] != 1
        ):
            raise RuntimeError("Bezier animation track replacement was incomplete")
        undo_bezier_track_update = await app.service.scene_undo(scene_file=scene_file)
        if not undo_bezier_track_update.get("changed"):
            raise RuntimeError("Bezier animation track replacement was not undoable")
        restored_bezier_animation = await app.service.animation_get(
            "/Main/ButtonAnimations", "button_hover", scene_file=scene_file
        )
        restored_bezier_track = _bezier_animation_track(
            restored_bezier_animation["animation"], reparented_button_path, "modulate:a"
        )
        if restored_bezier_track["key_count"] != 2 or restored_bezier_track["enabled"] is not True:
            raise RuntimeError("Undo did not restore the Bezier animation track")
        redo_bezier_track_update = await app.service.scene_redo(scene_file=scene_file)
        if not redo_bezier_track_update.get("changed"):
            raise RuntimeError("Bezier animation track replacement was not redoable")
        bezier_track_delete = await app.service.animation_track_delete(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            track_index=bezier_track_index,
            scene_file=scene_file,
        )
        if bezier_track_delete["track_index"] != bezier_track_index:
            raise RuntimeError("Bezier animation track delete returned an unexpected index")
        undo_bezier_track_delete = await app.service.scene_undo(scene_file=scene_file)
        if not undo_bezier_track_delete.get("changed"):
            raise RuntimeError("Bezier animation track delete was not undoable")
        redo_bezier_track_delete = await app.service.scene_redo(scene_file=scene_file)
        if not redo_bezier_track_delete.get("changed"):
            raise RuntimeError("Bezier animation track delete was not redoable")
        restore_bezier_track_delete = await app.service.scene_undo(scene_file=scene_file)
        if not restore_bezier_track_delete.get("changed"):
            raise RuntimeError("Undo did not restore the deleted Bezier animation track")
        await _expect_godot_error(
            app.service.animation_method_track_upsert(
                player_path="/Main/ButtonAnimations",
                animation="button_hover",
                target_path=reparented_button_path,
                keys=[{"time": 0.0, "method": "queue_free"}],
                scene_file=scene_file,
            ),
            "UNSAFE_ANIMATION_METHOD",
        )
        method_track_create = await app.service.animation_method_track_upsert(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            target_path=reparented_button_path,
            keys=[
                {"time": 0.0, "method": "show"},
                {"time": 0.15, "method": "hide", "args": []},
            ],
            scene_file=scene_file,
        )
        method_track_index = method_track_create["track"]["index"]
        if (
            method_track_create["replaced_existing"]
            or method_track_create["track"]["type"] != "method"
            or method_track_create["track"]["target_path"] != reparented_button_path
            or method_track_create["track"]["key_count"] != 2
        ):
            raise RuntimeError("Method animation track creation returned an unexpected result")
        method_animation = await app.service.animation_get(
            "/Main/ButtonAnimations", "button_hover", scene_file=scene_file
        )
        method_track = _method_animation_track(
            method_animation["animation"], reparented_button_path
        )
        if (
            method_track["keys"][0].get("method") != "show"
            or method_track["keys"][0].get("args") != []
            or method_track["keys"][1].get("method") != "hide"
        ):
            raise RuntimeError("Method animation keys were not serialized correctly")
        method_track_update = await app.service.animation_method_track_upsert(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            target_path=reparented_button_path,
            keys=[{"time": 0.1, "method": "hide"}],
            enabled=False,
            scene_file=scene_file,
        )
        if (
            method_track_update["replaced_existing"] is not True
            or method_track_update["track"]["enabled"] is not False
            or method_track_update["track"]["key_count"] != 1
        ):
            raise RuntimeError("Method animation track replacement was incomplete")
        undo_method_track_update = await app.service.scene_undo(scene_file=scene_file)
        if not undo_method_track_update.get("changed"):
            raise RuntimeError("Method animation track replacement was not undoable")
        restored_method_animation = await app.service.animation_get(
            "/Main/ButtonAnimations", "button_hover", scene_file=scene_file
        )
        restored_method_track = _method_animation_track(
            restored_method_animation["animation"], reparented_button_path
        )
        if restored_method_track["key_count"] != 2 or restored_method_track["enabled"] is not True:
            raise RuntimeError("Undo did not restore the method animation track")
        redo_method_track_update = await app.service.scene_redo(scene_file=scene_file)
        if not redo_method_track_update.get("changed"):
            raise RuntimeError("Method animation track replacement was not redoable")
        method_track_delete = await app.service.animation_track_delete(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            track_index=method_track_index,
            scene_file=scene_file,
        )
        if method_track_delete["track_index"] != method_track_index:
            raise RuntimeError("Method animation track delete returned an unexpected index")
        undo_method_track_delete = await app.service.scene_undo(scene_file=scene_file)
        if not undo_method_track_delete.get("changed"):
            raise RuntimeError("Method animation track delete was not undoable")
        redo_method_track_delete = await app.service.scene_redo(scene_file=scene_file)
        if not redo_method_track_delete.get("changed"):
            raise RuntimeError("Method animation track delete was not redoable")
        restore_method_track_delete = await app.service.scene_undo(scene_file=scene_file)
        if not restore_method_track_delete.get("changed"):
            raise RuntimeError("Undo did not restore the deleted method animation track")
        await _expect_godot_error(
            app.service.animation_nested_track_upsert(
                player_path="/Main/ButtonAnimations",
                animation="button_hover",
                target_path="/Main/ButtonAnimations",
                keys=[{"time": 0.0, "animation": "button_hover"}],
                scene_file=scene_file,
            ),
            "NESTED_ANIMATION_RECURSION",
        )
        nested_track_create = await app.service.animation_nested_track_upsert(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            target_path="/Main/ButtonAnimations",
            keys=[
                {"time": 0.0, "animation": "button_pulse"},
                {"time": 0.15, "animation": "[stop]"},
            ],
            scene_file=scene_file,
        )
        nested_track_index = nested_track_create["track"]["index"]
        if (
            nested_track_create["replaced_existing"]
            or nested_track_create["track"]["type"] != "animation"
            or nested_track_create["track"]["target_path"] != "/Main/ButtonAnimations"
            or nested_track_create["track"]["key_count"] != 2
        ):
            raise RuntimeError("Nested animation track creation returned an unexpected result")
        nested_animation = await app.service.animation_get(
            "/Main/ButtonAnimations", "button_hover", scene_file=scene_file
        )
        nested_track = _nested_animation_track(
            nested_animation["animation"], "/Main/ButtonAnimations"
        )
        if (
            nested_track["keys"][0].get("animation") != "button_pulse"
            or nested_track["keys"][1].get("animation") != "[stop]"
        ):
            raise RuntimeError("Nested animation keys were not serialized correctly")
        nested_track_update = await app.service.animation_nested_track_upsert(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            target_path="/Main/ButtonAnimations",
            keys=[{"time": 0.1, "animation": "[stop]"}],
            enabled=False,
            scene_file=scene_file,
        )
        if (
            nested_track_update["replaced_existing"] is not True
            or nested_track_update["track"]["enabled"] is not False
            or nested_track_update["track"]["key_count"] != 1
        ):
            raise RuntimeError("Nested animation track replacement was incomplete")
        undo_nested_track_update = await app.service.scene_undo(scene_file=scene_file)
        if not undo_nested_track_update.get("changed"):
            raise RuntimeError("Nested animation track replacement was not undoable")
        restored_nested_animation = await app.service.animation_get(
            "/Main/ButtonAnimations", "button_hover", scene_file=scene_file
        )
        restored_nested_track = _nested_animation_track(
            restored_nested_animation["animation"], "/Main/ButtonAnimations"
        )
        if restored_nested_track["key_count"] != 2 or restored_nested_track["enabled"] is not True:
            raise RuntimeError("Undo did not restore the nested animation track")
        redo_nested_track_update = await app.service.scene_redo(scene_file=scene_file)
        if not redo_nested_track_update.get("changed"):
            raise RuntimeError("Nested animation track replacement was not redoable")
        nested_track_delete = await app.service.animation_track_delete(
            player_path="/Main/ButtonAnimations",
            animation="button_hover",
            track_index=nested_track_index,
            scene_file=scene_file,
        )
        if nested_track_delete["track_index"] != nested_track_index:
            raise RuntimeError("Nested animation track delete returned an unexpected index")
        undo_nested_track_delete = await app.service.scene_undo(scene_file=scene_file)
        if not undo_nested_track_delete.get("changed"):
            raise RuntimeError("Nested animation track delete was not undoable")
        redo_nested_track_delete = await app.service.scene_redo(scene_file=scene_file)
        if not redo_nested_track_delete.get("changed"):
            raise RuntimeError("Nested animation track delete was not redoable")
        restore_nested_track_delete = await app.service.scene_undo(scene_file=scene_file)
        if not restore_nested_track_delete.get("changed"):
            raise RuntimeError("Undo did not restore the deleted nested animation track")

        sparks = await app.service.node_create(
            type_name="GPUParticles2D",
            name="AgentSparks",
            parent_path="/Main",
            scene_file=scene_file,
        )
        sparks_path = sparks["path"]
        fire = await app.service.node_create(
            type_name="GPUParticles2D",
            name="AgentFire",
            parent_path="/Main",
            scene_file=scene_file,
        )
        fire_path = fire["path"]
        initial_fire = await app.service.gpu_particles_2d_get(
            fire_path, scene_file=scene_file
        )
        if (
            initial_fire["configuration"]["texture_path"] != ""
            or initial_fire["configuration"]["process_material_path"] != ""
            or initial_fire["configuration"]["sub_emitter_path"] != ""
        ):
            raise RuntimeError("New GPUParticles2D had unexpected resource bindings")
        await _expect_godot_error(
            app.service.gpu_particles_2d_set(
                fire_path,
                {"texture_path": "res://test_audio.tres"},
                scene_file=scene_file,
            ),
            "RESOURCE_TYPE_MISMATCH",
        )
        await _expect_godot_error(
            app.service.gpu_particles_2d_set(
                fire_path,
                {"process_material_path": "res://test_icon.svg"},
                scene_file=scene_file,
            ),
            "RESOURCE_TYPE_MISMATCH",
        )
        await _expect_godot_error(
            app.service.gpu_particles_2d_set(
                fire_path,
                {"sub_emitter_path": fire_path},
                scene_file=scene_file,
            ),
            "INVALID_SUB_EMITTER",
        )
        fire_update = await app.service.gpu_particles_2d_set(
            fire_path,
            {
                "emitting": True,
                "amount": 96,
                "amount_ratio": 0.75,
                "sub_emitter_path": sparks_path,
                "texture_path": "res://test_icon.svg",
                "process_material_path": "res://test_particles.tres",
                "lifetime": 2.5,
                "interp_to_end": 0.25,
                "one_shot": True,
                "preprocess": 1.0,
                "speed_scale": 1.5,
                "explosiveness": 0.4,
                "randomness": 0.2,
                "use_fixed_seed": True,
                "seed": 4242,
                "fixed_fps": 30,
                "interpolate": False,
                "fractional_delta": False,
                "collision_base_size": 2.0,
                "visibility_rect": {
                    "position": {"x": -128.0, "y": -64.0},
                    "size": {"x": 256.0, "y": 128.0},
                },
                "local_coords": True,
                "draw_order": "reverse_lifetime",
                "trail_enabled": True,
                "trail_lifetime": 0.5,
                "trail_sections": 8,
                "trail_section_subdivisions": 4,
            },
            scene_file=scene_file,
        )
        fire_configuration = fire_update["configuration"]
        if (
            not fire_update.get("undoable")
            or fire_configuration["amount"] != 96
            or not _is_close(fire_configuration["amount_ratio"], 0.75)
            or fire_configuration["sub_emitter_path"] != sparks_path
            or fire_configuration["texture_path"] != "res://test_icon.svg"
            or fire_configuration["texture_type"] == ""
            or fire_configuration["process_material_path"]
            != "res://test_particles.tres"
            or fire_configuration["process_material_type"] != "ParticleProcessMaterial"
            or not _is_close(fire_configuration["lifetime"], 2.5)
            or not _is_close(fire_configuration["interp_to_end"], 0.25)
            or fire_configuration["one_shot"] is not True
            or not _is_close(fire_configuration["preprocess"], 1.0)
            or not _is_close(fire_configuration["speed_scale"], 1.5)
            or not _is_close(fire_configuration["explosiveness"], 0.4)
            or not _is_close(fire_configuration["randomness"], 0.2)
            or fire_configuration["use_fixed_seed"] is not True
            or fire_configuration["seed"] != 4242
            or fire_configuration["fixed_fps"] != 30
            or fire_configuration["interpolate"] is not False
            or fire_configuration["fractional_delta"] is not False
            or not _is_close(fire_configuration["collision_base_size"], 2.0)
            or fire_configuration["visibility_rect"]
            != {"position": {"x": -128.0, "y": -64.0}, "size": {"x": 256.0, "y": 128.0}}
            or fire_configuration["local_coords"] is not True
            or fire_configuration["draw_order"] != "reverse_lifetime"
            or fire_configuration["trail_enabled"] is not True
            or not _is_close(fire_configuration["trail_lifetime"], 0.5)
            or fire_configuration["trail_sections"] != 8
            or fire_configuration["trail_section_subdivisions"] != 4
        ):
            raise RuntimeError("GPUParticles2D configuration was not applied")
        undo_fire_update = await app.service.scene_undo(scene_file=scene_file)
        if not undo_fire_update.get("changed"):
            raise RuntimeError("GPUParticles2D configuration was not undoable")
        restored_fire = await app.service.gpu_particles_2d_get(
            fire_path, scene_file=scene_file
        )
        if (
            restored_fire["configuration"]["texture_path"] != ""
            or restored_fire["configuration"]["process_material_path"] != ""
            or restored_fire["configuration"]["sub_emitter_path"] != ""
        ):
            raise RuntimeError("Undo did not restore GPUParticles2D resource bindings")
        redo_fire_update = await app.service.scene_redo(scene_file=scene_file)
        if not redo_fire_update.get("changed"):
            raise RuntimeError("GPUParticles2D configuration was not redoable")
        cleared_fire = await app.service.gpu_particles_2d_set(
            fire_path,
            {
                "texture_path": "",
                "process_material_path": "",
                "sub_emitter_path": "",
            },
            scene_file=scene_file,
        )
        if (
            cleared_fire["configuration"]["texture_path"] != ""
            or cleared_fire["configuration"]["process_material_path"] != ""
            or cleared_fire["configuration"]["sub_emitter_path"] != ""
        ):
            raise RuntimeError("GPUParticles2D resource bindings were not cleared")
        undo_fire_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_fire_clear.get("changed"):
            raise RuntimeError("GPUParticles2D resource clear was not undoable")
        restored_fire_bindings = await app.service.gpu_particles_2d_get(
            fire_path, scene_file=scene_file
        )
        if (
            restored_fire_bindings["configuration"]["texture_path"]
            != "res://test_icon.svg"
            or restored_fire_bindings["configuration"]["process_material_path"]
            != "res://test_particles.tres"
            or restored_fire_bindings["configuration"]["sub_emitter_path"]
            != sparks_path
        ):
            raise RuntimeError("Undo did not restore GPUParticles2D resource bindings")

        initial_sparks_material = await app.service.particle_process_material_2d_get(
            sparks_path, scene_file=scene_file
        )
        if initial_sparks_material["material"]["assigned"]:
            raise RuntimeError("New GPUParticles2D unexpectedly had a process material")
        sparks_material = await app.service.particle_process_material_2d_create(
            sparks_path, scene_file=scene_file
        )
        if (
            not sparks_material.get("created")
            or sparks_material["material"]["origin"] != "embedded"
            or sparks_material["configuration"] is None
            or sparks_material["configuration"]["disable_z"] is not True
        ):
            raise RuntimeError(
                "ParticleProcessMaterial was not created as an embedded 2D material"
            )
        await _expect_godot_error(
            app.service.particle_process_material_2d_create(
                sparks_path, scene_file=scene_file
            ),
            "PROCESS_MATERIAL_ALREADY_ASSIGNED",
        )
        undo_sparks_material = await app.service.scene_undo(scene_file=scene_file)
        if not undo_sparks_material.get("changed"):
            raise RuntimeError("ParticleProcessMaterial creation was not undoable")
        restored_sparks_material = await app.service.particle_process_material_2d_get(
            sparks_path, scene_file=scene_file
        )
        if restored_sparks_material["material"]["assigned"]:
            raise RuntimeError(
                "Undo did not remove the created ParticleProcessMaterial"
            )
        redo_sparks_material = await app.service.scene_redo(scene_file=scene_file)
        if not redo_sparks_material.get("changed"):
            raise RuntimeError("ParticleProcessMaterial creation was not redoable")

        initial_fire_material = await app.service.particle_process_material_2d_get(
            fire_path, scene_file=scene_file
        )
        if (
            initial_fire_material["material"]["origin"] != "external"
            or initial_fire_material["material"]["resource_path"]
            != "res://test_particles.tres"
            or initial_fire_material["configuration"]["direction"]
            != {"x": 1.0, "y": 0.0}
        ):
            raise RuntimeError(
                "External ParticleProcessMaterial was not reported accurately"
            )
        await _expect_godot_error(
            app.service.particle_process_material_2d_set(
                fire_path,
                {"emission_ring_inner_radius": 5.0},
                scene_file=scene_file,
            ),
            "INVALID_PROCESS_MATERIAL_CONFIGURATION",
        )
        process_material_update = await app.service.particle_process_material_2d_set(
            fire_path,
            {
                "lifetime_randomness": 0.25,
                "align_y_to_velocity": True,
                "disable_z": True,
                "damping_as_friction": True,
                "emission_shape": "box",
                "emission_shape_offset": {"x": 4.0, "y": 8.0},
                "emission_shape_scale": {"x": 2.0, "y": 3.0},
                "emission_sphere_radius": 12.0,
                "emission_box_extents": {"x": 32.0, "y": 16.0},
                "emission_point_count": 64,
                "emission_ring_height": 8.0,
                "emission_ring_radius": 10.0,
                "emission_ring_inner_radius": 4.0,
                "emission_ring_cone_angle": 45.0,
                "direction": {"x": 0.5, "y": -1.0},
                "spread": 20.0,
                "flatness": 0.2,
                "inherit_velocity_ratio": 0.5,
                "velocity_pivot": {"x": 3.0, "y": 5.0},
                "initial_velocity_min": 32.0,
                "initial_velocity_max": 64.0,
                "angular_velocity_min": -10.0,
                "angular_velocity_max": 20.0,
                "orbit_velocity_min": -0.5,
                "orbit_velocity_max": 0.75,
                "radial_velocity_min": -12.0,
                "radial_velocity_max": 18.0,
                "directional_velocity_min": -9.0,
                "directional_velocity_max": 11.0,
                "gravity": {"x": 0.0, "y": 98.0},
                "linear_accel_min": -5.0,
                "linear_accel_max": 10.0,
                "radial_accel_min": -4.0,
                "radial_accel_max": 6.0,
                "tangential_accel_min": -3.0,
                "tangential_accel_max": 7.0,
                "damping_min": 0.1,
                "damping_max": 0.8,
                "attractor_interaction_enabled": True,
                "scale_min": 0.5,
                "scale_max": 1.5,
                "color": {"r": 1.0, "g": 0.5, "b": 0.25, "a": 0.8},
                "turbulence_enabled": True,
                "turbulence_noise_strength": 2.0,
                "turbulence_noise_scale": 0.5,
                "turbulence_noise_speed": {"x": 4.0, "y": -2.0},
                "turbulence_noise_speed_random": 0.3,
                "collision_mode": "rigid",
                "collision_friction": 0.4,
                "collision_bounce": 0.6,
                "collision_use_scale": True,
                "sub_emitter_mode": "at_collision",
                "sub_emitter_frequency": 12.0,
                "sub_emitter_amount_at_end": 2,
                "sub_emitter_amount_at_collision": 3,
                "sub_emitter_amount_at_start": 4,
                "sub_emitter_keep_velocity": True,
            },
            scene_file=scene_file,
        )
        process_configuration = process_material_update["configuration"]
        if (
            not process_material_update.get("undoable")
            or process_material_update.get("copied_external_material") is not True
            or process_material_update["material"]["origin"] != "embedded"
            or process_material_update["material"]["resource_path"] != ""
            or process_configuration["emission_shape"] != "box"
            or process_configuration["emission_box_extents"] != {"x": 32.0, "y": 16.0}
            or process_configuration["direction"] != {"x": 0.5, "y": -1.0}
            or not _is_close(process_configuration["initial_velocity_min"], 32.0)
            or not _is_close(process_configuration["initial_velocity_max"], 64.0)
            or process_configuration["gravity"] != {"x": 0.0, "y": 98.0}
            or not _color_matches(
                process_configuration["color"],
                {"r": 1.0, "g": 0.5, "b": 0.25, "a": 0.8},
            )
            or process_configuration["collision_mode"] != "rigid"
            or process_configuration["sub_emitter_mode"] != "at_collision"
            or process_configuration["sub_emitter_amount_at_collision"] != 3
        ):
            raise RuntimeError("ParticleProcessMaterial configuration was not applied")
        undo_process_material = await app.service.scene_undo(scene_file=scene_file)
        if not undo_process_material.get("changed"):
            raise RuntimeError("ParticleProcessMaterial update was not undoable")
        restored_fire_material = await app.service.particle_process_material_2d_get(
            fire_path, scene_file=scene_file
        )
        if (
            restored_fire_material["material"]["origin"] != "external"
            or restored_fire_material["material"]["resource_path"]
            != "res://test_particles.tres"
            or restored_fire_material["configuration"]["direction"]
            != {"x": 1.0, "y": 0.0}
        ):
            raise RuntimeError(
                "Undo did not restore the untouched external ParticleProcessMaterial"
            )
        redo_process_material = await app.service.scene_redo(scene_file=scene_file)
        if not redo_process_material.get("changed"):
            raise RuntimeError("ParticleProcessMaterial update was not redoable")

        undo_process_material_resources = await app.service.scene_undo(
            scene_file=scene_file
        )
        if not undo_process_material_resources.get("changed"):
            raise RuntimeError(
                "ParticleProcessMaterial resource setup did not restore the external material"
            )
        initial_process_curve = (
            await app.service.particle_process_material_2d_curve_get(
                fire_path,
                "scale",
                scene_file=scene_file,
            )
        )
        if initial_process_curve["resource"]["assigned"]:
            raise RuntimeError(
                "External ParticleProcessMaterial unexpectedly had a scale CurveTexture"
            )
        await _expect_godot_error(
            app.service.particle_process_material_2d_curve_bind(
                fire_path,
                "scale",
                "res://test_particle_gradient_texture.tres",
                scene_file=scene_file,
            ),
            "RESOURCE_TYPE_MISMATCH",
        )
        bound_process_curve = await app.service.particle_process_material_2d_curve_bind(
            fire_path,
            "scale",
            "res://test_particle_curve_texture.tres",
            scene_file=scene_file,
        )
        if (
            not bound_process_curve.get("undoable")
            or bound_process_curve.get("bound_external_resource") is not True
            or bound_process_curve.get("copied_external_material") is not True
            or bound_process_curve["material"]["origin"] != "embedded"
            or bound_process_curve["resource"]["resource_path"]
            != "res://test_particle_curve_texture.tres"
        ):
            raise RuntimeError(
                "ParticleProcessMaterial CurveTexture was not bound safely"
            )
        process_curve_update = await app.service.particle_process_material_2d_curve_set(
            fire_path,
            "scale",
            {
                "width": 128,
                "texture_mode": "red",
                "min_domain": 0.0,
                "max_domain": 1.0,
                "min_value": -2.0,
                "max_value": 2.0,
                "bake_resolution": 64,
                "points": [
                    {"position": {"x": 0.0, "y": -1.0}},
                    {"position": {"x": 1.0, "y": 1.0}},
                ],
            },
            scene_file=scene_file,
        )
        process_curve_configuration = process_curve_update["configuration"]
        if (
            not process_curve_update.get("undoable")
            or process_curve_update.get("copied_external_resource") is not True
            or process_curve_configuration["width"] != 128
            or process_curve_configuration["texture_mode"] != "red"
            or not _is_close(process_curve_configuration["curve"]["min_value"], -2.0)
            or not _is_close(process_curve_configuration["curve"]["max_value"], 2.0)
            or process_curve_configuration["curve"]["bake_resolution"] != 64
            or len(process_curve_configuration["curve"]["points"]) != 2
            or process_curve_update["resource"]["origin"] != "embedded"
        ):
            raise RuntimeError(
                "ParticleProcessMaterial CurveTexture configuration was not applied"
            )
        undo_process_curve_update = await app.service.scene_undo(scene_file=scene_file)
        if not undo_process_curve_update.get("changed"):
            raise RuntimeError(
                "ParticleProcessMaterial CurveTexture update was not undoable"
            )
        restored_process_curve = (
            await app.service.particle_process_material_2d_curve_get(
                fire_path,
                "scale",
                scene_file=scene_file,
            )
        )
        if (
            restored_process_curve["resource"]["resource_path"]
            != "res://test_particle_curve_texture.tres"
        ):
            raise RuntimeError(
                "Undo did not restore the external ParticleProcessMaterial CurveTexture"
            )
        redo_process_curve_update = await app.service.scene_redo(scene_file=scene_file)
        if not redo_process_curve_update.get("changed"):
            raise RuntimeError(
                "ParticleProcessMaterial CurveTexture update was not redoable"
            )
        cleared_process_curve = (
            await app.service.particle_process_material_2d_curve_clear(
                fire_path,
                "scale",
                scene_file=scene_file,
            )
        )
        if cleared_process_curve["resource"]["assigned"]:
            raise RuntimeError("ParticleProcessMaterial CurveTexture was not cleared")
        undo_process_curve_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_process_curve_clear.get("changed"):
            raise RuntimeError(
                "ParticleProcessMaterial CurveTexture clear was not undoable"
            )
        restored_embedded_process_curve = (
            await app.service.particle_process_material_2d_curve_get(
                fire_path,
                "scale",
                scene_file=scene_file,
            )
        )
        if restored_embedded_process_curve["resource"]["origin"] != "embedded":
            raise RuntimeError(
                "Undo did not restore the embedded ParticleProcessMaterial CurveTexture"
            )

        initial_process_gradient = (
            await app.service.particle_process_material_2d_gradient_get(
                fire_path,
                "color",
                scene_file=scene_file,
            )
        )
        if initial_process_gradient["resource"]["assigned"]:
            raise RuntimeError(
                "ParticleProcessMaterial unexpectedly had a color GradientTexture1D"
            )
        await _expect_godot_error(
            app.service.particle_process_material_2d_gradient_bind(
                fire_path,
                "color",
                "res://test_particle_curve_texture.tres",
                scene_file=scene_file,
            ),
            "RESOURCE_TYPE_MISMATCH",
        )
        bound_process_gradient = (
            await app.service.particle_process_material_2d_gradient_bind(
                fire_path,
                "color",
                "res://test_particle_gradient_texture.tres",
                scene_file=scene_file,
            )
        )
        if (
            not bound_process_gradient.get("undoable")
            or bound_process_gradient.get("bound_external_resource") is not True
            or bound_process_gradient["resource"]["resource_path"]
            != "res://test_particle_gradient_texture.tres"
        ):
            raise RuntimeError(
                "ParticleProcessMaterial GradientTexture1D was not bound safely"
            )
        process_gradient_update = (
            await app.service.particle_process_material_2d_gradient_set(
                fire_path,
                "color",
                {
                    "width": 512,
                    "use_hdr": True,
                    "points": [
                        {
                            "offset": 0.0,
                            "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0},
                        },
                        {
                            "offset": 0.5,
                            "color": {"r": 0.0, "g": 1.0, "b": 0.0, "a": 0.8},
                        },
                        {
                            "offset": 1.0,
                            "color": {"r": 0.0, "g": 0.0, "b": 1.0, "a": 0.5},
                        },
                    ],
                    "interpolation_mode": "cubic",
                    "interpolation_color_space": "oklab",
                },
                scene_file=scene_file,
            )
        )
        process_gradient_configuration = process_gradient_update["configuration"]
        if (
            not process_gradient_update.get("undoable")
            or process_gradient_update.get("copied_external_resource") is not True
            or process_gradient_configuration["width"] != 512
            or process_gradient_configuration["use_hdr"] is not True
            or process_gradient_configuration["gradient"]["interpolation_mode"]
            != "cubic"
            or process_gradient_configuration["gradient"]["interpolation_color_space"]
            != "oklab"
            or len(process_gradient_configuration["gradient"]["points"]) != 3
            or not _color_matches(
                process_gradient_configuration["gradient"]["points"][1]["color"],
                {"r": 0.0, "g": 1.0, "b": 0.0, "a": 0.8},
            )
            or process_gradient_update["resource"]["origin"] != "embedded"
        ):
            raise RuntimeError(
                "ParticleProcessMaterial GradientTexture1D configuration was not applied"
            )
        undo_process_gradient_update = await app.service.scene_undo(
            scene_file=scene_file
        )
        if not undo_process_gradient_update.get("changed"):
            raise RuntimeError(
                "ParticleProcessMaterial GradientTexture1D update was not undoable"
            )
        restored_process_gradient = (
            await app.service.particle_process_material_2d_gradient_get(
                fire_path,
                "color",
                scene_file=scene_file,
            )
        )
        if (
            restored_process_gradient["resource"]["resource_path"]
            != "res://test_particle_gradient_texture.tres"
        ):
            raise RuntimeError(
                "Undo did not restore the external ParticleProcessMaterial GradientTexture1D"
            )
        redo_process_gradient_update = await app.service.scene_redo(
            scene_file=scene_file
        )
        if not redo_process_gradient_update.get("changed"):
            raise RuntimeError(
                "ParticleProcessMaterial GradientTexture1D update was not redoable"
            )
        cleared_process_gradient = (
            await app.service.particle_process_material_2d_gradient_clear(
                fire_path,
                "color",
                scene_file=scene_file,
            )
        )
        if cleared_process_gradient["resource"]["assigned"]:
            raise RuntimeError(
                "ParticleProcessMaterial GradientTexture1D was not cleared"
            )
        undo_process_gradient_clear = await app.service.scene_undo(
            scene_file=scene_file
        )
        if not undo_process_gradient_clear.get("changed"):
            raise RuntimeError(
                "ParticleProcessMaterial GradientTexture1D clear was not undoable"
            )
        restored_embedded_process_gradient = (
            await app.service.particle_process_material_2d_gradient_get(
                fire_path,
                "color",
                scene_file=scene_file,
            )
        )
        if restored_embedded_process_gradient["resource"]["origin"] != "embedded":
            raise RuntimeError(
                "Undo did not restore the embedded ParticleProcessMaterial GradientTexture1D"
            )
        expected_process_curve_names = {
            "angle",
            "angular_velocity",
            "orbit_velocity",
            "radial_velocity",
            "velocity_limit",
            "linear_accel",
            "radial_accel",
            "tangential_accel",
            "damping",
            "scale",
            "scale_over_velocity",
            "alpha",
            "emission",
            "hue_variation",
            "anim_speed",
            "anim_offset",
            "turbulence_influence_over_life",
        }
        if set(
            restored_embedded_process_curve["curve_names"]
        ) != expected_process_curve_names or set(
            restored_embedded_process_gradient["gradient_names"]
        ) != {"color", "initial_color"}:
            raise RuntimeError(
                "ParticleProcessMaterial resource slots were not enumerated"
            )
        scalar_process_curve = await app.service.particle_process_material_2d_curve_set(
            fire_path,
            "alpha",
            {
                "points": [
                    {"position": {"x": 0.0, "y": 1.0}},
                    {"position": {"x": 1.0, "y": 0.0}},
                ]
            },
            scene_file=scene_file,
        )
        if (
            scalar_process_curve.get("created") is not True
            or scalar_process_curve["resource"]["origin"] != "embedded"
            or set(scalar_process_curve["curve_names"]) != expected_process_curve_names
        ):
            raise RuntimeError(
                "ParticleProcessMaterial direct CurveTexture slot was not configured"
            )
        initial_color_gradient = (
            await app.service.particle_process_material_2d_gradient_set(
                fire_path,
                "initial_color",
                {
                    "points": [
                        {
                            "offset": 0.0,
                            "color": {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0},
                        },
                        {
                            "offset": 1.0,
                            "color": {"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.0},
                        },
                    ]
                },
                scene_file=scene_file,
            )
        )
        if (
            initial_color_gradient.get("created") is not True
            or initial_color_gradient["resource"]["origin"] != "embedded"
            or len(initial_color_gradient["configuration"]["gradient"]["points"]) != 2
        ):
            raise RuntimeError(
                "ParticleProcessMaterial initial_color GradientTexture1D was not configured"
            )

        canvas_item = await app.service.node_create(
            type_name="Sprite2D",
            name="AgentCanvasItem",
            parent_path="/Main",
            scene_file=scene_file,
        )
        canvas_item_path = canvas_item["path"]
        bound_sprite_texture = await app.service.node_set_properties(
            canvas_item_path,
            {"texture": {"resource_path": "res://test_icon.svg"}},
            scene_file=scene_file,
        )
        texture_value = bound_sprite_texture["updated"].get("texture", {})
        if texture_value.get("resource_path") != "res://test_icon.svg":
            raise RuntimeError("Generic project Texture2D binding was not applied")
        await _expect_godot_error(
            app.service.node_set_properties(
                canvas_item_path,
                {"texture": {"resource_path": "res://test_cpu_curve.tres"}},
                scene_file=scene_file,
            ),
            "PROPERTY_TYPE_MISMATCH",
        )
        await _expect_godot_error(
            app.service.node_set_properties(
                canvas_item_path,
                {"texture": {"resource_path": "res://../test_icon.svg"}},
                scene_file=scene_file,
            ),
            "PROPERTY_TYPE_MISMATCH",
        )
        undo_sprite_texture = await app.service.scene_undo(scene_file=scene_file)
        if not undo_sprite_texture.get("changed"):
            raise RuntimeError("Generic project Texture2D binding was not undoable")
        restored_sprite_texture = await app.service.node_get_properties(
            canvas_item_path,
            fields=["texture"],
            scene_file=scene_file,
        )
        if _property_value(restored_sprite_texture, "texture") is not None:
            raise RuntimeError(
                "Undo did not clear the generic project Texture2D binding"
            )
        redo_sprite_texture = await app.service.scene_redo(scene_file=scene_file)
        if not redo_sprite_texture.get("changed"):
            raise RuntimeError("Generic project Texture2D binding was not redoable")

        semantic_sprite = await app.service.node_create(
            type_name="Sprite2D",
            name="AgentSpriteSemantic",
            parent_path="/Main",
            scene_file=scene_file,
        )
        semantic_sprite_path = semantic_sprite["path"]
        sprite_configuration = await app.service.sprite_2d_set(
            semantic_sprite_path,
            {
                "texture_path": "res://test_icon.svg",
                "centered": False,
                "offset": {"x": 12.0, "y": -6.0},
                "flip_h": True,
                "hframes": 2,
                "vframes": 2,
                "frame_coords": {"x": 1, "y": 1},
                "region_enabled": True,
                "region_rect": {
                    "position": {"x": 1.0, "y": 2.0},
                    "size": {"x": 12.0, "y": 14.0},
                },
            },
            scene_file=scene_file,
        )
        sprite_state = sprite_configuration["configuration"]
        if (
            not sprite_configuration.get("changed")
            or not sprite_configuration.get("undoable")
            or sprite_state["texture_path"] != "res://test_icon.svg"
            or sprite_state["frame_coords"] != {"x": 1, "y": 1}
            or sprite_state["region_rect"]["size"] != {"x": 12.0, "y": 14.0}
        ):
            raise RuntimeError("Sprite2D semantic configuration was not applied")
        await _expect_godot_error(
            app.service.sprite_2d_set(
                semantic_sprite_path,
                {"texture_path": "res://test_cpu_curve.tres"},
                scene_file=scene_file,
            ),
            "RESOURCE_TYPE_MISMATCH",
        )
        undo_semantic_sprite = await app.service.scene_undo(scene_file=scene_file)
        if not undo_semantic_sprite.get("changed"):
            raise RuntimeError("Sprite2D semantic configuration was not undoable")
        restored_semantic_sprite = await app.service.sprite_2d_get(
            semantic_sprite_path, scene_file=scene_file
        )
        if restored_semantic_sprite["configuration"]["texture_path"]:
            raise RuntimeError("Undo did not restore the Sprite2D texture")
        redo_semantic_sprite = await app.service.scene_redo(scene_file=scene_file)
        if not redo_semantic_sprite.get("changed"):
            raise RuntimeError("Sprite2D semantic configuration was not redoable")

        semantic_line = await app.service.node_create(
            type_name="Line2D",
            name="AgentLineSemantic",
            parent_path="/Main",
            scene_file=scene_file,
        )
        semantic_line_path = semantic_line["path"]
        line_configuration = await app.service.line_2d_set(
            semantic_line_path,
            {
                "points": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 16.0, "y": 8.0},
                    {"x": 32.0, "y": 0.0},
                ],
                "closed": True,
                "width": 3.0,
                "width_curve_path": "res://test_cpu_curve.tres",
                "default_color": {"r": 0.9, "g": 0.3, "b": 0.1, "a": 1.0},
                "gradient_path": "res://test_cpu_gradient.tres",
                "texture_path": "res://test_icon.svg",
                "texture_mode": "tile",
                "joint_mode": "round",
                "begin_cap_mode": "round",
                "end_cap_mode": "box",
                "sharp_limit": 2.0,
                "round_precision": 12,
                "antialiased": True,
            },
            scene_file=scene_file,
        )
        line_state = line_configuration["configuration"]
        if (
            not line_configuration.get("changed")
            or line_state["width_curve_path"] != "res://test_cpu_curve.tres"
            or line_state["gradient_path"] != "res://test_cpu_gradient.tres"
            or line_state["texture_mode"] != "tile"
            or line_state["joint_mode"] != "round"
            or line_state["points"][1] != {"x": 16.0, "y": 8.0}
        ):
            raise RuntimeError("Line2D semantic configuration was not applied")
        await _expect_godot_error(
            app.service.line_2d_set(
                semantic_line_path,
                {"gradient_path": "res://test_cpu_curve.tres"},
                scene_file=scene_file,
            ),
            "RESOURCE_TYPE_MISMATCH",
        )
        undo_semantic_line = await app.service.scene_undo(scene_file=scene_file)
        if not undo_semantic_line.get("changed"):
            raise RuntimeError("Line2D semantic configuration was not undoable")
        if (await app.service.line_2d_get(semantic_line_path, scene_file=scene_file))[
            "configuration"
        ]["points"]:
            raise RuntimeError("Undo did not restore Line2D points")
        redo_semantic_line = await app.service.scene_redo(scene_file=scene_file)
        if not redo_semantic_line.get("changed"):
            raise RuntimeError("Line2D semantic configuration was not redoable")

        semantic_polygon = await app.service.node_create(
            type_name="Polygon2D",
            name="AgentPolygonSemantic",
            parent_path="/Main",
            scene_file=scene_file,
        )
        semantic_polygon_path = semantic_polygon["path"]
        polygon_configuration = await app.service.polygon_2d_set(
            semantic_polygon_path,
            {
                "polygon": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 48.0, "y": 0.0},
                    {"x": 24.0, "y": 36.0},
                ],
                "uv": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 1.0, "y": 0.0},
                    {"x": 0.5, "y": 1.0},
                ],
                "vertex_colors": [
                    {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0},
                    {"r": 0.0, "g": 1.0, "b": 0.0, "a": 1.0},
                    {"r": 0.0, "g": 0.0, "b": 1.0, "a": 1.0},
                ],
                "color": {"r": 0.8, "g": 0.8, "b": 0.8, "a": 1.0},
                "texture_path": "res://test_icon.svg",
                "texture_offset": {"x": 4.0, "y": -2.0},
                "texture_rotation": 12.0,
                "texture_scale": {"x": 1.5, "y": 0.75},
                "invert_enabled": True,
                "invert_border": 6.0,
                "antialiased": True,
                "offset": {"x": 8.0, "y": 4.0},
            },
            scene_file=scene_file,
        )
        polygon_state = polygon_configuration["configuration"]
        if (
            not polygon_configuration.get("changed")
            or polygon_state["texture_path"] != "res://test_icon.svg"
            or len(polygon_state["polygon"]) != 3
            or len(polygon_state["vertex_colors"]) != 3
            or polygon_state["invert_enabled"] is not True
        ):
            raise RuntimeError("Polygon2D semantic configuration was not applied")
        await _expect_godot_error(
            app.service.polygon_2d_set(
                semantic_polygon_path,
                {
                    "polygon": [
                        {"x": 0.0, "y": 0.0},
                        {"x": 12.0, "y": 0.0},
                        {"x": 24.0, "y": 0.0},
                    ]
                },
                scene_file=scene_file,
            ),
            "INVALID_DRAW_2D_CONFIGURATION",
        )
        await _expect_godot_error(
            app.service.sprite_2d_get(semantic_line_path, scene_file=scene_file),
            "SPRITE_2D_REQUIRED",
        )
        undo_semantic_polygon = await app.service.scene_undo(scene_file=scene_file)
        if not undo_semantic_polygon.get("changed"):
            raise RuntimeError("Polygon2D semantic configuration was not undoable")
        if (
            await app.service.polygon_2d_get(
                semantic_polygon_path, scene_file=scene_file
            )
        )["configuration"]["polygon"]:
            raise RuntimeError("Undo did not restore Polygon2D geometry")
        redo_semantic_polygon = await app.service.scene_redo(scene_file=scene_file)
        if not redo_semantic_polygon.get("changed"):
            raise RuntimeError("Polygon2D semantic configuration was not redoable")

        animated_sprite = await app.service.node_create(
            type_name="AnimatedSprite2D",
            name="AgentAnimatedSprite",
            parent_path="/Main",
            scene_file=scene_file,
        )
        animated_sprite_path = animated_sprite["path"]
        await app.service.animated_sprite_2d_set(
            animated_sprite_path,
            {
                "sprite_frames_path": "res://test_sprite_frames.tres",
                "animation": "default",
                "autoplay": "default",
            },
            scene_file=scene_file,
        )
        external_sprite_frames = await app.service.sprite_frames_get(
            animated_sprite_path,
            animation="default",
            scene_file=scene_file,
        )
        if (
            external_sprite_frames["sprite_frames"]["origin"] != "external"
            or external_sprite_frames["selected_animation"]["frame_count"] != 1
        ):
            raise RuntimeError("External SpriteFrames resource was not assigned")
        copied_sprite_frames = await app.service.sprite_frames_animation_upsert(
            animated_sprite_path,
            "idle",
            speed=12.0,
            loop_mode=loop_mode,
            frames=[
                {"texture_path": "res://test_icon.svg", "duration": 0.5},
                {"texture_path": "res://test_icon.svg", "duration": 1.0},
            ],
            scene_file=scene_file,
        )
        if (
            copied_sprite_frames.get("copied_external_resource") is not True
            or copied_sprite_frames["sprite_frames"]["origin"] != "embedded"
            or copied_sprite_frames["selected_animation"]["loop_mode"] != loop_mode
            or len(copied_sprite_frames["selected_animation"]["frames"]) != 2
        ):
            raise RuntimeError("SpriteFrames copy-on-write animation update was not applied")
        if not (await app.service.scene_undo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("SpriteFrames copy-on-write update was not undoable")
        restored_external_frames = await app.service.sprite_frames_get(
            animated_sprite_path, scene_file=scene_file
        )
        if restored_external_frames["sprite_frames"]["origin"] != "external":
            raise RuntimeError("Undo did not restore the external SpriteFrames resource")
        if not (await app.service.scene_redo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("SpriteFrames copy-on-write update was not redoable")
        await app.service.animated_sprite_2d_set(
            animated_sprite_path,
            {"animation": "idle", "frame": 1, "frame_progress": 0.25, "speed_scale": 1.5},
            scene_file=scene_file,
        )
        renamed_sprite_frames = await app.service.sprite_frames_animation_rename(
            animated_sprite_path,
            "idle",
            "run",
            scene_file=scene_file,
        )
        if (
            renamed_sprite_frames.get("renamed") is not True
            or renamed_sprite_frames["configuration"]["animation"] != "run"
            or renamed_sprite_frames["selected_animation"]["name"] != "run"
        ):
            raise RuntimeError("SpriteFrames animation rename was not applied")
        removed_sprite_frames = await app.service.sprite_frames_animation_remove(
            animated_sprite_path,
            "run",
            scene_file=scene_file,
        )
        if (
            removed_sprite_frames.get("removed") is not True
            or removed_sprite_frames["configuration"]["animation"] != "default"
            or removed_sprite_frames["selected_animation"]["name"] != "default"
        ):
            raise RuntimeError("SpriteFrames animation removal did not restore a valid selection")
        await _expect_godot_error(
            app.service.sprite_frames_animation_remove(
                animated_sprite_path, "default", scene_file=scene_file
            ),
            "SPRITE_FRAMES_LAST_ANIMATION",
        )
        await _expect_godot_error(
            app.service.animated_sprite_2d_get(semantic_line_path, scene_file=scene_file),
            "ANIMATED_SPRITE_2D_REQUIRED",
        )

        semantic_button = await app.service.node_create(
            type_name="Button",
            name="AgentSemanticButton",
            parent_path="/Main",
            scene_file=scene_file,
        )
        semantic_button_path = semantic_button["path"]
        button_configuration = await app.service.button_2d_set(
            semantic_button_path,
            {
                "toggle_mode": True,
                "button_pressed": True,
                "action_mode": "press",
                "button_mask": ["left", "right"],
                "keep_pressed_outside": True,
                "shortcut_feedback": False,
                "shortcut_in_tooltip": False,
                "button_group_path": "res://test_button_group.tres",
                "text": "Launch",
                "icon_path": "res://test_icon.svg",
                "flat": True,
                "alignment": "left",
                "text_overrun_behavior": "ellipsis_force",
                "autowrap_mode": "smart_word",
                "autowrap_trim_flags": ["trim_start"],
                "clip_text": True,
                "icon_alignment": "right",
                "vertical_icon_alignment": "bottom",
                "expand_icon": True,
                "text_direction": "ltr",
                "language": "en",
            },
            scene_file=scene_file,
        )
        button_state = button_configuration["configuration"]
        text_button_state = button_state["button"]
        if (
            not button_configuration.get("changed")
            or button_state["button_pressed"] is not True
            or button_state["button_mask"] != ["left", "right"]
            or button_state["button_group"]["resource_path"] != "res://test_button_group.tres"
            or text_button_state["text"] != "Launch"
            or text_button_state["icon"]["resource_path"] != "res://test_icon.svg"
            or text_button_state["autowrap_trim_flags"] != ["trim_start"]
            or text_button_state["vertical_icon_alignment"] != "bottom"
        ):
            raise RuntimeError("Button semantic configuration was not applied")
        if not (await app.service.scene_undo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("Button semantic configuration was not undoable")
        restored_button = await app.service.button_2d_get(
            semantic_button_path, scene_file=scene_file
        )
        if restored_button["configuration"]["button"]["text"]:
            raise RuntimeError("Undo did not restore Button text")
        if not (await app.service.scene_redo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("Button semantic configuration was not redoable")

        semantic_texture_button = await app.service.node_create(
            type_name="TextureButton",
            name="AgentTextureButton",
            parent_path="/Main",
            scene_file=scene_file,
        )
        semantic_texture_button_path = semantic_texture_button["path"]
        texture_button_configuration = await app.service.button_2d_set(
            semantic_texture_button_path,
            {
                "texture_normal_path": "res://test_icon.svg",
                "texture_pressed_path": "res://test_icon.svg",
                "texture_hover_path": "res://test_icon.svg",
                "texture_disabled_path": "res://test_icon.svg",
                "texture_focused_path": "res://test_icon.svg",
                "ignore_texture_size": True,
                "stretch_mode": "keep_aspect_centered",
                "flip_h": True,
                "flip_v": True,
            },
            scene_file=scene_file,
        )
        texture_button_state = texture_button_configuration["configuration"]["texture_button"]
        if (
            texture_button_state["texture_normal"]["resource_path"] != "res://test_icon.svg"
            or texture_button_state["stretch_mode"] != "keep_aspect_centered"
            or texture_button_state["flip_h"] is not True
            or texture_button_state["flip_v"] is not True
        ):
            raise RuntimeError("TextureButton semantic configuration was not applied")
        if not (await app.service.scene_undo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("TextureButton semantic configuration was not undoable")
        restored_texture_button = await app.service.button_2d_get(
            semantic_texture_button_path, scene_file=scene_file
        )
        if restored_texture_button["configuration"]["texture_button"]["texture_normal"]["assigned"]:
            raise RuntimeError("Undo did not clear TextureButton textures")
        if not (await app.service.scene_redo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("TextureButton semantic configuration was not redoable")

        semantic_link_button = await app.service.node_create(
            type_name="LinkButton",
            name="AgentLinkButton",
            parent_path="/Main",
            scene_file=scene_file,
        )
        semantic_link_button_path = semantic_link_button["path"]
        link_button_configuration = await app.service.button_2d_set(
            semantic_link_button_path,
            {
                "text": "Godot Docs",
                "uri": "https://docs.godotengine.org/en/latest/",
                "underline": "on_hover",
                "text_overrun_behavior": "ellipsis_force",
                "ellipsis_char": ">",
                "text_direction": "ltr",
                "language": "en",
            },
            scene_file=scene_file,
        )
        link_button_state = link_button_configuration["configuration"]["link_button"]
        if (
            not link_button_configuration.get("changed")
            or link_button_state["uri"] != "https://docs.godotengine.org/en/latest/"
            or link_button_state["underline"] != "on_hover"
            or link_button_state["text_overrun_behavior"] != "ellipsis_force"
            or link_button_state["ellipsis_char"] != ">"
            or link_button_state["text_direction"] != "ltr"
            or link_button_state["language"] != "en"
        ):
            raise RuntimeError("LinkButton semantic configuration was not applied")
        if not (await app.service.scene_undo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("LinkButton semantic configuration was not undoable")
        restored_link_button = await app.service.button_2d_get(
            semantic_link_button_path, scene_file=scene_file
        )
        if restored_link_button["configuration"]["link_button"]["uri"]:
            raise RuntimeError("Undo did not restore LinkButton URI")
        if not (await app.service.scene_redo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("LinkButton semantic configuration was not redoable")
        await _expect_godot_error(
            app.service.button_2d_get(semantic_line_path, scene_file=scene_file),
            "BASE_BUTTON_REQUIRED",
        )

        option_button = await app.service.node_create(
            type_name="OptionButton",
            name="AgentOptionMenu",
            parent_path="/Main",
            scene_file=scene_file,
        )
        option_button_path = option_button["path"]
        option_menu = await app.service.button_menu_items_set(
            option_button_path,
            [
                {
                    "kind": "normal",
                    "text": "Easy",
                    "id": 10,
                    "icon_path": "res://test_icon.svg",
                    "metadata": {"difficulty": 1},
                    "tooltip": "Suitable for new players",
                },
                {"kind": "normal", "text": "Normal", "id": 20, "disabled": True},
                {"kind": "separator", "text": "Locked"},
            ],
            selected_index=1,
            scene_file=scene_file,
        )
        if (
            option_menu["type"] != "OptionButton"
            or option_menu["item_count"] != 3
            or option_menu["selected_index"] != 1
            or option_menu["items"][0]["icon"]["resource_path"] != "res://test_icon.svg"
            or option_menu["items"][0]["metadata"] != {"difficulty": 1}
            or option_menu["items"][2]["kind"] != "separator"
        ):
            raise RuntimeError("OptionButton menu items were not applied")
        if not (await app.service.scene_undo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("OptionButton menu item update was not undoable")
        restored_option_menu = await app.service.button_menu_items_get(
            option_button_path, scene_file=scene_file
        )
        if restored_option_menu["item_count"] != 0:
            raise RuntimeError("Undo did not restore the empty OptionButton menu")
        if not (await app.service.scene_redo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("OptionButton menu item update was not redoable")
        resized_option_menu = await app.service.button_menu_items_set(
            option_button_path,
            [{"kind": "normal", "text": "Easy", "id": 10}],
            scene_file=scene_file,
        )
        if resized_option_menu["selected_index"] != -1:
            raise RuntimeError("OptionButton did not clear an out-of-range preserved selection")
        cleared_option_menu = await app.service.button_menu_items_clear(
            option_button_path, scene_file=scene_file
        )
        if cleared_option_menu["item_count"] != 0 or not cleared_option_menu["undoable"]:
            raise RuntimeError("OptionButton menu items were not cleared")
        if not (await app.service.scene_undo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("OptionButton menu clearing was not undoable")

        menu_button = await app.service.node_create(
            type_name="MenuButton",
            name="AgentMenuButton",
            parent_path="/Main",
            scene_file=scene_file,
        )
        menu_button_path = menu_button["path"]
        menu_items = await app.service.button_menu_items_set(
            menu_button_path,
            [
                {
                    "kind": "normal",
                    "text": "Open",
                    "id": 100,
                    "icon_path": "res://test_icon.svg",
                    "metadata": {"command": "open"},
                    "tooltip": "Open an existing scene",
                    "accelerator": 79,
                    "indent": 1,
                    "text_direction": "ltr",
                    "auto_translate_mode": "always",
                    "icon_max_width": 24,
                    "icon_modulate": {"r": 0.8, "g": 0.9, "b": 1.0, "a": 1.0},
                },
                {"kind": "check", "text": "Show Grid", "checked": True},
                {"kind": "radio", "text": "Snap", "checked": True},
                {"kind": "multistate", "text": "Quality", "max_states": 3, "state": 2},
                {"kind": "separator", "text": "Advanced"},
            ],
            scene_file=scene_file,
        )
        if (
            menu_items["type"] != "MenuButton"
            or menu_items["item_count"] != 5
            or menu_items["items"][0]["icon"]["resource_path"] != "res://test_icon.svg"
            or menu_items["items"][0]["metadata"] != {"command": "open"}
            or menu_items["items"][1]["checked"] is not True
            or menu_items["items"][2]["kind"] != "radio"
            or menu_items["items"][3]["state"] != 2
            or menu_items["items"][4]["kind"] != "separator"
        ):
            raise RuntimeError("MenuButton menu items were not applied")
        if not (await app.service.scene_undo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("MenuButton menu item update was not undoable")
        restored_menu_button = await app.service.button_menu_items_get(
            menu_button_path, scene_file=scene_file
        )
        if restored_menu_button["item_count"] != 0:
            raise RuntimeError("Undo did not restore the empty MenuButton menu")
        if not (await app.service.scene_redo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("MenuButton menu item update was not redoable")
        cleared_menu_button = await app.service.button_menu_items_clear(
            menu_button_path, scene_file=scene_file
        )
        if cleared_menu_button["item_count"] != 0:
            raise RuntimeError("MenuButton menu items were not cleared")
        if not (await app.service.scene_undo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("MenuButton menu clearing was not undoable")
        await _expect_godot_error(
            app.service.button_menu_items_get(semantic_button_path, scene_file=scene_file),
            "BUTTON_MENU_REQUIRED",
        )

        _trace_smoke("starting Container smoke")
        hbox = await app.service.node_create(
            type_name="HBoxContainer",
            name="AgentHBox",
            parent_path="/Main",
            scene_file=scene_file,
        )
        hbox_path = hbox["path"]
        hbox_primary = await app.service.node_create(
            type_name="Label",
            name="AgentHBoxPrimary",
            parent_path=hbox_path,
            scene_file=scene_file,
        )
        hbox_primary_path = hbox_primary["path"]
        await app.service.node_create(
            type_name="Label",
            name="AgentHBoxSecondary",
            parent_path=hbox_path,
            scene_file=scene_file,
        )
        hbox_initial = await app.service.container_2d_get(
            hbox_path, child_limit=1, scene_file=scene_file
        )
        if (
            hbox_initial["type"] != "HBoxContainer"
            or hbox_initial["configuration"]["alignment"] != "begin"
            or hbox_initial["children_total"] != 2
            or len(hbox_initial["children"]) != 1
            or hbox_initial["children_truncated"] is not True
            or "size_flags_horizontal"
            not in hbox_initial["supported_child_layout_properties"]
        ):
            raise RuntimeError("HBoxContainer configuration was not reported")
        hbox_configuration = await app.service.container_2d_set(
            hbox_path,
            {"alignment": "end", "accessibility_region": True},
            scene_file=scene_file,
        )
        if (
            not hbox_configuration.get("changed")
            or hbox_configuration["configuration"]["alignment"] != "end"
            or hbox_configuration["configuration"]["accessibility_region"] is not True
        ):
            raise RuntimeError("HBoxContainer configuration was not applied")
        if not (await app.service.scene_undo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("HBoxContainer configuration was not undoable")
        restored_hbox = await app.service.container_2d_get(hbox_path, scene_file=scene_file)
        if (
            restored_hbox["configuration"]["alignment"] != "begin"
            or restored_hbox["configuration"]["accessibility_region"] is not False
        ):
            raise RuntimeError("Undo did not restore HBoxContainer configuration")
        if not (await app.service.scene_redo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("HBoxContainer configuration was not redoable")
        hbox_child_layout = await app.service.container_child_layout_set(
            hbox_path,
            hbox_primary_path,
            {
                "custom_minimum_size": {"x": 240.0, "y": 48.0},
                "size_flags_horizontal": ["fill", "expand"],
                "size_flags_vertical": ["shrink_end"],
                "size_flags_stretch_ratio": 2.5,
            },
            scene_file=scene_file,
        )
        if (
            not hbox_child_layout.get("changed")
            or hbox_child_layout["child"]["custom_minimum_size"]
            != {"x": 240.0, "y": 48.0}
            or hbox_child_layout["child"]["size_flags_horizontal"] != ["fill", "expand"]
            or hbox_child_layout["child"]["size_flags_vertical"] != ["shrink_end"]
            or not _is_close(hbox_child_layout["child"]["size_flags_stretch_ratio"], 2.5)
        ):
            raise RuntimeError("Container child layout constraints were not applied")
        await _expect_godot_error(
            app.service.control_set_layout(
                hbox_primary_path,
                offsets={"left": 8.0, "top": 0.0, "right": 8.0, "bottom": 0.0},
                scene_file=scene_file,
            ),
            "CONTAINER_LAYOUT_MANAGED",
        )
        if not (await app.service.scene_undo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("Container child layout constraints were not undoable")
        restored_hbox_child = await app.service.container_2d_get(
            hbox_path, scene_file=scene_file
        )
        if restored_hbox_child["children"][0]["custom_minimum_size"] != {"x": 0.0, "y": 0.0}:
            raise RuntimeError("Undo did not restore Container child layout constraints")
        if not (await app.service.scene_redo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("Container child layout constraints were not redoable")
        _trace_smoke("HBoxContainer smoke passed")

        grid = await app.service.node_create(
            type_name="GridContainer",
            name="AgentGrid",
            parent_path="/Main",
            scene_file=scene_file,
        )
        grid_path = grid["path"]
        grid_child = await app.service.node_create(
            type_name="Label",
            name="AgentGridChild",
            parent_path=grid_path,
            scene_file=scene_file,
        )
        grid_configuration = await app.service.container_2d_set(
            grid_path, {"columns": 3}, scene_file=scene_file
        )
        if grid_configuration["configuration"]["columns"] != 3:
            raise RuntimeError("GridContainer columns were not applied")
        await _expect_godot_error(
            app.service.container_child_layout_set(
                hbox_path,
                grid_child["path"],
                {"size_flags_horizontal": ["expand"]},
                scene_file=scene_file,
            ),
            "CONTAINER_CHILD_NOT_DIRECT",
        )
        _trace_smoke("GridContainer smoke passed")

        aspect = await app.service.node_create(
            type_name="AspectRatioContainer",
            name="AgentAspect",
            parent_path="/Main",
            scene_file=scene_file,
        )
        aspect_configuration = await app.service.container_2d_set(
            aspect["path"],
            {
                "ratio": 1.5,
                "stretch_mode": "cover",
                "alignment_horizontal": "end",
                "alignment_vertical": "center",
            },
            scene_file=scene_file,
        )
        if (
            not _is_close(aspect_configuration["configuration"]["ratio"], 1.5)
            or aspect_configuration["configuration"]["stretch_mode"] != "cover"
            or aspect_configuration["configuration"]["alignment_horizontal"] != "end"
            or aspect_configuration["configuration"]["alignment_vertical"] != "center"
        ):
            raise RuntimeError("AspectRatioContainer configuration was not applied")
        _trace_smoke("AspectRatioContainer smoke passed")

        flow = await app.service.node_create(
            type_name="HFlowContainer",
            name="AgentFlow",
            parent_path="/Main",
            scene_file=scene_file,
        )
        flow_configuration = await app.service.container_2d_set(
            flow["path"],
            {
                "alignment": "end",
                "last_wrap_alignment": "center",
                "reverse_fill": True,
            },
            scene_file=scene_file,
        )
        if (
            flow_configuration["configuration"]["alignment"] != "end"
            or flow_configuration["configuration"]["last_wrap_alignment"] != "center"
            or flow_configuration["configuration"]["reverse_fill"] is not True
        ):
            raise RuntimeError("HFlowContainer configuration was not applied")
        _trace_smoke("HFlowContainer smoke passed")

        split = await app.service.node_create(
            type_name="HSplitContainer",
            name="AgentSplit",
            parent_path="/Main",
            scene_file=scene_file,
        )
        split_path = split["path"]
        await app.service.node_create(
            type_name="Label",
            name="AgentSplitLeft",
            parent_path=split_path,
            scene_file=scene_file,
        )
        await app.service.node_create(
            type_name="Label",
            name="AgentSplitRight",
            parent_path=split_path,
            scene_file=scene_file,
        )
        split_configuration = await app.service.container_2d_set(
            split_path,
            {
                "split_offsets": [32],
                "collapsed": True,
                "dragging_enabled": False,
                "dragger_visibility": "hidden",
                "touch_dragger_enabled": True,
                "drag_nested_intersections": True,
                "drag_area_margin_begin": 4,
                "drag_area_margin_end": 5,
                "drag_area_offset": 6,
                "drag_area_highlight_in_editor": False,
            },
            scene_file=scene_file,
        )
        split_state = split_configuration["configuration"]
        if (
            split_state["split_offsets"] != [32]
            or split_state["collapsed"] is not True
            or split_state["dragging_enabled"] is not False
            or split_state["dragger_visibility"] != "hidden"
            or split_state["touch_dragger_enabled"] is not True
            or split_state["drag_nested_intersections"] is not True
            or split_state["drag_area_margin_begin"] != 4
            or split_state["drag_area_margin_end"] != 5
            or split_state["drag_area_offset"] != 6
            or split_state["drag_area_highlight_in_editor"] is not False
        ):
            raise RuntimeError("HSplitContainer configuration was not applied")
        _trace_smoke("HSplitContainer smoke passed")

        scroll = await app.service.node_create(
            type_name="ScrollContainer",
            name="AgentScroll",
            parent_path="/Main",
            scene_file=scene_file,
        )
        scroll_configuration = await app.service.container_2d_set(
            scroll["path"],
            {
                "follow_focus": False,
                "draw_focus_border": False,
                "scroll_horizontal_custom_step": 24.0,
                "scroll_vertical_custom_step": 12.0,
                "horizontal_scroll_mode": "always_show",
                "vertical_scroll_mode": "reserve",
                "scroll_horizontal_by_default": True,
                "scroll_deadzone": 8,
                "scroll_hint_mode": "all",
                "tile_scroll_hint": True,
            },
            scene_file=scene_file,
        )
        scroll_state = scroll_configuration["configuration"]
        if (
            scroll_state["follow_focus"] is not False
            or scroll_state["draw_focus_border"] is not False
            or not _is_close(scroll_state["scroll_horizontal_custom_step"], 24.0)
            or not _is_close(scroll_state["scroll_vertical_custom_step"], 12.0)
            or scroll_state["horizontal_scroll_mode"] != "always_show"
            or scroll_state["vertical_scroll_mode"] != "reserve"
            or scroll_state["scroll_horizontal_by_default"] is not True
            or scroll_state["scroll_deadzone"] != 8
            or scroll_state["scroll_hint_mode"] != "all"
            or scroll_state["tile_scroll_hint"] is not True
        ):
            raise RuntimeError("ScrollContainer configuration was not applied")
        _trace_smoke("ScrollContainer smoke passed")

        tabs = await app.service.node_create(
            type_name="TabContainer",
            name="AgentTabs",
            parent_path="/Main",
            scene_file=scene_file,
        )
        tabs_path = tabs["path"]
        tab_one = await app.service.node_create(
            type_name="Label",
            name="AgentTabOne",
            parent_path=tabs_path,
            scene_file=scene_file,
        )
        tab_one_path = tab_one["path"]
        await app.service.node_create(
            type_name="Label",
            name="AgentTabTwo",
            parent_path=tabs_path,
            scene_file=scene_file,
        )
        tabs_configuration = await app.service.container_2d_set(
            tabs_path,
            {
                "tab_alignment": "center",
                "current_tab": 1,
                "tabs_position": "bottom",
                "clip_tabs": False,
                "tabs_visible": False,
                "switch_on_drag_hover": True,
                "drag_to_rearrange_enabled": True,
                "tabs_rearrange_group": 9,
                "use_hidden_tabs_for_min_size": True,
                "tab_focus_mode": "all",
                "deselect_enabled": True,
            },
            scene_file=scene_file,
        )
        tabs_state = tabs_configuration["configuration"]
        if (
            tabs_state["tab_alignment"] != "center"
            or tabs_state["current_tab"] != 1
            or tabs_state["tabs_position"] != "bottom"
            or tabs_state["clip_tabs"] is not False
            or tabs_state["tabs_visible"] is not False
            or tabs_state["switch_on_drag_hover"] is not True
            or tabs_state["drag_to_rearrange_enabled"] is not True
            or tabs_state["tabs_rearrange_group"] != 9
            or tabs_state["use_hidden_tabs_for_min_size"] is not True
            or tabs_state["tab_focus_mode"] != "all"
            or tabs_state["deselect_enabled"] is not True
        ):
            raise RuntimeError("TabContainer configuration was not applied")
        tab_items_initial = await app.service.tab_container_items_get(
            tabs_path, item_limit=1, scene_file=scene_file
        )
        if (
            tab_items_initial["items_total"] != 2
            or len(tab_items_initial["items"]) != 1
            or tab_items_initial["items_truncated"] is not True
            or tab_items_initial["items"][0]["path"] != tab_one_path
            or tab_items_initial["items"][0]["title"] != "AgentTabOne"
            or "button_icon_path" not in tab_items_initial["supported_item_properties"]
        ):
            raise RuntimeError("TabContainer items were not reported")
        tab_item_update = await app.service.tab_container_item_set(
            tabs_path,
            tab_one_path,
            {
                "title": "Configured tab",
                "tooltip": "Configured by the MCP smoke test",
                "icon_path": "res://test_icon.svg",
                "icon_max_width": 24,
                "disabled": True,
                "hidden": True,
                "metadata": {"owner": "mcp", "priority": 2},
                "button_icon_path": "res://test_icon.svg",
            },
            scene_file=scene_file,
        )
        tab_item = tab_item_update["item"]
        if (
            not tab_item_update.get("changed")
            or tab_item["title"] != "Configured tab"
            or tab_item["tooltip"] != "Configured by the MCP smoke test"
            or tab_item["icon_max_width"] != 24
            or tab_item["disabled"] is not True
            or tab_item["hidden"] is not True
            or tab_item["metadata"] != {"owner": "mcp", "priority": 2}
            or tab_item["icon"].get("resource_path") != "res://test_icon.svg"
            or tab_item["button_icon"].get("resource_path") != "res://test_icon.svg"
        ):
            raise RuntimeError("TabContainer item configuration was not applied")
        if not (await app.service.scene_undo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("TabContainer item configuration was not undoable")
        restored_tab_items = await app.service.tab_container_items_get(tabs_path, scene_file=scene_file)
        restored_tab_item = restored_tab_items["items"][0]
        if (
            restored_tab_item["title"] != "AgentTabOne"
            or restored_tab_item["tooltip"] != ""
            or restored_tab_item["disabled"] is not False
            or restored_tab_item["hidden"] is not False
            or restored_tab_item["metadata"] is not None
            or restored_tab_item["icon"]["assigned"] is not False
            or restored_tab_item["button_icon"]["assigned"] is not False
        ):
            raise RuntimeError("Undo did not restore TabContainer item configuration")
        if not (await app.service.scene_redo(scene_file=scene_file)).get("changed"):
            raise RuntimeError("TabContainer item configuration was not redoable")
        await _expect_godot_error(
            app.service.tab_container_items_get(hbox_path, scene_file=scene_file),
            "TAB_CONTAINER_REQUIRED",
        )
        _trace_smoke("TabContainer smoke passed")

        subviewport_container = await app.service.node_create(
            type_name="SubViewportContainer",
            name="AgentSubViewportContainer",
            parent_path="/Main",
            scene_file=scene_file,
        )
        subviewport_configuration = await app.service.container_2d_set(
            subviewport_container["path"],
            {"stretch": True, "stretch_shrink": 2, "mouse_target": False},
            scene_file=scene_file,
        )
        if (
            subviewport_configuration["configuration"]["stretch"] is not True
            or subviewport_configuration["configuration"]["stretch_shrink"] != 2
            or subviewport_configuration["configuration"]["mouse_target"] is not False
        ):
            raise RuntimeError("SubViewportContainer configuration was not applied")
        _trace_smoke("Container smoke completed")

        initial_canvas_material = await app.service.canvas_item_material_get(
            canvas_item_path,
            scene_file=scene_file,
        )
        if (
            initial_canvas_material["material"]["assigned"]
            or initial_canvas_material["configuration"] is not None
        ):
            raise RuntimeError("New CanvasItem unexpectedly had a material")
        canvas_material = await app.service.canvas_item_material_create(
            canvas_item_path,
            scene_file=scene_file,
        )
        if (
            canvas_material.get("created") is not True
            or canvas_material["material"]["origin"] != "embedded"
            or canvas_material["configuration"]["blend_mode"] != "mix"
        ):
            raise RuntimeError(
                "CanvasItemMaterial was not created as an embedded resource"
            )
        await _expect_godot_error(
            app.service.canvas_item_material_create(
                canvas_item_path, scene_file=scene_file
            ),
            "CANVAS_ITEM_MATERIAL_ALREADY_ASSIGNED",
        )
        undo_canvas_material_create = await app.service.scene_undo(
            scene_file=scene_file
        )
        if not undo_canvas_material_create.get("changed"):
            raise RuntimeError("CanvasItemMaterial creation was not undoable")
        restored_empty_canvas_material = await app.service.canvas_item_material_get(
            canvas_item_path,
            scene_file=scene_file,
        )
        if restored_empty_canvas_material["material"]["assigned"]:
            raise RuntimeError("Undo did not remove the CanvasItemMaterial")
        redo_canvas_material_create = await app.service.scene_redo(
            scene_file=scene_file
        )
        if not redo_canvas_material_create.get("changed"):
            raise RuntimeError("CanvasItemMaterial creation was not redoable")
        await _expect_godot_error(
            app.service.canvas_item_material_bind(
                canvas_item_path,
                "res://test_cpu_curve.tres",
                scene_file=scene_file,
            ),
            "RESOURCE_TYPE_MISMATCH",
        )
        bound_canvas_material = await app.service.canvas_item_material_bind(
            canvas_item_path,
            "res://test_canvas_item_material.tres",
            scene_file=scene_file,
        )
        if (
            not bound_canvas_material.get("undoable")
            or bound_canvas_material.get("bound_external_resource") is not True
            or bound_canvas_material["material"]["origin"] != "external"
            or bound_canvas_material["material"]["resource_path"]
            != "res://test_canvas_item_material.tres"
        ):
            raise RuntimeError("External CanvasItemMaterial was not bound")
        canvas_material_update = await app.service.canvas_item_material_set(
            canvas_item_path,
            {
                "blend_mode": "add",
                "light_mode": "unshaded",
                "particles_animation": True,
                "particles_anim_h_frames": 4,
                "particles_anim_v_frames": 2,
                "particles_anim_loop": True,
            },
            scene_file=scene_file,
        )
        canvas_material_configuration = canvas_material_update["configuration"]
        if (
            not canvas_material_update.get("undoable")
            or canvas_material_update.get("copied_external_material") is not True
            or canvas_material_update["material"]["origin"] != "embedded"
            or canvas_material_configuration["blend_mode"] != "add"
            or canvas_material_configuration["light_mode"] != "unshaded"
            or canvas_material_configuration["particles_animation"] is not True
            or canvas_material_configuration["particles_anim_h_frames"] != 4
            or canvas_material_configuration["particles_anim_v_frames"] != 2
            or canvas_material_configuration["particles_anim_loop"] is not True
        ):
            raise RuntimeError("CanvasItemMaterial configuration was not applied")
        undo_canvas_material_update = await app.service.scene_undo(
            scene_file=scene_file
        )
        if not undo_canvas_material_update.get("changed"):
            raise RuntimeError("CanvasItemMaterial update was not undoable")
        restored_external_canvas_material = await app.service.canvas_item_material_get(
            canvas_item_path,
            scene_file=scene_file,
        )
        if (
            restored_external_canvas_material["material"]["resource_path"]
            != "res://test_canvas_item_material.tres"
        ):
            raise RuntimeError("Undo did not restore the external CanvasItemMaterial")
        redo_canvas_material_update = await app.service.scene_redo(
            scene_file=scene_file
        )
        if not redo_canvas_material_update.get("changed"):
            raise RuntimeError("CanvasItemMaterial update was not redoable")
        cleared_canvas_material = await app.service.canvas_item_material_clear(
            canvas_item_path,
            scene_file=scene_file,
        )
        if cleared_canvas_material["material"]["assigned"]:
            raise RuntimeError("CanvasItemMaterial was not cleared")
        undo_canvas_material_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_canvas_material_clear.get("changed"):
            raise RuntimeError("CanvasItemMaterial clear was not undoable")
        restored_embedded_canvas_material = await app.service.canvas_item_material_get(
            canvas_item_path,
            scene_file=scene_file,
        )
        if restored_embedded_canvas_material["material"]["origin"] != "embedded":
            raise RuntimeError("Undo did not restore the embedded CanvasItemMaterial")

        initial_canvas_shader = await app.service.canvas_item_shader_get(
            canvas_item_path,
            scene_file=scene_file,
        )
        if initial_canvas_shader["material"]["is_shader_material"]:
            raise RuntimeError(
                "CanvasItem unexpectedly had a ShaderMaterial before shader creation"
            )
        shader_source = (
            "shader_type canvas_item;\n\n"
            "void fragment() {\n"
            "\tCOLOR = vec4(0.2, 0.7, 1.0, 1.0);\n"
            "}\n"
        )
        await _expect_godot_error(
            app.service.canvas_item_shader_create(
                canvas_item_path,
                source="shader_type spatial;\n",
                replace_existing=True,
                scene_file=scene_file,
            ),
            "CANVAS_ITEM_SHADER_REQUIRED",
        )
        await _expect_godot_error(
            app.service.canvas_item_shader_create(
                canvas_item_path,
                source='shader_type canvas_item;\n#include "res://shared.gdshaderinc"\n',
                replace_existing=True,
                scene_file=scene_file,
            ),
            "CANVAS_ITEM_SHADER_INCLUDE_UNSUPPORTED",
        )
        await _expect_godot_error(
            app.service.canvas_item_shader_create(
                canvas_item_path,
                source=shader_source,
                scene_file=scene_file,
            ),
            "CANVAS_ITEM_MATERIAL_ALREADY_ASSIGNED",
        )
        created_canvas_shader = await app.service.canvas_item_shader_create(
            canvas_item_path,
            source=shader_source,
            replace_existing=True,
            scene_file=scene_file,
        )
        if (
            created_canvas_shader.get("created") is not True
            or created_canvas_shader["material"]["origin"] != "embedded"
            or created_canvas_shader["shader"]["origin"] != "embedded"
            or created_canvas_shader["shader"]["mode"] != "canvas_item"
            or created_canvas_shader["shader"]["source"] != shader_source
        ):
            raise RuntimeError("Embedded CanvasItem ShaderMaterial was not created")
        undo_canvas_shader_create = await app.service.scene_undo(scene_file=scene_file)
        if not undo_canvas_shader_create.get("changed"):
            raise RuntimeError("CanvasItem shader creation was not undoable")
        restored_canvas_material_after_shader_undo = (
            await app.service.canvas_item_material_get(
                canvas_item_path,
                scene_file=scene_file,
            )
        )
        if not restored_canvas_material_after_shader_undo["material"][
            "is_canvas_item_material"
        ]:
            raise RuntimeError(
                "Undo did not restore the CanvasItemMaterial after shader creation"
            )
        redo_canvas_shader_create = await app.service.scene_redo(scene_file=scene_file)
        if not redo_canvas_shader_create.get("changed"):
            raise RuntimeError("CanvasItem shader creation was not redoable")
        await _expect_godot_error(
            app.service.canvas_item_shader_bind(
                canvas_item_path,
                "res://test_canvas_item_material.tres",
                scene_file=scene_file,
            ),
            "RESOURCE_TYPE_MISMATCH",
        )
        await _expect_godot_error(
            app.service.canvas_item_shader_bind(
                canvas_item_path,
                "res://test_spatial_shader_material.tres",
                scene_file=scene_file,
            ),
            "CANVAS_ITEM_SHADER_REQUIRED",
        )
        bound_canvas_shader = await app.service.canvas_item_shader_bind(
            canvas_item_path,
            "res://test_canvas_item_shader_material.tres",
            scene_file=scene_file,
        )
        if (
            not bound_canvas_shader.get("undoable")
            or bound_canvas_shader.get("bound_external_resource") is not True
            or bound_canvas_shader["material"]["origin"] != "external"
            or bound_canvas_shader["shader"]["mode"] != "canvas_item"
        ):
            raise RuntimeError("External CanvasItem ShaderMaterial was not bound")
        external_uniform_update = await app.service.canvas_item_shader_uniforms_set(
            canvas_item_path,
            {"external_amount": 0.75},
            scene_file=scene_file,
        )
        external_uniforms = {
            uniform["name"]: uniform for uniform in external_uniform_update["uniforms"]
        }
        if (
            not external_uniform_update.get("undoable")
            or external_uniform_update.get("copied_external_material") is not True
            or external_uniform_update["material"]["origin"] != "embedded"
            or external_uniforms["external_amount"]["value"] != 0.75
        ):
            raise RuntimeError(
                "External CanvasItem ShaderMaterial uniform was not copy-on-write updated"
            )
        undo_external_uniform_update = await app.service.scene_undo(
            scene_file=scene_file
        )
        if not undo_external_uniform_update.get("changed"):
            raise RuntimeError(
                "External CanvasItem ShaderMaterial uniform update was not undoable"
            )
        restored_external_canvas_shader_after_uniform_update = (
            await app.service.canvas_item_shader_get(
                canvas_item_path,
                scene_file=scene_file,
            )
        )
        if (
            restored_external_canvas_shader_after_uniform_update["material"][
                "resource_path"
            ]
            != "res://test_canvas_item_shader_material.tres"
        ):
            raise RuntimeError(
                "Undo did not restore external CanvasItem ShaderMaterial after uniform update"
            )
        updated_shader_source = (
            "shader_type canvas_item;\n\n"
            "uniform float amount = 0.5;\n\n"
            "uniform vec2 uv_offset = vec2(0.0);\n"
            "uniform vec4 tint : source_color = vec4(1.0);\n"
            "uniform sampler2D overlay_texture : source_color;\n\n"
            "void fragment() {\n"
            "\tCOLOR = texture(overlay_texture, UV + uv_offset) * tint * amount;\n"
            "}\n"
        )
        canvas_shader_update = await app.service.canvas_item_shader_set(
            canvas_item_path,
            updated_shader_source,
            scene_file=scene_file,
        )
        if (
            not canvas_shader_update.get("undoable")
            or canvas_shader_update.get("copied_external_material") is not True
            or canvas_shader_update["material"]["origin"] != "embedded"
            or canvas_shader_update["shader"]["origin"] != "embedded"
            or canvas_shader_update["shader"]["source"] != updated_shader_source
        ):
            raise RuntimeError(
                "CanvasItem ShaderMaterial source was not copy-on-write updated"
            )
        shader_uniforms = {
            uniform["name"]: uniform for uniform in canvas_shader_update["uniforms"]
        }
        if set(shader_uniforms) != {"amount", "uv_offset", "tint", "overlay_texture"}:
            raise RuntimeError(
                "CanvasItem ShaderMaterial did not expose declared uniforms"
            )
        if not all(uniform["supported"] for uniform in shader_uniforms.values()):
            raise RuntimeError(
                "CanvasItem ShaderMaterial did not support a standard 2D uniform type"
            )
        undo_canvas_shader_update = await app.service.scene_undo(scene_file=scene_file)
        if not undo_canvas_shader_update.get("changed"):
            raise RuntimeError("CanvasItem ShaderMaterial update was not undoable")
        restored_external_canvas_shader = await app.service.canvas_item_shader_get(
            canvas_item_path,
            scene_file=scene_file,
        )
        if (
            restored_external_canvas_shader["material"]["resource_path"]
            != "res://test_canvas_item_shader_material.tres"
        ):
            raise RuntimeError(
                "Undo did not restore the external CanvasItem ShaderMaterial"
            )
        redo_canvas_shader_update = await app.service.scene_redo(scene_file=scene_file)
        if not redo_canvas_shader_update.get("changed"):
            raise RuntimeError("CanvasItem ShaderMaterial update was not redoable")
        await _expect_godot_error(
            app.service.canvas_item_shader_uniforms_set(
                canvas_item_path,
                {"unknown_uniform": 1.0},
                scene_file=scene_file,
            ),
            "CANVAS_ITEM_SHADER_UNIFORM_NOT_FOUND",
        )
        canvas_shader_uniform_update = (
            await app.service.canvas_item_shader_uniforms_set(
                canvas_item_path,
                {
                    "amount": 0.75,
                    "uv_offset": {"x": 0.125, "y": -0.25},
                    "tint": {"r": 1.0, "g": 0.5, "b": 0.25, "a": 0.8},
                    "overlay_texture": "res://test_icon.svg",
                },
                scene_file=scene_file,
            )
        )
        updated_uniforms = {
            uniform["name"]: uniform
            for uniform in canvas_shader_uniform_update["uniforms"]
        }
        if (
            not canvas_shader_uniform_update.get("undoable")
            or canvas_shader_uniform_update.get("copied_external_material") is not False
            or canvas_shader_uniform_update.get("updated_uniforms")
            != ["amount", "overlay_texture", "tint", "uv_offset"]
            or updated_uniforms["amount"]["value"] != 0.75
            or updated_uniforms["uv_offset"]["value"] != {"x": 0.125, "y": -0.25}
            or not _color_matches(
                updated_uniforms["tint"]["value"],
                {"r": 1.0, "g": 0.5, "b": 0.25, "a": 0.8},
            )
            or updated_uniforms["overlay_texture"]["value"].get("resource_path")
            != "res://test_icon.svg"
        ):
            raise RuntimeError(
                "CanvasItem ShaderMaterial uniforms were not copy-on-write updated: "
                f"{canvas_shader_uniform_update}"
            )
        undo_canvas_shader_uniform_update = await app.service.scene_undo(
            scene_file=scene_file
        )
        if not undo_canvas_shader_uniform_update.get("changed"):
            raise RuntimeError(
                "CanvasItem ShaderMaterial uniform update was not undoable"
            )
        restored_default_uniforms = await app.service.canvas_item_shader_get(
            canvas_item_path,
            scene_file=scene_file,
        )
        restored_default_uniforms_by_name = {
            uniform["name"]: uniform
            for uniform in restored_default_uniforms["uniforms"]
        }
        if restored_default_uniforms_by_name["amount"]["has_override"]:
            raise RuntimeError("Undo did not restore the default shader uniform values")
        redo_canvas_shader_uniform_update = await app.service.scene_redo(
            scene_file=scene_file
        )
        if not redo_canvas_shader_uniform_update.get("changed"):
            raise RuntimeError(
                "CanvasItem ShaderMaterial uniform update was not redoable"
            )
        cleared_canvas_shader_uniforms = (
            await app.service.canvas_item_shader_uniforms_clear(
                canvas_item_path,
                ["amount", "tint"],
                scene_file=scene_file,
            )
        )
        cleared_uniforms_by_name = {
            uniform["name"]: uniform
            for uniform in cleared_canvas_shader_uniforms["uniforms"]
        }
        if (
            cleared_canvas_shader_uniforms.get("cleared_uniforms") != ["amount", "tint"]
            or cleared_uniforms_by_name["amount"]["has_override"]
            or cleared_uniforms_by_name["tint"]["has_override"]
        ):
            raise RuntimeError(
                "CanvasItem ShaderMaterial uniform overrides were not cleared"
            )
        undo_canvas_shader_uniform_clear = await app.service.scene_undo(
            scene_file=scene_file
        )
        if not undo_canvas_shader_uniform_clear.get("changed"):
            raise RuntimeError(
                "CanvasItem ShaderMaterial uniform clear was not undoable"
            )
        restored_canvas_shader_uniforms = await app.service.canvas_item_shader_get(
            canvas_item_path,
            scene_file=scene_file,
        )
        restored_canvas_shader_uniforms_by_name = {
            uniform["name"]: uniform
            for uniform in restored_canvas_shader_uniforms["uniforms"]
        }
        if restored_canvas_shader_uniforms_by_name["amount"]["value"] != 0.75:
            raise RuntimeError(
                "Undo did not restore the CanvasItem ShaderMaterial uniform override"
            )
        cleared_canvas_shader = await app.service.canvas_item_shader_clear(
            canvas_item_path,
            scene_file=scene_file,
        )
        if cleared_canvas_shader["material"]["assigned"]:
            raise RuntimeError("CanvasItem ShaderMaterial was not cleared")
        undo_canvas_shader_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_canvas_shader_clear.get("changed"):
            raise RuntimeError("CanvasItem ShaderMaterial clear was not undoable")
        restored_embedded_canvas_shader = await app.service.canvas_item_shader_get(
            canvas_item_path,
            scene_file=scene_file,
        )
        if restored_embedded_canvas_shader["material"]["origin"] != "embedded":
            raise RuntimeError(
                "Undo did not restore the embedded CanvasItem ShaderMaterial"
            )

        cpu_particles = await app.service.node_create(
            type_name="CPUParticles2D",
            name="AgentCpuParticles",
            parent_path="/Main",
            scene_file=scene_file,
        )
        cpu_particles_path = cpu_particles["path"]
        initial_cpu_particles = await app.service.cpu_particles_2d_get(
            cpu_particles_path, scene_file=scene_file
        )
        if initial_cpu_particles["configuration"]["texture_path"] != "":
            raise RuntimeError("New CPUParticles2D had an unexpected texture binding")
        await _expect_godot_error(
            app.service.cpu_particles_2d_set(
                cpu_particles_path,
                {"texture_path": "res://test_audio.tres"},
                scene_file=scene_file,
            ),
            "RESOURCE_TYPE_MISMATCH",
        )
        cpu_particles_update = await app.service.cpu_particles_2d_set(
            cpu_particles_path,
            {
                "emitting": True,
                "amount": 96,
                "texture_path": "res://test_icon.svg",
                "lifetime": 2.5,
                "one_shot": True,
                "preprocess": 1.0,
                "speed_scale": 1.5,
                "explosiveness": 0.4,
                "randomness": 0.2,
                "use_fixed_seed": True,
                "seed": 4242,
                "lifetime_randomness": 0.3,
                "fixed_fps": 30,
                "fractional_delta": False,
                "local_coords": True,
                "draw_order": "lifetime",
                "emission_shape": "directed_points",
                "emission_sphere_radius": 12.0,
                "emission_rect_extents": {"x": 32.0, "y": 16.0},
                "emission_points": [{"x": -8.0, "y": 4.0}, {"x": 8.0, "y": -4.0}],
                "emission_normals": [{"x": 0.0, "y": -1.0}, {"x": 1.0, "y": 0.0}],
                "emission_colors": [
                    {"r": 1.0, "g": 0.5, "b": 0.25, "a": 0.8},
                    {"r": 0.1, "g": 0.2, "b": 0.3, "a": 0.4},
                ],
                "emission_ring_inner_radius": 4.0,
                "emission_ring_radius": 10.0,
                "align_y_to_velocity": True,
                "direction": {"x": 0.5, "y": -1.0},
                "spread": 20.0,
                "gravity": {"x": 0.0, "y": 98.0},
                "initial_velocity_min": 32.0,
                "initial_velocity_max": 64.0,
                "angular_velocity_min": -10.0,
                "angular_velocity_max": 20.0,
                "orbit_velocity_min": -0.5,
                "orbit_velocity_max": 0.75,
                "linear_accel_min": -5.0,
                "linear_accel_max": 10.0,
                "radial_accel_min": -4.0,
                "radial_accel_max": 6.0,
                "tangential_accel_min": -3.0,
                "tangential_accel_max": 7.0,
                "damping_min": 0.1,
                "damping_max": 0.8,
                "angle_min": -15.0,
                "angle_max": 30.0,
                "scale_amount_min": 0.5,
                "scale_amount_max": 1.5,
                "hue_variation_min": -0.25,
                "hue_variation_max": 0.5,
                "anim_speed_min": 0.25,
                "anim_speed_max": 1.0,
                "anim_offset_min": 0.0,
                "anim_offset_max": 0.5,
                "split_scale": True,
                "color": {"r": 1.0, "g": 0.5, "b": 0.25, "a": 0.8},
            },
            scene_file=scene_file,
        )
        cpu_configuration = cpu_particles_update["configuration"]
        if (
            not cpu_particles_update.get("undoable")
            or cpu_configuration["amount"] != 96
            or cpu_configuration["texture_path"] != "res://test_icon.svg"
            or cpu_configuration["texture_type"] == ""
            or not _is_close(cpu_configuration["lifetime"], 2.5)
            or cpu_configuration["draw_order"] != "lifetime"
            or cpu_configuration["emission_shape"] != "directed_points"
            or cpu_configuration["emission_points"]
            != [{"x": -8.0, "y": 4.0}, {"x": 8.0, "y": -4.0}]
            or cpu_configuration["emission_normals"]
            != [{"x": 0.0, "y": -1.0}, {"x": 1.0, "y": 0.0}]
            or not _color_matches(
                cpu_configuration["emission_colors"][0],
                {"r": 1.0, "g": 0.5, "b": 0.25, "a": 0.8},
            )
            or not cpu_configuration["align_y_to_velocity"]
            or cpu_configuration["direction"] != {"x": 0.5, "y": -1.0}
            or cpu_configuration["gravity"] != {"x": 0.0, "y": 98.0}
            or not _is_close(cpu_configuration["initial_velocity_min"], 32.0)
            or not _is_close(cpu_configuration["initial_velocity_max"], 64.0)
            or not _is_close(cpu_configuration["scale_amount_max"], 1.5)
            or not cpu_configuration["split_scale"]
            or not _color_matches(
                cpu_configuration["color"],
                {"r": 1.0, "g": 0.5, "b": 0.25, "a": 0.8},
            )
        ):
            raise RuntimeError("CPUParticles2D configuration was not applied")
        undo_cpu_particles_update = await app.service.scene_undo(scene_file=scene_file)
        if not undo_cpu_particles_update.get("changed"):
            raise RuntimeError("CPUParticles2D configuration was not undoable")
        restored_cpu_particles = await app.service.cpu_particles_2d_get(
            cpu_particles_path, scene_file=scene_file
        )
        if restored_cpu_particles["configuration"]["texture_path"] != "":
            raise RuntimeError(
                "Undo did not restore the CPUParticles2D texture binding"
            )
        redo_cpu_particles_update = await app.service.scene_redo(scene_file=scene_file)
        if not redo_cpu_particles_update.get("changed"):
            raise RuntimeError("CPUParticles2D configuration was not redoable")
        cleared_cpu_particles = await app.service.cpu_particles_2d_set(
            cpu_particles_path,
            {"texture_path": ""},
            scene_file=scene_file,
        )
        if cleared_cpu_particles["configuration"]["texture_path"] != "":
            raise RuntimeError("CPUParticles2D texture binding was not cleared")
        undo_cpu_particles_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_cpu_particles_clear.get("changed"):
            raise RuntimeError("CPUParticles2D texture clear was not undoable")
        restored_cpu_texture = await app.service.cpu_particles_2d_get(
            cpu_particles_path, scene_file=scene_file
        )
        if (
            restored_cpu_texture["configuration"]["texture_path"]
            != "res://test_icon.svg"
        ):
            raise RuntimeError(
                "Undo did not restore the CPUParticles2D texture binding"
            )

        initial_cpu_curve = await app.service.cpu_particles_2d_curve_get(
            cpu_particles_path,
            "initial_velocity",
            scene_file=scene_file,
        )
        if (
            initial_cpu_curve["resource"]["assigned"]
            or initial_cpu_curve["configuration"] is not None
        ):
            raise RuntimeError(
                "New CPUParticles2D unexpectedly had an initial velocity Curve"
            )
        await _expect_godot_error(
            app.service.cpu_particles_2d_curve_bind(
                cpu_particles_path,
                "initial_velocity",
                "res://test_cpu_gradient.tres",
                scene_file=scene_file,
            ),
            "RESOURCE_TYPE_MISMATCH",
        )
        bound_cpu_curve = await app.service.cpu_particles_2d_curve_bind(
            cpu_particles_path,
            "initial_velocity",
            "res://test_cpu_curve.tres",
            scene_file=scene_file,
        )
        if (
            not bound_cpu_curve.get("bound_external_resource")
            or bound_cpu_curve["resource"]["origin"] != "external"
            or bound_cpu_curve["resource"]["resource_path"]
            != "res://test_cpu_curve.tres"
        ):
            raise RuntimeError(
                "CPUParticles2D Curve was not bound as an external resource"
            )
        cpu_curve_update = await app.service.cpu_particles_2d_curve_set(
            cpu_particles_path,
            "initial_velocity",
            {
                "min_domain": 0.0,
                "max_domain": 1.0,
                "min_value": -2.0,
                "max_value": 2.0,
                "bake_resolution": 64,
                "points": [
                    {
                        "position": {"x": 0.0, "y": -1.0},
                        "left_tangent": 0.0,
                        "right_tangent": 2.0,
                        "left_mode": "free",
                        "right_mode": "linear",
                    },
                    {
                        "position": {"x": 1.0, "y": 1.0},
                        "left_tangent": 2.0,
                        "right_tangent": 0.0,
                        "left_mode": "linear",
                        "right_mode": "free",
                    },
                ],
            },
            scene_file=scene_file,
        )
        cpu_curve_configuration = cpu_curve_update["configuration"]
        if (
            not cpu_curve_update.get("undoable")
            or cpu_curve_update.get("copied_external_resource") is not True
            or cpu_curve_update["resource"]["origin"] != "embedded"
            or cpu_curve_update["resource"]["resource_path"] != ""
            or not _is_close(cpu_curve_configuration["min_value"], -2.0)
            or not _is_close(cpu_curve_configuration["max_value"], 2.0)
            or cpu_curve_configuration["bake_resolution"] != 64
            or cpu_curve_configuration["points"]
            != [
                {
                    "position": {"x": 0.0, "y": -1.0},
                    "left_tangent": 0.0,
                    "right_tangent": 2.0,
                    "left_mode": "free",
                    "right_mode": "linear",
                },
                {
                    "position": {"x": 1.0, "y": 1.0},
                    "left_tangent": 2.0,
                    "right_tangent": 0.0,
                    "left_mode": "linear",
                    "right_mode": "free",
                },
            ]
        ):
            raise RuntimeError("CPUParticles2D Curve configuration was not applied")
        undo_cpu_curve_update = await app.service.scene_undo(scene_file=scene_file)
        if not undo_cpu_curve_update.get("changed"):
            raise RuntimeError("CPUParticles2D Curve update was not undoable")
        restored_cpu_curve = await app.service.cpu_particles_2d_curve_get(
            cpu_particles_path,
            "initial_velocity",
            scene_file=scene_file,
        )
        if (
            restored_cpu_curve["resource"]["resource_path"]
            != "res://test_cpu_curve.tres"
        ):
            raise RuntimeError("Undo did not restore the external CPUParticles2D Curve")
        redo_cpu_curve_update = await app.service.scene_redo(scene_file=scene_file)
        if not redo_cpu_curve_update.get("changed"):
            raise RuntimeError("CPUParticles2D Curve update was not redoable")
        cleared_cpu_curve = await app.service.cpu_particles_2d_curve_clear(
            cpu_particles_path,
            "initial_velocity",
            scene_file=scene_file,
        )
        if cleared_cpu_curve["resource"]["assigned"]:
            raise RuntimeError("CPUParticles2D Curve was not cleared")
        undo_cpu_curve_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_cpu_curve_clear.get("changed"):
            raise RuntimeError("CPUParticles2D Curve clear was not undoable")
        restored_embedded_curve = await app.service.cpu_particles_2d_curve_get(
            cpu_particles_path,
            "initial_velocity",
            scene_file=scene_file,
        )
        if restored_embedded_curve["resource"]["origin"] != "embedded":
            raise RuntimeError("Undo did not restore the embedded CPUParticles2D Curve")

        initial_cpu_gradient = await app.service.cpu_particles_2d_gradient_get(
            cpu_particles_path,
            "color",
            scene_file=scene_file,
        )
        if (
            initial_cpu_gradient["resource"]["assigned"]
            or initial_cpu_gradient["configuration"] is not None
        ):
            raise RuntimeError("New CPUParticles2D unexpectedly had a color Gradient")
        await _expect_godot_error(
            app.service.cpu_particles_2d_gradient_bind(
                cpu_particles_path,
                "color",
                "res://test_cpu_curve.tres",
                scene_file=scene_file,
            ),
            "RESOURCE_TYPE_MISMATCH",
        )
        bound_cpu_gradient = await app.service.cpu_particles_2d_gradient_bind(
            cpu_particles_path,
            "color",
            "res://test_cpu_gradient.tres",
            scene_file=scene_file,
        )
        if (
            not bound_cpu_gradient.get("bound_external_resource")
            or bound_cpu_gradient["resource"]["origin"] != "external"
            or bound_cpu_gradient["resource"]["resource_path"]
            != "res://test_cpu_gradient.tres"
        ):
            raise RuntimeError(
                "CPUParticles2D Gradient was not bound as an external resource"
            )
        cpu_gradient_update = await app.service.cpu_particles_2d_gradient_set(
            cpu_particles_path,
            "color",
            {
                "points": [
                    {"offset": 0.0, "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}},
                    {"offset": 0.5, "color": {"r": 0.0, "g": 1.0, "b": 0.0, "a": 0.8}},
                    {"offset": 1.0, "color": {"r": 0.0, "g": 0.0, "b": 1.0, "a": 0.5}},
                ],
                "interpolation_mode": "cubic",
                "interpolation_color_space": "oklab",
            },
            scene_file=scene_file,
        )
        cpu_gradient_configuration = cpu_gradient_update["configuration"]
        if (
            not cpu_gradient_update.get("undoable")
            or cpu_gradient_update.get("copied_external_resource") is not True
            or cpu_gradient_update["resource"]["origin"] != "embedded"
            or cpu_gradient_configuration["interpolation_mode"] != "cubic"
            or cpu_gradient_configuration["interpolation_color_space"] != "oklab"
            or len(cpu_gradient_configuration["points"]) != 3
            or not _color_matches(
                cpu_gradient_configuration["points"][1]["color"],
                {"r": 0.0, "g": 1.0, "b": 0.0, "a": 0.8},
            )
        ):
            raise RuntimeError("CPUParticles2D Gradient configuration was not applied")
        undo_cpu_gradient_update = await app.service.scene_undo(scene_file=scene_file)
        if not undo_cpu_gradient_update.get("changed"):
            raise RuntimeError("CPUParticles2D Gradient update was not undoable")
        restored_cpu_gradient = await app.service.cpu_particles_2d_gradient_get(
            cpu_particles_path,
            "color",
            scene_file=scene_file,
        )
        if (
            restored_cpu_gradient["resource"]["resource_path"]
            != "res://test_cpu_gradient.tres"
        ):
            raise RuntimeError(
                "Undo did not restore the external CPUParticles2D Gradient"
            )
        redo_cpu_gradient_update = await app.service.scene_redo(scene_file=scene_file)
        if not redo_cpu_gradient_update.get("changed"):
            raise RuntimeError("CPUParticles2D Gradient update was not redoable")
        cleared_cpu_gradient = await app.service.cpu_particles_2d_gradient_clear(
            cpu_particles_path,
            "color",
            scene_file=scene_file,
        )
        if cleared_cpu_gradient["resource"]["assigned"]:
            raise RuntimeError("CPUParticles2D Gradient was not cleared")
        undo_cpu_gradient_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_cpu_gradient_clear.get("changed"):
            raise RuntimeError("CPUParticles2D Gradient clear was not undoable")
        restored_embedded_gradient = await app.service.cpu_particles_2d_gradient_get(
            cpu_particles_path,
            "color",
            scene_file=scene_file,
        )
        if restored_embedded_gradient["resource"]["origin"] != "embedded":
            raise RuntimeError(
                "Undo did not restore the embedded CPUParticles2D Gradient"
            )

        viewport = await app.service.node_create(
            type_name="SubViewport",
            name="AgentViewport",
            parent_path="/Main",
            scene_file=scene_file,
        )
        viewport_path = viewport["path"]
        camera = await app.service.node_create(
            type_name="Camera2D",
            name="AgentCamera",
            parent_path="/Main",
            scene_file=scene_file,
        )
        camera_path = camera["path"]
        initial_camera = await app.service.camera_2d_get(
            camera_path, scene_file=scene_file
        )
        if initial_camera["configuration"]["custom_viewport_path"] != "":
            raise RuntimeError("New Camera2D unexpectedly had a custom viewport")
        camera_update = await app.service.camera_2d_set(
            camera_path,
            {
                "anchor_mode": "drag_center",
                "custom_viewport_path": viewport_path,
                "drag_left_margin": 0.1,
                "drag_right_margin": 0.3,
                "drag_horizontal_enabled": True,
                "limit_left": -960,
                "limit_right": 960,
                "position_smoothing_enabled": True,
                "position_smoothing_speed": 8.0,
                "process_callback": "physics",
                "zoom": {"x": 1.5, "y": 1.5},
            },
            scene_file=scene_file,
        )
        camera_configuration = camera_update["configuration"]
        if (
            camera_configuration["custom_viewport_path"] != viewport_path
            or not _is_close(camera_configuration["drag_left_margin"], 0.1)
            or camera_configuration["limit_left"] != -960
            or camera_configuration["process_callback"] != "physics"
            or camera_configuration["zoom"] != {"x": 1.5, "y": 1.5}
        ):
            raise RuntimeError("Camera2D configuration was not applied")
        await _expect_godot_error(
            app.service.camera_2d_set(
                camera_path,
                {"limit_left": 100, "limit_right": -100},
                scene_file=scene_file,
            ),
            "INVALID_VIEWPORT_CONFIGURATION",
        )
        await _expect_godot_error(
            app.service.camera_2d_set(
                camera_path,
                {"custom_viewport_path": camera_path},
                scene_file=scene_file,
            ),
            "VIEWPORT_NOT_FOUND",
        )
        undo_camera = await app.service.scene_undo(scene_file=scene_file)
        if not undo_camera.get("changed"):
            raise RuntimeError("Camera2D configuration was not undoable")
        restored_camera = await app.service.camera_2d_get(
            camera_path, scene_file=scene_file
        )
        if restored_camera["configuration"]["custom_viewport_path"] != "":
            raise RuntimeError("Undo did not restore Camera2D viewport binding")
        redo_camera = await app.service.scene_redo(scene_file=scene_file)
        if not redo_camera.get("changed"):
            raise RuntimeError("Camera2D configuration was not redoable")

        parallax = await app.service.node_create(
            type_name="Parallax2D",
            name="AgentParallax",
            parent_path="/Main",
            scene_file=scene_file,
        )
        parallax_path = parallax["path"]
        parallax_update = await app.service.parallax_2d_set(
            parallax_path,
            {
                "autoscroll": {"x": 12.0, "y": 0.0},
                "limit_begin": {"x": -1024.0, "y": -512.0},
                "limit_end": {"x": 1024.0, "y": 512.0},
                "repeat_size": {"x": 320.0, "y": 180.0},
                "repeat_times": 3,
                "scroll_offset": {"x": 8.0, "y": 4.0},
                "scroll_scale": {"x": 0.5, "y": 0.5},
            },
            scene_file=scene_file,
        )
        parallax_configuration = parallax_update["configuration"]
        if (
            parallax_configuration["repeat_times"] != 3
            or parallax_configuration["repeat_size"] != {"x": 320.0, "y": 180.0}
            or parallax_configuration["scroll_scale"] != {"x": 0.5, "y": 0.5}
        ):
            raise RuntimeError("Parallax2D configuration was not applied")
        await _expect_godot_error(
            app.service.parallax_2d_set(
                parallax_path,
                {
                    "limit_begin": {"x": 32.0, "y": 32.0},
                    "limit_end": {"x": 32.0, "y": 64.0},
                },
                scene_file=scene_file,
            ),
            "INVALID_VIEWPORT_CONFIGURATION",
        )
        undo_parallax = await app.service.scene_undo(scene_file=scene_file)
        if not undo_parallax.get("changed"):
            raise RuntimeError("Parallax2D configuration was not undoable")
        redo_parallax = await app.service.scene_redo(scene_file=scene_file)
        if not redo_parallax.get("changed"):
            raise RuntimeError("Parallax2D configuration was not redoable")

        canvas_layer = await app.service.node_create(
            type_name="CanvasLayer",
            name="AgentCanvasLayer",
            parent_path="/Main",
            scene_file=scene_file,
        )
        canvas_layer_path = canvas_layer["path"]
        canvas_layer_update = await app.service.canvas_layer_set(
            canvas_layer_path,
            {
                "custom_viewport_path": viewport_path,
                "follow_viewport_enabled": True,
                "follow_viewport_scale": 0.75,
                "layer": 10,
                "offset": {"x": 16.0, "y": 24.0},
                "scale": {"x": 1.0, "y": -1.0},
                "visible": True,
            },
            scene_file=scene_file,
        )
        canvas_layer_configuration = canvas_layer_update["configuration"]
        if (
            canvas_layer_configuration["custom_viewport_path"] != viewport_path
            or not _is_close(canvas_layer_configuration["follow_viewport_scale"], 0.75)
            or canvas_layer_configuration["layer"] != 10
            or canvas_layer_configuration["scale"] != {"x": 1.0, "y": -1.0}
        ):
            raise RuntimeError("CanvasLayer configuration was not applied")
        undo_canvas_layer = await app.service.scene_undo(scene_file=scene_file)
        if not undo_canvas_layer.get("changed"):
            raise RuntimeError("CanvasLayer configuration was not undoable")
        restored_canvas_layer = await app.service.canvas_layer_get(
            canvas_layer_path, scene_file=scene_file
        )
        if restored_canvas_layer["configuration"]["custom_viewport_path"] != "":
            raise RuntimeError("Undo did not restore CanvasLayer viewport binding")
        redo_canvas_layer = await app.service.scene_redo(scene_file=scene_file)
        if not redo_canvas_layer.get("changed"):
            raise RuntimeError("CanvasLayer configuration was not redoable")

        point_light = await app.service.node_create(
            type_name="PointLight2D",
            name="AgentPointLight",
            parent_path="/Main",
            scene_file=scene_file,
        )
        point_light_path = point_light["path"]
        initial_point_light = await app.service.light_2d_get(
            point_light_path, scene_file=scene_file
        )
        if initial_point_light["configuration"]["texture_path"] != "":
            raise RuntimeError("New PointLight2D unexpectedly had a texture")
        point_light_update = await app.service.light_2d_set(
            point_light_path,
            {
                "enabled": True,
                "color": {"r": 1.0, "g": 0.8, "b": 0.4, "a": 1.0},
                "energy": 2.5,
                "blend_mode": "add",
                "range_item_cull_layers": [1, 3],
                "shadow_enabled": True,
                "shadow_filter": "pcf5",
                "shadow_filter_smooth": 2.0,
                "shadow_item_cull_layers": [2],
                "height": 64.0,
                "texture_path": "res://test_icon.svg",
                "offset": {"x": 4.0, "y": -2.0},
                "texture_scale": 1.25,
            },
            scene_file=scene_file,
        )
        point_configuration = point_light_update["configuration"]
        if (
            point_configuration["energy"] != 2.5
            or point_configuration["range_item_cull_layers"] != [1, 3]
            or point_configuration["shadow_item_cull_layers"] != [2]
            or point_configuration["texture_path"] != "res://test_icon.svg"
            or point_configuration["offset"] != {"x": 4.0, "y": -2.0}
        ):
            raise RuntimeError("PointLight2D configuration was not applied")
        undo_point_light = await app.service.scene_undo(scene_file=scene_file)
        if not undo_point_light.get("changed"):
            raise RuntimeError("PointLight2D configuration was not undoable")
        restored_point_light = await app.service.light_2d_get(
            point_light_path, scene_file=scene_file
        )
        if restored_point_light["configuration"]["energy"] != 1.0:
            raise RuntimeError("Undo did not restore PointLight2D configuration")
        redo_point_light = await app.service.scene_redo(scene_file=scene_file)
        if not redo_point_light.get("changed"):
            raise RuntimeError("PointLight2D configuration was not redoable")

        directional_light = await app.service.node_create(
            type_name="DirectionalLight2D",
            name="AgentDirectionalLight",
            parent_path="/Main",
            scene_file=scene_file,
        )
        directional_light_path = directional_light["path"]
        directional_light_update = await app.service.light_2d_set(
            directional_light_path,
            {"height": 0.75, "max_distance": 4096.0, "shadow_enabled": True},
            scene_file=scene_file,
        )
        if (
            directional_light_update["configuration"]["height"] != 0.75
            or directional_light_update["configuration"]["max_distance"] != 4096.0
        ):
            raise RuntimeError("DirectionalLight2D configuration was not applied")
        await _expect_godot_error(
            app.service.light_2d_set(
                directional_light_path,
                {"texture_path": "res://test_icon.svg"},
                scene_file=scene_file,
            ),
            "UNSUPPORTED_LIGHT_PROPERTY",
        )

        light_occluder = await app.service.node_create(
            type_name="LightOccluder2D",
            name="AgentLightOccluder",
            parent_path="/Main",
            scene_file=scene_file,
        )
        light_occluder_path = light_occluder["path"]
        occluder_polygon = {
            "points": [
                {"x": -16.0, "y": -16.0},
                {"x": 16.0, "y": -16.0},
                {"x": 16.0, "y": 16.0},
                {"x": -16.0, "y": 16.0},
            ],
            "closed": True,
            "cull_mode": "counter_clockwise",
        }
        light_occluder_update = await app.service.light_occluder_2d_set(
            light_occluder_path,
            layers=[2, 5],
            sdf_collision=False,
            polygon=occluder_polygon,
            scene_file=scene_file,
        )
        if (
            light_occluder_update["layers"] != [2, 5]
            or light_occluder_update["sdf_collision"] is not False
            or light_occluder_update["polygon"] is None
            or light_occluder_update["polygon"]["points"] != occluder_polygon["points"]
        ):
            raise RuntimeError("LightOccluder2D configuration was not applied")
        await _expect_godot_error(
            app.service.light_occluder_2d_set(
                light_occluder_path,
                polygon={
                    "points": [
                        {"x": -8.0, "y": -8.0},
                        {"x": 8.0, "y": 8.0},
                        {"x": -8.0, "y": 8.0},
                        {"x": 8.0, "y": -8.0},
                    ]
                },
                scene_file=scene_file,
            ),
            "INVALID_LIGHT_OCCLUDER_POLYGON",
        )
        cleared_light_occluder = await app.service.light_occluder_2d_set(
            light_occluder_path, clear=True, scene_file=scene_file
        )
        if cleared_light_occluder["polygon"] is not None:
            raise RuntimeError("LightOccluder2D polygon was not cleared")
        undo_light_occluder = await app.service.scene_undo(scene_file=scene_file)
        if not undo_light_occluder.get("changed"):
            raise RuntimeError("LightOccluder2D clear was not undoable")
        restored_light_occluder = await app.service.light_occluder_2d_get(
            light_occluder_path, scene_file=scene_file
        )
        if restored_light_occluder["polygon"]["points"] != occluder_polygon["points"]:
            raise RuntimeError("Undo did not restore LightOccluder2D polygon")
        redo_light_occluder = await app.service.scene_redo(scene_file=scene_file)
        if not redo_light_occluder.get("changed"):
            raise RuntimeError("LightOccluder2D clear was not redoable")

        tile_map_layer = await app.service.node_create(
            type_name="TileMapLayer",
            name="AgentTileMap",
            parent_path="/Main",
            scene_file=scene_file,
        )
        tile_map_layer_path = tile_map_layer["path"]
        initial_tile_map = await app.service.tile_map_layer_get(
            tile_map_layer_path, scene_file=scene_file
        )
        if (
            initial_tile_map["tile_set"] is not None
            or initial_tile_map["used_cells"] != 0
        ):
            raise RuntimeError("New TileMapLayer unexpectedly had TileSet data")
        await _expect_godot_error(
            app.service.tile_map_layer_cells_set(
                tile_map_layer_path,
                [
                    {
                        "coords": {"x": 0, "y": 0},
                        "source_id": 3,
                        "atlas_coords": {"x": 0, "y": 0},
                        "alternative_tile": 0,
                    }
                ],
                scene_file=scene_file,
            ),
            "TILE_SET_NOT_ASSIGNED",
        )
        created_tile_set = await app.service.tile_set_create(
            tile_map_layer_path, tile_size={"x": 16, "y": 16}, scene_file=scene_file
        )
        if created_tile_set["tile_set"]["tile_size"] != {"x": 16, "y": 16}:
            raise RuntimeError("TileSet creation did not set tile_size")
        atlas_source = await app.service.tile_set_atlas_source_create(
            tile_map_layer_path,
            texture_path="res://test_icon.svg",
            source_id=3,
            scene_file=scene_file,
        )
        if atlas_source["source_id"] != 3:
            raise RuntimeError(
                "TileSetAtlasSource did not retain its requested source ID"
            )
        created_atlas_tile = await app.service.tile_set_atlas_tile_create(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            scene_file=scene_file,
        )
        if created_atlas_tile["atlas_coords"] != {"x": 0, "y": 0}:
            raise RuntimeError("TileSetAtlasSource did not create its atlas tile")
        initial_tile_set_layers = await app.service.tile_set_layers_get(
            tile_map_layer_path, scene_file=scene_file
        )
        if any(
            initial_tile_set_layers[name] != 0
            for name in (
                "physics_layers_total",
                "navigation_layers_total",
                "occlusion_layers_total",
                "custom_data_layers_total",
                "terrain_sets_total",
            )
        ):
            raise RuntimeError(
                "New TileSet unexpectedly had semantic layer definitions"
            )
        physics_layer = await app.service.tile_set_physics_layer_create(
            tile_map_layer_path,
            layers=[2],
            masks=[1, 3],
            priority=0.5,
            scene_file=scene_file,
        )
        if physics_layer["physics_layer_index"] != 0 or physics_layer["physics_layers"][
            0
        ] != {"index": 0, "layers": [2], "masks": [1, 3], "priority": 0.5}:
            raise RuntimeError("TileSet physics layer definition was not applied")
        navigation_layer = await app.service.tile_set_navigation_layer_create(
            tile_map_layer_path,
            layers=[4],
            scene_file=scene_file,
        )
        if navigation_layer["navigation_layers"] != [{"index": 0, "layers": [4]}]:
            raise RuntimeError("TileSet navigation layer definition was not applied")
        occlusion_layer = await app.service.tile_set_occlusion_layer_create(
            tile_map_layer_path,
            layers=[2, 5],
            sdf_collision=True,
            scene_file=scene_file,
        )
        if occlusion_layer["occlusion_layers"] != [
            {"index": 0, "layers": [2, 5], "sdf_collision": True}
        ]:
            raise RuntimeError("TileSet occlusion layer definition was not applied")
        custom_data_layer = await app.service.tile_set_custom_data_layer_create(
            tile_map_layer_path,
            name="damage",
            value_type="int",
            scene_file=scene_file,
        )
        if custom_data_layer["custom_data_layers"] != [
            {"index": 0, "name": "damage", "value_type": "int"}
        ]:
            raise RuntimeError("TileSet custom-data layer definition was not applied")
        updated_physics_layer = await app.service.tile_set_layer_set(
            tile_map_layer_path,
            kind="physics",
            index=0,
            properties={"layers": [6], "masks": [2, 4], "priority": 0.75},
            scene_file=scene_file,
        )
        if updated_physics_layer["physics_layers"] != [
            {"index": 0, "layers": [6], "masks": [2, 4], "priority": 0.75}
        ]:
            raise RuntimeError("TileSet physics layer update was not applied")
        updated_navigation_layer = await app.service.tile_set_layer_set(
            tile_map_layer_path,
            kind="navigation",
            index=0,
            properties={"layers": [7]},
            scene_file=scene_file,
        )
        if updated_navigation_layer["navigation_layers"] != [
            {"index": 0, "layers": [7]}
        ]:
            raise RuntimeError("TileSet navigation layer update was not applied")
        updated_occlusion_layer = await app.service.tile_set_layer_set(
            tile_map_layer_path,
            kind="occlusion",
            index=0,
            properties={"layers": [3, 6], "sdf_collision": False},
            scene_file=scene_file,
        )
        if updated_occlusion_layer["occlusion_layers"] != [
            {"index": 0, "layers": [3, 6], "sdf_collision": False}
        ]:
            raise RuntimeError("TileSet occlusion layer update was not applied")
        updated_custom_data_layer = await app.service.tile_set_layer_set(
            tile_map_layer_path,
            kind="custom_data",
            index=0,
            properties={"name": "terrain_tag", "value_type": "int"},
            scene_file=scene_file,
        )
        if updated_custom_data_layer["custom_data_layers"] != [
            {"index": 0, "name": "terrain_tag", "value_type": "int"}
        ]:
            raise RuntimeError("TileSet custom-data layer update was not applied")
        terrain_set = await app.service.tile_set_terrain_set_create(
            tile_map_layer_path,
            mode="match_sides",
            scene_file=scene_file,
        )
        if (
            terrain_set["terrain_set"] != 0
            or terrain_set["terrain_sets"][0]["mode"] != "match_sides"
        ):
            raise RuntimeError("TileSet terrain set definition was not applied")
        terrain = await app.service.tile_set_terrain_create(
            tile_map_layer_path,
            terrain_set=0,
            name="Ground",
            color={"r": 0.2, "g": 0.7, "b": 0.3, "a": 1.0},
            scene_file=scene_file,
        )
        terrain_definition = terrain["terrain_sets"][0]["terrains"][0]
        terrain_color = terrain_definition["color"]
        if (
            terrain["terrain"] != 0
            or terrain_definition["name"] != "Ground"
            or any(
                abs(terrain_color[channel] - expected) > 0.0001
                for channel, expected in {
                    "r": 0.2,
                    "g": 0.7,
                    "b": 0.3,
                    "a": 1.0,
                }.items()
            )
        ):
            raise RuntimeError("TileSet terrain definition was not applied")
        extra_terrain = await app.service.tile_set_terrain_create(
            tile_map_layer_path,
            terrain_set=0,
            name="GroundVariant",
            scene_file=scene_file,
        )
        if extra_terrain["terrain"] != 1:
            raise RuntimeError("TileSet did not create a second terrain definition")
        removed_terrain = await app.service.tile_set_terrain_remove(
            tile_map_layer_path,
            terrain_set=0,
            terrain=1,
            scene_file=scene_file,
        )
        if removed_terrain["terrain_sets"][0]["terrain_total"] != 1:
            raise RuntimeError("TileSet terrain definition was not removed")
        undo_terrain_remove = await app.service.scene_undo(scene_file=scene_file)
        if not undo_terrain_remove.get("changed"):
            raise RuntimeError("TileSet terrain removal was not undoable")
        restored_terrain_layers = await app.service.tile_set_layers_get(
            tile_map_layer_path, scene_file=scene_file
        )
        if restored_terrain_layers["terrain_sets"][0]["terrain_total"] != 2:
            raise RuntimeError("Undo did not restore the TileSet terrain definition")
        redo_terrain_remove = await app.service.scene_redo(scene_file=scene_file)
        if not redo_terrain_remove.get("changed"):
            raise RuntimeError("TileSet terrain removal was not redoable")
        second_terrain_set = await app.service.tile_set_terrain_set_create(
            tile_map_layer_path,
            mode="match_corners_and_sides",
            scene_file=scene_file,
        )
        if second_terrain_set["terrain_set"] != 1:
            raise RuntimeError("TileSet did not create a second terrain set")
        removed_terrain_set = await app.service.tile_set_terrain_set_remove(
            tile_map_layer_path,
            terrain_set=1,
            scene_file=scene_file,
        )
        if removed_terrain_set["terrain_sets_total"] != 1:
            raise RuntimeError("TileSet terrain set was not removed")
        undo_terrain_set_remove = await app.service.scene_undo(scene_file=scene_file)
        if not undo_terrain_set_remove.get("changed"):
            raise RuntimeError("TileSet terrain set removal was not undoable")
        restored_terrain_set_layers = await app.service.tile_set_layers_get(
            tile_map_layer_path, scene_file=scene_file
        )
        if restored_terrain_set_layers["terrain_sets_total"] != 2:
            raise RuntimeError("Undo did not restore the TileSet terrain set")
        redo_terrain_set_remove = await app.service.scene_redo(scene_file=scene_file)
        if not redo_terrain_set_remove.get("changed"):
            raise RuntimeError("TileSet terrain set removal was not redoable")
        await _expect_godot_error(
            app.service.tile_set_atlas_tile_terrain_set(
                tile_map_layer_path,
                source_id=3,
                atlas_coords={"x": 0, "y": 0},
                terrain_set=0,
                terrain=0,
                peering_bits={"top_left_side": 0},
                scene_file=scene_file,
            ),
            "INVALID_TILE_TERRAIN",
        )
        base_atlas_terrain = await app.service.tile_set_atlas_tile_terrain_set(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            terrain_set=0,
            terrain=0,
            scene_file=scene_file,
        )
        if (
            base_atlas_terrain["terrain_set"] != 0
            or base_atlas_terrain["terrain"] != 0
            or base_atlas_terrain["peering_bits"] != {}
        ):
            raise RuntimeError("TileSet base atlas terrain data was not applied")
        atlas_alternative = await app.service.tile_set_atlas_alternative_create(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            alternative_tile=1,
            scene_file=scene_file,
        )
        if atlas_alternative["alternative_tile"] != 1:
            raise RuntimeError("TileSet atlas alternative was not created")
        blank_atlas_alternative = await app.service.tile_set_atlas_alternative_create(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            alternative_tile=2,
            scene_file=scene_file,
        )
        if blank_atlas_alternative["alternative_tile"] != 2:
            raise RuntimeError("TileSet blank atlas alternative was not created")
        atlas_terrain = await app.service.tile_set_atlas_tile_terrain_set(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            terrain_set=0,
            terrain=0,
            peering_bits={"right_side": 0},
            alternative_tile=1,
            scene_file=scene_file,
        )
        if atlas_terrain["terrain_set"] != 0 or atlas_terrain["peering_bits"] != {
            "right_side": 0
        }:
            raise RuntimeError("TileSet atlas terrain data was not applied")
        atlas_custom_data = await app.service.tile_set_atlas_tile_custom_data_set(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            values={"terrain_tag": 8},
            alternative_tile=1,
            scene_file=scene_file,
        )
        if atlas_custom_data["custom_data"] != {"terrain_tag": 8}:
            raise RuntimeError("TileSet atlas custom data was not applied")
        undo_tile_custom_data = await app.service.scene_undo(scene_file=scene_file)
        if not undo_tile_custom_data.get("changed"):
            raise RuntimeError("TileSet atlas custom-data edit was not undoable")
        redo_tile_custom_data = await app.service.scene_redo(scene_file=scene_file)
        if not redo_tile_custom_data.get("changed"):
            raise RuntimeError("TileSet atlas custom-data edit was not redoable")
        collision_polygons = [
            {
                "points": [
                    {"x": -8.0, "y": -8.0},
                    {"x": 8.0, "y": -8.0},
                    {"x": 8.0, "y": 8.0},
                    {"x": -8.0, "y": 8.0},
                ],
                "one_way": True,
                "one_way_margin": 2.5,
            }
        ]
        atlas_collision = await app.service.tile_set_atlas_tile_collision_set(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            physics_layer=0,
            polygons=collision_polygons,
            alternative_tile=1,
            scene_file=scene_file,
        )
        if atlas_collision["collision_polygons"] != collision_polygons:
            raise RuntimeError("TileSet atlas collision polygons were not applied")
        await _expect_godot_error(
            app.service.tile_set_atlas_tile_collision_set(
                tile_map_layer_path,
                source_id=3,
                atlas_coords={"x": 0, "y": 0},
                physics_layer=0,
                polygons=[
                    {
                        "points": [
                            {"x": -8.0, "y": -8.0},
                            {"x": 0.0, "y": 0.0},
                            {"x": 8.0, "y": 8.0},
                        ]
                    }
                ],
                alternative_tile=1,
                scene_file=scene_file,
            ),
            "INVALID_TILE_COLLISION",
        )
        navigation_vertices = [
            {"x": -8.0, "y": -8.0},
            {"x": 8.0, "y": -8.0},
            {"x": 8.0, "y": 8.0},
            {"x": -8.0, "y": 8.0},
        ]
        atlas_navigation = await app.service.tile_set_atlas_tile_navigation_set(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            navigation_layer=0,
            vertices=navigation_vertices,
            polygons=[[0, 1, 2, 3]],
            agent_radius=0.5,
            alternative_tile=1,
            scene_file=scene_file,
        )
        navigation_polygon = atlas_navigation["navigation_polygon"]
        if (
            navigation_polygon["agent_radius"] != 0.5
            or navigation_polygon["vertices"] != navigation_vertices
            or navigation_polygon["polygons"] != [[0, 1, 2, 3]]
        ):
            raise RuntimeError("TileSet atlas navigation polygon was not applied")
        occlusion_polygons = [
            {
                "points": [
                    {"x": -8.0, "y": -8.0},
                    {"x": 8.0, "y": -8.0},
                    {"x": 8.0, "y": 8.0},
                    {"x": -8.0, "y": 8.0},
                ],
                "closed": True,
                "cull_mode": "counter_clockwise",
            },
            {
                "points": [{"x": -8.0, "y": 0.0}, {"x": 8.0, "y": 0.0}],
                "closed": False,
                "cull_mode": "clockwise",
            },
        ]
        atlas_occlusion = await app.service.tile_set_atlas_tile_occlusion_set(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            occlusion_layer=0,
            polygons=occlusion_polygons,
            alternative_tile=1,
            scene_file=scene_file,
        )
        if atlas_occlusion["occluder_polygons"] != occlusion_polygons:
            raise RuntimeError("TileSet atlas occlusion polygons were not applied")
        await _expect_godot_error(
            app.service.tile_set_atlas_tile_occlusion_set(
                tile_map_layer_path,
                source_id=3,
                atlas_coords={"x": 0, "y": 0},
                occlusion_layer=0,
                polygons=[
                    {
                        "points": [
                            {"x": 0.0, "y": 0.0},
                            {"x": 4.0, "y": 0.0},
                            {"x": 0.0, "y": 4.0},
                            {"x": 4.0, "y": 4.0},
                            {"x": 0.0, "y": 8.0},
                        ]
                    }
                ],
                alternative_tile=1,
                scene_file=scene_file,
            ),
            "INVALID_TILE_OCCLUSION",
        )
        atlas_tile_state = await app.service.tile_set_atlas_tile_get(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            alternative_tile=1,
            scene_file=scene_file,
        )
        if (
            atlas_tile_state["physics_layers"]
            != [{"index": 0, "collision_polygons": collision_polygons}]
            or atlas_tile_state["navigation_layers"]
            != [{"index": 0, "navigation_polygon": navigation_polygon}]
            or atlas_tile_state["occlusion_layers"]
            != [{"index": 0, "occluder_polygons": occlusion_polygons}]
        ):
            raise RuntimeError(
                "tile_set_atlas_tile_get did not return TileData geometry"
            )
        await _expect_godot_error(
            app.service.tile_set_atlas_tile_navigation_set(
                tile_map_layer_path,
                source_id=3,
                atlas_coords={"x": 0, "y": 0},
                navigation_layer=0,
                vertices=[
                    {"x": -8.0, "y": -8.0},
                    {"x": 8.0, "y": -8.0},
                    {"x": -8.0, "y": 8.0},
                    {"x": 8.0, "y": 8.0},
                ],
                polygons=[[0, 1, 2, 3]],
                alternative_tile=1,
                scene_file=scene_file,
            ),
            "INVALID_TILE_NAVIGATION",
        )
        cleared_atlas_navigation = await app.service.tile_set_atlas_tile_navigation_set(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            navigation_layer=0,
            clear=True,
            alternative_tile=1,
            scene_file=scene_file,
        )
        if cleared_atlas_navigation["navigation_polygon"] is not None:
            raise RuntimeError("TileSet atlas navigation polygon was not cleared")
        undo_tile_navigation_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_tile_navigation_clear.get("changed"):
            raise RuntimeError("TileSet atlas navigation clear was not undoable")
        restored_atlas_tile = await app.service.tile_set_atlas_tile_get(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            alternative_tile=1,
            scene_file=scene_file,
        )
        if (
            restored_atlas_tile["navigation_layers"][0]["navigation_polygon"]
            != navigation_polygon
        ):
            raise RuntimeError("Undo did not restore TileSet atlas navigation geometry")
        redo_tile_navigation_clear = await app.service.scene_redo(scene_file=scene_file)
        if not redo_tile_navigation_clear.get("changed"):
            raise RuntimeError("TileSet atlas navigation clear was not redoable")
        cleared_atlas_occlusion = await app.service.tile_set_atlas_tile_occlusion_set(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            occlusion_layer=0,
            polygons=[],
            alternative_tile=1,
            scene_file=scene_file,
        )
        if cleared_atlas_occlusion["occluder_polygons"] != []:
            raise RuntimeError("TileSet atlas occlusion polygons were not cleared")
        undo_tile_occlusion_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_tile_occlusion_clear.get("changed"):
            raise RuntimeError("TileSet atlas occlusion clear was not undoable")
        restored_atlas_tile = await app.service.tile_set_atlas_tile_get(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            alternative_tile=1,
            scene_file=scene_file,
        )
        if (
            restored_atlas_tile["occlusion_layers"][0]["occluder_polygons"]
            != occlusion_polygons
        ):
            raise RuntimeError("Undo did not restore TileSet atlas occlusion geometry")
        redo_tile_occlusion_clear = await app.service.scene_redo(scene_file=scene_file)
        if not redo_tile_occlusion_clear.get("changed"):
            raise RuntimeError("TileSet atlas occlusion clear was not redoable")
        removed_custom_data_layer = await app.service.tile_set_layer_remove(
            tile_map_layer_path,
            kind="custom_data",
            index=0,
            scene_file=scene_file,
        )
        if removed_custom_data_layer["custom_data_layers_total"] != 0:
            raise RuntimeError("TileSet custom-data layer was not removed")
        undo_custom_data_layer_remove = await app.service.scene_undo(scene_file=scene_file)
        if not undo_custom_data_layer_remove.get("changed"):
            raise RuntimeError("TileSet layer removal was not undoable")
        restored_custom_data_layers = await app.service.tile_set_layers_get(
            tile_map_layer_path, scene_file=scene_file
        )
        if restored_custom_data_layers["custom_data_layers"] != [
            {"index": 0, "name": "terrain_tag", "value_type": "int"}
        ]:
            raise RuntimeError("Undo did not restore the TileSet custom-data layer")
        redo_custom_data_layer_remove = await app.service.scene_redo(scene_file=scene_file)
        if not redo_custom_data_layer_remove.get("changed"):
            raise RuntimeError("TileSet layer removal was not redoable")
        tile_set_state = await app.service.tile_set_get(
            tile_map_layer_path, scene_file=scene_file
        )
        if (
            tile_set_state["total"] != 1
            or tile_set_state["sources"][0]["type"] != "TileSetAtlasSource"
            or tile_set_state["sources"][0]["tiles_count"] != 1
        ):
            raise RuntimeError("tile_set_get did not return the atlas source state")
        tile_cells = [
            {
                "coords": {"x": -1, "y": 2},
                "source_id": 3,
                "atlas_coords": {"x": 0, "y": 0},
                "alternative_tile": 2,
            },
            {
                "coords": {"x": 0, "y": 2},
                "source_id": 3,
                "atlas_coords": {"x": 0, "y": 0},
                "alternative_tile": 2,
            },
        ]
        tile_cells_update = await app.service.tile_map_layer_cells_set(
            tile_map_layer_path, tile_cells, scene_file=scene_file
        )
        if (
            tile_cells_update["changed_cells"] != 2
            or tile_cells_update["used_cells"] != 2
        ):
            raise RuntimeError("TileMapLayer cells were not assigned")
        tile_cells_state = await app.service.tile_map_layer_cells_get(
            tile_map_layer_path, limit=10, scene_file=scene_file
        )
        if tile_cells_state["total"] != 2 or tile_cells_state["cells"] != tile_cells:
            raise RuntimeError(
                "tile_map_layer_cells_get did not return stable cell assignments"
            )
        terrain_connect = await app.service.tile_map_layer_terrain_paint(
            tile_map_layer_path,
            [{"x": -1, "y": 2}],
            terrain_set=0,
            terrain=0,
            strategy="connect",
            scene_file=scene_file,
        )
        if terrain_connect["strategy"] != "connect" or terrain_connect["changed_cells"] < 1:
            raise RuntimeError("TileMapLayer terrain connect did not change any cells")
        connected_tile_cells = await app.service.tile_map_layer_cells_get(
            tile_map_layer_path, limit=10, scene_file=scene_file
        )
        if connected_tile_cells["cells"] == tile_cells:
            raise RuntimeError("TileMapLayer terrain connect did not alter the cell state")
        undo_terrain_connect = await app.service.scene_undo(scene_file=scene_file)
        if not undo_terrain_connect.get("changed"):
            raise RuntimeError("TileMapLayer terrain connect was not undoable")
        undone_terrain_connect_cells = await app.service.tile_map_layer_cells_get(
            tile_map_layer_path, limit=10, scene_file=scene_file
        )
        if undone_terrain_connect_cells["cells"] != tile_cells:
            raise RuntimeError("Undo did not restore TileMapLayer terrain connect cells")
        redo_terrain_connect = await app.service.scene_redo(scene_file=scene_file)
        if not redo_terrain_connect.get("changed"):
            raise RuntimeError("TileMapLayer terrain connect was not redoable")
        redone_terrain_connect_cells = await app.service.tile_map_layer_cells_get(
            tile_map_layer_path, limit=10, scene_file=scene_file
        )
        if redone_terrain_connect_cells["cells"] != connected_tile_cells["cells"]:
            raise RuntimeError("Redo did not restore TileMapLayer terrain connect cells")
        terrain_path = await app.service.tile_map_layer_terrain_paint(
            tile_map_layer_path,
            [{"x": -1, "y": 2}, {"x": 0, "y": 2}],
            terrain_set=0,
            terrain=0,
            strategy="path",
            scene_file=scene_file,
        )
        if terrain_path["strategy"] != "path" or terrain_path["changed_cells"] < 1:
            raise RuntimeError("TileMapLayer terrain path did not change any cells")
        path_tile_cells = await app.service.tile_map_layer_cells_get(
            tile_map_layer_path, limit=10, scene_file=scene_file
        )
        if path_tile_cells["cells"] == connected_tile_cells["cells"]:
            raise RuntimeError("TileMapLayer terrain path did not alter the cell state")
        undo_terrain_path = await app.service.scene_undo(scene_file=scene_file)
        if not undo_terrain_path.get("changed"):
            raise RuntimeError("TileMapLayer terrain path was not undoable")
        undone_terrain_path_cells = await app.service.tile_map_layer_cells_get(
            tile_map_layer_path, limit=10, scene_file=scene_file
        )
        if undone_terrain_path_cells["cells"] != connected_tile_cells["cells"]:
            raise RuntimeError("Undo did not restore TileMapLayer terrain path cells")
        redo_terrain_path = await app.service.scene_redo(scene_file=scene_file)
        if not redo_terrain_path.get("changed"):
            raise RuntimeError("TileMapLayer terrain path was not redoable")
        redone_terrain_path_cells = await app.service.tile_map_layer_cells_get(
            tile_map_layer_path, limit=10, scene_file=scene_file
        )
        if redone_terrain_path_cells["cells"] != path_tile_cells["cells"]:
            raise RuntimeError("Redo did not restore TileMapLayer terrain path cells")
        await _expect_godot_error(
            app.service.tile_map_layer_terrain_paint(
                tile_map_layer_path,
                [{"x": -1, "y": 2}, {"x": 1, "y": 2}],
                terrain_set=0,
                terrain=0,
                strategy="path",
                scene_file=scene_file,
            ),
            "INVALID_TERRAIN_PATH",
        )
        cleared_tile_cells = await app.service.tile_map_layer_cells_clear(
            tile_map_layer_path,
            [{"x": -1, "y": 2}],
            scene_file=scene_file,
        )
        if (
            cleared_tile_cells["cleared_cells"] != 1
            or cleared_tile_cells["used_cells"] != 1
        ):
            raise RuntimeError("TileMapLayer cell clear was not applied")
        undo_tile_cell_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_tile_cell_clear.get("changed"):
            raise RuntimeError("TileMapLayer cell clear was not undoable")
        restored_tile_cells = await app.service.tile_map_layer_cells_get(
            tile_map_layer_path, limit=10, scene_file=scene_file
        )
        if restored_tile_cells["total"] != 2:
            raise RuntimeError("Undo did not restore TileMapLayer cells")
        cleared_tile_set = await app.service.tile_set_clear(
            tile_map_layer_path, scene_file=scene_file
        )
        if cleared_tile_set["tile_set"] is not None:
            raise RuntimeError("TileSet resource was not detached")
        undo_tile_set_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_tile_set_clear.get("changed"):
            raise RuntimeError("TileSet clear was not undoable")
        restored_tile_set = await app.service.tile_set_get(
            tile_map_layer_path, scene_file=scene_file
        )
        if restored_tile_set["tile_set"] is None or restored_tile_set["total"] != 1:
            raise RuntimeError("Undo did not restore the TileSet resource")

        final_hierarchy = await app.service.scene_get_hierarchy(limit=30)
        if final_hierarchy.get("total") != 75 or _has_node(
            final_hierarchy, marker_path
        ):
            raise RuntimeError("Unexpected final hierarchy after write operations")
        saved = await app.service.scene_save(scene_file=scene_file)
        if not saved.get("saved"):
            raise RuntimeError("Scene save did not report success")
        reopened_after_packed_overrides = await app.service.scene_open(scene_file)
        if not reopened_after_packed_overrides.get("opened"):
            raise RuntimeError("Scene did not reopen after PackedScene override save")
        persisted_packed_properties = await app.service.node_get_properties(
            f"{packed_instance_path}/PackedSceneInternalSprite",
            fields=["position"],
            scene_file=scene_file,
        )
        if _property_value(persisted_packed_properties, "position") != {"x": 18.0, "y": 30.0}:
            raise RuntimeError("PackedScene internal property override did not survive reload")
        reopened_packed_hierarchy = await app.service.scene_get_hierarchy(limit=200)
        if not _has_node(reopened_packed_hierarchy, f"{packed_instance_path}/AgentPackedOverride"):
            raise RuntimeError("PackedScene local override child did not survive reload")

        saved_scene = (project_path / "test_scene.tscn").read_text(encoding="utf-8")
        if (
            "AgentButton" not in saved_scene
            or "Created by MCP" not in saved_scene
            or "AgentMarkerCopy" not in saved_scene
            or "AgentWall" not in saved_scene
            or "ConcavePolygonShape2D" not in saved_scene
            or "AgentSpringJoint" not in saved_scene
            or "AgentShapeCast" not in saved_scene
            or "AgentNavigationLink" not in saved_scene
            or "AgentAnimatedSprite" not in saved_scene
            or "AgentSemanticButton" not in saved_scene
            or "AgentTextureButton" not in saved_scene
            or "AgentLinkButton" not in saved_scene
            or "https://docs.godotengine.org/en/latest/" not in saved_scene
            or "AgentOptionMenu" not in saved_scene
            or "AgentMenuButton" not in saved_scene
            or "AgentHBox" not in saved_scene
            or "AgentGrid" not in saved_scene
            or "AgentAspect" not in saved_scene
            or "AgentFlow" not in saved_scene
            or "AgentSplit" not in saved_scene
            or "AgentScroll" not in saved_scene
            or "AgentTabs" not in saved_scene
            or "AgentSubViewportContainer" not in saved_scene
            or "Easy" not in saved_scene
            or "Show Grid" not in saved_scene
            or "Quality" not in saved_scene
            or "AgentPatrolPath" not in saved_scene
            or "AgentSkeleton" not in saved_scene
            or "AgentRootBone" not in saved_scene
            or "AgentChildBone" not in saved_scene
            or "AgentSound" not in saved_scene
            or "test_audio.tres" not in saved_scene
            or "AgentSparks" not in saved_scene
            or "AgentFire" not in saved_scene
            or "AgentCanvasItem" not in saved_scene
            or "AgentSpriteSemantic" not in saved_scene
            or "AgentLineSemantic" not in saved_scene
            or "AgentPolygonSemantic" not in saved_scene
            or "AgentPackedVisualRenamed" not in saved_scene
            or "AgentPackedVisualCopy" not in saved_scene
            or "AgentPackedOverride" not in saved_scene
            or "packed_scene_2d.tscn" not in saved_scene
            or "PackedSceneInternalSprite" not in saved_scene
            or "test_node_2d.gd" not in saved_scene
            or "accent_colors =" not in saved_scene
            or "color_labels =" not in saved_scene
            or "color_lookup =" not in saved_scene
            or "AgentCpuParticles" not in saved_scene
            or "Curve" not in saved_scene
            or "Gradient" not in saved_scene
            or "CurveTexture" not in saved_scene
            or "GradientTexture1D" not in saved_scene
            or "test_icon.svg" not in saved_scene
            or "ParticleProcessMaterial" not in saved_scene
            or "ShaderMaterial" not in saved_scene
            or "AgentViewport" not in saved_scene
            or "AgentCamera" not in saved_scene
            or "AgentParallax" not in saved_scene
            or "AgentCanvasLayer" not in saved_scene
            or "AgentPointLight" not in saved_scene
            or "AgentDirectionalLight" not in saved_scene
            or "AgentLightOccluder" not in saved_scene
            or "Curve2D" not in saved_scene
            or "NavigationPolygon" not in saved_scene
            or "AgentTileMap" not in saved_scene
            or "TileSetAtlasSource" not in saved_scene
        ):
            raise RuntimeError("Saved scene does not contain the created Button")
        reopened_scene = await app.service.scene_open(scene_file)
        if reopened_scene.get("scene_file") != scene_file:
            raise RuntimeError("Saved scene did not reopen")
        reopened_audio_animation = await app.service.animation_get(
            "/Main/ButtonAnimations", "button_hover", scene_file=scene_file
        )
        reopened_audio_track = _audio_animation_track(
            reopened_audio_animation["animation"], audio_player_path
        )
        if (
            reopened_audio_track["key_count"] != 1
            or reopened_audio_track["enabled"] is not False
            or reopened_audio_track.get("use_blend") is not False
            or reopened_audio_track["keys"][0].get("stream_path") != "res://test_audio.tres"
        ):
            raise RuntimeError("Saved audio animation track did not survive reopening")
        reopened_bezier_track = _bezier_animation_track(
            reopened_audio_animation["animation"], reparented_button_path, "modulate:a"
        )
        if (
            reopened_bezier_track["key_count"] != 1
            or reopened_bezier_track["enabled"] is not False
            or not _is_close(reopened_bezier_track["keys"][0].get("value"), 0.75)
        ):
            raise RuntimeError("Saved Bezier animation track did not survive reopening")
        reopened_method_track = _method_animation_track(
            reopened_audio_animation["animation"], reparented_button_path
        )
        if (
            reopened_method_track["key_count"] != 1
            or reopened_method_track["enabled"] is not False
            or reopened_method_track["keys"][0].get("method") != "hide"
            or reopened_method_track["keys"][0].get("args") != []
        ):
            raise RuntimeError("Saved method animation track did not survive reopening")
        reopened_nested_track = _nested_animation_track(
            reopened_audio_animation["animation"], "/Main/ButtonAnimations"
        )
        if (
            reopened_nested_track["key_count"] != 1
            or reopened_nested_track["enabled"] is not False
            or reopened_nested_track["keys"][0].get("animation") != "[stop]"
        ):
            raise RuntimeError("Saved nested animation track did not survive reopening")

        await _expect_godot_error(
            app.service.editor_run(
                mode="custom", scene_file="res://missing_scene.tscn"
            ),
            "RUN_SCENE_NOT_FOUND",
        )
        for mode in ("current", "custom", "main"):
            run_kwargs = {"mode": mode}
            if mode == "custom":
                run_kwargs["scene_file"] = scene_file
            run_result = await app.service.editor_run(**run_kwargs)
            if run_result.get("requested_scene") != scene_file:
                raise RuntimeError(
                    f"editor_run({mode}) did not target the expected scene"
                )
            playing_state = await _wait_for_play_state(app, "playing")
            if playing_state.get("playing_scene") != scene_file:
                raise RuntimeError(
                    f"editor_run({mode}) did not report the running scene"
                )
            await _expect_godot_error(
                app.service.editor_run(mode="main"), "SCENE_ALREADY_PLAYING"
            )
            stop_result = await app.service.editor_stop()
            if stop_result.get("was_playing") is not True:
                raise RuntimeError(f"editor_stop did not observe editor_run({mode})")
            stopped_state = await _wait_for_play_state(app, "stopped")
            if stopped_state.get("readiness") != "ready":
                raise RuntimeError("Editor did not become writable after editor_stop")
        idle_stop_result = await app.service.editor_stop()
        if idle_stop_result.get("was_playing") is not False:
            raise RuntimeError("editor_stop was not idempotent after the scene stopped")

        runtime_scene_file = "res://runtime_smoke.tscn"
        runtime_run = await app.service.editor_run(
            mode="custom", scene_file=runtime_scene_file
        )
        if runtime_run.get("requested_scene") != runtime_scene_file:
            raise RuntimeError("runtime feedback smoke did not start its custom scene")
        await _wait_for_play_state(app, "playing")
        runtime_state = await _wait_for_runtime_connected(app)
        if runtime_state.get("autoload", {}).get("available") is not True:
            raise RuntimeError("Runtime bridge did not report its managed autoload")
        missing_audio_request = (
            await app.service.runtime_audio_stream_player_2d_control(
                "/RuntimeSmoke/MissingSound", "get"
            )
        )
        missing_audio_result = await _wait_for_runtime_audio_control_result(
            app, missing_audio_request["request_id"]
        )
        if (
            missing_audio_result.get("status") != "error"
            or missing_audio_result.get("result", {}).get("code")
            != "RUNTIME_AUDIO_NODE_NOT_FOUND"
        ):
            raise RuntimeError(
                f"Runtime audio missing-node error was not reported: {missing_audio_result}"
            )
        audio_state_request = await app.service.runtime_audio_stream_player_2d_control(
            "/RuntimeSmoke/RuntimeSound", "get"
        )
        audio_state = await _wait_for_runtime_audio_control_result(
            app, audio_state_request["request_id"]
        )
        audio_player_state = audio_state.get("result", {}).get("player", {})
        if (
            audio_state.get("status") != "ready"
            or audio_state.get("result", {}).get("action") != "get"
            or audio_player_state.get("stream_path") != "res://test_audio.tres"
            or audio_player_state.get("is_playing") is not False
        ):
            raise RuntimeError(f"Runtime audio state was not reported: {audio_state}")
        audio_play_request = await app.service.runtime_audio_stream_player_2d_control(
            "/RuntimeSmoke/RuntimeSound", "play"
        )
        audio_play = await _wait_for_runtime_audio_control_result(
            app, audio_play_request["request_id"]
        )
        if (
            audio_play.get("status") != "ready"
            or audio_play.get("result", {}).get("action") != "play"
            or audio_play.get("result", {}).get("player", {}).get("is_playing")
            is not True
        ):
            raise RuntimeError(f"Runtime audio did not start playing: {audio_play}")
        audio_seek_request = await app.service.runtime_audio_stream_player_2d_control(
            "/RuntimeSmoke/RuntimeSound", "seek", position_seconds=0.02
        )
        audio_seek = await _wait_for_runtime_audio_control_result(
            app, audio_seek_request["request_id"]
        )
        if (
            audio_seek.get("status") != "ready"
            or audio_seek.get("result", {}).get("action") != "seek"
            or not _is_close(
                audio_seek.get("result", {}).get("requested_position_seconds"), 0.02
            )
        ):
            raise RuntimeError(f"Runtime audio seek was not applied: {audio_seek}")
        audio_stop_request = await app.service.runtime_audio_stream_player_2d_control(
            "/RuntimeSmoke/RuntimeSound", "stop"
        )
        audio_stop = await _wait_for_runtime_audio_control_result(
            app, audio_stop_request["request_id"]
        )
        if (
            audio_stop.get("status") != "ready"
            or audio_stop.get("result", {}).get("action") != "stop"
            or audio_stop.get("result", {}).get("player", {}).get("is_playing")
            is not False
        ):
            raise RuntimeError(f"Runtime audio did not stop playing: {audio_stop}")
        missing_tween_request = await app.service.runtime_tween_start(
            "/RuntimeSmoke/MissingTween",
            [
                {
                    "property": "modulate:a",
                    "to": 0.5,
                    "duration_seconds": 0.1,
                }
            ],
        )
        missing_tween = await _wait_for_runtime_tween_result(
            app, missing_tween_request["request_id"]
        )
        if (
            missing_tween.get("status") != "error"
            or missing_tween.get("result", {}).get("code")
            != "RUNTIME_TWEEN_NODE_NOT_FOUND"
        ):
            raise RuntimeError(
                f"Runtime tween missing-node error was not reported: {missing_tween}"
            )
        non_canvas_tween_request = await app.service.runtime_tween_start(
            "/RuntimeSmoke/Canvas",
            [{"property": "layer", "to": 1, "duration_seconds": 0.1}],
        )
        non_canvas_tween = await _wait_for_runtime_tween_result(
            app, non_canvas_tween_request["request_id"]
        )
        if (
            non_canvas_tween.get("status") != "error"
            or non_canvas_tween.get("result", {}).get("code")
            != "RUNTIME_TWEEN_CANVAS_ITEM_REQUIRED"
        ):
            raise RuntimeError(
                f"Runtime tween non-CanvasItem error was not reported: {non_canvas_tween}"
            )
        scripted_property_tween_request = await app.service.runtime_tween_start(
            "/RuntimeSmoke",
            [{"property": "tween_script_value", "to": 1.0, "duration_seconds": 0.1}],
        )
        scripted_property_tween = await _wait_for_runtime_tween_result(
            app, scripted_property_tween_request["request_id"]
        )
        if (
            scripted_property_tween.get("status") != "error"
            or scripted_property_tween.get("result", {}).get("code")
            != "RUNTIME_TWEEN_PROPERTY_NOT_FOUND"
        ):
            raise RuntimeError(
                "Runtime tween script-defined-property error was not reported: "
                f"{scripted_property_tween}"
            )
        label_tween_request = await app.service.runtime_tween_start(
            "/RuntimeSmoke/Canvas/Label",
            [
                {
                    "property": "position",
                    "from": {"x": 24, "y": 24},
                    "to": {"x": 8, "y": 0},
                    "duration_seconds": 0.1,
                    "transition": "sine",
                    "ease": "out",
                    "relative": True,
                },
                {
                    "property": "modulate:a",
                    "from": 1.0,
                    "to": 0.5,
                    "duration_seconds": 0.1,
                    "delay_seconds": 0.02,
                },
            ],
            parallel=True,
            loops=1,
        )
        label_tween = await _wait_for_runtime_tween_result(app, label_tween_request["request_id"])
        label_tween_data = label_tween.get("result", {})
        if (
            label_tween.get("status") != "ready"
            or label_tween_data.get("state") != "completed"
            or label_tween_data.get("path") != "/RuntimeSmoke/Canvas/Label"
            or label_tween_data.get("track_count") != 2
            or label_tween_data.get("loops") != 1
            or label_tween_data.get("elapsed_seconds", 0.0) < 0.1
        ):
            raise RuntimeError(f"Runtime finite tween did not complete: {label_tween}")
        cancellable_tween_request = await app.service.runtime_tween_start(
            "/RuntimeSmoke/Canvas/Label",
            [
                {
                    "property": "modulate:a",
                    "to": 1.0,
                    "duration_seconds": 1.0,
                }
            ],
            loops=0,
        )
        tween_stop = await app.service.runtime_tween_stop(cancellable_tween_request["request_id"])
        if tween_stop.get("status") != "cancellation_requested":
            raise RuntimeError(f"Runtime tween stop was not accepted: {tween_stop}")
        cancelled_tween = await _wait_for_runtime_tween_result(
            app, cancellable_tween_request["request_id"]
        )
        if (
            cancelled_tween.get("status") != "ready"
            or cancelled_tween.get("result", {}).get("state") != "cancelled"
            or cancelled_tween.get("result", {}).get("loops") != 0
        ):
            raise RuntimeError(f"Runtime tween cancellation did not complete: {cancelled_tween}")
        background_tween_request = await app.service.runtime_tween_start(
            "/RuntimeSmoke/Canvas/Background",
            [
                {
                    "property": "color",
                    "to": {"r": 0.25, "g": 0.6, "b": 0.35, "a": 1.0},
                    "duration_seconds": 0.1,
                    "transition": "quad",
                    "ease": "in_out",
                }
            ],
        )
        background_tween = await _wait_for_runtime_tween_result(
            app, background_tween_request["request_id"]
        )
        if (
            background_tween.get("status") != "ready"
            or background_tween.get("result", {}).get("state") != "completed"
        ):
            raise RuntimeError(f"Runtime color tween did not complete: {background_tween}")
        screenshot_request = await app.service.runtime_screenshot_request(
            format="png", max_width=128, max_height=128
        )
        screenshot = await _wait_for_runtime_screenshot(
            app, screenshot_request["request_id"]
        )
        screenshot_result = screenshot.get("result", {})
        if screenshot_result.get("ok") is not True:
            raise RuntimeError(f"Runtime screenshot failed: {screenshot_result}")
        screenshot_bytes = base64.b64decode(
            screenshot_result["data_base64"], validate=True
        )
        if screenshot_bytes[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("Runtime screenshot was not PNG data")
        if (screenshot_result.get("width"), screenshot_result.get("height")) != (
            128,
            72,
        ):
            raise RuntimeError(
                f"Runtime screenshot had unexpected dimensions: {screenshot_result}"
            )
        red, green, blue = _png_top_left_rgb(screenshot_bytes)
        if not (60 <= red <= 68 and 149 <= green <= 157 and 85 <= blue <= 93):
            raise RuntimeError(
                "Runtime screenshot did not contain the tweened smoke-scene background"
            )
        screenshot_assertions = await app.service.runtime_screenshot_assert(
            screenshot_request["request_id"],
            [
                {"kind": "dimensions", "width": 128, "height": 72},
                {
                    "kind": "pixel",
                    "x": 0,
                    "y": 0,
                    "color": {"r": 64, "g": 153, "b": 89},
                    "tolerance": 4,
                },
                {
                    "kind": "color_presence",
                    "color": {"r": 64, "g": 153, "b": 89},
                    "tolerance": 4,
                    "min_pixels": 100,
                },
            ],
        )
        if screenshot_assertions.get("status") != "ready" or not screenshot_assertions.get("passed"):
            raise RuntimeError(f"Runtime screenshot assertions failed: {screenshot_assertions}")
        performance_request = await app.service.runtime_performance_sample_request(0.2)
        performance_result = await _wait_for_runtime_performance_sample(
            app, performance_request["request_id"]
        )
        performance_data = performance_result.get("result", {})
        if (
            performance_result.get("status") != "ready"
            or performance_data.get("ok") is not True
            or performance_data.get("frame_count", 0) < 1
            or performance_data.get("actual_duration_seconds", 0.0) < 0.2
            or set(performance_data.get("monitors", {}))
            != {
                "time_fps",
                "memory_static_bytes",
                "object_count",
                "draw_calls_in_frame",
            }
        ):
            raise RuntimeError(f"Runtime performance sample was incomplete: {performance_result}")
        input_request = await app.service.runtime_input_send(
            [{"type": "action", "action": "godot_2d_mcp_smoke", "pressed": True}]
        )
        input_result = await _wait_for_runtime_input_result(
            app, input_request["request_id"]
        )
        if input_result.get("result", {}).get("applied") != 1:
            raise RuntimeError(f"Runtime input was not applied: {input_result}")
        await _wait_for_runtime_log(app, "GODOT_2D_MCP_RUNTIME_INPUT_RECEIVED")
        touch_input_request = await app.service.runtime_input_send(
            [
                {
                    "type": "screen_touch",
                    "index": 1,
                    "position": {"x": 32, "y": 48},
                    "pressed": True,
                    "double_tap": True,
                },
                {
                    "type": "screen_drag",
                    "index": 1,
                    "position": {"x": 64, "y": 96},
                    "relative": {"x": 32, "y": 48},
                    "screen_relative": {"x": 64, "y": 96},
                    "pressure": 0.5,
                    "tilt": {"x": 0.25, "y": -0.25},
                    "pen_inverted": True,
                },
                {
                    "type": "screen_touch",
                    "index": 1,
                    "position": {"x": 64, "y": 96},
                    "pressed": False,
                    "canceled": True,
                },
            ]
        )
        touch_input_result = await _wait_for_runtime_input_result(
            app, touch_input_request["request_id"]
        )
        if touch_input_result.get("result", {}).get("applied") != 3:
            raise RuntimeError(f"Runtime touch input was not applied: {touch_input_result}")
        for marker in (
            "GODOT_2D_MCP_RUNTIME_TOUCH_PRESS_RECEIVED",
            "GODOT_2D_MCP_RUNTIME_TOUCH_DRAG_RECEIVED",
            "GODOT_2D_MCP_RUNTIME_TOUCH_RELEASE_RECEIVED",
        ):
            await _wait_for_runtime_log(app, marker)
        runtime_stop = await app.service.editor_stop()
        if runtime_stop.get("was_playing") is not True:
            raise RuntimeError("Runtime feedback smoke could not stop its custom scene")
        await _wait_for_play_state(app, "stopped")
        orchestrated_test = await app.service.runtime_test_run(
            mode="custom",
            scene_file=runtime_scene_file,
            inputs=[{"type": "action", "action": "godot_2d_mcp_smoke", "pressed": True}],
            settle_seconds=0.1,
            performance_sample_seconds=0.1,
            screenshot={"format": "png", "max_width": 64, "max_height": 64},
            screenshot_assertions=[
                {"kind": "dimensions", "width": 64, "height": 36},
                {
                    "kind": "color_presence",
                    "color": {"r": 230, "g": 13, "b": 26},
                    "tolerance": 4,
                    "min_pixels": 100,
                },
            ],
            timeout_seconds=10.0,
        )
        if (
            orchestrated_test.get("status") != "passed"
            or orchestrated_test.get("cleanup", {}).get("editor_state", {}).get("play_state")
            != "stopped"
        ):
            raise RuntimeError(f"Runtime test orchestration failed: {orchestrated_test}")

        print(
            "Godot smoke passed: "
            f"session={sessions[0]['session_id']} "
            f"nodes={final_hierarchy['total']} "
            f"button_classes={classes['total']}"
        )
    except BaseException as error:
        failure = error
        raise
    finally:
        _signal_process_group(process, signal.SIGTERM)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout=5.0)
        except TimeoutError:
            _signal_process_group(process, signal.SIGKILL)
            output, _ = await process.communicate()
        await app.bridge.stop()
        if failure is not None and output:
            print(
                "Godot output after smoke failure:\n" + output.decode(errors="replace")
            )

    editor_output = output.decode(errors="replace")
    fatal_markers = ("SCRIPT ERROR", "Parse Error", "ERROR: Failed to load script")
    if any(marker in editor_output for marker in fatal_markers):
        raise RuntimeError(f"Godot reported script errors:\n{editor_output}")


def _signal_process_group(
    process: asyncio.subprocess.Process, signal_number: int
) -> None:
    if os.name == "nt":
        if process.returncode is None:
            if signal_number == signal.SIGTERM:
                process.terminate()
            else:
                process.kill()
        return
    try:
        os.killpg(process.pid, signal_number)
    except ProcessLookupError:
        pass


async def _smoke_generic_2d_node_lifecycle(
    app: object, original_scene_file: str, coverage_snapshot: dict
) -> None:
    """Exercise every node that the live ClassDB audit claims generic support for."""
    entries = coverage_snapshot.get("entries")
    if not isinstance(entries, list):
        raise TypeError("2D coverage snapshot did not contain node entries")
    node_entries = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("kind") == "node"
        and entry.get("base_support", {}).get("create") is True
    ]
    if not node_entries:
        raise RuntimeError("2D coverage snapshot did not contain creatable node entries")

    _trace_smoke(f"starting generic lifecycle smoke for {len(node_entries)} 2D nodes")
    coverage_scene_file = "res://generated/class_2d_coverage_smoke.tscn"
    coverage_root_name = "Class2DCoverage"
    coverage_root_path = f"/{coverage_root_name}"
    created: list[tuple[str, str, str]] = []
    failures: list[str] = []
    try:
        created_scene = await app.service.scene_create(
            scene_path=coverage_scene_file,
            root_type="Node2D",
            root_name=coverage_root_name,
        )
        if not created_scene.get("created") or created_scene.get("scene_file") != coverage_scene_file:
            raise RuntimeError("Generic 2D coverage scene was not created")
        for index, entry in enumerate(node_entries):
            type_name = str(entry["name"])
            name = f"CoverageNode{index:03d}"
            try:
                result = await app.service.node_create(
                    type_name=type_name,
                    name=name,
                    parent_path=coverage_root_path,
                    scene_file=coverage_scene_file,
                )
                path = str(result.get("path", ""))
                if result.get("type") != type_name or not path:
                    failures.append(f"{type_name}: create returned {result}")
                    continue
                properties = await app.service.node_get_properties(
                    path, scene_file=coverage_scene_file
                )
                if properties.get("type") != type_name or not isinstance(
                    properties.get("properties"), list
                ):
                    failures.append(f"{type_name}: property inspection returned {properties}")
                    continue
                created.append((path, type_name, name))
            except GodotCommandError as error:
                failures.append(f"{type_name}: {error.code}")
        if failures:
            raise RuntimeError(
                "ClassDB nodes advertised as generically supported failed lifecycle smoke: "
                + ", ".join(failures)
            )

        saved = await app.service.scene_save(scene_file=coverage_scene_file)
        if not saved.get("saved"):
            raise RuntimeError("Generic 2D coverage scene could not be saved")
        reopened = await app.service.scene_open(coverage_scene_file)
        if not reopened.get("opened"):
            raise RuntimeError("Generic 2D coverage scene could not be reopened")
        hierarchy = await app.service.scene_get_hierarchy(max_depth=1, limit=500)
        nodes_by_path = {str(node.get("path", "")): node for node in hierarchy.get("nodes", [])}
        missing_or_changed = [
            type_name
            for path, type_name, _name in created
            if nodes_by_path.get(path, {}).get("type") != type_name
        ]
        if missing_or_changed:
            raise RuntimeError(
                "Generic 2D coverage nodes were not preserved after save/reopen: "
                + ", ".join(missing_or_changed)
            )

        last_path = created[0][0]
        for path, _type_name, _name in reversed(created):
            deleted = await app.service.node_delete(path, scene_file=coverage_scene_file)
            if not deleted.get("deleted"):
                raise RuntimeError(f"Generic 2D coverage node was not deleted: {path}")
        undone = await app.service.scene_undo(scene_file=coverage_scene_file)
        if not undone.get("changed"):
            raise RuntimeError("Generic 2D coverage deletion was not undoable")
        restored = await app.service.node_get_properties(last_path, scene_file=coverage_scene_file)
        if not isinstance(restored.get("properties"), list):
            raise TypeError("Generic 2D coverage undo did not restore the deleted node")
        redone = await app.service.scene_redo(scene_file=coverage_scene_file)
        if not redone.get("changed"):
            raise RuntimeError("Generic 2D coverage deletion was not redoable")
        after_redo = await app.service.scene_get_hierarchy(max_depth=1, limit=500)
        if any(node.get("path") == last_path for node in after_redo.get("nodes", [])):
            raise RuntimeError("Generic 2D coverage redo did not remove the restored node")
        if not (await app.service.scene_save(scene_file=coverage_scene_file)).get("saved"):
            raise RuntimeError("Generic 2D coverage cleanup could not be saved")
    finally:
        reopened_original = await app.service.scene_open(original_scene_file)
        if not reopened_original.get("opened"):
            raise RuntimeError("Generic 2D coverage smoke could not restore the original scene")


async def _wait_for_editor_ready(app: object, timeout_seconds: float = 30.0) -> dict:
    """Wait for a newly imported isolated project to become writable."""
    attempts = int(timeout_seconds / 0.1)
    state: dict = {}
    for _ in range(attempts):
        state = await app.service.editor_get_state()
        if state.get("readiness") == "ready":
            return state
        await asyncio.sleep(0.1)
    raise RuntimeError(
        "Editor did not become ready within "
        f"{timeout_seconds:.0f} seconds; last state: {state}"
    )


async def _wait_for_play_state(
    app: object, expected_state: str, timeout_seconds: float = 10.0
) -> dict:
    attempts = int(timeout_seconds / 0.1)
    state: dict = {}
    for _ in range(attempts):
        state = await app.service.editor_get_state()
        if state.get("play_state") == expected_state:
            return state
        await asyncio.sleep(0.1)
    raise RuntimeError(
        "Editor did not reach play state "
        f"'{expected_state}' within {timeout_seconds:.0f} seconds; last state: {state}"
    )


async def _wait_for_runtime_connected(
    app: object, timeout_seconds: float = 10.0
) -> dict:
    attempts = int(timeout_seconds / 0.1)
    state: dict = {}
    for _ in range(attempts):
        state = await app.service.runtime_get_state()
        if state.get("connected") is True:
            return state
        await asyncio.sleep(0.1)
    raise RuntimeError(
        "Runtime bridge did not connect within "
        f"{timeout_seconds:.0f} seconds; last state: {state}"
    )


async def _wait_for_runtime_screenshot(
    app: object, request_id: str, timeout_seconds: float = 10.0
) -> dict:
    attempts = int(timeout_seconds / 0.1)
    result: dict = {}
    for _ in range(attempts):
        result = await app.service.runtime_screenshot_get(request_id)
        if result.get("status") != "pending":
            return result
        await asyncio.sleep(0.1)
    raise RuntimeError(
        "Runtime screenshot did not complete within "
        f"{timeout_seconds:.0f} seconds; last result: {result}"
    )


async def _wait_for_runtime_input_result(
    app: object, request_id: str, timeout_seconds: float = 10.0
) -> dict:
    attempts = int(timeout_seconds / 0.1)
    result: dict = {}
    for _ in range(attempts):
        result = await app.service.runtime_input_result_get(request_id)
        if result.get("status") != "pending":
            return result
        await asyncio.sleep(0.1)
    raise RuntimeError(
        "Runtime input did not complete within "
        f"{timeout_seconds:.0f} seconds; last result: {result}"
    )


async def _wait_for_runtime_performance_sample(
    app: object, request_id: str, timeout_seconds: float = 10.0
) -> dict:
    attempts = int(timeout_seconds / 0.1)
    result: dict = {}
    for _ in range(attempts):
        result = await app.service.runtime_performance_sample_result_get(request_id)
        if result.get("status") != "pending":
            return result
        await asyncio.sleep(0.1)
    raise RuntimeError(
        "Runtime performance sample did not complete within "
        f"{timeout_seconds:.0f} seconds; last result: {result}"
    )


async def _wait_for_runtime_audio_control_result(
    app: object, request_id: str, timeout_seconds: float = 10.0
) -> dict:
    attempts = int(timeout_seconds / 0.1)
    result: dict = {}
    for _ in range(attempts):
        result = await app.service.runtime_audio_stream_player_2d_control_result_get(
            request_id
        )
        if result.get("status") != "pending":
            return result
        await asyncio.sleep(0.1)
    raise RuntimeError(
        "Runtime audio control did not complete within "
        f"{timeout_seconds:.0f} seconds; last result: {result}"
    )


async def _wait_for_runtime_tween_result(
    app: object, request_id: str, timeout_seconds: float = 10.0
) -> dict:
    attempts = int(timeout_seconds / 0.1)
    result: dict = {}
    for _ in range(attempts):
        result = await app.service.runtime_tween_result_get(request_id)
        if result.get("status") != "pending":
            return result
        await asyncio.sleep(0.1)
    raise RuntimeError(
        "Runtime tween did not complete within "
        f"{timeout_seconds:.0f} seconds; last result: {result}"
    )


async def _wait_for_navigation_polygon_bake(
    app: object, request_id: str, timeout_seconds: float = 10.0
) -> dict:
    attempts = int(timeout_seconds / 0.1)
    result: dict = {}
    for _ in range(attempts):
        result = await app.service.navigation_polygon_bake_result_get(request_id)
        if result.get("status") != "pending":
            return result
        await asyncio.sleep(0.1)
    raise RuntimeError(
        "NavigationPolygon source geometry bake did not complete within "
        f"{timeout_seconds:.0f} seconds; last result: {result}"
    )


async def _wait_for_runtime_log(
    app: object, message: str, timeout_seconds: float = 10.0
) -> dict:
    attempts = int(timeout_seconds / 0.1)
    logs: dict = {}
    for _ in range(attempts):
        logs = await app.service.runtime_logs_get(limit=200)
        if any(
            message in str(entry.get("message", ""))
            for entry in logs.get("entries", [])
        ):
            return logs
        await asyncio.sleep(0.1)
    raise RuntimeError(
        "Runtime log did not contain "
        f"'{message}' within {timeout_seconds:.0f} seconds; last logs: {logs}"
    )


def _png_top_left_rgb(data: bytes) -> tuple[int, int, int]:
    position = 8
    width = height = bit_depth = color_type = 0
    compressed = bytearray()
    while position < len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        chunk_type = data[position + 4 : position + 8]
        chunk_data = data[position + 8 : position + 8 + length]
        position += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, _ = struct.unpack(
                ">IIBBBBB", chunk_data
            )
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if width < 1 or height < 1 or bit_depth != 8 or color_type not in {2, 6}:
        raise RuntimeError("Runtime screenshot PNG had an unsupported format")
    raw = zlib.decompress(compressed)
    channels = 4 if color_type == 6 else 3
    if len(raw) < channels + 1:
        raise RuntimeError("Runtime screenshot PNG did not contain its first pixel")
    return raw[1], raw[2], raw[3]


def _property_value(result: dict, name: str) -> object:
    return _property_data(result, name).get("value")


def _property_data(result: dict, name: str) -> dict:
    for property_data in result.get("properties", []):
        if property_data.get("name") == name:
            return property_data
    raise RuntimeError(f"Property was not returned: {name}")


def _theme_item(result: dict, group: str, theme_type: str, name: str) -> dict | None:
    theme = result.get("theme") or {}
    for item in theme.get("items", {}).get(group, []):
        if item.get("theme_type") == theme_type and item.get("name") == name:
            return item
    return None


def _is_close(actual: object, expected: float) -> bool:
    return isinstance(actual, (int, float)) and abs(float(actual) - expected) < 1e-6


def _color_matches(actual: object, expected: dict[str, float]) -> bool:
    return isinstance(actual, dict) and all(
        _is_close(actual.get(channel), value) for channel, value in expected.items()
    )


def _has_node(hierarchy: dict, path: str) -> bool:
    return any(node.get("path") == path for node in hierarchy.get("nodes", []))


def _node_data(hierarchy: dict, path: str) -> dict:
    for node in hierarchy.get("nodes", []):
        if node.get("path") == path:
            return node
    raise RuntimeError(f"Node was not returned: {path}")


def _signal_data(result: dict, name: str) -> dict | None:
    for signal_data in result.get("signals", []):
        if signal_data.get("name") == name:
            return signal_data
    return None


def _has_animation(result: dict, library: str, name: str) -> bool:
    return any(
        item.get("name") == library
        and any(
            animation.get("name") == name for animation in item.get("animations", [])
        )
        for item in result.get("libraries", [])
    )


def _has_animation_track(animation: dict, target_path: str, property_name: str) -> bool:
    return any(
        track.get("target_path") == target_path
        and track.get("property") == property_name
        for track in animation.get("tracks", [])
    )


def _animation_track(animation: dict, target_path: str, property_name: str) -> dict:
    for track in animation.get("tracks", []):
        if (
            track.get("target_path") == target_path
            and track.get("property") == property_name
        ):
            return track
    raise RuntimeError(
        f"Animation track was not returned: {target_path}:{property_name}"
    )


def _audio_animation_track(animation: dict, target_path: str) -> dict:
    for track in animation.get("tracks", []):
        if track.get("type") == "audio" and track.get("target_path") == target_path:
            return track
    raise RuntimeError(f"Audio animation track was not returned: {target_path}")


def _bezier_animation_track(animation: dict, target_path: str, property_name: str) -> dict:
    for track in animation.get("tracks", []):
        if (
            track.get("type") == "bezier"
            and track.get("target_path") == target_path
            and track.get("property") == property_name
        ):
            return track
    raise RuntimeError(
        f"Bezier animation track was not returned: {target_path}:{property_name}"
    )


def _method_animation_track(animation: dict, target_path: str) -> dict:
    for track in animation.get("tracks", []):
        if track.get("type") == "method" and track.get("target_path") == target_path:
            return track
    raise RuntimeError(f"Method animation track was not returned: {target_path}")


def _nested_animation_track(animation: dict, target_path: str) -> dict:
    for track in animation.get("tracks", []):
        if track.get("type") == "animation" and track.get("target_path") == target_path:
            return track
    raise RuntimeError(f"Nested animation track was not returned: {target_path}")


def _vector2_match(actual: object, expected: dict[str, float]) -> bool:
    return (
        isinstance(actual, dict)
        and all(
            axis in actual and _is_close(actual[axis], value)
            for axis, value in expected.items()
        )
    )


def _layout_sides_match(actual: object, expected: dict[str, float]) -> bool:
    return isinstance(actual, dict) and all(
        key in actual
        and isinstance(actual[key], (int, float))
        and abs(float(actual[key]) - value) < 1e-6
        for key, value in expected.items()
    )


def _stylebox_state(result: dict, state_name: str) -> dict | None:
    for state in result.get("styles", []):
        if state.get("state") == state_name:
            return state
    return None


def _has_signal_connection(
    result: dict,
    signal_name: str,
    target_path: str,
    method: str,
    binds: list[object],
) -> bool:
    signal_data = _signal_data(result, signal_name)
    return bool(
        signal_data
        and any(
            connection.get("target_path") == target_path
            and connection.get("method") == method
            and connection.get("binds") == binds
            for connection in signal_data.get("connections", [])
        )
    )


async def _expect_godot_error(call: Awaitable[object], expected_code: str) -> None:
    try:
        await call
    except GodotCommandError as error:
        if error.code == expected_code:
            return
        raise RuntimeError(
            f"Expected {expected_code}, received {error.code}"
        ) from error
    raise RuntimeError(f"Expected Godot command error: {expected_code}")


def _color_matches(actual: object, expected: dict[str, float]) -> bool:
    return isinstance(actual, dict) and all(
        component in actual
        and isinstance(actual[component], (int, float))
        and abs(float(actual[component]) - value) < 1e-6
        for component, value in expected.items()
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default="godot", help="Godot editor executable")
    parser.add_argument(
        "--project",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "plugin",
        help="Plugin test project path",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run_smoke(args.godot, args.project.resolve()))


if __name__ == "__main__":
    main()

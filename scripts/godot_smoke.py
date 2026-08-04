"""Run a real Godot editor against the Python WebSocket bridge."""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import socket
import tempfile
from collections.abc import Awaitable
from pathlib import Path

from godot_2d_mcp.bridge import GodotCommandError
from godot_2d_mcp.server import create_application


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
    )

    output = b""
    try:
        for _ in range(100):
            sessions = await app.registry.list_sessions()
            if sessions:
                break
            if process.returncode is not None:
                raise RuntimeError("Godot exited before the plugin connected")
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("Godot plugin did not connect within 10 seconds")

        state = await app.service.editor_get_state()
        hierarchy = await app.service.scene_get_hierarchy(limit=20)
        classes = await app.service.class_search(query="Button", limit=20)

        if state.get("readiness") != "ready":
            raise RuntimeError(f"Unexpected editor readiness: {state.get('readiness')}")
        if hierarchy.get("total") != 5:
            raise RuntimeError(f"Unexpected scene node count: {hierarchy.get('total')}")
        if classes.get("total", 0) < 4:
            raise RuntimeError("2D class search returned too few Button types")

        scene_file = state.get("current_scene", "")
        initial_revision = state["meta"]["scene_revision"]
        await _expect_godot_error(
            app.service.node_create(type_name="Node3D", scene_file=scene_file),
            "UNSUPPORTED_2D_TYPE",
        )
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
        if _property_value(follower_properties, "remote_path") != "../UI/Panel/RenamedButton":
            raise RuntimeError("Rename did not update the RemoteTransform2D path")

        undo_rename = await app.service.scene_undo(scene_file=scene_file)
        if not undo_rename.get("changed"):
            raise RuntimeError("Rename was not undoable")
        follower_properties = await app.service.node_get_properties(
            follower_path,
            fields=["remote_path"],
            scene_file=scene_file,
        )
        if _property_value(follower_properties, "remote_path") != "../UI/Panel/StartButton":
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
            raise RuntimeError("Reparent did not preserve the default global transform policy")
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
        if _property_value(follower_properties, "remote_path") != "../UI/Panel/RenamedButton":
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
            raise RuntimeError("Animation track target was not resolved after reparenting")
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
            raise RuntimeError("Animation track did not retain its keyframe configuration")
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
        if (
            normal_style["effective_type"] != "StyleBoxFlat"
            or not _color_matches(
                normal_style["flat_properties"].get("bg_color"),
                {"r": 0.08, "g": 0.3, "b": 0.55, "a": 1.0},
            )
        ):
            raise RuntimeError("StyleBoxFlat override did not retain requested properties")
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
            raise RuntimeError("Signal connection flags were not returned by node_get_signals")
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
            app.service.node_rename(marker_copy_path, "AgentMarker", scene_file=scene_file),
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
        moved_copy = await app.service.node_move(marker_copy_path, index=0, scene_file=scene_file)
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

        final_hierarchy = await app.service.scene_get_hierarchy(limit=30)
        if final_hierarchy.get("total") != 11 or _has_node(final_hierarchy, marker_path):
            raise RuntimeError("Unexpected final hierarchy after write operations")
        saved = await app.service.scene_save(scene_file=scene_file)
        if not saved.get("saved"):
            raise RuntimeError("Scene save did not report success")

        saved_scene = (project_path / "test_scene.tscn").read_text(encoding="utf-8")
        if (
            "AgentButton" not in saved_scene
            or "Created by MCP" not in saved_scene
            or "AgentMarkerCopy" not in saved_scene
        ):
            raise RuntimeError("Saved scene does not contain the created Button")

        print(
            "Godot smoke passed: "
            f"session={sessions[0]['session_id']} "
            f"nodes={final_hierarchy['total']} "
            f"button_classes={classes['total']}"
        )
    finally:
        if process.returncode is None:
            process.terminate()
        output, _ = await process.communicate()
        await app.bridge.stop()

    editor_output = output.decode(errors="replace")
    fatal_markers = ("SCRIPT ERROR", "Parse Error", "ERROR: Failed to load script")
    if any(marker in editor_output for marker in fatal_markers):
        raise RuntimeError(f"Godot reported script errors:\n{editor_output}")


def _property_value(result: dict, name: str) -> object:
    for property_data in result.get("properties", []):
        if property_data.get("name") == name:
            return property_data.get("value")
    raise RuntimeError(f"Property was not returned: {name}")


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
        and any(animation.get("name") == name for animation in item.get("animations", []))
        for item in result.get("libraries", [])
    )


def _has_animation_track(animation: dict, target_path: str, property_name: str) -> bool:
    return any(
        track.get("target_path") == target_path and track.get("property") == property_name
        for track in animation.get("tracks", [])
    )


def _animation_track(animation: dict, target_path: str, property_name: str) -> dict:
    for track in animation.get("tracks", []):
        if track.get("target_path") == target_path and track.get("property") == property_name:
            return track
    raise RuntimeError(f"Animation track was not returned: {target_path}:{property_name}")


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
        raise RuntimeError(f"Expected {expected_code}, received {error.code}") from error
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

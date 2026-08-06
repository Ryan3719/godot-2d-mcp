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
    failure: BaseException | None = None
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

        state = await _wait_for_editor_ready(app)
        hierarchy = await app.service.scene_get_hierarchy(limit=20)
        classes = await app.service.class_search(query="Button", limit=20)

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
        themed_state = await app.service.control_theme_get(styled_button_path, scene_file=scene_file)
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
        themed_state = await app.service.control_theme_get(styled_button_path, scene_file=scene_file)
        if any(value is not None for value in themed_state["theme"]["defaults"].values()):
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
            raise RuntimeError("Theme font size item did not retain the requested value")
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
        themed_state = await app.service.control_theme_get(styled_button_path, scene_file=scene_file)
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
            raise RuntimeError("External Theme assignment did not retain its project path")
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
        restored_theme = await app.service.control_theme_get(styled_button_path, scene_file=scene_file)
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
        if "SmokeUiTheme" not in saved_scene or 'theme = SubResource("Theme_' not in saved_scene:
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
            raise RuntimeError("New CollisionShape2D unexpectedly had a Shape2D resource")
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
        cleared_shape = await app.service.collision_shape_clear(wall_shape_path, scene_file=scene_file)
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
        initial_layers = await app.service.collision_object_get_layers(wall_path, scene_file=scene_file)
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
        restored_layers = await app.service.collision_object_get_layers(wall_path, scene_file=scene_file)
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
        if static_update["body_kind"] != "StaticBody2D" or static_update["configuration"][
            "constant_linear_velocity"
        ] != {"x": 24.0, "y": 0.0}:
            raise RuntimeError("StaticBody2D configuration was not applied")
        static_state = await app.service.physics_body_2d_get(wall_path, scene_file=scene_file)
        if static_state["configuration"]["constant_angular_velocity"] != 0.5:
            raise RuntimeError("physics_body_2d_get did not return the current StaticBody2D configuration")

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
            raise RuntimeError("PinJoint2D configuration or endpoint path was not applied")
        pin_state = await app.service.joint_2d_get(pin_joint_path, scene_file=scene_file)
        if pin_state["node_a_path"] != rigid_body_path or pin_state["configuration"]["softness"] != 0.5:
            raise RuntimeError("joint_2d_get did not return the current PinJoint2D configuration")

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
        initial_ray_cast = await app.service.ray_cast_2d_get(ray_cast_path, scene_file=scene_file)
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
            or ray_cast_update["configuration"]["target_position"] != {"x": 96.0, "y": 24.0}
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
        restored_shape_cast = await app.service.shape_cast_2d_get(shape_cast_path, scene_file=scene_file)
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
            raise RuntimeError("New NavigationRegion2D unexpectedly had a NavigationPolygon resource")
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
        direct_navigation_polygon = await app.service.navigation_polygon_geometry_set(
            navigation_region_path,
            navigation_polygon_vertices,
            [[0, 1, 2, 3]],
            agent_radius=8.0,
            scene_file=scene_file,
        )
        if (
            direct_navigation_polygon["navigation_polygon"]["agent_radius"] != 8.0
            or direct_navigation_polygon["navigation_polygon"]["polygons"] != [[0, 1, 2, 3]]
        ):
            raise RuntimeError("NavigationPolygon direct geometry was not applied")
        outlined_navigation_polygon = await app.service.navigation_polygon_outline_set(
            navigation_region_path, navigation_polygon_vertices, scene_file=scene_file
        )
        if outlined_navigation_polygon["outline_index"] != 0:
            raise RuntimeError("NavigationPolygon outline was not appended")
        baked_navigation_polygon = await app.service.navigation_polygon_make_from_outlines(
            navigation_region_path, scene_file=scene_file
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
        undo_navigation_polygon_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_navigation_polygon_clear.get("changed"):
            raise RuntimeError("NavigationPolygon clear was not undoable")
        restored_navigation_polygon = await app.service.navigation_polygon_get(
            navigation_region_path, scene_file=scene_file
        )
        if not restored_navigation_polygon["navigation_polygon"]["polygons"]:
            raise RuntimeError("Undo did not restore the NavigationPolygon resource")

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
        if (
            obstacle_update["configuration"]["radius"] != 16.0
            or obstacle_update["configuration"]["avoidance_layers"] != [2]
        ):
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
        if navigation_link_state["configuration"]["end_position"] != {"x": 128.0, "y": 32.0}:
            raise RuntimeError("navigation_2d_get did not return the current NavigationLink2D configuration")
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
        if initial_patrol_path["curve"] is not None or initial_patrol_path["total_points"] != 0:
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
            paged_patrol_path["points"] != [
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
        if inserted_patrol_point["point_index"] != 1 or inserted_patrol_point["total_points"] != 4:
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
        if removed_patrol_point["removed_point_index"] != 0 or removed_patrol_point["total_points"] != 3:
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
        if restored_patrol_curve["curve"] is None or restored_patrol_curve["total_points"] != 3:
            raise RuntimeError("Undo did not restore the Path2D Curve2D resource")

        skeleton = await app.service.node_create(
            type_name="Skeleton2D",
            name="AgentSkeleton",
            parent_path="/Main",
            scene_file=scene_file,
        )
        skeleton_path = skeleton["path"]
        empty_skeleton = await app.service.skeleton_2d_get(skeleton_path, scene_file=scene_file)
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
        initial_skeleton = await app.service.skeleton_2d_get(skeleton_path, scene_file=scene_file)
        if initial_skeleton["bone_count"] != 2 or {
            bone["path"] for bone in initial_skeleton["bones"]
        } != {root_bone_path, child_bone_path}:
            raise RuntimeError("Skeleton2D did not discover its Bone2D hierarchy")
        initial_root_bone = await app.service.bone_2d_get(root_bone_path, scene_file=scene_file)
        if not initial_root_bone["valid_hierarchy"] or initial_root_bone["skeleton_path"] != skeleton_path:
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
        reset_root_bone = await app.service.bone_2d_get(root_bone_path, scene_file=scene_file)
        if reset_root_bone["transform"] != root_rest:
            raise RuntimeError("Skeleton2D reset-to-rest did not restore the Bone2D transform")
        undo_skeleton_reset = await app.service.scene_undo(scene_file=scene_file)
        if not undo_skeleton_reset.get("changed"):
            raise RuntimeError("Skeleton2D reset-to-rest was not undoable")
        restored_root_transform = await app.service.bone_2d_get(root_bone_path, scene_file=scene_file)
        if restored_root_transform["transform"] == root_rest:
            raise RuntimeError("Undo did not restore the Bone2D transform before reset-to-rest")
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
        current_rest_root_bone = await app.service.bone_2d_get(root_bone_path, scene_file=scene_file)
        if current_rest_root_bone["rest"]["origin"] != {"x": 64.0, "y": 16.0}:
            raise RuntimeError("Skeleton2D did not copy the current Bone2D transform to rest")
        undo_make_rest = await app.service.scene_undo(scene_file=scene_file)
        if not undo_make_rest.get("changed"):
            raise RuntimeError("Skeleton2D make-rest-from-current was not undoable")
        restored_rest_root_bone = await app.service.bone_2d_get(root_bone_path, scene_file=scene_file)
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
            raise RuntimeError("New AudioStreamPlayer2D had unexpected stream or bus state")
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
            raise RuntimeError("Undo did not clear the AudioStreamPlayer2D stream binding")
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
        if restored_audio_stream["configuration"]["stream_path"] != "res://test_audio.tres":
            raise RuntimeError("Undo did not restore the AudioStreamPlayer2D stream binding")

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
        initial_camera = await app.service.camera_2d_get(camera_path, scene_file=scene_file)
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
        restored_camera = await app.service.camera_2d_get(camera_path, scene_file=scene_file)
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
        if initial_tile_map["tile_set"] is not None or initial_tile_map["used_cells"] != 0:
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
            raise RuntimeError("TileSetAtlasSource did not retain its requested source ID")
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
            raise RuntimeError("New TileSet unexpectedly had semantic layer definitions")
        physics_layer = await app.service.tile_set_physics_layer_create(
            tile_map_layer_path,
            layers=[2],
            masks=[1, 3],
            priority=0.5,
            scene_file=scene_file,
        )
        if (
            physics_layer["physics_layer_index"] != 0
            or physics_layer["physics_layers"][0]
            != {"index": 0, "layers": [2], "masks": [1, 3], "priority": 0.5}
        ):
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
        terrain_set = await app.service.tile_set_terrain_set_create(
            tile_map_layer_path,
            mode="match_sides",
            scene_file=scene_file,
        )
        if terrain_set["terrain_set"] != 0 or terrain_set["terrain_sets"][0]["mode"] != "match_sides":
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
                for channel, expected in {"r": 0.2, "g": 0.7, "b": 0.3, "a": 1.0}.items()
            )
        ):
            raise RuntimeError("TileSet terrain definition was not applied")
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
        atlas_alternative = await app.service.tile_set_atlas_alternative_create(
            tile_map_layer_path,
            source_id=3,
            atlas_coords={"x": 0, "y": 0},
            alternative_tile=1,
            scene_file=scene_file,
        )
        if atlas_alternative["alternative_tile"] != 1:
            raise RuntimeError("TileSet atlas alternative was not created")
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
            values={"damage": 8},
            alternative_tile=1,
            scene_file=scene_file,
        )
        if atlas_custom_data["custom_data"] != {"damage": 8}:
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
            atlas_tile_state["physics_layers"] != [
                {"index": 0, "collision_polygons": collision_polygons}
            ]
            or atlas_tile_state["navigation_layers"]
            != [{"index": 0, "navigation_polygon": navigation_polygon}]
            or atlas_tile_state["occlusion_layers"]
            != [{"index": 0, "occluder_polygons": occlusion_polygons}]
        ):
            raise RuntimeError("tile_set_atlas_tile_get did not return TileData geometry")
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
        if restored_atlas_tile["navigation_layers"][0]["navigation_polygon"] != navigation_polygon:
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
        if restored_atlas_tile["occlusion_layers"][0]["occluder_polygons"] != occlusion_polygons:
            raise RuntimeError("Undo did not restore TileSet atlas occlusion geometry")
        redo_tile_occlusion_clear = await app.service.scene_redo(scene_file=scene_file)
        if not redo_tile_occlusion_clear.get("changed"):
            raise RuntimeError("TileSet atlas occlusion clear was not redoable")
        tile_set_state = await app.service.tile_set_get(tile_map_layer_path, scene_file=scene_file)
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
                "alternative_tile": 0,
            },
            {
                "coords": {"x": 0, "y": 2},
                "source_id": 3,
                "atlas_coords": {"x": 0, "y": 0},
                "alternative_tile": 0,
            },
        ]
        tile_cells_update = await app.service.tile_map_layer_cells_set(
            tile_map_layer_path, tile_cells, scene_file=scene_file
        )
        if tile_cells_update["changed_cells"] != 2 or tile_cells_update["used_cells"] != 2:
            raise RuntimeError("TileMapLayer cells were not assigned")
        tile_cells_state = await app.service.tile_map_layer_cells_get(
            tile_map_layer_path, limit=10, scene_file=scene_file
        )
        if tile_cells_state["total"] != 2 or tile_cells_state["cells"] != tile_cells:
            raise RuntimeError("tile_map_layer_cells_get did not return stable cell assignments")
        cleared_tile_cells = await app.service.tile_map_layer_cells_clear(
            tile_map_layer_path,
            [{"x": -1, "y": 2}],
            scene_file=scene_file,
        )
        if cleared_tile_cells["cleared_cells"] != 1 or cleared_tile_cells["used_cells"] != 1:
            raise RuntimeError("TileMapLayer cell clear was not applied")
        undo_tile_cell_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_tile_cell_clear.get("changed"):
            raise RuntimeError("TileMapLayer cell clear was not undoable")
        restored_tile_cells = await app.service.tile_map_layer_cells_get(
            tile_map_layer_path, limit=10, scene_file=scene_file
        )
        if restored_tile_cells["total"] != 2:
            raise RuntimeError("Undo did not restore TileMapLayer cells")
        cleared_tile_set = await app.service.tile_set_clear(tile_map_layer_path, scene_file=scene_file)
        if cleared_tile_set["tile_set"] is not None:
            raise RuntimeError("TileSet resource was not detached")
        undo_tile_set_clear = await app.service.scene_undo(scene_file=scene_file)
        if not undo_tile_set_clear.get("changed"):
            raise RuntimeError("TileSet clear was not undoable")
        restored_tile_set = await app.service.tile_set_get(tile_map_layer_path, scene_file=scene_file)
        if restored_tile_set["tile_set"] is None or restored_tile_set["total"] != 1:
            raise RuntimeError("Undo did not restore the TileSet resource")

        final_hierarchy = await app.service.scene_get_hierarchy(limit=30)
        if final_hierarchy.get("total") != 39 or _has_node(final_hierarchy, marker_path):
            raise RuntimeError("Unexpected final hierarchy after write operations")
        saved = await app.service.scene_save(scene_file=scene_file)
        if not saved.get("saved"):
            raise RuntimeError("Scene save did not report success")

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
            or "AgentPatrolPath" not in saved_scene
            or "AgentSkeleton" not in saved_scene
            or "AgentRootBone" not in saved_scene
            or "AgentChildBone" not in saved_scene
            or "AgentSound" not in saved_scene
            or "test_audio.tres" not in saved_scene
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
        if process.returncode is None:
            process.terminate()
        output, _ = await process.communicate()
        await app.bridge.stop()
        if failure is not None and output:
            print("Godot output after smoke failure:\n" + output.decode(errors="replace"))

    editor_output = output.decode(errors="replace")
    fatal_markers = ("SCRIPT ERROR", "Parse Error", "ERROR: Failed to load script")
    if any(marker in editor_output for marker in fatal_markers):
        raise RuntimeError(f"Godot reported script errors:\n{editor_output}")


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


def _property_value(result: dict, name: str) -> object:
    for property_data in result.get("properties", []):
        if property_data.get("name") == name:
            return property_data.get("value")
    raise RuntimeError(f"Property was not returned: {name}")


def _theme_item(result: dict, group: str, theme_type: str, name: str) -> dict | None:
    theme = result.get("theme") or {}
    for item in theme.get("items", {}).get(group, []):
        if item.get("theme_type") == theme_type and item.get("name") == name:
            return item
    return None


def _is_close(actual: object, expected: float) -> bool:
    return isinstance(actual, (int, float)) and abs(float(actual) - expected) < 1e-6


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

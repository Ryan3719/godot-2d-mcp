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
        if hierarchy.get("total") != 4:
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

        final_hierarchy = await app.service.scene_get_hierarchy(limit=20)
        if final_hierarchy.get("total") != 5 or _has_node(final_hierarchy, marker_path):
            raise RuntimeError("Unexpected final hierarchy after write operations")
        saved = await app.service.scene_save(scene_file=scene_file)
        if not saved.get("saved"):
            raise RuntimeError("Scene save did not report success")

        saved_scene = (project_path / "test_scene.tscn").read_text(encoding="utf-8")
        if "AgentButton" not in saved_scene or "Created by MCP" not in saved_scene:
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

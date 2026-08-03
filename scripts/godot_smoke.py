"""Run a real Godot editor against the Python WebSocket bridge."""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
from pathlib import Path

from godot_2d_mcp.server import create_application


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def run_smoke(godot_binary: str, project_path: Path) -> None:
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

        print(
            "Godot smoke passed: "
            f"session={sessions[0]['session_id']} "
            f"nodes={hierarchy['total']} "
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

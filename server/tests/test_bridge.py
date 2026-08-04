from __future__ import annotations

import asyncio
import json
import socket

import pytest
from websockets.asyncio.client import connect

from godot_2d_mcp.bridge import GodotWebSocketBridge
from godot_2d_mcp.sessions import SessionRegistry


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_command_round_trip_with_fake_godot_plugin() -> None:
    port = free_port()
    registry = SessionRegistry()
    bridge = GodotWebSocketBridge(registry, port=port, command_timeout=1.0)
    await bridge.start()
    try:
        async with connect(f"ws://127.0.0.1:{port}", proxy=None) as websocket:
            await websocket.send(
                json.dumps(
                    {
                        "type": "handshake",
                        "protocol_version": 1,
                        "session_id": "project@a1b2",
                        "plugin_version": "0.1.0",
                        "godot_version": "4.7.stable",
                        "project_name": "project",
                        "project_path": "/tmp/project",
                    }
                )
            )
            ack = json.loads(await websocket.recv())
            assert ack["type"] == "handshake_ack"

            call_task = asyncio.create_task(bridge.call("editor_get_state"))
            command = json.loads(await websocket.recv())
            assert command["command"] == "editor_get_state"
            await websocket.send(
                json.dumps(
                    {
                        "type": "response",
                        "request_id": command["request_id"],
                        "status": "ok",
                        "data": {"readiness": "ready"},
                        "meta": {
                            "session_id": "project@a1b2",
                            "readiness": "ready",
                            "scene_revision": 0,
                        },
                    }
                )
            )

            assert await call_task == {
                "readiness": "ready",
                "meta": {
                    "session_id": "project@a1b2",
                    "readiness": "ready",
                    "scene_revision": 0,
                },
            }
    finally:
        await bridge.stop()

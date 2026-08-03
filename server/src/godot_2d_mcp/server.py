"""FastMCP application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from godot_2d_mcp.bridge import GodotWebSocketBridge
from godot_2d_mcp.service import GodotService
from godot_2d_mcp.sessions import SessionRegistry

INSTRUCTIONS = """Godot 2D editor integration. Inspect editor state before editing.
When multiple sessions are connected, activate the intended session before issuing commands.
This foundation release exposes read-only editor, scene hierarchy, and 2D class discovery tools.
"""

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


@dataclass(slots=True)
class Application:
    mcp: FastMCP
    registry: SessionRegistry
    bridge: GodotWebSocketBridge
    service: GodotService


def create_application(
    ws_host: str = "127.0.0.1",
    ws_port: int = 9500,
    command_timeout: float = 10.0,
) -> Application:
    registry = SessionRegistry()
    bridge = GodotWebSocketBridge(
        registry=registry,
        host=ws_host,
        port=ws_port,
        command_timeout=command_timeout,
    )
    service = GodotService(registry, bridge)

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        await bridge.start()
        try:
            yield {}
        finally:
            await bridge.stop()

    mcp = FastMCP("Godot 2D MCP", instructions=INSTRUCTIONS, lifespan=lifespan)

    @mcp.tool(annotations=READ_ONLY)
    async def session_list() -> dict[str, Any]:
        """List connected Godot editor sessions and their live state."""
        return await service.session_list()

    @mcp.tool(annotations=READ_ONLY)
    async def session_activate(session_id: str) -> dict[str, Any]:
        """Select the Godot editor session used by calls that omit session_id."""
        return await service.session_activate(session_id)

    @mcp.tool(annotations=READ_ONLY)
    async def editor_get_state(session_id: str | None = None) -> dict[str, Any]:
        """Read project, scene, play, import, and compatibility state from Godot."""
        return await service.editor_get_state(session_id)

    @mcp.tool(annotations=READ_ONLY)
    async def scene_get_hierarchy(
        session_id: str | None = None,
        root_path: str = "",
        max_depth: int = 8,
        offset: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Read a paginated preorder snapshot of the edited scene hierarchy."""
        return await service.scene_get_hierarchy(
            session_id=session_id,
            root_path=root_path,
            max_depth=max_depth,
            offset=offset,
            limit=limit,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def class_search(
        query: str = "",
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Search Godot classes allowed by the server's 2D node policy."""
        return await service.class_search(
            query=query,
            session_id=session_id,
            offset=offset,
            limit=limit,
        )

    return Application(mcp=mcp, registry=registry, bridge=bridge, service=service)

"""Application service exposed through MCP tools."""

from __future__ import annotations

from typing import Any, Protocol

from godot_2d_mcp.sessions import SessionRegistry


class CommandBridge(Protocol):
    async def call(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]: ...


class GodotService:
    """Small typed boundary between MCP tools and Godot RPC commands."""

    def __init__(self, registry: SessionRegistry, bridge: CommandBridge) -> None:
        self.registry = registry
        self.bridge = bridge

    async def session_list(self) -> dict[str, Any]:
        sessions = await self.registry.list_sessions()
        return {"sessions": sessions, "count": len(sessions)}

    async def session_activate(self, session_id: str) -> dict[str, Any]:
        session = await self.registry.activate(session_id)
        return {
            "session_id": session.session_id,
            "project_name": session.project_name,
            "project_path": session.project_path,
        }

    async def editor_get_state(self, session_id: str | None = None) -> dict[str, Any]:
        return await self.bridge.call("editor_get_state", session_id=session_id)

    async def scene_get_hierarchy(
        self,
        session_id: str | None = None,
        root_path: str = "",
        max_depth: int = 8,
        offset: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        if not 0 <= max_depth <= 64:
            raise ValueError("max_depth must be between 0 and 64")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        return await self.bridge.call(
            "scene_get_hierarchy",
            {
                "root_path": root_path,
                "max_depth": max_depth,
                "offset": offset,
                "limit": limit,
            },
            session_id=session_id,
        )

    async def class_search(
        self,
        query: str = "",
        session_id: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        return await self.bridge.call(
            "class_search",
            {"query": query, "offset": offset, "limit": limit},
            session_id=session_id,
        )

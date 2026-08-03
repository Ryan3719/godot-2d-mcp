from __future__ import annotations

import pytest

from godot_2d_mcp.protocol import HandshakeMessage
from godot_2d_mcp.sessions import (
    DuplicateSession,
    SessionNotFound,
    SessionRegistry,
)


def handshake(session_id: str) -> HandshakeMessage:
    return HandshakeMessage(
        session_id=session_id,
        plugin_version="0.1.0",
        godot_version="4.7.stable",
        project_name=session_id,
        project_path=f"/tmp/{session_id}",
    )


@pytest.mark.asyncio
async def test_single_session_is_resolved_automatically() -> None:
    registry = SessionRegistry()
    websocket = object()
    expected = await registry.register(handshake("project@a1b2"), websocket)

    assert await registry.resolve() is expected


@pytest.mark.asyncio
async def test_duplicate_live_session_is_rejected() -> None:
    registry = SessionRegistry()
    await registry.register(handshake("project@a1b2"), object())

    with pytest.raises(DuplicateSession):
        await registry.register(handshake("project@a1b2"), object())


@pytest.mark.asyncio
async def test_unregister_does_not_remove_replacement_connection() -> None:
    registry = SessionRegistry()
    first_socket = object()
    await registry.register(handshake("project@a1b2"), first_socket)
    await registry.unregister("project@a1b2", first_socket)
    second = await registry.register(handshake("project@a1b2"), object())

    await registry.unregister("project@a1b2", first_socket)

    assert await registry.resolve() is second


@pytest.mark.asyncio
async def test_empty_registry_reports_actionable_error() -> None:
    registry = SessionRegistry()

    with pytest.raises(SessionNotFound, match="No Godot editor"):
        await registry.resolve()

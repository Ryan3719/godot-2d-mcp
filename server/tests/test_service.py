from __future__ import annotations

from typing import Any

import pytest

from godot_2d_mcp.service import GodotService
from godot_2d_mcp.sessions import SessionRegistry


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], str | None]] = []

    async def call(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((command, params or {}, session_id))
        return {"command": command}


@pytest.mark.asyncio
async def test_hierarchy_params_are_forwarded() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    result = await service.scene_get_hierarchy(
        session_id="project@a1b2",
        root_path="/Main/UI",
        max_depth=3,
        offset=5,
        limit=20,
    )

    assert result == {"command": "scene_get_hierarchy"}
    assert bridge.calls == [
        (
            "scene_get_hierarchy",
            {"root_path": "/Main/UI", "max_depth": 3, "offset": 5, "limit": 20},
            "project@a1b2",
        )
    ]


@pytest.mark.asyncio
async def test_hierarchy_rejects_unbounded_page() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="limit"):
        await service.scene_get_hierarchy(limit=1001)

from __future__ import annotations

import pytest

from godot_2d_mcp.server import create_application


@pytest.mark.asyncio
async def test_foundation_tool_catalog_is_small_and_read_only() -> None:
    app = create_application(ws_port=19999)

    tools = await app.mcp.list_tools()

    assert [tool.name for tool in tools] == [
        "session_list",
        "session_activate",
        "editor_get_state",
        "scene_get_hierarchy",
        "class_search",
    ]
    assert all(tool.annotations is not None for tool in tools)
    assert all(tool.annotations.readOnlyHint for tool in tools if tool.annotations is not None)

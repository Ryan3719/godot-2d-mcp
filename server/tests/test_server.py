from __future__ import annotations

import pytest

from godot_2d_mcp.server import create_application


@pytest.mark.asyncio
async def test_tool_catalog_exposes_read_and_write_annotations() -> None:
    app = create_application(ws_port=19999)

    tools = await app.mcp.list_tools()

    assert [tool.name for tool in tools] == [
        "session_list",
        "session_activate",
        "editor_get_state",
        "scene_get_hierarchy",
        "class_search",
        "node_get_properties",
        "node_create",
        "node_set_properties",
        "node_delete",
        "scene_save",
        "scene_undo",
        "scene_redo",
    ]
    assert all(tool.annotations is not None for tool in tools)
    annotations = {tool.name: tool.annotations for tool in tools}
    assert annotations["node_get_properties"].readOnlyHint is True
    assert annotations["node_create"].readOnlyHint is False
    assert annotations["node_delete"].destructiveHint is True
    assert annotations["scene_save"].idempotentHint is True

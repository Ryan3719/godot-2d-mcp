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
        "node_get_signals",
        "animation_list",
        "animation_get",
        "node_create",
        "node_set_properties",
        "node_delete",
        "node_rename",
        "node_duplicate",
        "node_reparent",
        "node_move",
        "signal_connect",
        "signal_disconnect",
        "animation_create",
        "animation_delete",
        "animation_track_upsert",
        "animation_track_delete",
        "animation_key_upsert",
        "animation_key_delete",
        "scene_save",
        "scene_undo",
        "scene_redo",
    ]
    assert all(tool.annotations is not None for tool in tools)
    annotations = {tool.name: tool.annotations for tool in tools}
    assert annotations["node_get_properties"].readOnlyHint is True
    assert annotations["node_get_signals"].readOnlyHint is True
    assert annotations["animation_list"].readOnlyHint is True
    assert annotations["animation_get"].readOnlyHint is True
    assert annotations["node_create"].readOnlyHint is False
    assert annotations["node_delete"].destructiveHint is True
    assert annotations["node_rename"].destructiveHint is False
    assert annotations["node_duplicate"].readOnlyHint is False
    assert annotations["node_reparent"].readOnlyHint is False
    assert annotations["node_move"].readOnlyHint is False
    assert annotations["signal_connect"].readOnlyHint is False
    assert annotations["signal_disconnect"].readOnlyHint is False
    assert annotations["animation_create"].readOnlyHint is False
    assert annotations["animation_delete"].destructiveHint is True
    assert annotations["animation_track_upsert"].readOnlyHint is False
    assert annotations["animation_track_delete"].destructiveHint is True
    assert annotations["animation_key_upsert"].readOnlyHint is False
    assert annotations["animation_key_delete"].destructiveHint is True
    assert annotations["scene_save"].idempotentHint is True

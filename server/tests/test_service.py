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


@pytest.mark.asyncio
async def test_node_create_forwards_scene_guard_and_session() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    result = await service.node_create(
        type_name="Button",
        name="ConfirmButton",
        parent_path="/Main/UI",
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )

    assert result == {"command": "node_create"}
    assert bridge.calls == [
        (
            "node_create",
            {
                "type": "Button",
                "name": "ConfirmButton",
                "parent_path": "/Main/UI",
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        )
    ]


@pytest.mark.asyncio
async def test_node_set_properties_forwards_one_atomic_payload() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)
    properties = {"text": "Start", "position": {"x": 24, "y": 48}}

    await service.node_set_properties(
        path="/Main/UI/StartButton",
        properties=properties,
    )

    assert bridge.calls == [
        (
            "node_set_properties",
            {"path": "/Main/UI/StartButton", "properties": properties},
            None,
        )
    ]


@pytest.mark.asyncio
async def test_node_set_properties_rejects_empty_or_unbounded_updates() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="non-empty"):
        await service.node_set_properties("/Main", {})
    with pytest.raises(ValueError, match="at most 64"):
        await service.node_set_properties(
            "/Main",
            {f"property_{index}": index for index in range(65)},
        )


@pytest.mark.asyncio
async def test_scene_commands_forward_to_godot() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    await service.scene_undo(scene_file="res://main.tscn")
    await service.scene_redo(scene_file="res://main.tscn")
    await service.scene_save(scene_file="res://main.tscn")

    assert bridge.calls == [
        ("scene_undo", {"scene_file": "res://main.tscn"}, None),
        ("scene_redo", {"scene_file": "res://main.tscn"}, None),
        ("scene_save", {"scene_file": "res://main.tscn"}, None),
    ]


@pytest.mark.asyncio
async def test_node_structure_tools_forward_scene_guard_and_options() -> None:
    bridge = FakeBridge()
    service = GodotService(SessionRegistry(), bridge)

    await service.node_rename(
        path="/Main/UI/StartButton",
        name="PlayButton",
        scene_file="res://main.tscn",
        session_id="project@a1b2",
    )
    await service.node_duplicate(
        path="/Main/UI/PlayButton",
        name="PlayButtonCopy",
        scene_file="res://main.tscn",
    )
    await service.node_reparent(
        path="/Main/UI/PlayButton",
        new_parent_path="/Main",
        index=1,
        keep_global_transform=False,
        scene_file="res://main.tscn",
    )
    await service.node_move(
        path="/Main/PlayButton",
        index=0,
        scene_file="res://main.tscn",
    )

    assert bridge.calls == [
        (
            "node_rename",
            {
                "path": "/Main/UI/StartButton",
                "name": "PlayButton",
                "scene_file": "res://main.tscn",
            },
            "project@a1b2",
        ),
        (
            "node_duplicate",
            {
                "path": "/Main/UI/PlayButton",
                "name": "PlayButtonCopy",
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "node_reparent",
            {
                "path": "/Main/UI/PlayButton",
                "new_parent_path": "/Main",
                "index": 1,
                "keep_global_transform": False,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
        (
            "node_move",
            {
                "path": "/Main/PlayButton",
                "index": 0,
                "scene_file": "res://main.tscn",
            },
            None,
        ),
    ]


@pytest.mark.asyncio
async def test_node_structure_tools_validate_names_and_indexes() -> None:
    service = GodotService(SessionRegistry(), FakeBridge())

    with pytest.raises(ValueError, match="name"):
        await service.node_rename("/Main/UI/StartButton", "")
    with pytest.raises(ValueError, match="index"):
        await service.node_reparent("/Main/UI/StartButton", "/Main", index=-1)
    with pytest.raises(ValueError, match="index"):
        await service.node_move("/Main/UI/StartButton", index=-1)
    with pytest.raises(ValueError, match="keep_global_transform"):
        await service.node_reparent("/Main/UI/StartButton", "/Main", keep_global_transform=1)  # type: ignore[arg-type]

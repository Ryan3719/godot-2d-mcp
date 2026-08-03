"""Validated messages exchanged between the MCP server and Godot plugin."""

from __future__ import annotations

import math
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

PROTOCOL_VERSION = 1


def find_non_finite_float(value: Any, path: str = "params") -> str | None:
    """Return the path of the first NaN or infinity in a JSON-like value."""
    if isinstance(value, float) and not math.isfinite(value):
        return path
    if isinstance(value, dict):
        for key, item in value.items():
            found = find_non_finite_float(item, f"{path}.{key}")
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = find_non_finite_float(item, f"{path}[{index}]")
            if found is not None:
                return found
    return None


class RpcError(BaseModel):
    """Stable error payload returned by the Godot plugin."""

    code: str
    message: str
    retryable: bool = False
    hint: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class ResponseMeta(BaseModel):
    """Live editor metadata stamped on each response."""

    session_id: str = ""
    readiness: str = "ready"
    scene_revision: int = 0


class HandshakeMessage(BaseModel):
    """First message sent by a Godot editor connection."""

    type: Literal["handshake"] = "handshake"
    protocol_version: int = PROTOCOL_VERSION
    session_id: str = Field(pattern=r"^[A-Za-z0-9._@-]{1,128}$")
    plugin_version: str = Field(max_length=64)
    godot_version: str = Field(max_length=128)
    project_name: str = Field(max_length=256)
    project_path: str = Field(max_length=4096)
    editor_pid: int = Field(default=0, ge=0)
    readiness: str = "ready"
    current_scene: str = ""
    play_state: str = "stopped"


class HandshakeAck(BaseModel):
    """Handshake acknowledgement sent by the Python server."""

    type: Literal["handshake_ack"] = "handshake_ack"
    protocol_version: int = PROTOCOL_VERSION
    server_version: str


class CommandRequest(BaseModel):
    """Command sent to one Godot editor instance."""

    type: Literal["command"] = "command"
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    command: str = Field(min_length=1, max_length=128)
    params: dict[str, Any] = Field(default_factory=dict)


class CommandResponse(BaseModel):
    """Command result returned by the Godot plugin."""

    type: Literal["response"] = "response"
    request_id: str
    status: Literal["ok", "error"]
    data: dict[str, Any] = Field(default_factory=dict)
    error: RpcError | None = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)


class StateEvent(BaseModel):
    """Editor state update emitted independently of command responses."""

    type: Literal["state_changed"] = "state_changed"
    readiness: str
    current_scene: str = ""
    play_state: str = "stopped"
    scene_revision: int = Field(default=0, ge=0)

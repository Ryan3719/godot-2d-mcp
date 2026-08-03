"""Concurrency-safe registry for connected Godot editor sessions."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from godot_2d_mcp.protocol import HandshakeMessage, StateEvent


class SessionError(RuntimeError):
    """Base error for session selection and lifecycle failures."""


class SessionNotFound(SessionError):
    pass


class SessionSelectionRequired(SessionError):
    pass


class DuplicateSession(SessionError):
    pass


@dataclass(slots=True)
class Session:
    """One live Godot editor connection."""

    session_id: str
    websocket: Any
    plugin_version: str
    godot_version: str
    project_name: str
    project_path: str
    editor_pid: int
    readiness: str
    current_scene: str
    play_state: str
    scene_revision: int = 0
    connected_at: float = 0.0
    last_seen: float = 0.0

    @classmethod
    def from_handshake(cls, handshake: HandshakeMessage, websocket: Any) -> Session:
        now = time.monotonic()
        return cls(
            session_id=handshake.session_id,
            websocket=websocket,
            plugin_version=handshake.plugin_version,
            godot_version=handshake.godot_version,
            project_name=handshake.project_name,
            project_path=handshake.project_path,
            editor_pid=handshake.editor_pid,
            readiness=handshake.readiness,
            current_scene=handshake.current_scene,
            play_state=handshake.play_state,
            connected_at=now,
            last_seen=now,
        )

    def apply_state(self, event: StateEvent) -> None:
        self.readiness = event.readiness
        self.current_scene = event.current_scene
        self.play_state = event.play_state
        self.scene_revision = event.scene_revision
        self.last_seen = time.monotonic()

    def to_public_dict(self, active: bool) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "active": active,
            "project_name": self.project_name,
            "project_path": self.project_path,
            "godot_version": self.godot_version,
            "plugin_version": self.plugin_version,
            "editor_pid": self.editor_pid,
            "readiness": self.readiness,
            "current_scene": self.current_scene,
            "play_state": self.play_state,
            "scene_revision": self.scene_revision,
        }


class SessionRegistry:
    """Tracks sessions and resolves the target for each MCP call."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._active_session_id: str | None = None
        self._lock = asyncio.Lock()

    async def register(self, handshake: HandshakeMessage, websocket: Any) -> Session:
        async with self._lock:
            if handshake.session_id in self._sessions:
                raise DuplicateSession(f"Session already connected: {handshake.session_id}")
            session = Session.from_handshake(handshake, websocket)
            self._sessions[session.session_id] = session
            if len(self._sessions) == 1:
                self._active_session_id = session.session_id
            return session

    async def unregister(self, session_id: str, websocket: Any) -> None:
        async with self._lock:
            current = self._sessions.get(session_id)
            if current is None or current.websocket is not websocket:
                return
            del self._sessions[session_id]
            if self._active_session_id == session_id:
                self._active_session_id = None
                if len(self._sessions) == 1:
                    self._active_session_id = next(iter(self._sessions))

    async def list_sessions(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [
                session.to_public_dict(session.session_id == self._active_session_id)
                for session in sorted(self._sessions.values(), key=lambda item: item.session_id)
            ]

    async def activate(self, session_id: str) -> Session:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionNotFound(f"Unknown Godot session: {session_id}")
            self._active_session_id = session_id
            return session

    async def resolve(self, session_id: str | None = None) -> Session:
        async with self._lock:
            if session_id:
                session = self._sessions.get(session_id)
                if session is None:
                    raise SessionNotFound(f"Unknown Godot session: {session_id}")
                return session
            if self._active_session_id is not None:
                session = self._sessions.get(self._active_session_id)
                if session is not None:
                    return session
            if not self._sessions:
                raise SessionNotFound("No Godot editor is connected")
            if len(self._sessions) > 1:
                raise SessionSelectionRequired(
                    "Multiple Godot editors are connected; call session_activate first"
                )
            return next(iter(self._sessions.values()))

    async def update_state(self, session_id: str, event: StateEvent) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.apply_state(event)

    async def touch(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.last_seen = time.monotonic()

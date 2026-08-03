"""Loopback WebSocket bridge used by the Godot editor plugin."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import ValidationError
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from godot_2d_mcp import __version__
from godot_2d_mcp.protocol import (
    PROTOCOL_VERSION,
    CommandRequest,
    CommandResponse,
    HandshakeAck,
    HandshakeMessage,
    StateEvent,
    find_non_finite_float,
)
from godot_2d_mcp.sessions import DuplicateSession, SessionRegistry

logger = logging.getLogger(__name__)


class GodotCommandError(RuntimeError):
    """Structured failure returned by a Godot command handler."""

    def __init__(self, response: CommandResponse) -> None:
        error = response.error
        self.code = error.code if error is not None else "UNKNOWN_ERROR"
        self.retryable = error.retryable if error is not None else False
        self.hint = error.hint if error is not None else ""
        message = error.message if error is not None else "Godot command failed"
        super().__init__(f"{self.code}: {message}")


class GodotWebSocketBridge:
    """Accepts editor sessions and correlates commands with responses."""

    def __init__(
        self,
        registry: SessionRegistry,
        host: str = "127.0.0.1",
        port: int = 9500,
        command_timeout: float = 10.0,
    ) -> None:
        self.registry = registry
        self.host = host
        self.port = port
        self.command_timeout = command_timeout
        self._server: Server | None = None
        self._pending: dict[str, tuple[str, asyncio.Future[CommandResponse]]] = {}

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await serve(
            self._handle_connection,
            self.host,
            self.port,
            max_size=2 * 1024 * 1024,
            max_queue=32,
            ping_interval=20,
            ping_timeout=20,
        )

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None
        for _, future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError("Godot WebSocket bridge stopped"))
        self._pending.clear()

    async def call(
        self,
        command: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        command_params = params or {}
        invalid_path = find_non_finite_float(command_params)
        if invalid_path is not None:
            raise ValueError(f"Non-finite float at {invalid_path}")

        session = await self.registry.resolve(session_id)
        request = CommandRequest(command=command, params=command_params)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[CommandResponse] = loop.create_future()
        self._pending[request.request_id] = (session.session_id, future)
        try:
            await session.websocket.send(request.model_dump_json())
            response = await asyncio.wait_for(future, timeout=self.command_timeout)
        finally:
            self._pending.pop(request.request_id, None)

        if response.status == "error":
            raise GodotCommandError(response)
        return response.data

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        session_id = ""
        try:
            raw_handshake = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            if not isinstance(raw_handshake, str):
                await websocket.close(1003, "Text messages required")
                return
            handshake = HandshakeMessage.model_validate_json(raw_handshake)
            if handshake.protocol_version != PROTOCOL_VERSION:
                await websocket.close(4002, "Unsupported protocol version")
                return
            session = await self.registry.register(handshake, websocket)
            session_id = session.session_id
            await websocket.send(HandshakeAck(server_version=__version__).model_dump_json())

            async for raw_message in websocket:
                if not isinstance(raw_message, str):
                    continue
                await self._handle_message(session_id, raw_message)
        except DuplicateSession as exc:
            await websocket.close(4001, str(exc))
        except (ValidationError, json.JSONDecodeError) as exc:
            logger.warning("Rejected malformed Godot WebSocket message: %s", exc)
            await websocket.close(1007, "Malformed protocol message")
        except TimeoutError:
            await websocket.close(1008, "Handshake timeout")
        except ConnectionClosed:
            logger.debug("Godot WebSocket connection closed: %s", session_id or "pre-handshake")
        except Exception:
            logger.exception("Godot WebSocket connection failed")
        finally:
            if session_id:
                await self.registry.unregister(session_id, websocket)
                self._fail_pending_for_session(session_id)

    async def _handle_message(self, session_id: str, raw_message: str) -> None:
        payload = json.loads(raw_message)
        message_type = payload.get("type")
        if message_type == "response":
            response = CommandResponse.model_validate(payload)
            pending = self._pending.get(response.request_id)
            if pending is None or pending[0] != session_id:
                return
            future = pending[1]
            if not future.done():
                future.set_result(response)
            await self.registry.touch(session_id)
            return
        if message_type == "state_changed":
            await self.registry.update_state(session_id, StateEvent.model_validate(payload))
            return
        logger.debug("Ignored unknown Godot message type: %s", message_type)

    def _fail_pending_for_session(self, session_id: str) -> None:
        for pending_session_id, future in self._pending.values():
            if pending_session_id == session_id and not future.done():
                future.set_exception(ConnectionError(f"Godot session disconnected: {session_id}"))

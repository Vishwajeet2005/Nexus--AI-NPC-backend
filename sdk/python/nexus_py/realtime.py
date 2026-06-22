"""
nexus_py.realtime
─────────────────────
RealtimeClient — WebSocket event subscription with an event-emitter API.

Usage:
    nexus.realtime.on("npc_state_changed", my_async_handler)
    await nexus.realtime.connect(session_id)
    ...
    await nexus.realtime.disconnect()

Handlers are async callables: `async def handler(event: dict) -> None`.
Register a handler for `"*"` to receive every event regardless of type.

Connection lifecycle (mirrors the server's documented WS protocol):
    1. Open WebSocket to `{ws_url}/realtime/{session_id}`
    2. Immediately send `{"type": "auth", "token": "<access_token>"}`
    3. Server responds `{"type": "connected", ...}` on success, or closes
       with code 4001 (auth failure) / 4002 (session not found/ended)
    4. Server sends `{"type": "ping"}` every 15s — SDK auto-replies "pong"
    5. All session/NPC events arrive as JSON frames and are dispatched to
       registered handlers by their `type` (or `event` for relayed pub/sub
       frames — see `_normalise_event`)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import websockets
from websockets.exceptions import ConnectionClosed

if TYPE_CHECKING:
    from nexus_py.client import NexusClient

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]

# Server sends a ping every 15s; reply promptly so the connection survives.
_HEARTBEAT_INTERVAL_SECONDS: float = 15.0


def _normalise_event(message: dict[str, Any]) -> dict[str, Any]:
    """
    Normalise the two wire shapes the server can send into one consistent
    dict with a `type` key, so handlers never need to branch on shape.

    WS-native frames already have `type`: {"type": "connected", ...},
    {"type": "ping"}, {"type": "npc_state_changed", "payload": {...}}.

    Pub/sub-relayed frames (session/player events forwarded from Redis)
    use `event` instead of `type`: {"event": "player.joined", "data": {...}}.
    These are remapped to {"type": "player.joined", "payload": {...}, ...}.
    """
    if "type" in message:
        return message
    if "event" in message:
        normalised = dict(message)
        normalised["type"] = normalised.pop("event")
        if "data" in normalised and "payload" not in normalised:
            normalised["payload"] = normalised.pop("data")
        return normalised
    return message


class RealtimeClient:
    """
    WebSocket event subscription client with an event-emitter pattern.

    Not typically instantiated directly — accessed via `nexus.realtime`
    on a `NexusClient`, which wires it to the client's access token and
    WebSocket base URL automatically.
    """

    def __init__(self, client: "NexusClient") -> None:
        self._c = client
        self._handlers: dict[str, list[EventHandler]] = {}
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._running = False
        self._listen_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

    def on(self, event_type: str, handler: EventHandler) -> None:
        """
        Register an async handler for a specific event type.

        Args:
            event_type: The event's `type` field to match, e.g.
                       "npc_state_changed", "player.joined", "connected".
                       Pass "*" to receive every event regardless of type.
            handler:    An async callable: `async def handler(event: dict) -> None`.

        Multiple handlers can be registered for the same event_type — all
        are called, in registration order, when a matching event arrives.
        """
        self._handlers.setdefault(event_type, []).append(handler)

    def off(self, event_type: str, handler: EventHandler | None = None) -> None:
        """
        Remove a previously registered handler.

        If `handler` is None, removes ALL handlers for `event_type`.
        """
        if event_type not in self._handlers:
            return
        if handler is None:
            self._handlers[event_type] = []
        else:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h is not handler
            ]

    async def connect(self, session_id: str) -> None:
        """
        Connect to the session's WebSocket channel and start listening.

        Performs the auth handshake automatically using the access token
        currently stored on the parent `NexusClient` (set by a prior
        `login()`, `guest()`, or `refresh()` call). Starts two background
        tasks: one to listen for and dispatch incoming events, and one to
        reply to server heartbeat pings.

        Raises:
            nexus_py.exceptions.AuthError: if no access token is set.
        """
        if self._c._access_token is None:
            from nexus_py.exceptions import AuthError
            raise AuthError(
                "Cannot connect to realtime channel without an access token. "
                "Call login() or guest() first."
            )

        ws_url = f"{self._c.ws_url}/realtime/{session_id}"
        self._ws = await websockets.connect(ws_url)
        self._running = True

        # Step 2 of the protocol: send the auth frame immediately.
        await self._ws.send(json.dumps({
            "type": "auth",
            "token": self._c._access_token,
        }))

        self._listen_task = asyncio.create_task(self._listen())
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

        logger.debug("realtime.connected", extra={"session_id": session_id})

    async def _listen(self) -> None:
        """
        Background task: read frames from the WebSocket and dispatch to
        registered handlers. Automatically replies to server pings.

        Exits cleanly when the connection closes (server disconnect,
        network error, or explicit `disconnect()` call).
        """
        if self._ws is None:
            return

        try:
            async for raw in self._ws:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("realtime.invalid_json", extra={"raw": str(raw)[:200]})
                    continue

                event = _normalise_event(message)
                event_type = event.get("type", "")

                # Auto-reply to server heartbeat pings — keeps the connection
                # alive without requiring the consumer to handle "ping" themselves.
                if event_type == "ping":
                    await self._send_pong()

                handlers = (
                    self._handlers.get(event_type, [])
                    + self._handlers.get("*", [])
                )
                for handler in handlers:
                    try:
                        await handler(event)
                    except Exception as exc:
                        logger.error(
                            "realtime.handler_error",
                            extra={"event_type": event_type, "error": str(exc)},
                            exc_info=exc,
                        )
        except ConnectionClosed:
            logger.debug("realtime.connection_closed")
        finally:
            self._running = False

    async def _heartbeat(self) -> None:
        """
        Background task: send a periodic pong every 15s as a keepalive.

        The server's own ping triggers an immediate pong reply in `_listen`;
        this loop is a belt-and-suspenders safety net in case a ping frame
        is ever missed, matching the spec's reference implementation.
        """
        try:
            while self._running:
                await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
                if self._running:
                    await self._send_pong()
        except asyncio.CancelledError:
            pass

    async def _send_pong(self) -> None:
        """Send a pong frame if the connection is open. Swallows send errors."""
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"type": "pong"}))
        except ConnectionClosed:
            pass

    async def disconnect(self) -> None:
        """
        Close the WebSocket connection and stop all background tasks.

        Safe to call even if not currently connected (no-op in that case).
        Always called automatically by `NexusClient.close()` /
        `async with NexusClient(...) as nexus:` exit.
        """
        self._running = False

        for task in (self._listen_task, self._heartbeat_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        self._listen_task = None
        self._heartbeat_task = None

    @property
    def is_connected(self) -> bool:
        """True if the WebSocket connection is currently open."""
        return self._ws is not None and self._running

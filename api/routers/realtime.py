"""
api/routers/realtime.py
────────────────────────
WebSocket endpoint for real-time session events.

Connection lifecycle (per spec)
───────────────────────────────
1. Client connects to `wss://<host>/v1/realtime/{session_id}`
2. Client immediately sends: `{ "type": "auth", "token": "<access_token>" }`
3. Server validates the JWT. On failure: close with code 4001 and return.
4. Server sends:            `{ "type": "connected", "session_id": "...", "player_id": "..." }`
5. Server subscribes to Redis channel `session:{session_id}`
6. Two concurrent tasks run:
     a. Redis listener  — reads from the pub/sub channel, forwards to WS client
     b. WS receiver     — reads from the WS client, handles pong / unknown frames

Heartbeat (per spec)
────────────────────
- Server sends `{ "type": "ping" }` every PING_INTERVAL_SECONDS (15s).
- Client must respond with `{ "type": "pong" }` within PONG_TIMEOUT_SECONDS (30s).
- Missing pong → close with code 1001 (Going Away), log the disconnect.

Reconnect replay (per spec)
───────────────────────────
- On fresh connection, server checks if the player reconnected within
  RECONNECT_WINDOW_SECONDS (30s) of their last disconnect by looking for
  a Redis key `ws_disconnect:{session_id}:{player_id}`.
- If a reconnect is detected, the server replays the last 50 messages
  from the Redis stream `ws_stream:{session_id}` before starting live relay.
- Every event published to the session channel is also XADD'd to the stream
  with MAXLEN=50 (approximate, for efficiency).

Error codes
───────────
4001 — Authentication failed (bad/expired/missing token)
4002 — Session not found or already ended
1001 — Server-side disconnect (pong timeout, shutdown, etc.)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from api.dependencies import _decode_token, get_db, get_redis, init_db, init_redis
from api.models.player import Player
from api.models.session import Session
from api.services.realtime_service import subscribe_to_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/realtime", tags=["Real-time"])

# ── Timing constants ───────────────────────────────────────────────────────────
PING_INTERVAL_SECONDS: int = 15
PONG_TIMEOUT_SECONDS: int = 30
RECONNECT_WINDOW_SECONDS: int = 30
STREAM_MAX_LEN: int = 50
AUTH_TIMEOUT_SECONDS: int = 10  # how long to wait for the initial auth frame

# ── Redis key helpers ──────────────────────────────────────────────────────────

def _disconnect_key(session_id: UUID, player_id: UUID) -> str:
    return f"ws_disconnect:{session_id}:{player_id}"


def _stream_key(session_id: UUID) -> str:
    return f"ws_stream:{session_id}"


# ── Internal helpers ───────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(event_type: str, payload: dict[str, Any]) -> str:
    """Wrap an event in the spec's server-to-client envelope."""
    return json.dumps(
        {"type": event_type, "payload": payload, "timestamp": _now_iso()},
        separators=(",", ":"),
    )


async def _send_json(ws: WebSocket, data: dict[str, Any]) -> None:
    """Send a dict as a compact JSON text frame. Ignores disconnect errors."""
    try:
        await ws.send_text(json.dumps(data, separators=(",", ":")))
    except Exception:
        pass  # Connection may already be closing


async def _recv_json_with_timeout(
    ws: WebSocket, timeout: float
) -> dict[str, Any] | None:
    """
    Wait up to `timeout` seconds for a JSON text frame from the client.
    Returns None on timeout, disconnect, or parse failure.
    """
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=timeout)
        return json.loads(raw)
    except (asyncio.TimeoutError, WebSocketDisconnect, json.JSONDecodeError):
        return None


async def _authenticate(
    ws: WebSocket,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> Player | None:
    """
    Wait for the initial `{ "type": "auth", "token": "..." }` frame.

    Returns the authenticated Player on success, or None after sending
    close code 4001 on any failure.
    """
    frame = await _recv_json_with_timeout(ws, timeout=AUTH_TIMEOUT_SECONDS)

    if frame is None or frame.get("type") != "auth" or not frame.get("token"):
        await ws.close(code=4001, reason="Authentication frame missing or malformed.")
        return None

    # Validate the JWT
    try:
        payload = _decode_token(frame["token"], expected_type="access")
    except Exception:
        await ws.close(code=4001, reason="Invalid or expired access token.")
        return None

    # JTI blacklist check
    blacklisted = await redis.exists(f"blacklist:{payload.jti}")
    if blacklisted:
        await ws.close(code=4001, reason="Token has been revoked.")
        return None

    # Load player
    result = await db.execute(
        select(Player).where(Player.id == payload.player_id)
    )
    player: Player | None = result.scalar_one_or_none()

    if player is None or player.is_locked:
        await ws.close(code=4001, reason="Player not found or account locked.")
        return None

    return player


async def _check_session(
    session_id: UUID,
    ws: WebSocket,
    db: AsyncSession,
) -> Session | None:
    """
    Verify the session exists and has not ended.
    Sends close code 4002 and returns None on failure.
    """
    result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    session: Session | None = result.scalar_one_or_none()

    if session is None:
        await ws.close(code=4002, reason="Session not found.")
        return None

    if session.status == "ended":
        await ws.close(code=4002, reason="Session has ended.")
        return None

    return session


async def _replay_recent_messages(
    ws: WebSocket,
    redis: aioredis.Redis,
    session_id: UUID,
) -> None:
    """
    Replay up to the last 50 messages from the Redis stream for this session.
    Used on reconnect (when the disconnect key exists in Redis).
    """
    stream_key = _stream_key(session_id)
    try:
        # XREVRANGE returns newest first; we reverse to replay in order
        entries = await redis.xrevrange(stream_key, count=STREAM_MAX_LEN)
        if not entries:
            return
        for _entry_id, fields in reversed(entries):
            msg = fields.get(b"data") or fields.get("data")
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8")
            if msg:
                await ws.send_text(msg)
    except Exception as exc:
        logger.warning("realtime.replay_failed", extra={"error": str(exc)})


async def _append_to_stream(
    redis: aioredis.Redis,
    session_id: UUID,
    message: str,
) -> None:
    """
    Append a message to the session's Redis stream with MAXLEN cap.
    Failures are swallowed — stream writes are best-effort.
    """
    try:
        await redis.xadd(
            _stream_key(session_id),
            {"data": message},
            maxlen=STREAM_MAX_LEN,
            approximate=True,
        )
    except Exception as exc:
        logger.warning("realtime.stream_append_failed", extra={"error": str(exc)})


# ── Connection handler tasks ───────────────────────────────────────────────────

async def _redis_to_ws(
    ws: WebSocket,
    pubsub: aioredis.client.PubSub,
    session_id: UUID,
    redis: aioredis.Redis,
    stop_event: asyncio.Event,
) -> None:
    """
    Task: read from Redis pub/sub → forward to WebSocket client.

    Also writes each message to the stream (for reconnect replay).
    Exits when `stop_event` is set or the pub/sub connection drops.
    """
    try:
        async for raw in pubsub.listen():
            if stop_event.is_set():
                break
            if raw["type"] != "message":
                continue

            data = raw.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            if not data:
                continue

            # Write to stream before forwarding (best-effort)
            asyncio.ensure_future(_append_to_stream(redis, session_id, data))

            try:
                await ws.send_text(data)
            except Exception:
                # Client disconnected — signal the sibling task to stop
                stop_event.set()
                break
    except Exception as exc:
        logger.warning("realtime.redis_listener_error", extra={"error": str(exc)})
    finally:
        stop_event.set()


async def _ws_receiver(
    ws: WebSocket,
    player_id: UUID,
    stop_event: asyncio.Event,
    last_pong: list[float],
) -> None:
    """
    Task: read from WebSocket client.

    Handles `pong` frames (updates `last_pong[0]`) and ignores unknown
    message types. Exits on disconnect or when `stop_event` is set.
    """
    import time

    try:
        while not stop_event.is_set():
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break

            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if frame.get("type") == "pong":
                last_pong[0] = time.monotonic()
                logger.debug(
                    "realtime.pong_received",
                    extra={"player_id": str(player_id)},
                )
            else:
                logger.debug(
                    "realtime.unknown_frame",
                    extra={"player_id": str(player_id), "type": frame.get("type")},
                )
    except Exception as exc:
        logger.warning("realtime.ws_receiver_error", extra={"error": str(exc)})
    finally:
        stop_event.set()


async def _heartbeat(
    ws: WebSocket,
    player_id: UUID,
    stop_event: asyncio.Event,
    last_pong: list[float],
) -> None:
    """
    Task: send `{ "type": "ping" }` every PING_INTERVAL_SECONDS.

    If no pong is received within PONG_TIMEOUT_SECONDS of the most recent
    ping, close the connection with code 1001.
    """
    import time

    last_ping_sent: float = time.monotonic()

    try:
        while not stop_event.is_set():
            await asyncio.sleep(PING_INTERVAL_SECONDS)
            if stop_event.is_set():
                break

            await _send_json(ws, {"type": "ping"})
            last_ping_sent = time.monotonic()

            # Check pong deadline: last_pong must be after (last_ping - timeout)
            pong_deadline = last_ping_sent - PONG_TIMEOUT_SECONDS
            if last_pong[0] < pong_deadline:
                logger.warning(
                    "realtime.pong_timeout",
                    extra={"player_id": str(player_id)},
                )
                try:
                    await ws.close(code=1001, reason="Pong timeout.")
                except Exception:
                    pass
                stop_event.set()
                break
    except Exception as exc:
        logger.warning("realtime.heartbeat_error", extra={"error": str(exc)})
    finally:
        stop_event.set()


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

@router.websocket("/{session_id}")
async def websocket_session(
    websocket: WebSocket,
    session_id: UUID,
) -> None:
    """
    WebSocket endpoint for real-time session events.

    Full lifecycle:
    1. Accept the TCP connection.
    2. Wait up to 10 seconds for `{ "type": "auth", "token": "..." }`.
       Close with **4001** on failure.
    3. Verify the session exists and is not ended. Close with **4002** otherwise.
    4. Check for a recent disconnect (reconnect window). If found, replay
       the last 50 messages from the Redis stream.
    5. Send `{ "type": "connected", "session_id": "...", "player_id": "..." }`.
    6. Subscribe to `session:{session_id}` on Redis.
    7. Run three concurrent tasks: redis_to_ws, ws_receiver, heartbeat.
    8. On disconnect: record disconnect timestamp in Redis (TTL = reconnect window),
       unsubscribe from Redis, log.

    Dependencies are resolved manually (not via Depends) because WebSocket
    handlers cannot use FastAPI's full dependency injection system for
    generator-based dependencies — we call the underlying factory functions
    directly via the module-level singletons initialised in main.py.
    """
    import time
    from api.dependencies import _async_session_factory, _redis_pool

    # ── Step 1: Accept connection ──────────────────────────────────────────────
    await websocket.accept()

    # ── Step 2: Acquire dependencies manually ─────────────────────────────────
    if _async_session_factory is None or _redis_pool is None:
        await websocket.close(code=1011, reason="Server not initialised.")
        return

    redis: aioredis.Redis = _redis_pool

    async with _async_session_factory() as db:
        # ── Step 3: Authenticate ───────────────────────────────────────────────
        player = await _authenticate(websocket, db, redis)
        if player is None:
            return  # _authenticate already closed the connection

        # ── Step 4: Verify session ─────────────────────────────────────────────
        session = await _check_session(session_id, websocket, db)
        if session is None:
            return  # _check_session already closed the connection

        player_id = player.id
        logger.info(
            "realtime.connection_established",
            extra={"session_id": str(session_id), "player_id": str(player_id)},
        )

        # ── Step 5: Reconnect replay ───────────────────────────────────────────
        disconnect_key = _disconnect_key(session_id, player_id)
        was_recently_connected = await redis.exists(disconnect_key)
        if was_recently_connected:
            await redis.delete(disconnect_key)
            await _replay_recent_messages(websocket, redis, session_id)
            logger.info(
                "realtime.reconnect_replay_sent",
                extra={"session_id": str(session_id), "player_id": str(player_id)},
            )

        # ── Step 6: Send connected confirmation ───────────────────────────────
        await _send_json(
            websocket,
            {
                "type": "connected",
                "session_id": str(session_id),
                "player_id": str(player_id),
            },
        )

        # ── Step 7: Subscribe to Redis channel ────────────────────────────────
        pubsub = await subscribe_to_session(redis, session_id)

        # Shared stop signal — any task sets this to signal the others to exit
        stop_event = asyncio.Event()

        # last_pong[0] is a mutable float shared between heartbeat and receiver.
        # Initialise to now so the first ping has a full timeout window.
        last_pong: list[float] = [time.monotonic()]

        # ── Step 8: Run concurrent tasks ──────────────────────────────────────
        tasks = [
            asyncio.create_task(
                _redis_to_ws(websocket, pubsub, session_id, redis, stop_event),
                name=f"redis_to_ws:{session_id}:{player_id}",
            ),
            asyncio.create_task(
                _ws_receiver(websocket, player_id, stop_event, last_pong),
                name=f"ws_receiver:{session_id}:{player_id}",
            ),
            asyncio.create_task(
                _heartbeat(websocket, player_id, stop_event, last_pong),
                name=f"heartbeat:{session_id}:{player_id}",
            ),
        ]

        try:
            # Wait until any task completes (which sets stop_event)
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            stop_event.set()

            # Cancel remaining tasks and await them to suppress warnings
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Surface any unexpected exceptions from completed tasks
            for task in done:
                exc = task.exception()
                if exc is not None:
                    logger.error(
                        "realtime.task_exception",
                        extra={
                            "task": task.get_name(),
                            "error": str(exc),
                        },
                        exc_info=exc,
                    )

        except Exception as exc:
            logger.error(
                "realtime.connection_error",
                extra={
                    "session_id": str(session_id),
                    "player_id": str(player_id),
                    "error": str(exc),
                },
                exc_info=exc,
            )
        finally:
            # ── Step 9: Clean up ───────────────────────────────────────────────
            stop_event.set()

            # Record disconnect for reconnect window detection
            try:
                await redis.set(
                    disconnect_key,
                    "1",
                    ex=RECONNECT_WINDOW_SECONDS,
                )
            except Exception:
                pass

            # Unsubscribe from Redis pub/sub
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except Exception:
                pass

            logger.info(
                "realtime.connection_closed",
                extra={"session_id": str(session_id), "player_id": str(player_id)},
            )

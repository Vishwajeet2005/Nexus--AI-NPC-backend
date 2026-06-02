"""
api/services/realtime_service.py
──────────────────────────────────
Redis Pub/Sub layer for real-time session events.

Architecture (as specified):
  - Every event — regardless of origin — is published to a Redis channel.
  - Channel naming : `session:{session_id}`
  - All WebSocket handlers (Stage 5) subscribe to that channel and fan
    messages out to connected clients.
  - Even on a single-instance deployment, events route through Redis so
    the architecture is correct-by-construction for horizontal scale.

Message wire format (JSON):
  {
    "event":      "player.joined",          ← event_type
    "session_id": "uuid-string",
    "data":       { ...event-specific... },
    "ts":         1700000000.123             ← Unix timestamp (float, ms precision)
  }

Public API:
  publish_event(redis, session_id, event_type, data) → None
  subscribe_to_session(redis, session_id)             → PubSub  (caller manages lifecycle)

Supported event types (non-exhaustive — the channel accepts any string):
  session.created         session.ended         session.locked
  session.state_updated   player.joined         player.left
  npc.interaction         analytics.event
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncGenerator
from uuid import UUID

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# ── Channel naming ─────────────────────────────────────────────────────────────

def _session_channel(session_id: UUID | str) -> str:
    """Return the Redis pub/sub channel name for a session."""
    return f"session:{session_id}"


# ── Publish ────────────────────────────────────────────────────────────────────

async def publish_event(
    redis: aioredis.Redis,
    session_id: UUID,
    event_type: str,
    data: dict[str, Any],
) -> int:
    """
    Publish a structured JSON event to the session's Redis channel.

    Returns the number of subscribers that received the message
    (0 means no WebSocket clients are currently listening — not an error).

    Failures are logged as warnings rather than raised — a pub/sub publish
    failure should never cause the HTTP response to fail. The source-of-truth
    write (Postgres) has already committed before this is called.
    """
    channel = _session_channel(session_id)
    message = json.dumps(
        {
            "event": event_type,
            "session_id": str(session_id),
            "data": data,
            "ts": time.time(),
        },
        # Compact encoding — no extra whitespace over the wire
        separators=(",", ":"),
    )

    try:
        receivers: int = await redis.publish(channel, message)
        logger.debug(
            "realtime.published",
            extra={
                "channel": channel,
                "event": event_type,
                "receivers": receivers,
            },
        )
        return receivers
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "realtime.publish_failed",
            extra={"channel": channel, "event": event_type, "error": str(exc)},
        )
        return 0


# ── Subscribe ──────────────────────────────────────────────────────────────────

async def subscribe_to_session(
    redis: aioredis.Redis,
    session_id: UUID,
) -> aioredis.client.PubSub:
    """
    Create and return a PubSub object subscribed to `session:{session_id}`.

    The caller (WebSocket handler) owns the lifecycle of the returned PubSub
    object and MUST close it when the WebSocket disconnects:

        pubsub = await subscribe_to_session(redis, session_id)
        try:
            async for message in listen_to_session(pubsub):
                await websocket.send_text(message)
        finally:
            await pubsub.unsubscribe()
            await pubsub.close()

    We return the raw PubSub rather than an async generator so the caller
    can select on multiple awaitables (e.g. WebSocket receive + Redis messages)
    using `asyncio.wait` or `asyncio.gather`.
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(_session_channel(session_id))
    logger.debug(
        "realtime.subscribed",
        extra={"channel": _session_channel(session_id)},
    )
    return pubsub


async def listen_to_session(
    pubsub: aioredis.client.PubSub,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields raw JSON strings from a subscribed PubSub.

    Filters out Redis subscription-confirmation messages (type != 'message')
    so the caller only receives actual event payloads.

    Usage (inside a WebSocket handler):
        async for payload in listen_to_session(pubsub):
            await websocket.send_text(payload)
    """
    async for raw in pubsub.listen():
        if raw["type"] != "message":
            # Subscription confirmations and pings — skip
            continue
        data = raw.get("data")
        if isinstance(data, bytes):
            yield data.decode("utf-8")
        elif isinstance(data, str):
            yield data


# ── Convenience broadcast helpers ──────────────────────────────────────────────
# These thin wrappers exist so router code stays readable:
#   await broadcast_player_joined(redis, session_id, player)
# rather than spelling out the dict every time.

async def broadcast_player_joined(
    redis: aioredis.Redis,
    session_id: UUID,
    player_id: UUID,
    username: str,
) -> None:
    await publish_event(
        redis=redis,
        session_id=session_id,
        event_type="player.joined",
        data={"player_id": str(player_id), "username": username},
    )


async def broadcast_player_left(
    redis: aioredis.Redis,
    session_id: UUID,
    player_id: UUID,
    username: str,
) -> None:
    await publish_event(
        redis=redis,
        session_id=session_id,
        event_type="player.left",
        data={"player_id": str(player_id), "username": username},
    )


async def broadcast_session_state_updated(
    redis: aioredis.Redis,
    session_id: UUID,
    updated_by: UUID,
    new_state: dict[str, Any],
) -> None:
    await publish_event(
        redis=redis,
        session_id=session_id,
        event_type="session.state_updated",
        data={"updated_by": str(updated_by), "state": new_state},
    )


async def broadcast_session_ended(
    redis: aioredis.Redis,
    session_id: UUID,
    ended_by: UUID,
) -> None:
    await publish_event(
        redis=redis,
        session_id=session_id,
        event_type="session.ended",
        data={"ended_by": str(ended_by)},
    )


async def broadcast_npc_interaction(
    redis: aioredis.Redis,
    session_id: UUID,
    npc_id: UUID,
    player_id: UUID,
    behaviour: str,
    secret_leaked: str | None,
) -> None:
    await publish_event(
        redis=redis,
        session_id=session_id,
        event_type="npc.interaction",
        data={
            "npc_id": str(npc_id),
            "player_id": str(player_id),
            "behaviour": behaviour,
            "secret_leaked": secret_leaked,
        },
    )

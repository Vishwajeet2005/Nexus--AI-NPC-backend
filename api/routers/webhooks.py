"""
api/routers/webhooks.py
─────────────────────────
Webhook management endpoints for the developer dashboard.

Endpoints:
  GET  /v1/webhooks                   — list webhooks for current user
  POST /v1/webhooks                   — register a new webhook
  POST /v1/webhooks/{webhook_id}/test — send a test delivery

Webhooks are stored in a `_webhooks` list inside the Player's associated
data via a lightweight in-memory registry using Redis keys
`webhooks:{player_id}`. No additional Postgres table is required for
Phase 3; persistence is best-effort (dashboard feature, not game-critical).
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from api.dependencies import get_current_user, get_db, get_redis
from api.models.player import Player

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

_WEBHOOK_KEY = "webhooks:{player_id}"
_WEBHOOK_TTL = 60 * 60 * 24 * 30  # 30 days


def _webhook_key(player_id: str) -> str:
    return _WEBHOOK_KEY.format(player_id=player_id)


# ── Request schemas ────────────────────────────────────────────────────────────

class WebhookCreate(BaseModel):
    url: str
    events: list[str]
    name: str = "My Webhook"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _load_webhooks(player_id: str, redis: aioredis.Redis) -> list[dict]:
    raw = await redis.get(_webhook_key(player_id))
    if not raw:
        return []
    data = raw if isinstance(raw, str) else raw.decode()
    return json.loads(data)


async def _save_webhooks(player_id: str, hooks: list[dict], redis: aioredis.Redis) -> None:
    await redis.set(_webhook_key(player_id), json.dumps(hooks), ex=_WEBHOOK_TTL)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", summary="List registered webhooks")
async def list_webhooks(
    current_user: Player = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> dict:
    hooks = await _load_webhooks(str(current_user.id), redis)
    return {"webhooks": hooks}


@router.post("", status_code=status.HTTP_201_CREATED, summary="Register a webhook")
async def create_webhook(
    payload: WebhookCreate,
    current_user: Player = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> dict:
    hooks = await _load_webhooks(str(current_user.id), redis)
    webhook = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "url": payload.url,
        "events": payload.events,
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_delivery_status": None,
        "delivery_history": [],
    }
    hooks.append(webhook)
    await _save_webhooks(str(current_user.id), hooks, redis)
    return webhook


@router.post("/{webhook_id}/test", summary="Send a test delivery to a webhook")
async def test_webhook(
    webhook_id: str,
    current_user: Player = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    POST a mock `test.ping` payload to the webhook URL and return the
    HTTP status code and response time. Updates the hook's last_delivery_status.
    """
    hooks = await _load_webhooks(str(current_user.id), redis)
    hook = next((h for h in hooks if h["id"] == webhook_id), None)
    if hook is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Webhook not found.", "code": "WEBHOOK_NOT_FOUND"},
        )

    test_payload = {
        "event": "test.ping",
        "webhook_id": webhook_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"message": "This is a test delivery from Nexus."},
    }

    start_ms = time.monotonic() * 1000
    http_status: int | None = None
    error: str | None = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(hook["url"], json=test_payload)
            http_status = resp.status_code
    except Exception as exc:
        error = str(exc)

    duration_ms = round(time.monotonic() * 1000 - start_ms, 1)

    delivery_record = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "test.ping",
        "http_status": http_status,
        "duration_ms": duration_ms,
        "error": error,
        "success": http_status is not None and 200 <= http_status < 300,
    }

    # Update hook metadata
    hook["last_delivery_status"] = http_status
    history: list[dict] = hook.get("delivery_history", [])
    history.insert(0, delivery_record)
    hook["delivery_history"] = history[:50]  # keep last 50

    await _save_webhooks(str(current_user.id), hooks, redis)

    return {
        "delivery": delivery_record,
        "webhook_id": webhook_id,
        "url": hook["url"],
    }

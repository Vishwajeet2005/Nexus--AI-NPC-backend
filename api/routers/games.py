"""
api/routers/games.py
──────────────────────
API key management endpoints for the developer dashboard.

Endpoints:
  GET    /v1/games/{game_id}/api-keys            — list keys
  POST   /v1/games/{game_id}/api-keys            — create key (returns raw key ONCE)
  DELETE /v1/games/{game_id}/api-keys/{key_id}   — revoke key (marks inactive)

API keys are stored on the Game row's `api_key` field. This implementation
tracks multiple keys per game via a dedicated in-memory/JSONB store on the
game's `config` column since Phase 1/2 only provisioned a single `api_key`
string. In production you would add an `api_keys` table; here we use the
Game.config JSONB to store additional key metadata for the dashboard without
a schema migration.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_db
from api.models.game import Game
from api.models.player import Player

router = APIRouter(prefix="/games", tags=["API Keys"])


# ── Request/response schemas (inline for this router only) ────────────────────

class CreateKeyRequest(BaseModel):
    name: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_keys(game: Game) -> list[dict]:
    """Extract the api_keys list from game.config JSONB."""
    config = game.config or {}
    return config.get("_api_keys", [])


def _set_keys(game: Game, keys: list[dict]) -> None:
    """Write the api_keys list back into game.config JSONB."""
    config = dict(game.config or {})
    config["_api_keys"] = keys
    game.config = config


async def _require_game_owner(game_id: UUID, player: Player, db: AsyncSession) -> Game:
    result = await db.execute(select(Game).where(Game.id == game_id))
    game: Game | None = result.scalar_one_or_none()
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": "Game not found.", "code": "GAME_NOT_FOUND"})
    if game.owner_id != player.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail={"error": "Not authorised for this game.", "code": "FORBIDDEN"})
    return game


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{game_id}/api-keys", summary="List API keys for a game")
async def list_api_keys(
    game_id: UUID,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return all API keys for a game (key values are not returned — only metadata)."""
    game = await _require_game_owner(game_id, current_user, db)
    keys = _get_keys(game)
    # Return metadata only, never the raw key after initial creation
    return {
        "keys": [
            {
                "id": k["id"],
                "name": k["name"],
                "prefix": k["prefix"],
                "is_active": k["is_active"],
                "created_at": k["created_at"],
                "last_used": k.get("last_used"),
            }
            for k in keys
        ]
    }


@router.post("/{game_id}/api-keys", status_code=status.HTTP_201_CREATED,
             summary="Create a new API key")
async def create_api_key(
    game_id: UUID,
    payload: CreateKeyRequest,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Create a new API key for the game.

    The raw key is returned ONCE in this response — it is never returned again.
    Store it securely immediately.
    """
    game = await _require_game_owner(game_id, current_user, db)

    raw_key = f"nxs_{secrets.token_hex(24)}"  # 48 hex chars — URL-safe prefix
    key_id = str(uuid4())
    prefix = raw_key[:12]  # "nxs_XXXXXXXX" — safe to show for identification

    keys = _get_keys(game)
    keys.append({
        "id": key_id,
        "name": payload.name,
        "prefix": prefix,
        "key_hash": hashlib.sha256(raw_key.encode()).hexdigest(),
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_used": None,
    })
    _set_keys(game, keys)
    await db.commit()

    return {
        "id": key_id,
        "name": payload.name,
        "key": raw_key,  # ONLY TIME this is returned
        "prefix": prefix,
        "created_at": keys[-1]["created_at"],
        "message": "Save this key immediately — it will not be shown again.",
    }


@router.delete("/{game_id}/api-keys/{key_id}", status_code=status.HTTP_200_OK,
               summary="Revoke an API key")
async def revoke_api_key(
    game_id: UUID,
    key_id: str,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Revoke (mark inactive) an API key. The row is retained for audit trail.
    """
    game = await _require_game_owner(game_id, current_user, db)
    keys = _get_keys(game)

    updated = False
    for k in keys:
        if k["id"] == key_id:
            k["is_active"] = False
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"error": "API key not found.", "code": "KEY_NOT_FOUND"})

    _set_keys(game, keys)
    await db.commit()
    return {"revoked": True, "key_id": key_id}

"""
api/routers/sessions.py
────────────────────────
FastAPI router for all session endpoints under `/v1/sessions`.

All endpoints require authentication via `Depends(get_current_user)`.

Endpoints
─────────
POST   /v1/sessions                         → 201 SessionResponse
GET    /v1/sessions/{session_id}            → 200 SessionResponse
POST   /v1/sessions/{session_id}/join       → 200 SessionResponse
POST   /v1/sessions/join/{join_code}        → 200 SessionResponse
POST   /v1/sessions/{session_id}/leave      → 200 SessionResponse
POST   /v1/sessions/{session_id}/lock       → 200 SessionResponse
POST   /v1/sessions/{session_id}/end        → 200 SessionResponse
GET    /v1/sessions/{session_id}/players    → 200 list[SessionPlayerResponse]
PATCH  /v1/sessions/{session_id}/state      → 200 SessionResponse

Route ordering note:
  `/sessions/join/{join_code}` MUST be registered BEFORE `/{session_id}/...`
  otherwise FastAPI will try to parse "join" as a UUID and return 422.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from api.dependencies import get_current_user, get_db, get_redis
from api.models.player import Player
from api.schemas.session import (
    SessionCreate,
    SessionPlayerResponse,
    SessionResponse,
    SessionStateUpdate,
)
from api.services import session_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["Sessions"])


# ── POST /sessions ─────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new game session",
    responses={
        404: {"description": "Game not found"},
        422: {"description": "Validation error"},
    },
)
async def create_session(
    payload: SessionCreate,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SessionResponse:
    """
    Create a new game session.

    - Generates a unique join code (`NEXUS-XXXX`).
    - The requesting player becomes the session host.
    - Session status starts as `created`.
    - Publishes `session.created` to the Redis pub/sub channel.
    """
    return await session_service.create_session(payload, current_user, db, redis)


# ── POST /sessions/join/{join_code} ───────────────────────────────────────────
# IMPORTANT: This route MUST be defined before /{session_id}/... routes.
# FastAPI matches routes in registration order — if /{session_id}/join were
# registered first, the path segment "join" would be captured as a UUID and
# produce a 422 Unprocessable Entity.

@router.post(
    "/join/{join_code}",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Join a session by human-readable join code",
    responses={
        404: {"description": "No session found with that join code"},
        409: {"description": "Session full, already in session, or session ended"},
        410: {"description": "Session has ended"},
        423: {"description": "Session is locked"},
    },
)
async def join_session_by_code(
    join_code: str,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SessionResponse:
    """
    Join a session using its human-typeable join code (e.g. `NEXUS-AB23`).

    The join code is case-insensitive — the service normalises to upper-case.
    """
    return await session_service.join_session_by_code(join_code, current_user, db, redis)


# ── GET /sessions/{session_id} ─────────────────────────────────────────────────

@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get full session details",
    responses={
        404: {"description": "Session not found"},
    },
)
async def get_session(
    session_id: UUID,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """
    Retrieve the full session record including current player list,
    configuration, and live game state.
    """
    return await session_service.get_session(session_id, current_user, db)


# ── POST /sessions/{session_id}/join ──────────────────────────────────────────

@router.post(
    "/{session_id}/join",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Join a session by UUID",
    responses={
        404: {"description": "Session not found"},
        409: {"description": "Session full, already in session, or session ended"},
        410: {"description": "Session has ended"},
        423: {"description": "Session is locked"},
    },
)
async def join_session_by_id(
    session_id: UUID,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SessionResponse:
    """
    Join a session by its UUID.

    - Returns **410** if the session has ended.
    - Returns **423** if the session is locked.
    - Returns **409** if the session is full or you are already a member.
    - Publishes `player.joined` to the Redis pub/sub channel.
    """
    return await session_service.join_session_by_id(session_id, current_user, db, redis)


# ── POST /sessions/{session_id}/leave ─────────────────────────────────────────

@router.post(
    "/{session_id}/leave",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Leave the session",
    responses={
        404: {"description": "Session not found"},
        409: {"description": "Not currently in session or session already ended"},
    },
)
async def leave_session(
    session_id: UUID,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SessionResponse:
    """
    Mark the current player as having left the session (`left_at` is set).

    The player remains in the `session_players` audit trail but is excluded
    from active player counts and lists. Publishes `player.left` event.
    """
    return await session_service.leave_session(session_id, current_user, db, redis)


# ── POST /sessions/{session_id}/lock ──────────────────────────────────────────

@router.post(
    "/{session_id}/lock",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Lock the session to prevent new players joining",
    responses={
        403: {"description": "Only the session host may lock"},
        404: {"description": "Session not found"},
        409: {"description": "Session has already ended"},
    },
)
async def lock_session(
    session_id: UUID,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SessionResponse:
    """
    Set `is_locked = True` on the session. Only the host may do this.

    Locked sessions reject all subsequent join attempts with **423**.
    """
    return await session_service.lock_session(session_id, current_user, db, redis)


# ── POST /sessions/{session_id}/end ───────────────────────────────────────────

@router.post(
    "/{session_id}/end",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
    summary="End the session",
    responses={
        403: {"description": "Only the session host may end the session"},
        404: {"description": "Session not found"},
        409: {"description": "Session has already ended"},
    },
)
async def end_session(
    session_id: UUID,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SessionResponse:
    """
    Transition the session to `ended` status.

    - Sets `ended_at` to the current timestamp.
    - Marks all still-active memberships as departed.
    - Publishes `session.ended` event.
    - Only the session host may end the session (**403** otherwise).
    """
    return await session_service.end_session(session_id, current_user, db, redis)


# ── GET /sessions/{session_id}/players ────────────────────────────────────────

@router.get(
    "/{session_id}/players",
    response_model=list[SessionPlayerResponse],
    status_code=status.HTTP_200_OK,
    summary="List active players in the session",
    responses={
        404: {"description": "Session not found"},
    },
)
async def get_session_players(
    session_id: UUID,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionPlayerResponse]:
    """
    Return only players whose `left_at` is `null` (currently in the session).

    Departed players are excluded — use `GET /sessions/{id}` if you need
    the full membership history.
    """
    return await session_service.get_session_players(session_id, current_user, db)


# ── PATCH /sessions/{session_id}/state ────────────────────────────────────────

@router.patch(
    "/{session_id}/state",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Merge game state into the session",
    responses={
        403: {"description": "Not an active member of this session"},
        404: {"description": "Session not found"},
        409: {"description": "Session has already ended"},
    },
)
async def update_session_state(
    session_id: UUID,
    payload: SessionStateUpdate,
    current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> SessionResponse:
    """
    Shallow-merge `state` into the session's existing `state` JSONB.

    `{ **current_state, **provided_delta }` — top-level keys in the delta
    overwrite existing keys; nested dicts are replaced wholesale.

    Any active player in the session may update state (not host-only).
    Publishes `session.state_updated` event with the changed keys.
    """
    return await session_service.update_session_state(
        session_id, payload.state, current_user, db, redis
    )

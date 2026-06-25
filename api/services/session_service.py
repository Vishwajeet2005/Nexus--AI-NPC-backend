"""
api/services/session_service.py
────────────────────────────────
Business logic for all game session operations.

Join code spec:
  - Format  : NEXUS-{4 chars from JOIN_CODE_ALPHABET}
  - Alphabet : ABCDEFGHJKLMNPQRSTUVWXYZ23456789  (no 0/O/1/I ambiguity)
  - Uniqueness: loop with SELECT until a free code is found (collision is
                extremely rare but the loop makes it correct-by-construction)

State update spec:
  - PATCH /sessions/{id}/state is a SHALLOW merge:
    { **current_state, **provided_delta }
  - Nested dicts are NOT deep-merged — the spec says "shallow merge".

Capacity:
  - max_players is enforced at join time by counting active session_players
    (left_at IS NULL).

Lifecycle:
  - status transitions: created → active → ended
  - Only the session creator (host) can lock/end a session.
  - Once ended, the session is immutable.
"""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import redis.asyncio as aioredis

from api.models.player import Player
from api.models.session import Session, SessionPlayer
from api.schemas.session import SessionCreate, SessionPlayerResponse, SessionResponse

logger = logging.getLogger(__name__)

# ── Join code generation ───────────────────────────────────────────────────────
# No 0/O or 1/I to prevent player confusion when reading codes aloud.
JOIN_CODE_ALPHABET: str = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
JOIN_CODE_LENGTH: int = 4
JOIN_CODE_PREFIX: str = "NEXUS-"
JOIN_CODE_MAX_ATTEMPTS: int = 10  # practically unreachable given search space of 32^4 = 1,048,576


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _generate_unique_join_code(db: AsyncSession) -> str:
    """
    Generate a join code in the format 'NEXUS-XXXX' that does not already
    exist in the `sessions` table.

    Uses `secrets.choice` (CSPRNG) rather than `random.choice` to prevent
    predictable code sequences.
    """
    for attempt in range(JOIN_CODE_MAX_ATTEMPTS):
        suffix = "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))
        code = f"{JOIN_CODE_PREFIX}{suffix}"

        existing = await db.scalar(
            select(Session).where(Session.join_code == code)
        )
        if existing is None:
            return code

        logger.debug(
            "session.join_code_collision",
            extra={"code": code, "attempt": attempt + 1},
        )

    # Astronomically unlikely given ~1M codes; surface as 500 so ops can investigate.
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"error": "Could not generate unique join code.", "code": "JOIN_CODE_EXHAUSTED"},
    )


async def _get_session_or_404(session_id: UUID, db: AsyncSession) -> Session:
    """Load a Session by PK, eagerly loading active session_players. Raises 404 if missing."""
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .options(
            selectinload(Session.session_players).selectinload(SessionPlayer.player)
        )
    )
    session: Session | None = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Session not found.", "code": "SESSION_NOT_FOUND"},
        )
    return session


def _active_player_count(session: Session) -> int:
    """Count players whose `left_at` is None (currently in session)."""
    return sum(1 for sp in session.session_players if sp.left_at is None)


def _require_host(session: Session, player: Player) -> SessionPlayer:
    """
    Confirm `player` is the host of `session`. Raises 403 if not.

    The host is the SessionPlayer row with role='host'.
    """
    for sp in session.session_players:
        if sp.player_id == player.id and sp.role == "host":
            return sp
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "Only the session host may perform this action.", "code": "NOT_HOST"},
    )


def _require_active_or_created(session: Session) -> None:
    """Raise 409 if the session has already ended."""
    if session.status == "ended":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Session has already ended.", "code": "SESSION_ENDED"},
        )


def _build_session_response(session: Session) -> SessionResponse:
    """
    Construct a `SessionResponse` from an ORM `Session` that has its
    `session_players` relationship loaded.
    """
    players = [
        SessionPlayerResponse(
            id=sp.id,
            player_id=sp.player_id,
            username=sp.player.username,
            role=sp.role,
            joined_at=sp.joined_at,
            left_at=sp.left_at,
        )
        for sp in session.session_players
        if sp.left_at is None  # only currently present players
    ]

    return SessionResponse(
        id=session.id,
        game_id=session.game_id,
        join_code=session.join_code,
        status=session.status,
        max_players=session.max_players,
        region=session.region,
        game_mode=session.game_mode,
        is_locked=session.is_locked,
        config=session.config,
        state=session.state,
        players=players,
        created_at=session.created_at,
        ended_at=session.ended_at,
    )


# ── Service functions ──────────────────────────────────────────────────────────

async def create_session(
    payload: SessionCreate,
    creator: Player,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> SessionResponse:
    """
    POST /v1/sessions

    1. Validate that the referenced game exists (404 if not).
    2. Generate a unique join code.
    3. Promote well-known config keys to top-level columns.
    4. INSERT session + SessionPlayer (creator as host).
    5. Publish session.created event via pub/sub.
    """
    from api.models.game import Game  # local import avoids circular at module level
    from api.services.realtime_service import publish_event  # local import

    # Validate game exists
    game = await db.scalar(
        select(Game).where(Game.id == payload.game_id)
    )
    if game is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Game not found.", "code": "GAME_NOT_FOUND"},
        )

    # Extract well-known config keys; fall back to sane defaults
    config = payload.config
    max_players: int = int(config.get("max_players", 4))
    region: str = str(config.get("region", "us-east-1"))
    game_mode: str | None = config.get("mode") or None

    join_code = await _generate_unique_join_code(db)

    session = Session(
        game_id=payload.game_id,
        join_code=join_code,
        status="created",
        max_players=max_players,
        region=region,
        game_mode=game_mode,
        is_locked=False,
        config=config or None,
        state={},
    )
    db.add(session)
    # Flush to get the session.id before adding the SessionPlayer FK
    await db.flush()

    host_membership = SessionPlayer(
        session_id=session.id,
        player_id=creator.id,
        role="host",
        joined_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(host_membership)
    await db.commit()

    # Reload with relationships for response building
    session = await _get_session_or_404(session.id, db)

    await publish_event(
        redis=redis,
        session_id=session.id,
        event_type="session.created",
        data={"join_code": session.join_code, "creator_id": str(creator.id)},
    )

    logger.info(
        "session.created",
        extra={"session_id": str(session.id), "creator_id": str(creator.id)},
    )
    return _build_session_response(session)


async def get_session(session_id: UUID, player: Player, db: AsyncSession) -> SessionResponse:
    """GET /v1/sessions/{id}"""
    session = await _get_session_or_404(session_id, db)

    in_session = any(
        sp.player_id == player.id
        for sp in session.session_players
    )
    if not in_session:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "You are not an active member of this session.", "code": "NOT_IN_SESSION"},
        )

    return _build_session_response(session)


async def join_session_by_id(
    session_id: UUID,
    player: Player,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> SessionResponse:
    """POST /v1/sessions/{id}/join — join by UUID."""
    return await _join_session(
        session=await _get_session_or_404(session_id, db),
        player=player,
        db=db,
        redis=redis,
    )


async def join_session_by_code(
    join_code: str,
    player: Player,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> SessionResponse:
    """POST /v1/sessions/join/{join_code} — join by human-readable code."""
    result = await db.execute(
        select(Session)
        .where(Session.join_code == join_code.upper())
        .options(
            selectinload(Session.session_players).selectinload(SessionPlayer.player)
        )
    )
    session: Session | None = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "No session found with that join code.", "code": "SESSION_NOT_FOUND"},
        )
    return await _join_session(session=session, player=player, db=db, redis=redis)


async def _join_session(
    session: Session,
    player: Player,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> SessionResponse:
    """
    Shared join logic for both join-by-id and join-by-code.

    Rejection conditions (in order):
    1. Session ended            → 409 SESSION_ENDED
    2. Session locked           → 423 SESSION_LOCKED
    3. Player already in session → 409 ALREADY_IN_SESSION
    4. Session full             → 409 SESSION_FULL
    """
    from api.services.realtime_service import publish_event

    _require_active_or_created(session)

    if session.is_locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"error": "Session is locked and not accepting new players.", "code": "SESSION_LOCKED"},
        )

    # Check if player is already an active member
    already_in = any(
        sp.player_id == player.id and sp.left_at is None
        for sp in session.session_players
    )
    if already_in:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "You are already in this session.", "code": "ALREADY_IN_SESSION"},
        )

    if _active_player_count(session) >= session.max_players:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Session is full.", "code": "SESSION_FULL"},
        )

    # If the player previously left this session, create a new membership row
    membership = SessionPlayer(
        session_id=session.id,
        player_id=player.id,
        role="player",
        joined_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(membership)

    # Auto-transition to 'active' on first non-host join
    if session.status == "created":
        session.status = "active"

    await db.commit()

    # Expunge the old session from the identity map so _get_session_or_404
    # is forced to execute a fresh query and load the new session_players.
    db.expunge(session)

    # Reload to include the new membership in the response
    session = await _get_session_or_404(session.id, db)

    await publish_event(
        redis=redis,
        session_id=session.id,
        event_type="player.joined",
        data={"player_id": str(player.id), "username": player.username},
    )

    logger.info(
        "session.player_joined",
        extra={"session_id": str(session.id), "player_id": str(player.id)},
    )
    return _build_session_response(session)


async def leave_session(
    session_id: UUID,
    player: Player,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> SessionResponse:
    """
    POST /v1/sessions/{id}/leave

    Sets `left_at` on the player's active membership row (soft delete).
    Does NOT remove them from the session_players table — the audit trail
    is preserved. If the leaving player is the host and others remain, the
    session continues (no host transfer in Phase 1).
    """
    from api.services.realtime_service import publish_event

    session = await _get_session_or_404(session_id, db)
    _require_active_or_created(session)

    # Find the player's active membership
    active_membership: SessionPlayer | None = next(
        (sp for sp in session.session_players if sp.player_id == player.id and sp.left_at is None),
        None,
    )
    if active_membership is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "You are not currently in this session.", "code": "NOT_IN_SESSION"},
        )

    active_membership.left_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()

    session = await _get_session_or_404(session_id, db)

    await publish_event(
        redis=redis,
        session_id=session.id,
        event_type="player.left",
        data={"player_id": str(player.id), "username": player.username},
    )

    logger.info(
        "session.player_left",
        extra={"session_id": str(session.id), "player_id": str(player.id)},
    )
    return _build_session_response(session)


async def lock_session(
    session_id: UUID,
    player: Player,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> SessionResponse:
    """
    POST /v1/sessions/{id}/lock

    Toggles `is_locked = True`. Only the host may do this.
    """
    from api.services.realtime_service import publish_event

    session = await _get_session_or_404(session_id, db)
    _require_active_or_created(session)
    _require_host(session, player)

    session.is_locked = True
    await db.commit()
    session = await _get_session_or_404(session_id, db)

    await publish_event(
        redis=redis,
        session_id=session.id,
        event_type="session.locked",
        data={"locked_by": str(player.id)},
    )

    logger.info(
        "session.locked",
        extra={"session_id": str(session_id), "host_id": str(player.id)},
    )
    return _build_session_response(session)


async def end_session(
    session_id: UUID,
    player: Player,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> SessionResponse:
    """
    POST /v1/sessions/{id}/end

    Transitions the session to 'ended'. Only the host may end a session.
    Sets `ended_at` to now and marks all still-active memberships as left.
    """
    from api.services.realtime_service import publish_event

    session = await _get_session_or_404(session_id, db)
    _require_active_or_created(session)
    _require_host(session, player)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    session.status = "ended"
    session.ended_at = now

    # Close all open memberships
    for sp in session.session_players:
        if sp.left_at is None:
            sp.left_at = now

    await db.commit()
    session = await _get_session_or_404(session_id, db)

    await publish_event(
        redis=redis,
        session_id=session.id,
        event_type="session.ended",
        data={"ended_by": str(player.id), "ended_at": now.isoformat()},
    )

    logger.info(
        "session.ended",
        extra={"session_id": str(session_id), "host_id": str(player.id)},
    )
    return _build_session_response(session)


async def update_session_state(
    session_id: UUID,
    delta: dict[str, Any],
    player: Player,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> SessionResponse:
    """
    PATCH /v1/sessions/{id}/state

    Spec: SHALLOW merge only — `{ **current_state, **delta }`.
    Nested dicts in current_state are replaced wholesale by keys in delta,
    NOT recursively merged. Any authenticated player in the session may update state.
    """
    from api.services.realtime_service import publish_event

    session = await _get_session_or_404(session_id, db)
    _require_active_or_created(session)

    # Confirm the requesting player is an active member
    in_session = any(
        sp.player_id == player.id and sp.left_at is None
        for sp in session.session_players
    )
    if not in_session:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "You are not an active member of this session.", "code": "NOT_IN_SESSION"},
        )

    # Shallow merge: existing state keys not in delta are preserved
    current: dict[str, Any] = session.state or {}
    session.state = {**current, **delta}

    await db.commit()
    session = await _get_session_or_404(session_id, db)

    await publish_event(
        redis=redis,
        session_id=session.id,
        event_type="session.state_updated",
        data={"updated_by": str(player.id), "delta_keys": list(delta.keys())},
    )

    logger.info(
        "session.state_updated",
        extra={"session_id": str(session_id), "player_id": str(player.id)},
    )
    return _build_session_response(session)


async def get_session_players(
    session_id: UUID,
    player: Player,
    db: AsyncSession,
) -> list[SessionPlayerResponse]:
    """GET /v1/sessions/{id}/players — returns only currently active players."""
    session = await _get_session_or_404(session_id, db)

    in_session = any(
        sp.player_id == player.id
        for sp in session.session_players
    )
    if not in_session:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "You are not an active member of this session.", "code": "NOT_IN_SESSION"},
        )

    return [
        SessionPlayerResponse(
            id=sp.id,
            player_id=sp.player_id,
            username=sp.player.username,
            role=sp.role,
            joined_at=sp.joined_at,
            left_at=sp.left_at,
        )
        for sp in session.session_players
        if sp.left_at is None
    ]

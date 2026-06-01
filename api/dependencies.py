"""
api/dependencies.py
───────────────────
Shared FastAPI dependency functions injected via `Depends()`.

Three dependency families:

1. `get_db`          — yields an `AsyncSession` bound to a per-request
                       transaction; rolls back and closes on any exception.

2. `get_redis`       — yields an `aioredis.Redis` client from a
                       connection pool created at startup.

3. `get_current_user` — extracts and validates the Bearer JWT from the
                        Authorization header, checks the JTI blacklist in
                        Redis, and returns the authenticated `Player` ORM row.
                        Use `Depends(get_current_user)` on any protected route.

Engine and Redis pool lifecycle is managed by the FastAPI lifespan handler
in `main.py` (Stage 5). The module-level `_engine` and `_redis_pool`
references are set there via `init_db()` and `init_redis()`.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import redis.asyncio as aioredis

from api.config import get_settings
from api.models.player import Player
from api.schemas.auth import TokenPayload

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Module-level singletons (set by main.py lifespan) ─────────────────────────
# These are intentionally mutable globals rather than app.state attributes so
# dependency functions — which only receive `Request` — can access them without
# needing to thread `request.app.state` through every call site.

_async_session_factory: async_sessionmaker[AsyncSession] | None = None
_redis_pool: aioredis.Redis | None = None


def init_db(engine: AsyncEngine) -> None:
    """
    Called once during application startup (lifespan) with the async engine.
    Creates the session factory bound to that engine.
    """
    global _async_session_factory
    _async_session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        # expire_on_commit=False prevents "DetachedInstanceError" when
        # returning ORM objects from a service after the session commits.
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    logger.info("Database session factory initialised.")


def init_redis(redis: aioredis.Redis) -> None:
    """Called once during application startup with the connected Redis client."""
    global _redis_pool
    _redis_pool = redis
    logger.info("Redis connection pool initialised.")


# ── 1. Database dependency ─────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an `AsyncSession` for the duration of a single request.

    Lifecycle:
    - A new session is acquired from the factory on each request.
    - The calling code (router / service) is responsible for committing.
    - On any unhandled exception the session is rolled back automatically.
    - The session is always closed in the `finally` block.

    Usage:
        @router.get("/foo")
        async def handler(db: AsyncSession = Depends(get_db)):
            ...
    """
    if _async_session_factory is None:
        raise RuntimeError(
            "Database session factory has not been initialised. "
            "Ensure init_db() is called in the application lifespan."
        )

    async with _async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── 2. Redis dependency ────────────────────────────────────────────────────────

async def get_redis() -> aioredis.Redis:
    """
    Return the shared `aioredis.Redis` client.

    The Redis client maintains its own internal connection pool; we do NOT
    yield-and-close here because the pool is long-lived across requests.
    Closing it per-request would destroy the pool.

    Usage:
        @router.post("/foo")
        async def handler(redis: aioredis.Redis = Depends(get_redis)):
            await redis.set("key", "value")
    """
    if _redis_pool is None:
        raise RuntimeError(
            "Redis pool has not been initialised. "
            "Ensure init_redis() is called in the application lifespan."
        )
    return _redis_pool


# ── 3. Auth dependencies ───────────────────────────────────────────────────────

# HTTPBearer extracts the token from "Authorization: Bearer <token>"
# auto_error=False lets us return a proper ErrorResponse instead of the
# default 403 from FastAPI's built-in handler.
_bearer_scheme = HTTPBearer(auto_error=False)


def _decode_token(token: str, expected_type: str) -> TokenPayload:
    """
    Decode and validate a JWT string.

    Raises `HTTPException(401)` on any JWT problem:
    - Expired token
    - Invalid signature
    - Wrong token type (e.g. refresh token used where access is required)
    - Missing required claims
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "Could not validate credentials.", "code": "INVALID_TOKEN"},
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload_dict: dict = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Token has expired.", "code": "TOKEN_EXPIRED"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise credentials_exception

    try:
        payload = TokenPayload(**payload_dict)
    except Exception:
        raise credentials_exception

    if payload.type != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": f"Expected token type '{expected_type}', got '{payload.type}'.",
                "code": "WRONG_TOKEN_TYPE",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def _check_jti_blacklist(jti: str, redis: aioredis.Redis) -> None:
    """
    Raise 401 if the token's JTI has been blacklisted (i.e. the user logged out).

    Blacklist key format: `blacklist:{jti}` (set with TTL = token expiry by logout).
    """
    blacklisted = await redis.exists(f"blacklist:{jti}")
    if blacklisted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Token has been revoked.", "code": "TOKEN_REVOKED"},
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> Player:
    """
    Extract, validate, and return the authenticated `Player` for the request.

    Steps:
    1. Extract Bearer token from Authorization header.
    2. Decode and verify JWT signature + expiry.
    3. Confirm token type is 'access'.
    4. Check JTI is not blacklisted in Redis.
    5. Load the Player row from Postgres.
    6. Confirm the account is not locked.

    Usage:
        @router.get("/protected")
        async def handler(current_user: Player = Depends(get_current_user)):
            ...
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Authorization header missing or malformed.", "code": "MISSING_TOKEN"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _decode_token(credentials.credentials, expected_type="access")
    await _check_jti_blacklist(payload.jti, redis)

    # Load player from DB
    result = await db.execute(
        select(Player).where(Player.id == payload.player_id)
    )
    player: Player | None = result.scalar_one_or_none()

    if player is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Player not found.", "code": "PLAYER_NOT_FOUND"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    if player.is_locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"error": "Account locked.", "code": "ACCOUNT_LOCKED"},
        )

    return player


async def verify_refresh_token(
    body_token: str,
    redis: aioredis.Redis,
    db: AsyncSession,
) -> tuple[TokenPayload, Player]:
    """
    Validate a refresh token string (from request body, not Authorization header).

    Used by POST /auth/refresh and POST /auth/logout.
    Returns the decoded payload and the associated Player row.

    Not a FastAPI dependency itself (takes explicit args) so it can be called
    from auth_service without creating a circular dependency chain.
    """
    payload = _decode_token(body_token, expected_type="refresh")
    await _check_jti_blacklist(payload.jti, redis)

    result = await db.execute(
        select(Player).where(Player.id == payload.player_id)
    )
    player: Player | None = result.scalar_one_or_none()

    if player is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Player not found.", "code": "PLAYER_NOT_FOUND"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    if player.is_locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"error": "Account locked.", "code": "ACCOUNT_LOCKED"},
        )

    return payload, player

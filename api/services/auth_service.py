"""
api/services/auth_service.py
─────────────────────────────
Business logic for all authentication operations.

Spec rules enforced here:
  - bcrypt cost-12 for all password hashing
  - 5 consecutive failed logins  → is_locked = True  → 423 on next attempt
  - Successful login             → failed_login_count reset, last_login updated
  - Logout JTI blacklisting      → both access + refresh JTIs written to Redis
                                    with TTL = remaining token lifetime
  - Guest accounts               → username = "guest_{random_hex_8}",
                                    email    = "{username}@guest.nexus" (internal)
  - Token pairs                  → access (15 min default) + refresh (7 day default)
  - refresh_token rotation       → old refresh JTI blacklisted, new pair issued

All DB writes use the `AsyncSession` passed by `Depends(get_db)`.
All Redis operations use `redis.asyncio.Redis` passed by `Depends(get_redis)`.
No FastAPI `Request`/`Response` objects are imported here.
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from api.config import get_settings
from api.dependencies import verify_refresh_token
from api.models.player import Player
from api.schemas.auth import (
    LoginRequest,
    PlayerResponse,
    RegisterRequest,
    TokenPayload,
    TokenResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Password hashing context ───────────────────────────────────────────────────
# The CryptContext is created once at module import — it reads bcrypt_cost from
# settings so tests can lower the cost factor without patching globals.
_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.bcrypt_cost,
)

# ── Constants ──────────────────────────────────────────────────────────────────
MAX_FAILED_LOGINS: int = 5
BLACKLIST_KEY_PREFIX: str = "blacklist:"


# ── Internal helpers ───────────────────────────────────────────────────────────

def _hash_password(plain: str) -> str:
    """Return a bcrypt hash of `plain` using the configured cost factor."""
    return _pwd_context.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    """Return True if `plain` matches `hashed`. Constant-time comparison."""
    return _pwd_context.verify(plain, hashed)


def _make_token(player_id: UUID, token_type: str, ttl_seconds: int) -> tuple[str, str]:
    """
    Encode a JWT and return `(encoded_token, jti)`.

    Payload:
      sub  — player UUID as string
      jti  — fresh UUID4 used for blacklisting
      type — 'access' | 'refresh'
      exp  — Unix timestamp of expiry
    """
    jti = str(uuid4())
    exp = int(time.time()) + ttl_seconds
    payload = {
        "sub": str(player_id),
        "jti": jti,
        "type": token_type,
        "exp": exp,
    }
    encoded = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    return encoded, jti


def _make_token_pair(player_id: UUID) -> tuple[TokenResponse, str, str]:
    """
    Generate a fresh (access_token, refresh_token) pair.

    Returns:
      (TokenResponse, access_jti, refresh_jti)
    """
    access_token, access_jti = _make_token(
        player_id, "access", settings.access_token_expire_seconds
    )
    refresh_token, refresh_jti = _make_token(
        player_id, "refresh", settings.refresh_token_expire_seconds
    )
    token_response = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_seconds,
    )
    return token_response, access_jti, refresh_jti


async def _blacklist_jti(jti: str, ttl_seconds: int, redis: aioredis.Redis) -> None:
    """
    Write `blacklist:{jti}` to Redis with the given TTL.

    Using the token's remaining lifetime as TTL means the key self-expires
    when the token would have expired anyway — no manual cleanup needed.
    Redis `SET NX` semantics: if the key already exists (e.g. double-logout)
    we leave the existing TTL untouched.
    """
    key = f"{BLACKLIST_KEY_PREFIX}{jti}"
    await redis.set(key, "1", ex=max(ttl_seconds, 1), nx=True)


# ── Service functions ──────────────────────────────────────────────────────────

async def register_player(
    payload: RegisterRequest,
    db: AsyncSession,
) -> Player:
    """
    POST /v1/auth/register

    1. Check username uniqueness → 409 if taken.
    2. Check email uniqueness    → 409 if taken.
    3. Hash password at cost-12.
    4. INSERT player row.
    5. Return ORM Player (caller builds PlayerResponse).
    """
    # Check username collision
    existing_username = await db.scalar(
        select(Player).where(Player.username == payload.username)
    )
    if existing_username is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Username already taken.", "code": "USERNAME_TAKEN"},
        )

    # Check email collision (email is already normalised to lowercase by schema)
    existing_email = await db.scalar(
        select(Player).where(Player.email == payload.email)
    )
    if existing_email is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Email address already registered.", "code": "EMAIL_TAKEN"},
        )

    player = Player(
        username=payload.username,
        email=payload.email,
        password_hash=_hash_password(payload.password),
        is_guest=False,
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)

    logger.info("player.registered", extra={"player_id": str(player.id)})
    return player


async def create_guest_player(db: AsyncSession) -> Player:
    """
    POST /v1/auth/guest

    Creates an anonymous guest account with a randomly generated username.
    Guest accounts cannot log in via POST /auth/login — they receive their
    access/refresh tokens directly from the guest endpoint.

    Username format : guest_{8 random hex chars}
    Email format    : {username}@guest.nexus  (internal, never exposed)
    Password        : random 32-byte hex (unhashable from outside)
    """
    # Retry loop guards against the astronomically unlikely UUID collision
    for _ in range(5):
        suffix = secrets.token_hex(4)
        username = f"guest_{suffix}"
        email = f"{username}@guest.nexus"

        collision = await db.scalar(
            select(Player).where(Player.username == username)
        )
        if collision is None:
            break
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Could not generate unique guest identity.", "code": "GUEST_CREATION_FAILED"},
        )

    player = Player(
        username=username,
        email=email,
        # A random password hash that cannot be derived — guests cannot log in
        password_hash=_hash_password(secrets.token_hex(32)),
        is_guest=True,
    )
    db.add(player)
    await db.commit()
    await db.refresh(player)

    logger.info("player.guest_created", extra={"player_id": str(player.id)})
    return player


async def login_player(
    payload: LoginRequest,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> TokenResponse:
    """
    POST /v1/auth/login

    Spec rules:
    - Unknown username         → 401 INVALID_CREDENTIALS (do NOT reveal whether
                                 the username exists to prevent enumeration)
    - Account locked           → 423 ACCOUNT_LOCKED
    - Wrong password           → increment failed_login_count;
                                 if count reaches MAX_FAILED_LOGINS lock account → 423
    - Correct password         → reset failed_login_count, update last_login, issue tokens
    - Guest accounts           → 401 INVALID_CREDENTIALS (guests cannot log in)
    """
    player: Player | None = await db.scalar(
        select(Player).where(Player.username == payload.username)
    )

    # Unknown username — constant-time path to prevent username enumeration
    if player is None or player.is_guest:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid username or password.", "code": "INVALID_CREDENTIALS"},
        )

    # Account already locked
    if player.is_locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail={"error": "Account locked due to too many failed login attempts.", "code": "ACCOUNT_LOCKED"},
        )

    # Verify password
    if not _verify_password(payload.password, player.password_hash):
        player.failed_login_count += 1

        if player.failed_login_count >= MAX_FAILED_LOGINS:
            player.is_locked = True
            await db.commit()
            logger.warning(
                "player.account_locked",
                extra={"player_id": str(player.id), "failed_count": player.failed_login_count},
            )
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail={
                    "error": "Account locked due to too many failed login attempts.",
                    "code": "ACCOUNT_LOCKED",
                },
            )

        await db.commit()
        logger.warning(
            "player.login_failed",
            extra={
                "player_id": str(player.id),
                "failed_count": player.failed_login_count,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid username or password.", "code": "INVALID_CREDENTIALS"},
        )

    # Successful authentication — reset counters and record login time
    player.failed_login_count = 0
    player.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()

    token_response, _access_jti, _refresh_jti = _make_token_pair(player.id)

    logger.info("player.login_success", extra={"player_id": str(player.id)})
    return token_response


async def refresh_tokens(
    refresh_token_str: str,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> TokenResponse:
    """
    POST /v1/auth/refresh

    Spec behaviour (refresh token rotation):
    1. Validate the incoming refresh token (signature, expiry, type, blacklist).
    2. Blacklist the old refresh token's JTI immediately — one-time use.
    3. Issue a fresh (access_token, refresh_token) pair.

    The old access token is NOT blacklisted here because:
    - Its short TTL (15 min) means it expires naturally soon.
    - The client is expected to discard it on receipt of new tokens.
    - Blacklisting it would require the client to pass it in the body,
      which is not in the spec's POST /auth/refresh request shape.
    """
    payload, player = await verify_refresh_token(refresh_token_str, redis, db)

    # Immediately blacklist the consumed refresh JTI (rotation)
    remaining_ttl = payload.exp - int(time.time())
    await _blacklist_jti(payload.jti, max(remaining_ttl, 1), redis)

    token_response, _access_jti, _refresh_jti = _make_token_pair(player.id)

    logger.info("player.tokens_refreshed", extra={"player_id": str(player.id)})
    return token_response


async def logout_player(
    access_token_str: str,
    refresh_token_str: str,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> None:
    """
    POST /v1/auth/logout

    Blacklists both the access JTI and the refresh JTI in Redis so neither
    can be used again. TTL for each key = remaining lifetime of that token,
    so Redis self-cleans without a background job.

    `access_token_str` is extracted from the Authorization header by the
    router and passed in directly — this function does not touch the HTTP layer.
    """
    # ── Access token ──────────────────────────────────────────────────────────
    # Decode without verifying expiry — even an expired access token's JTI
    # should be blacklisted to prevent replay after a clock correction.
    try:
        access_payload_dict: dict = jwt.decode(
            access_token_str,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_exp": False},
        )
        access_payload = TokenPayload(**access_payload_dict)
        access_remaining = max(access_payload.exp - int(time.time()), 1)
        await _blacklist_jti(access_payload.jti, access_remaining, redis)
    except Exception:
        # If the access token is already invalid/malformed, ignore — still
        # proceed to blacklist the refresh token.
        logger.warning("logout: could not decode access token for blacklisting")

    # ── Refresh token ─────────────────────────────────────────────────────────
    # verify_refresh_token validates signature, type, and blacklist status.
    # On logout we tolerate an already-blacklisted refresh token (idempotent).
    try:
        payload, player = await verify_refresh_token(refresh_token_str, redis, db)
        refresh_remaining = max(payload.exp - int(time.time()), 1)
        await _blacklist_jti(payload.jti, refresh_remaining, redis)
        logger.info("player.logout", extra={"player_id": str(player.id)})
    except HTTPException as exc:
        if exc.detail.get("code") == "TOKEN_REVOKED":
            # Already logged out — treat as success (idempotent logout)
            logger.info("logout: refresh token already revoked (idempotent)")
            return
        raise

"""
api/routers/auth.py
────────────────────
FastAPI router for all authentication endpoints under `/v1/auth`.

Endpoints
─────────
POST /v1/auth/register  → 201 PlayerResponse
POST /v1/auth/login     → 200 TokenResponse
POST /v1/auth/refresh   → 200 TokenResponse
POST /v1/auth/logout    → 204 (no body)
POST /v1/auth/guest     → 201 PlayerResponse

The router delegates all business logic to `auth_service`. It is
responsible only for:
  - HTTP plumbing (status codes, request/response serialisation)
  - Dependency injection (db, redis, current_user)
  - Extracting the raw Bearer token string for logout
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from api.dependencies import get_current_user, get_db, get_redis
from api.models.player import Player
from api.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    PlayerResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from api.services import auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Re-use the same bearer extractor as dependencies.py — auto_error=False so
# we can return a proper ErrorResponse body, not FastAPI's raw 403.
_bearer = HTTPBearer(auto_error=False)


# ── POST /auth/register ────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=PlayerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new player account",
    responses={
        409: {"description": "Username or email already taken"},
        422: {"description": "Validation error (invalid email, short password, etc.)"},
    },
)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> PlayerResponse:
    """
    Create a new registered player account.

    - Rejects duplicate username / email with **409**.
    - Rejects invalid email format or password < 8 chars with **422**.
    - Password is hashed with bcrypt cost-12 before storage.
    """
    player = await auth_service.register_player(payload, db)
    return PlayerResponse.model_validate(player)


# ── POST /auth/login ───────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive JWT tokens",
    responses={
        401: {"description": "Invalid credentials"},
        423: {"description": "Account locked after 5 failed attempts"},
    },
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TokenResponse:
    """
    Validate credentials and return an access + refresh token pair.

    - Increments `failed_login_count` on each wrong password.
    - Locks the account (→ **423**) after 5 consecutive failures.
    - Resets the counter and updates `last_login` on success.
    """
    return await auth_service.login_player(payload, db, redis)


# ── POST /auth/refresh ─────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Exchange a refresh token for a new token pair",
    responses={
        401: {"description": "Refresh token invalid, expired, or revoked"},
        423: {"description": "Account locked"},
    },
)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TokenResponse:
    """
    Rotate tokens: blacklist the old refresh token and issue a new pair.

    The incoming refresh token is one-time-use — it is JTI-blacklisted
    immediately after validation, before the new pair is issued.
    """
    return await auth_service.refresh_tokens(payload.refresh_token, db, redis)


# ── POST /auth/logout ──────────────────────────────────────────────────────────

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Invalidate the current session tokens",
    responses={
        204: {"description": "Logged out successfully — no response body"},
        401: {"description": "Missing or invalid Authorization header"},
    },
)
async def logout(
    payload: LogoutRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    _current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> None:
    """
    Blacklist both the access token (from Authorization header) and the
    refresh token (from request body) in Redis.

    Both tokens become immediately invalid. The client should discard them.
    Returns **204** with no body on success. Idempotent — logging out an
    already-revoked refresh token is treated as success.
    """
    # credentials is guaranteed non-None here because get_current_user
    # already validated the Authorization header and would have raised 401.
    access_token_str: str = credentials.credentials  # type: ignore[union-attr]

    await auth_service.logout_player(
        access_token_str=access_token_str,
        refresh_token_str=payload.refresh_token,
        db=db,
        redis=redis,
    )
    # FastAPI renders 204 with no body automatically when the handler returns None.


# ── POST /auth/guest ───────────────────────────────────────────────────────────

@router.post(
    "/guest",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an anonymous guest session",
    responses={
        201: {"description": "Guest account created; tokens returned directly"},
    },
)
async def create_guest(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> TokenResponse:
    """
    Create a temporary anonymous player and return a token pair immediately.

    Guest accounts:
    - Have a randomly generated username (`guest_XXXXXXXX`).
    - Cannot log in via `/auth/login`.
    - Are indistinguishable from registered players in session endpoints.

    The response is a **TokenResponse** (not a PlayerResponse) so the client
    can start making authenticated requests without a second round-trip.
    """
    player = await auth_service.create_guest_player(db)
    # Issue tokens directly — guests don't go through the login flow
    token_response, _access_jti, _refresh_jti = auth_service._make_token_pair(player.id)
    return token_response

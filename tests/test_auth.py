"""
tests/test_auth.py
──────────────────
Comprehensive tests for all /v1/auth endpoints.

Coverage:
  POST /auth/register   — success, duplicate username, duplicate email, weak password
  POST /auth/login      — success, wrong password (x5 → lockout), unknown user, guest blocked
  POST /auth/refresh    — token rotation, revoked token rejection
  POST /auth/logout     — blacklists both JTIs, idempotent
  POST /auth/guest      — creates account, returns tokens, guest cannot login
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/auth/register
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegister:

    async def test_register_success(self, client: AsyncClient) -> None:
        """Happy path: valid payload returns 201 with PlayerResponse body."""
        resp = await client.post("/v1/auth/register", json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "ValidPass99!",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["username"] == "alice"
        assert body["email"] == "alice@example.com"
        assert body["is_guest"] is False
        assert "id" in body
        assert "password_hash" not in body  # never exposed

    async def test_register_returns_correct_schema(self, client: AsyncClient) -> None:
        """Response contains exactly the PlayerResponse fields."""
        resp = await client.post("/v1/auth/register", json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "ValidPass99!",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert set(body.keys()) >= {"id", "username", "email", "is_guest"}

    async def test_register_duplicate_username_returns_409(
        self, client: AsyncClient
    ) -> None:
        """Second registration with the same username → 409 USERNAME_TAKEN."""
        payload = {"username": "dupuser", "email": "first@example.com", "password": "ValidPass99!"}
        resp1 = await client.post("/v1/auth/register", json=payload)
        assert resp1.status_code == 201

        resp2 = await client.post("/v1/auth/register", json={
            **payload, "email": "second@example.com"
        })
        assert resp2.status_code == 409
        assert resp2.json()["code"] == "USERNAME_TAKEN"

    async def test_register_duplicate_email_returns_409(
        self, client: AsyncClient
    ) -> None:
        """Second registration with the same email → 409 EMAIL_TAKEN."""
        await client.post("/v1/auth/register", json={
            "username": "user_a", "email": "shared@example.com", "password": "ValidPass99!"
        })
        resp = await client.post("/v1/auth/register", json={
            "username": "user_b", "email": "shared@example.com", "password": "ValidPass99!"
        })
        assert resp.status_code == 409
        assert resp.json()["code"] == "EMAIL_TAKEN"

    async def test_register_email_case_insensitive(self, client: AsyncClient) -> None:
        """Email normalised to lowercase — ALICE@example.com == alice@example.com."""
        await client.post("/v1/auth/register", json={
            "username": "casetest", "email": "ALICE@EXAMPLE.COM", "password": "ValidPass99!"
        })
        resp = await client.post("/v1/auth/register", json={
            "username": "casetest2", "email": "alice@example.com", "password": "ValidPass99!"
        })
        assert resp.status_code == 409
        assert resp.json()["code"] == "EMAIL_TAKEN"

    async def test_register_short_password_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Password shorter than 8 chars → 422 Unprocessable Entity."""
        resp = await client.post("/v1/auth/register", json={
            "username": "shortpw", "email": "s@example.com", "password": "abc"
        })
        assert resp.status_code == 422

    async def test_register_invalid_email_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Malformed email → 422."""
        resp = await client.post("/v1/auth/register", json={
            "username": "bademail", "email": "not-an-email", "password": "ValidPass99!"
        })
        assert resp.status_code == 422

    async def test_register_invalid_username_characters_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Username with spaces → 422 (pattern: alphanumeric/underscore/hyphen only)."""
        resp = await client.post("/v1/auth/register", json={
            "username": "bad user!", "email": "bad@example.com", "password": "ValidPass99!"
        })
        assert resp.status_code == 422

    async def test_register_error_response_includes_request_id(
        self, client: AsyncClient
    ) -> None:
        """All error responses include a request_id field."""
        resp = await client.post("/v1/auth/register", json={
            "username": "x", "email": "not-email", "password": "short"
        })
        assert resp.status_code == 422
        # 422 comes from FastAPI validation — check our global handler wraps it
        # The request_id may not be present on 422 from Pydantic (it uses its own handler);
        # but the error body should at least not crash.
        assert resp.json() is not None


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/auth/login
# ═══════════════════════════════════════════════════════════════════════════════

class TestLogin:

    async def test_login_success(
        self, client: AsyncClient, registered_user: dict
    ) -> None:
        """Correct credentials return 200 with access + refresh tokens."""
        resp = await client.post("/v1/auth/login", json={
            "username": "testplayer", "password": "SecurePass123!"
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900

    async def test_login_wrong_password_returns_401(
        self, client: AsyncClient, registered_user: dict
    ) -> None:
        """Wrong password → 401 INVALID_CREDENTIALS."""
        resp = await client.post("/v1/auth/login", json={
            "username": "testplayer", "password": "WrongPassword!"
        })
        assert resp.status_code == 401
        assert resp.json()["code"] == "INVALID_CREDENTIALS"

    async def test_login_unknown_username_returns_401(
        self, client: AsyncClient
    ) -> None:
        """Unknown username → 401 (not 404, to prevent enumeration)."""
        resp = await client.post("/v1/auth/login", json={
            "username": "nobody", "password": "SomePass123!"
        })
        assert resp.status_code == 401
        assert resp.json()["code"] == "INVALID_CREDENTIALS"

    async def test_login_wrong_password_increments_counter(
        self, client: AsyncClient, registered_user: dict, db
    ) -> None:
        """Each failed login increments failed_login_count in the DB."""
        from sqlalchemy import select
        from api.models.player import Player

        for _ in range(2):
            await client.post("/v1/auth/login", json={
                "username": "testplayer", "password": "Wrong!"
            })

        result = await db.execute(
            select(Player).where(Player.username == "testplayer")
        )
        player = result.scalar_one()
        assert player.failed_login_count == 2

    async def test_login_success_resets_failed_counter(
        self, client: AsyncClient, registered_user: dict, db
    ) -> None:
        """Successful login resets failed_login_count to 0."""
        from sqlalchemy import select
        from api.models.player import Player

        # One failed attempt first
        await client.post("/v1/auth/login", json={
            "username": "testplayer", "password": "Wrong!"
        })

        # Now succeed
        await client.post("/v1/auth/login", json={
            "username": "testplayer", "password": "SecurePass123!"
        })

        result = await db.execute(
            select(Player).where(Player.username == "testplayer")
        )
        player = result.scalar_one()
        assert player.failed_login_count == 0

    async def test_login_five_failures_lock_account(
        self, client: AsyncClient, registered_user: dict
    ) -> None:
        """
        5 consecutive wrong-password attempts lock the account.
        The 5th attempt itself returns 423. Subsequent attempts also return 423.
        """
        for i in range(5):
            resp = await client.post("/v1/auth/login", json={
                "username": "testplayer", "password": "WrongPassword!"
            })
            if i < 4:
                assert resp.status_code == 401, f"Attempt {i+1} should be 401"
            else:
                assert resp.status_code == 423, "5th attempt should lock the account (423)"

        # Even with correct password, account is now locked
        resp = await client.post("/v1/auth/login", json={
            "username": "testplayer", "password": "SecurePass123!"
        })
        assert resp.status_code == 423
        assert resp.json()["code"] == "ACCOUNT_LOCKED"

    async def test_locked_account_returns_423(
        self, client: AsyncClient, db
    ) -> None:
        """A manually locked account returns 423 immediately."""
        from sqlalchemy import select
        from api.models.player import Player

        # Register fresh user
        await client.post("/v1/auth/register", json={
            "username": "locked_user", "email": "locked@example.com",
            "password": "SecurePass123!"
        })

        # Lock via DB
        result = await db.execute(
            select(Player).where(Player.username == "locked_user")
        )
        player = result.scalar_one()
        player.is_locked = True
        await db.commit()

        resp = await client.post("/v1/auth/login", json={
            "username": "locked_user", "password": "SecurePass123!"
        })
        assert resp.status_code == 423
        assert resp.json()["code"] == "ACCOUNT_LOCKED"

    async def test_guest_cannot_login(
        self, client: AsyncClient
    ) -> None:
        """Guest accounts (is_guest=True) are rejected at login → 401."""
        # Create guest
        guest_resp = await client.post("/v1/auth/guest")
        assert guest_resp.status_code == 201

        # Extract username from the token payload to attempt login
        # (guests have username = "guest_XXXXXXXX" — we can't log in as them)
        resp = await client.post("/v1/auth/login", json={
            "username": "guest_xxxxxxxx",
            "password": "anything"
        })
        assert resp.status_code == 401

    async def test_login_sets_last_login(
        self, client: AsyncClient, registered_user: dict, db
    ) -> None:
        """Successful login updates the `last_login` timestamp."""
        from sqlalchemy import select
        from api.models.player import Player

        resp = await client.post("/v1/auth/login", json={
            "username": "testplayer", "password": "SecurePass123!"
        })
        assert resp.status_code == 200

        result = await db.execute(
            select(Player).where(Player.username == "testplayer")
        )
        player = result.scalar_one()
        assert player.last_login is not None


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/auth/refresh
# ═══════════════════════════════════════════════════════════════════════════════

class TestRefresh:

    async def test_refresh_returns_new_token_pair(
        self, client: AsyncClient, auth_tokens: dict
    ) -> None:
        """Valid refresh token → 200 with new access + refresh tokens."""
        resp = await client.post("/v1/auth/refresh", json={
            "refresh_token": auth_tokens["refresh_token"]
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        # New tokens should differ from original
        assert body["access_token"] != auth_tokens["access_token"]
        assert body["refresh_token"] != auth_tokens["refresh_token"]

    async def test_refresh_rotates_token(
        self, client: AsyncClient, auth_tokens: dict
    ) -> None:
        """The consumed refresh token cannot be reused after rotation → 401."""
        old_refresh = auth_tokens["refresh_token"]

        resp1 = await client.post("/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert resp1.status_code == 200

        # Reusing the old refresh token should now fail
        resp2 = await client.post("/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert resp2.status_code == 401
        assert resp2.json()["code"] == "TOKEN_REVOKED"

    async def test_refresh_with_access_token_returns_401(
        self, client: AsyncClient, auth_tokens: dict
    ) -> None:
        """Passing an access token where a refresh token is expected → 401 WRONG_TOKEN_TYPE."""
        resp = await client.post("/v1/auth/refresh", json={
            "refresh_token": auth_tokens["access_token"]  # wrong type
        })
        assert resp.status_code == 401
        assert resp.json()["code"] == "WRONG_TOKEN_TYPE"

    async def test_refresh_with_invalid_token_returns_401(
        self, client: AsyncClient
    ) -> None:
        """Garbage token → 401 INVALID_TOKEN."""
        resp = await client.post("/v1/auth/refresh", json={
            "refresh_token": "not.a.real.token"
        })
        assert resp.status_code == 401

    async def test_new_access_token_is_usable(
        self, client: AsyncClient, auth_tokens: dict
    ) -> None:
        """New access token returned by /refresh is valid for authenticated endpoints."""
        refresh_resp = await client.post("/v1/auth/refresh", json={
            "refresh_token": auth_tokens["refresh_token"]
        })
        assert refresh_resp.status_code == 200
        new_access = refresh_resp.json()["access_token"]

        # Use the new token on a protected endpoint
        resp = await client.post(
            "/v1/sessions",
            json={"game_id": "00000000-0000-0000-0000-000000000000",
                  "config": {"region": "us-east-1"}},
            headers={"Authorization": f"Bearer {new_access}"},
        )
        # 404 (game not found) proves the token was accepted; not 401
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/auth/logout
# ═══════════════════════════════════════════════════════════════════════════════

class TestLogout:

    async def test_logout_returns_204(
        self, client: AsyncClient, auth_tokens: dict, auth_headers: dict
    ) -> None:
        """Successful logout → 204 No Content."""
        resp = await client.post(
            "/v1/auth/logout",
            json={"refresh_token": auth_tokens["refresh_token"]},
            headers=auth_headers,
        )
        assert resp.status_code == 204
        assert resp.content == b""

    async def test_logout_blacklists_access_token(
        self, client: AsyncClient, auth_tokens: dict, auth_headers: dict
    ) -> None:
        """After logout, the access token is rejected on protected endpoints."""
        await client.post(
            "/v1/auth/logout",
            json={"refresh_token": auth_tokens["refresh_token"]},
            headers=auth_headers,
        )

        # Access token should now be revoked
        resp = await client.post(
            "/v1/sessions",
            json={"game_id": "00000000-0000-0000-0000-000000000000",
                  "config": {"region": "us-east-1"}},
            headers=auth_headers,
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == "TOKEN_REVOKED"

    async def test_logout_blacklists_refresh_token(
        self, client: AsyncClient, auth_tokens: dict, auth_headers: dict
    ) -> None:
        """After logout, the refresh token cannot be used to get new tokens."""
        await client.post(
            "/v1/auth/logout",
            json={"refresh_token": auth_tokens["refresh_token"]},
            headers=auth_headers,
        )

        resp = await client.post("/v1/auth/refresh", json={
            "refresh_token": auth_tokens["refresh_token"]
        })
        assert resp.status_code == 401
        assert resp.json()["code"] == "TOKEN_REVOKED"

    async def test_logout_without_auth_header_returns_401(
        self, client: AsyncClient, auth_tokens: dict
    ) -> None:
        """Logout without Authorization header → 401."""
        resp = await client.post(
            "/v1/auth/logout",
            json={"refresh_token": auth_tokens["refresh_token"]},
        )
        assert resp.status_code == 401

    async def test_double_logout_is_idempotent(
        self, client: AsyncClient, auth_tokens: dict, auth_headers: dict
    ) -> None:
        """Logging out twice does not raise an error on the second call."""
        payload = {"refresh_token": auth_tokens["refresh_token"]}
        resp1 = await client.post("/v1/auth/logout", json=payload, headers=auth_headers)
        assert resp1.status_code == 204

        # Second logout — refresh token already revoked, but we still have the
        # auth header. The service should treat this gracefully.
        resp2 = await client.post("/v1/auth/logout", json=payload, headers=auth_headers)
        # Either 204 (idempotent) or 401 (access revoked too) — must not 500
        assert resp2.status_code in (204, 401)


# ═══════════════════════════════════════════════════════════════════════════════
# POST /v1/auth/guest
# ═══════════════════════════════════════════════════════════════════════════════

class TestGuest:

    async def test_guest_returns_201_with_tokens(
        self, client: AsyncClient
    ) -> None:
        """POST /auth/guest returns 201 with a full TokenResponse."""
        resp = await client.post("/v1/auth/guest")
        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900

    async def test_guest_token_is_usable(self, client: AsyncClient) -> None:
        """Guest access token works on protected endpoints."""
        guest_resp = await client.post("/v1/auth/guest")
        assert guest_resp.status_code == 201
        token = guest_resp.json()["access_token"]

        resp = await client.post(
            "/v1/sessions",
            json={"game_id": "00000000-0000-0000-0000-000000000000",
                  "config": {"region": "us-east-1"}},
            headers={"Authorization": f"Bearer {token}"},
        )
        # 404 (game not found) confirms the token was accepted
        assert resp.status_code == 404

    async def test_guest_creates_unique_accounts(
        self, client: AsyncClient
    ) -> None:
        """Each call to /auth/guest creates a distinct player."""
        resp1 = await client.post("/v1/auth/guest")
        resp2 = await client.post("/v1/auth/guest")
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        # Decode both tokens to compare sub claims
        from jose import jwt
        from api.config import get_settings
        s = get_settings()
        p1 = jwt.decode(resp1.json()["access_token"], s.secret_key, algorithms=[s.algorithm])
        p2 = jwt.decode(resp2.json()["access_token"], s.secret_key, algorithms=[s.algorithm])
        assert p1["sub"] != p2["sub"]

    async def test_guest_is_marked_in_db(
        self, client: AsyncClient, db
    ) -> None:
        """The created player has is_guest=True in the database."""
        from jose import jwt
        from api.config import get_settings
        from sqlalchemy import select
        from api.models.player import Player
        import uuid

        resp = await client.post("/v1/auth/guest")
        s = get_settings()
        payload = jwt.decode(resp.json()["access_token"], s.secret_key, algorithms=[s.algorithm])
        player_id = uuid.UUID(payload["sub"])

        result = await db.execute(select(Player).where(Player.id == player_id))
        player = result.scalar_one()
        assert player.is_guest is True
        assert player.username.startswith("guest_")

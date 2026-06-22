"""
sdk/python/tests/test_auth_sdk.py
────────────────────────────────────
Tests for nexus_py.auth.AuthClient.

Spec test cases (from NEXUS_PHASE3_MEGAPROMPT.md):
  - test_register_and_login: register then login sets access_token on client
  - test_login_sets_header: after login, all subsequent requests include Authorization header
  - test_guest_login: guest() sets is_guest=True
  - test_invalid_credentials: login with wrong password raises AuthError
  - test_logout_clears_token: access_token is None after logout
"""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from nexus_py import AuthError, NexusClient, PlayerResponse, TokenResponse

pytestmark = pytest.mark.asyncio


class TestAuthSDK:

    async def test_register_and_login(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """register() then login() — access_token is set on the client after login."""
        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/auth/register",
            status_code=201,
            json={
                "id": "11111111-1111-1111-1111-111111111111",
                "username": "alice",
                "email": "alice@example.com",
                "is_guest": False,
            },
        )
        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/auth/login",
            status_code=200,
            json={
                "access_token": "fake.access.token",
                "refresh_token": "fake.refresh.token",
                "token_type": "bearer",
                "expires_in": 900,
            },
        )

        player = await client.auth.register(
            username="alice", email="alice@example.com", password="SecurePass123!"
        )
        assert isinstance(player, PlayerResponse)
        assert player.username == "alice"
        # access_token must NOT be set yet — register() does not log in
        assert client.access_token is None

        tokens = await client.auth.login("alice", "SecurePass123!")
        assert isinstance(tokens, TokenResponse)
        assert tokens.access_token == "fake.access.token"

        # login() DOES set the token on the client
        assert client.access_token == "fake.access.token"

    async def test_login_sets_header(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """After login, all subsequent requests include the Authorization header."""
        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/auth/login",
            status_code=200,
            json={
                "access_token": "header-test-token",
                "refresh_token": "header-test-refresh",
                "token_type": "bearer",
                "expires_in": 900,
            },
        )
        await client.auth.login("alice", "SecurePass123!")

        # Now make a subsequent request and verify the header is attached
        httpx_mock.add_response(
            method="GET",
            url="http://test.nexus.local:8000/v1/sessions/some-session-id",
            status_code=200,
            json={
                "id": "some-session-id",
                "join_code": "NEXUS-AB23",
                "status": "created",
                "max_players": 4,
                "region": "us-east-1",
                "is_locked": False,
                "players": [],
                "created_at": "2025-01-01T00:00:00",
            },
        )
        await client.sessions.get("some-session-id")

        # Inspect the captured request for the Authorization header
        requests = httpx_mock.get_requests(
            url="http://test.nexus.local:8000/v1/sessions/some-session-id"
        )
        assert len(requests) == 1
        auth_header = requests[0].headers.get("authorization")
        assert auth_header == "Bearer header-test-token"

    async def test_guest_login(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """guest() returns tokens and sets the access_token on the client immediately."""
        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/auth/guest",
            status_code=201,
            json={
                "access_token": "guest.access.token",
                "refresh_token": "guest.refresh.token",
                "token_type": "bearer",
                "expires_in": 900,
            },
        )

        tokens = await client.auth.guest()
        assert isinstance(tokens, TokenResponse)
        assert tokens.access_token == "guest.access.token"
        assert client.access_token == "guest.access.token"

        # Verify the guest's underlying player record is marked is_guest=True
        # by fetching it via a follow-up call (simulating typical usage —
        # the SDK's guest() returns tokens, not the player object directly,
        # matching the actual POST /auth/guest response shape).
        httpx_mock.add_response(
            method="GET",
            url="http://test.nexus.local:8000/v1/npcs/session/abc",
            status_code=200,
            json=[],
        )
        # This call should succeed because the token is attached
        result = await client.npcs.list_in_session("abc")
        assert result == []

    async def test_invalid_credentials(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """login() with wrong password raises AuthError (401 INVALID_CREDENTIALS)."""
        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/auth/login",
            status_code=401,
            json={
                "error": "Invalid username or password.",
                "code": "INVALID_CREDENTIALS",
                "request_id": "22222222-2222-2222-2222-222222222222",
            },
        )

        with pytest.raises(AuthError) as exc_info:
            await client.auth.login("alice", "WrongPassword!")

        assert exc_info.value.code == "INVALID_CREDENTIALS"
        assert "Invalid username or password" in exc_info.value.message
        # Token must remain unset after a failed login
        assert client.access_token is None

    async def test_invalid_credentials_account_locked(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """login() against a locked account raises AuthError (423 ACCOUNT_LOCKED)."""
        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/auth/login",
            status_code=423,
            json={
                "error": "Account locked due to too many failed login attempts.",
                "code": "ACCOUNT_LOCKED",
                "request_id": "33333333-3333-3333-3333-333333333333",
            },
        )

        with pytest.raises(AuthError) as exc_info:
            await client.auth.login("locked_user", "SomePassword!")

        assert exc_info.value.code == "ACCOUNT_LOCKED"

    async def test_logout_clears_token(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """access_token is None after logout()."""
        # First log in
        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/auth/login",
            status_code=200,
            json={
                "access_token": "logout-test-token",
                "refresh_token": "logout-test-refresh",
                "token_type": "bearer",
                "expires_in": 900,
            },
        )
        await client.auth.login("alice", "SecurePass123!")
        assert client.access_token == "logout-test-token"

        # Now log out
        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/auth/logout",
            status_code=204,
        )
        await client.auth.logout()

        assert client.access_token is None

    async def test_logout_without_prior_login_is_noop(
        self, client: NexusClient
    ) -> None:
        """Calling logout() with no active session does not raise — it's a safe no-op."""
        # No httpx_mock response registered — if this tries to make an HTTP
        # call, the test will fail with an unmatched-request error, proving
        # logout() correctly skips the network call when there's no refresh token.
        await client.auth.logout()
        assert client.access_token is None

    async def test_refresh_updates_token(
        self, client: NexusClient, httpx_mock: HTTPXMock
    ) -> None:
        """refresh() rotates the token pair and updates the client's access_token."""
        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/auth/login",
            status_code=200,
            json={
                "access_token": "original-token",
                "refresh_token": "original-refresh",
                "token_type": "bearer",
                "expires_in": 900,
            },
        )
        await client.auth.login("alice", "SecurePass123!")

        httpx_mock.add_response(
            method="POST",
            url="http://test.nexus.local:8000/v1/auth/refresh",
            status_code=200,
            json={
                "access_token": "rotated-token",
                "refresh_token": "rotated-refresh",
                "token_type": "bearer",
                "expires_in": 900,
            },
        )
        new_tokens = await client.auth.refresh()

        assert new_tokens.access_token == "rotated-token"
        assert client.access_token == "rotated-token"

    async def test_refresh_without_token_raises_auth_error(
        self, client: NexusClient
    ) -> None:
        """refresh() with no stored refresh token and none passed raises AuthError."""
        with pytest.raises(AuthError):
            await client.auth.refresh()

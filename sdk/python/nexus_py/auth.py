"""
nexus_py.auth
───────────────
AuthClient — handles all authentication endpoints.

Accessed via `nexus.auth.*` on a NexusClient instance. Never instantiate
directly — it requires a reference to the parent NexusClient for its
shared HTTP transport and token storage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nexus_py.models import PlayerResponse, TokenResponse

if TYPE_CHECKING:
    from nexus_py.client import NexusClient


class AuthClient:
    """
    Authentication operations: register, login, guest, refresh, logout.

    All methods that return a `TokenResponse` automatically call
    `client._set_token(...)` so subsequent requests on the same
    `NexusClient` are authenticated without any extra step.
    """

    def __init__(self, client: "NexusClient") -> None:
        self._c = client

    async def register(
        self,
        username: str,
        email: str,
        password: str,
    ) -> PlayerResponse:
        """
        Create a new registered player account.

        Does NOT log the player in — call `.login()` afterward to obtain
        tokens. Raises `NexusError` (409) if username/email is already taken.
        """
        data = await self._c._post(
            "/auth/register",
            json={"username": username, "email": email, "password": password},
        )
        return PlayerResponse(**data)

    async def login(self, username: str, password: str) -> TokenResponse:
        """
        Authenticate with username/password and obtain a token pair.

        On success, the access token is automatically attached to the
        client's HTTP transport — all subsequent calls on this `NexusClient`
        (and its sub-clients) are authenticated.

        Raises:
            AuthError: invalid credentials (401) or account locked (423).
        """
        data = await self._c._post(
            "/auth/login",
            json={"username": username, "password": password},
        )
        token = TokenResponse(**data)
        self._c._set_token(token.access_token)
        self._c._refresh_token = token.refresh_token
        return token

    async def guest(self) -> TokenResponse:
        """
        Create an anonymous guest account and log in immediately.

        Returns a full token pair — no separate login call needed.
        The access token is automatically attached to the client.
        """
        data = await self._c._post("/auth/guest")
        token = TokenResponse(**data)
        self._c._set_token(token.access_token)
        self._c._refresh_token = token.refresh_token
        return token

    async def refresh(self, refresh_token: str | None = None) -> TokenResponse:
        """
        Exchange a refresh token for a new access/refresh token pair.

        Args:
            refresh_token: The refresh token to use. If omitted, uses the
                          refresh token stored from the last login/guest call.

        Raises:
            AuthError: refresh token invalid, expired, or already revoked.
        """
        token_to_use = refresh_token or self._c._refresh_token
        if token_to_use is None:
            from nexus_py.exceptions import AuthError
            raise AuthError(
                "No refresh token available. Call login() or guest() first, "
                "or pass refresh_token explicitly."
            )

        data = await self._c._post(
            "/auth/refresh",
            json={"refresh_token": token_to_use},
        )
        token = TokenResponse(**data)
        self._c._set_token(token.access_token)
        self._c._refresh_token = token.refresh_token
        return token

    async def logout(self, refresh_token: str | None = None) -> None:
        """
        Invalidate the current session's tokens.

        Both the access token (from the Authorization header) and the
        refresh token are blacklisted server-side. After this call,
        `client.access_token` is None.

        Args:
            refresh_token: The refresh token to blacklist. If omitted, uses
                          the refresh token stored from the last login/guest call.
        """
        token_to_use = refresh_token or self._c._refresh_token
        if token_to_use is not None:
            await self._c._post(
                "/auth/logout",
                json={"refresh_token": token_to_use},
            )
        self._c._clear_token()
        self._c._refresh_token = None

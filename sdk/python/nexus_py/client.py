"""
nexus_py.client
─────────────────
NexusClient — the single entry point for the Nexus Python SDK.

Usage:
    async with NexusClient(host="localhost:8000") as nexus:
        await nexus.auth.login("dev", "password123")
        session = await nexus.sessions.create(game_id="...")
        npc = await nexus.npcs.create({...})
        response = await nexus.npcs.interact(npc.id, "Where were you?")

The client owns a single `httpx.AsyncClient` shared by every sub-client
(`auth`, `sessions`, `npcs`, `realtime`). Sub-clients never instantiate
their own HTTP client — they all route through `NexusClient._get/_post/_patch`
so the Authorization header, base URL, and timeout are configured exactly
once, in exactly one place.
"""

from __future__ import annotations

from typing import Any

import httpx

from nexus_py.auth import AuthClient
from nexus_py.exceptions import AuthError, NexusError, NPCError, SessionError
from nexus_py.exceptions import TimeoutError as NexusTimeoutError
from nexus_py.npcs import NPCsClient
from nexus_py.realtime import RealtimeClient
from nexus_py.sessions import SessionsClient

# ── Default request timeout (seconds) ──────────────────────────────────────────
# Set comfortably above the server's own 10s LLM timeout so an /interact call
# that hits the server-side LLM timeout still completes successfully (the
# server returns 200 with a fallback response well within 30s).
DEFAULT_TIMEOUT_SECONDS: float = 30.0


class NexusClient:
    """
    Main SDK entry point.

    Attributes:
        base_url: HTTP base URL, e.g. "http://localhost:8000/v1"
        ws_url:   WebSocket base URL, e.g. "ws://localhost:8000/v1"
        auth:     AuthClient      — register/login/refresh/logout/guest
        sessions: SessionsClient  — create/join/leave/lock/end/state
        npcs:     NPCsClient      — create/get/interact/memory
        realtime: RealtimeClient  — WebSocket event subscription
    """

    def __init__(
        self,
        host: str = "localhost:8000",
        api_key: str | None = None,
        use_tls: bool = False,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """
        Args:
            host:     Host:port of the Nexus API, without scheme.
            api_key:  Reserved for future game-level API key auth.
                      Not yet used by Phase 1/2 endpoints (which use JWT).
            use_tls:  If True, use https:// and wss:// instead of http:// / ws://.
            timeout:  Request timeout in seconds for all HTTP calls.
        """
        scheme = "https" if use_tls else "http"
        ws_scheme = "wss" if use_tls else "ws"
        self.base_url = f"{scheme}://{host}/v1"
        self.ws_url = f"{ws_scheme}://{host}/v1"

        self._api_key = api_key
        self._access_token: str | None = None
        self._refresh_token: str | None = None

        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
        )

        # Sub-clients all share this instance and route every call through
        # the _get/_post/_patch helpers below.
        self.auth = AuthClient(self)
        self.sessions = SessionsClient(self)
        self.npcs = NPCsClient(self)
        self.realtime = RealtimeClient(self)

    # ── Token management ───────────────────────────────────────────────────────

    def _set_token(self, token: str) -> None:
        """
        Store the access token and attach it to every subsequent HTTP request.

        Called internally by AuthClient after login/refresh/guest.
        """
        self._access_token = token
        self._http.headers.update({"Authorization": f"Bearer {token}"})

    def _clear_token(self) -> None:
        """Remove the access token from memory and future requests."""
        self._access_token = None
        self._http.headers.pop("Authorization", None)

    @property
    def access_token(self) -> str | None:
        """The current access token, or None if not authenticated."""
        return self._access_token

    # ── HTTP verbs ──────────────────────────────────────────────────────────────

    async def _get(self, path: str, **kwargs: Any) -> Any:
        response = await self._request("GET", path, **kwargs)
        self._raise_for_status(response)
        return self._parse_json(response)

    async def _post(self, path: str, **kwargs: Any) -> Any:
        response = await self._request("POST", path, **kwargs)
        self._raise_for_status(response)
        return self._parse_json(response)

    async def _patch(self, path: str, **kwargs: Any) -> Any:
        response = await self._request("PATCH", path, **kwargs)
        self._raise_for_status(response)
        return self._parse_json(response)

    async def _delete(self, path: str, **kwargs: Any) -> Any:
        response = await self._request("DELETE", path, **kwargs)
        self._raise_for_status(response)
        return self._parse_json(response)

    # ── Internal request plumbing ──────────────────────────────────────────────

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """
        Issue the underlying HTTP request, converting httpx timeout/transport
        errors into the SDK's typed `TimeoutError` / `NexusError`.
        """
        try:
            return await self._http.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise NexusTimeoutError(
                f"Request to {path} timed out after {self._http.timeout}"
            ) from exc
        except httpx.TransportError as exc:
            raise NexusError(f"Network error calling {path}: {exc}") from exc

    @staticmethod
    def _parse_json(response: httpx.Response) -> Any:
        """
        Parse the response body as JSON.

        204 No Content (e.g. DELETE /auth/logout) has no body — return None
        rather than raising a JSON decode error.
        """
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def _raise_for_status(self, response: httpx.Response) -> None:
        """
        Translate HTTP error responses into typed SDK exceptions.

        Mapping:
            401 → AuthError      (invalid/expired/missing/revoked token, bad creds)
            423 → AuthError      (account locked)
            404 → NPCError       (NPC not found) — only for /npcs/* paths;
                                  otherwise falls through to generic NexusError
            409 → SessionError   (session conflicts: full, locked, ended, etc.)
            4xx/5xx (other) → NexusError
        """
        if response.status_code < 400:
            return

        # Attempt to extract the structured ErrorResponse body.
        # Fall back gracefully if the body isn't JSON (e.g. a raw 502 from a proxy).
        try:
            body = response.json()
        except Exception:
            body = {}

        message = body.get("error", f"HTTP {response.status_code}")
        code = body.get("code")

        if response.status_code == 401:
            raise AuthError(message, code=code)

        if response.status_code == 423:
            raise AuthError(message, code=code)

        if response.status_code == 404 and "/npcs" in str(response.request.url):
            raise NPCError(message, code=code)

        if response.status_code == 409:
            raise SessionError(message, code=code)

        raise NexusError(message, code=code)

    # ── Lifecycle ───────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying HTTP client and any open WebSocket connection."""
        await self.realtime.disconnect()
        await self._http.aclose()

    async def __aenter__(self) -> "NexusClient":
        return self

    async def __aexit__(self, *_exc_info: Any) -> None:
        await self.close()

    def __repr__(self) -> str:
        auth_state = "authenticated" if self._access_token else "anonymous"
        return f"NexusClient(base_url={self.base_url!r}, {auth_state})"

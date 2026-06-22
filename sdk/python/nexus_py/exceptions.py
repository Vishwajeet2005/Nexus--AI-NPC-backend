"""
nexus_py.exceptions
────────────────────
Typed exception hierarchy for the Nexus Python SDK.

All SDK methods raise one of these instead of returning raw dicts or
letting an httpx.HTTPStatusError leak through. This means SDK consumers
can write:

    try:
        await nexus.auth.login(username, password)
    except AuthError:
        ...
    except NexusError:
        ...

without ever inspecting status codes or response bodies directly.

Hierarchy:
    NexusError              ← base class for everything the SDK raises
    ├── AuthError            401 Unauthorized, 423 Locked
    ├── SessionError         409 Conflict (session full, locked, ended, etc.)
    ├── NPCError             404 on NPC-specific endpoints
    └── TimeoutError         client-side request timeout (httpx.TimeoutException)

Note: `TimeoutError` here shadows the Python builtin `TimeoutError` within
this module's namespace. It is exported as `nexus_py.TimeoutError` and is
intentionally named to match the spec; SDK consumers should import it
explicitly (`from nexus_py import TimeoutError as NexusTimeoutError`) if
they need to disambiguate from the builtin in their own code.
"""

from __future__ import annotations


class NexusError(Exception):
    """
    Base exception for all Nexus SDK errors.

    Carries the optional machine-readable `code` from the API's
    ErrorResponse envelope (`{"error": ..., "code": ..., "request_id": ...}`)
    alongside the human-readable message.
    """

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code

    def __repr__(self) -> str:
        if self.code:
            return f"{self.__class__.__name__}({self.message!r}, code={self.code!r})"
        return f"{self.__class__.__name__}({self.message!r})"


class AuthError(NexusError):
    """
    Raised for authentication and authorization failures.

    Triggers: HTTP 401 (invalid/expired/missing/revoked token, bad
    credentials) and HTTP 423 (account locked after too many failed logins).
    """
    pass


class SessionError(NexusError):
    """
    Raised for session lifecycle conflicts.

    Triggers: HTTP 409 (session full, already in session, session ended,
    not in session) and HTTP 423 when raised against a session-specific
    endpoint (session locked).
    """
    pass


class NPCError(NexusError):
    """
    Raised for NPC-specific failures.

    Triggers: HTTP 404 on NPC endpoints (NPC not found) and any other
    NPC-domain error the API surfaces with an `NPC_` prefixed code.
    """
    pass


class TimeoutError(NexusError):
    """
    Raised when a request to the Nexus API exceeds the client timeout.

    This is a client-side condition (no response was received in time),
    distinct from the server's own internal LLM timeout handling — an
    NPC interact call that hits the server's 10s LLM timeout still
    returns HTTP 200 with a fallback response, which is NOT this error.
    This error fires only when the SDK's own httpx call times out.
    """
    pass

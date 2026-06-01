"""
api/schemas/auth.py
───────────────────
Pydantic v2 schemas for all authentication endpoints.

Endpoint → schema mapping:
  POST /v1/auth/register   →  RegisterRequest  → PlayerResponse (201)
  POST /v1/auth/login      →  LoginRequest     → TokenResponse  (200)
  POST /v1/auth/refresh    →  RefreshRequest   → TokenResponse  (200)
  POST /v1/auth/logout     →  LogoutRequest    → (204, no body)
  POST /v1/auth/guest      →  (no body)        → PlayerResponse (201)

`PlayerResponse` is also used as the identity payload embedded in token
introspection and session player lists, so it lives here rather than in
a separate identity module.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ── Request schemas ────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    """
    POST /v1/auth/register

    Spec rules enforced here via validators:
    - password must be ≥ 8 characters (422 on failure)
    - email must be a valid format (422 on failure)
    Duplicate username/email → 409, handled in the service layer.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Unique display name. Alphanumeric, underscores, and hyphens only.",
        examples=["vishwajeet"],
    )
    email: EmailStr = Field(
        ...,
        description="Valid email address. Stored lower-cased.",
        examples=["v@example.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Plain-text password. Must be ≥ 8 characters. Hashed with bcrypt before storage.",
        examples=["SecurePass123!"],
    )

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        """Store emails consistently lower-cased to prevent duplicate registrations."""
        return v.lower()


class LoginRequest(BaseModel):
    """POST /v1/auth/login"""

    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="The player's registered username.",
        examples=["vishwajeet"],
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Plain-text password to verify.",
        examples=["SecurePass123!"],
    )


class RefreshRequest(BaseModel):
    """POST /v1/auth/refresh"""

    refresh_token: str = Field(
        ...,
        description="A valid, non-blacklisted refresh JWT previously issued by /auth/login.",
    )


class LogoutRequest(BaseModel):
    """
    POST /v1/auth/logout

    The refresh token is provided in the request body so it can be JTI-blacklisted
    in Redis. The access token is extracted from the Authorization header by the
    `get_current_user` dependency — it is not repeated here.
    """

    refresh_token: str = Field(
        ...,
        description="The refresh token to blacklist. Paired with the Bearer access token in the header.",
    )


# ── Response schemas ───────────────────────────────────────────────────────────

class PlayerResponse(BaseModel):
    """
    Public player identity object.

    Returned by:
    - POST /v1/auth/register (201)
    - POST /v1/auth/guest    (201)
    - Embedded in SessionPlayerResponse

    `password_hash` is never included — the `from_attributes` mode lets us
    construct this directly from an ORM `Player` instance.
    """

    model_config = ConfigDict(
        from_attributes=True,
        frozen=True,
    )

    id: UUID = Field(..., description="Stable player UUID.")
    username: str = Field(..., description="Player's display name.")
    email: str = Field(..., description="Player's email address.")
    is_guest: bool = Field(..., description="True for anonymous guest accounts.")


class TokenResponse(BaseModel):
    """
    JWT token pair returned by /auth/login and /auth/refresh.

    Spec response shape:
    {
      "access_token":  "jwt...",
      "refresh_token": "jwt...",
      "token_type":    "bearer",
      "expires_in":    900        ← access token TTL in seconds
    }
    """

    model_config = ConfigDict(frozen=True)

    access_token: str = Field(..., description="Short-lived JWT for API authentication.")
    refresh_token: str = Field(..., description="Long-lived JWT for obtaining new access tokens.")
    token_type: str = Field(
        default="bearer",
        description="OAuth2 token type. Always 'bearer'.",
    )
    expires_in: int = Field(
        ...,
        gt=0,
        description="Access token lifetime in seconds.",
        examples=[900],
    )


# ── Internal token payload (not exposed via API) ───────────────────────────────

class TokenPayload(BaseModel):
    """
    Decoded JWT payload validated by `dependencies.get_current_user`.

    Spec JWT structure:
      { "sub": player_id, "jti": uuid, "type": "access" | "refresh", "exp": unix_ts }

    This schema is used internally only — it is never serialised to JSON in a
    response. It lives here so services can import it without touching dependencies.py.
    """

    model_config = ConfigDict(frozen=True)

    sub: str = Field(..., description="Subject: the player's UUID as a string.")
    jti: str = Field(..., description="JWT ID: unique token identifier used for blacklisting.")
    type: str = Field(..., description="Token type: 'access' or 'refresh'.")
    exp: int = Field(..., description="Unix timestamp at which the token expires.")

    @field_validator("type")
    @classmethod
    def type_must_be_valid(cls, v: str) -> str:
        if v not in {"access", "refresh"}:
            raise ValueError(f"Token type must be 'access' or 'refresh', got {v!r}")
        return v

    @property
    def player_id(self) -> UUID:
        """Convenience accessor that returns `sub` as a proper UUID."""
        return UUID(self.sub)

"""
api/config.py
─────────────
Central application configuration loaded from environment variables / .env file.
All runtime settings must be sourced from this module — no hardcoded values elsewhere.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, Field, field_validator
# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
   
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Allow extra vars in .env without raising a validation error
        extra="ignore",
        # Case-insensitive env var matching
        case_sensitive=False,
    )

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://nexus:nexus@localhost:5432/nexus",
        description="Full SQLAlchemy async DSN. Must use the asyncpg driver.",
    )

    # ── Redis ──────────────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL used for pub/sub and token blacklisting.",
    )

    # ── JWT / Auth ─────────────────────────────────────────────────────────────
    secret_key: str = Field(
        ...,  # required — no default, must be set
        description="HMAC secret for signing JWTs. Must be ≥32 random bytes in production.",
    )
    access_token_expire_minutes: int = Field(
        default=15,
        ge=1,
        description="Lifetime of access tokens in minutes.",
    )
    refresh_token_expire_days: int = Field(
        default=7,
        ge=1,
        description="Lifetime of refresh tokens in days.",
    )
    algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm. HS256 is the only supported value in Phase 1.",
    )

    # ── Password Hashing ───────────────────────────────────────────────────────
    bcrypt_cost: int = Field(
        default=12,
        ge=4,
        le=31,
        description="bcrypt work factor. 12 is the production minimum.",
    )

    # ── CORS ───────────────────────────────────────────────────────────────────
    cors_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated list of allowed CORS origins.",
    )

    # ── Rate Limiting ──────────────────────────────────────────────────────────
    rate_limit_per_minute: int = Field(
        default=100,
        ge=1,
        description="Sliding-window request cap per IP per minute.",
    )

    # ── Runtime ────────────────────────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Deployment environment. Controls log verbosity and safety checks.",
    )

    # ── Derived / computed properties ─────────────────────────────────────────

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS origins string into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def access_token_expire_seconds(self) -> int:
        """Access token TTL in seconds (used when setting Redis TTLs)."""
        return self.access_token_expire_minutes * 60

    @property
    def refresh_token_expire_seconds(self) -> int:
        """Refresh token TTL in seconds (used when setting Redis TTLs)."""
        return self.refresh_token_expire_days * 24 * 60 * 60

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    # ── Validators ─────────────────────────────────────────────────────────────

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_not_be_default(cls, v: str) -> str:
        """
        Warn loudly if the placeholder secret is used outside development.
        The environment check happens at runtime via the property, but we can
        still enforce a minimum length here regardless of environment.
        """
        if len(v) < 16:
            raise ValueError(
                "SECRET_KEY must be at least 16 characters. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    @field_validator("algorithm")
    @classmethod
    def algorithm_must_be_supported(cls, v: str) -> str:
        supported = {"HS256", "HS384", "HS512"}
        if v not in supported:
            raise ValueError(f"ALGORITHM must be one of {supported}. Got: {v!r}")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton Settings instance.

    Using @lru_cache ensures .env is parsed exactly once per process.
    In tests, call `get_settings.cache_clear()` after patching env vars.
    """
    return Settings()


# Module-level convenience alias — importable directly as `from api.config import settings`
settings: Settings = get_settings()

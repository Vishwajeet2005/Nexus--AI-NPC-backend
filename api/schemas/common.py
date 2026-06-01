"""
api/schemas/common.py
─────────────────────
Shared Pydantic v2 schemas used across all routers.

`ErrorResponse` is the single error envelope returned by the global exception
handler and all deliberate HTTP errors. Every error includes a `request_id`
so support/ops can correlate logs to user-reported incidents.

`PaginatedResponse` is a generic wrapper for list endpoints. Using a TypeVar
keeps it fully type-safe — `PaginatedResponse[SessionResponse]` gives correct
type inference without any extra code.
"""

from __future__ import annotations

from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Generic type parameter for paginated item payloads
T = TypeVar("T")


class ErrorResponse(BaseModel):
    """
    Standard error envelope returned on all 4xx / 5xx responses.

    Fields map directly to the spec's error schema:
      { "error": "Human-readable message", "code": "ERROR_SLUG", "request_id": "uuid" }
    """

    model_config = ConfigDict(
        # Freeze instances — errors should never be mutated after construction.
        frozen=True,
    )

    error: str = Field(
        ...,
        description="Human-readable description of what went wrong.",
        examples=["Account locked due to too many failed login attempts."],
    )
    code: str = Field(
        ...,
        description="Machine-readable error slug in SCREAMING_SNAKE_CASE.",
        examples=["ACCOUNT_LOCKED", "SESSION_FULL", "TOKEN_EXPIRED"],
    )
    request_id: UUID = Field(
        ...,
        description="UUID assigned to this request by the logging middleware. Use for log correlation.",
    )


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic wrapper for paginated list endpoints.

    Usage:
        PaginatedResponse[SessionResponse](
            items=[...],
            total=42,
            page=1,
            page_size=20,
        )
    """

    model_config = ConfigDict(frozen=True)

    items: list[T] = Field(
        ...,
        description="The page of results.",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of items across all pages.",
    )
    page: int = Field(
        ...,
        ge=1,
        description="Current 1-based page number.",
    )
    page_size: int = Field(
        ...,
        ge=1,
        le=100,
        description="Maximum number of items per page.",
    )
    pages: int = Field(
        ...,
        ge=0,
        description="Total number of pages.",
    )

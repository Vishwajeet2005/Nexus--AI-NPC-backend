"""
api/models/base.py
──────────────────
SQLAlchemy 2.0 declarative base and shared mixins.

All ORM models inherit from `Base`. The `TimestampMixin` supplies
`created_at` as a server-side default so the database clock is always
the source of truth — never the application server clock.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Project-wide SQLAlchemy declarative base.

    Using the class-based `DeclarativeBase` (2.0 style) rather than the
    legacy `declarative_base()` factory gives us full Mapped[] type inference
    and plays nicely with mypy / pyright without a plugin.
    """
    pass


class TimestampMixin:
    """
    Adds a `created_at` column with a server-side default of `NOW()`.

    Defined as a plain mixin (not a mapped class) so it can be composed
    into any model without introducing an extra table or join.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=text("NOW()"),
        nullable=False,
        index=True,
        doc="Wall-clock time of row creation, set by the database server.",
    )

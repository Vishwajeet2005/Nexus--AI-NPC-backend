"""
api/models/__init__.py
──────────────────────
Re-exports every ORM model so that:

1. Alembic's `env.py` can do `from api.models import Base` and have the
   full `Base.metadata` populated for autogenerate.

2. Application code can do `from api.models import Player, Session, ...`
   without knowing which sub-module each model lives in.

Import order matters: models that are referenced by FK in others must be
imported first so SQLAlchemy's mapper registry is complete before
relationship resolution occurs at class definition time.
"""

# Base must be imported first — everything else derives from it.
from api.models.base import Base, TimestampMixin  # noqa: F401

# Core identity models (no FK dependencies on other Nexus models)
from api.models.player import Player  # noqa: F401
from api.models.game import Game  # noqa: F401

# Session models (depend on Player and Game)
from api.models.session import Session, SessionPlayer  # noqa: F401

# NPC models (depend on Session and Player)
from api.models.npc import NPC, NPCInteraction  # noqa: F401

# Analytics (depends on Session; player_id has no FK)
from api.models.event import AnalyticsEvent  # noqa: F401

__all__ = [
    "Base",
    "TimestampMixin",
    "Player",
    "Game",
    "Session",
    "SessionPlayer",
    "NPC",
    "NPCInteraction",
    "AnalyticsEvent",
]

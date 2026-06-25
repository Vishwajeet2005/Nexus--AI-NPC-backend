"""
api/routers/analytics.py
──────────────────────────
Analytics events endpoint for the developer dashboard.

Endpoint:
  GET /v1/analytics/events  — paginated query against the analytics_events table
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_db
from api.models.event import AnalyticsEvent
from api.models.player import Player

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get(
    "/events",
    summary="Query analytics events",
    responses={200: {"description": "Paginated analytics events"}},
)
async def get_analytics_events(
    session_id: Optional[UUID] = Query(None, description="Filter by session UUID"),
    event_type: Optional[str] = Query(None, description="Filter by event type string"),
    from_ts: Optional[datetime] = Query(None, alias="from", description="ISO 8601 start timestamp"),
    to_ts: Optional[datetime] = Query(None, alias="to", description="ISO 8601 end timestamp"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _current_user: Player = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return paginated analytics events from the `analytics_events` table.

    All filters are optional and combinable. Results are ordered by
    `created_at` descending (most recent first).
    """
    from sqlalchemy import func

    q = select(AnalyticsEvent)

    if session_id is not None:
        q = q.where(AnalyticsEvent.session_id == session_id)
    if event_type is not None:
        q = q.where(AnalyticsEvent.event_type == event_type)
    if from_ts is not None:
        q = q.where(AnalyticsEvent.created_at >= from_ts)
    if to_ts is not None:
        q = q.where(AnalyticsEvent.created_at <= to_ts)

    # Total count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Paginated results
    results = (
        await db.execute(
            q.order_by(AnalyticsEvent.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    return {
        "events": [
            {
                "id": str(e.id),
                "session_id": str(e.session_id) if e.session_id else None,
                "player_id": str(e.player_id) if e.player_id else None,
                "event_type": e.event_type,
                "properties": e.properties,
                "created_at": e.created_at.isoformat(),
            }
            for e in results
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }

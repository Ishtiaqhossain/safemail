import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.auth import get_current_parent
from app.models.parent import Parent
from app.models.child import Child
from app.models.weekly_stats import WeeklyStats

router = APIRouter(tags=["stats"])


@router.get("/children/{child_id}/stats")
async def get_stats(
    child_id: str,
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
    week: date = Query(default=None),
):
    result = await db.execute(
        select(Child).where(Child.id == uuid.UUID(child_id), Child.parent_id == current_parent.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")

    if week is None:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).date()
        week = today - __import__("datetime").timedelta(days=today.weekday() + 1)

    result = await db.execute(
        select(WeeklyStats).where(
            WeeklyStats.child_id == uuid.UUID(child_id),
            WeeklyStats.week_start == week,
        )
    )
    stats = result.scalar_one_or_none()

    if not stats:
        return {
            "week_start": str(week),
            "total_emails": 0,
            "emails_scanned": 0,
            "alerts_by_severity": {},
            "alerts_by_category": {},
            "top_senders": [],
        }

    return {
        "week_start": str(stats.week_start),
        "total_emails": stats.total_emails,
        "emails_scanned": stats.emails_scanned,
        "alerts_by_severity": stats.alerts_by_severity,
        "alerts_by_category": stats.alerts_by_category,
        "top_senders": stats.top_senders,
    }

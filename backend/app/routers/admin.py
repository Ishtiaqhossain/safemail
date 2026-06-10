from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.database import get_db
from app.auth import get_current_admin
from app.models.parent import Parent
from app.models.child import Child
from app.models.gmail_connection import GmailConnection
from app.models.alert import Alert
from app.models.task_log import TaskLog

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
async def overview(
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    now = datetime.now(timezone.utc)

    # System counts
    total_parents = (await db.execute(select(func.count()).select_from(Parent))).scalar()
    total_children = (await db.execute(select(func.count()).select_from(Child))).scalar()

    conn_counts = (await db.execute(
        select(GmailConnection.status, func.count().label("n"))
        .group_by(GmailConnection.status)
    )).all()
    connections_by_status = {row.status: row.n for row in conn_counts}

    # Stale active connections (not synced in >1 hour)
    stale_cutoff = now - timedelta(hours=1)
    stale_rows = (await db.execute(
        select(GmailConnection.gmail_address, GmailConnection.last_synced_at, Child.display_name)
        .join(Child, Child.id == GmailConnection.child_id)
        .where(
            GmailConnection.status == "active",
            GmailConnection.last_synced_at < stale_cutoff,
        )
    )).all()
    stale_connections = [
        {"gmail_address": r.gmail_address, "child_name": r.display_name,
         "last_synced_at": r.last_synced_at.isoformat() if r.last_synced_at else None}
        for r in stale_rows
    ]

    # Alert counts by period and severity
    async def alert_counts(since: datetime):
        rows = (await db.execute(
            select(Alert.severity, func.count().label("n"))
            .where(Alert.created_at >= since)
            .group_by(Alert.severity)
        )).all()
        return {r.severity: r.n for r in rows}

    alerts_24h = await alert_counts(now - timedelta(hours=24))
    alerts_7d = await alert_counts(now - timedelta(days=7))
    alerts_30d = await alert_counts(now - timedelta(days=30))

    # False positive rate
    fp_row = (await db.execute(
        select(
            func.count().filter(Alert.parent_feedback == "false_positive").label("fp"),
            func.count().filter(Alert.parent_feedback.isnot(None)).label("total"),
        )
    )).one()
    false_positive_rate = (fp_row.fp / fp_row.total) if fp_row.total else None

    # Recent task failures
    failures = (await db.execute(
        select(TaskLog)
        .where(TaskLog.status == "failure")
        .order_by(TaskLog.created_at.desc())
        .limit(10)
    )).scalars().all()
    recent_failures = [
        {"task_name": t.task_name, "error": t.error,
         "created_at": t.created_at.isoformat(), "meta": t.meta}
        for t in failures
    ]

    return {
        "system": {
            "total_parents": total_parents,
            "total_children": total_children,
            "connections_by_status": connections_by_status,
        },
        "stale_connections": stale_connections,
        "alerts": {
            "last_24h": alerts_24h,
            "last_7d": alerts_7d,
            "last_30d": alerts_30d,
        },
        "false_positive_rate": false_positive_rate,
        "recent_failures": recent_failures,
    }


@router.get("/events")
async def events(
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
):
    # Collect events from multiple tables, merge, paginate in Python
    alert_rows = (await db.execute(
        select(Alert.id, Alert.created_at, Alert.severity, Alert.category, Child.display_name)
        .join(Child, Child.id == Alert.child_id)
        .order_by(Alert.created_at.desc())
        .limit(500)
    )).all()

    conn_rows = (await db.execute(
        select(GmailConnection.id, GmailConnection.created_at, GmailConnection.gmail_address,
               GmailConnection.status, Child.display_name)
        .join(Child, Child.id == GmailConnection.child_id)
        .order_by(GmailConnection.created_at.desc())
        .limit(200)
    )).all()

    task_rows = (await db.execute(
        select(TaskLog)
        .order_by(TaskLog.created_at.desc())
        .limit(500)
    )).scalars().all()

    feed = []
    for r in alert_rows:
        feed.append({
            "type": "alert",
            "ts": r.created_at,
            "description": f"Alert ({r.severity}/{r.category}) created for {r.display_name}",
        })
    for r in conn_rows:
        feed.append({
            "type": "gmail_connection",
            "ts": r.created_at,
            "description": f"Gmail {r.gmail_address} connected for {r.display_name} (status: {r.status})",
        })
    for t in task_rows:
        feed.append({
            "type": "task",
            "ts": t.created_at,
            "description": f"Task {t.task_name}: {t.status}"
                           + (f" — {t.error[:120]}" if t.error else ""),
        })

    feed.sort(key=lambda x: x["ts"], reverse=True)

    total = len(feed)
    offset = (page - 1) * per_page
    page_items = feed[offset: offset + per_page]

    return {
        "data": [
            {"type": e["type"], "ts": e["ts"].isoformat(), "description": e["description"]}
            for e in page_items
        ],
        "meta": {"total": total, "page": page, "per_page": per_page},
    }


@router.get("/tasks")
async def tasks(
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    status: str | None = Query(None),
):
    filters = []
    if status:
        filters.append(TaskLog.status == status)

    total = (await db.execute(
        select(func.count()).select_from(TaskLog).where(and_(*filters) if filters else True)
    )).scalar()

    rows = (await db.execute(
        select(TaskLog)
        .where(and_(*filters) if filters else True)
        .order_by(TaskLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )).scalars().all()

    return {
        "data": [
            {
                "id": str(t.id),
                "task_name": t.task_name,
                "status": t.status,
                "error": t.error,
                "duration_ms": t.duration_ms,
                "meta": t.meta,
                "created_at": t.created_at.isoformat(),
            }
            for t in rows
        ],
        "meta": {"total": total, "page": page, "per_page": per_page},
    }

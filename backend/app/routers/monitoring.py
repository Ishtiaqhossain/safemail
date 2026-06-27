import uuid
from datetime import datetime, timezone
from typing import Annotated

import redis
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.auth import get_current_admin
from app.models.parent import Parent
from app.models.gmail_connection import GmailConnection
from app.models.health_incident import HealthIncident
from app.models.task_log import TaskLog
from app.services.remediation import (
    resolve_auto_remediation, get_auto_remediation_override, set_auto_remediation_override,
)

_FIX_TOOLS = {"requeue_gmail_polling", "poll_connection_now"}

router = APIRouter(prefix="/monitoring", tags=["monitoring"])
settings = get_settings()


def _incident_dict(inc: HealthIncident) -> dict:
    return {
        "id": str(inc.id),
        "fingerprint": inc.fingerprint,
        "check_name": inc.check_name,
        "severity": inc.severity,
        "status": inc.status,
        "title": inc.title,
        "detail": inc.detail,
        "metrics": inc.metrics,
        "diagnosis": inc.diagnosis,
        "remediation_status": inc.remediation_status,
        "remediation": inc.remediation,
        "times_seen": inc.times_seen,
        "alerted_at": inc.alerted_at.isoformat() if inc.alerted_at else None,
        "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
        "created_at": inc.created_at.isoformat(),
        "updated_at": inc.updated_at.isoformat(),
    }


@router.get("/health")
async def health(
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Live system-health snapshot for the monitoring console."""
    # Redis liveness + queue depth (sync client, mirrors the developer router).
    redis_ok = True
    queue_depth = None
    client = redis.from_url(settings.redis_url)
    try:
        client.ping()
        queue_depth = client.llen("celery")
    except Exception:
        redis_ok = False
    auto_remediation = resolve_auto_remediation(client)

    conn_counts = (await db.execute(
        select(GmailConnection.status, func.count().label("n")).group_by(GmailConnection.status)
    )).all()
    connections_by_status = {row.status: row.n for row in conn_counts}

    open_rows = (await db.execute(
        select(HealthIncident.severity, func.count().label("n"))
        .where(HealthIncident.status == "open")
        .group_by(HealthIncident.severity)
    )).all()
    open_by_severity = {row.severity: row.n for row in open_rows}

    last_cycle_row = (await db.execute(
        select(TaskLog)
        .where(TaskLog.task_name == "run_monitoring_cycle")
        .order_by(TaskLog.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    last_cycle = None
    if last_cycle_row:
        last_cycle = {
            "status": last_cycle_row.status,
            "created_at": last_cycle_row.created_at.isoformat(),
            "meta": last_cycle_row.meta,
            "error": last_cycle_row.error,
        }

    if not redis_ok or open_by_severity.get("critical"):
        overall = "critical"
    elif open_by_severity.get("warning"):
        overall = "warning"
    else:
        overall = "ok"

    return {
        "overall_status": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "monitoring_enabled": settings.monitoring_enabled,
        "auto_remediation_enabled": auto_remediation,
        "redis_ok": redis_ok,
        "queue_depth": queue_depth,
        "connections_by_status": connections_by_status,
        "open_incidents_by_severity": open_by_severity,
        "last_cycle": last_cycle,
    }


@router.get("/incidents")
async def list_incidents(
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
):
    where = []
    if status:
        where.append(HealthIncident.status == status)

    total = (await db.execute(
        select(func.count()).select_from(HealthIncident).where(*where)
    )).scalar()

    rows = (await db.execute(
        select(HealthIncident)
        .where(*where)
        .order_by(HealthIncident.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )).scalars().all()

    return {
        "data": [_incident_dict(r) for r in rows],
        "meta": {"total": total, "page": page, "per_page": per_page},
    }


@router.get("/incidents/{incident_id}")
async def get_incident(
    incident_id: str,
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    inc = await db.get(HealthIncident, uuid.UUID(incident_id))
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return _incident_dict(inc)


@router.post("/run", status_code=202)
async def run_now(
    _: Annotated[Parent, Depends(get_current_admin)],
):
    """Manually trigger a monitoring cycle (enqueues the Celery task)."""
    from app.tasks.monitoring import run_monitoring_cycle
    run_monitoring_cycle.delay()
    return {"status": "enqueued"}


# ── Agent control pane ──────────────────────────────────────────────────────────

def _auto_state(client) -> dict:
    return {
        "effective": resolve_auto_remediation(client),
        "override": get_auto_remediation_override(client),  # True/False/None
        "env_default": settings.auto_remediation_enabled,
    }


@router.get("/agent")
async def agent_status(
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Agent control pane: effective config, run history, and aggregate stats.

    Built entirely from the remediation result already persisted on each
    HealthIncident — no new infrastructure, no data leaving the box.
    """
    client = redis.from_url(settings.redis_url)

    # Incidents the agent has acted on (remediation result present). Volume is low
    # (incidents are deduped), so aggregate in Python. Cap for safety.
    rows = (await db.execute(
        select(HealthIncident)
        .where(HealthIncident.remediation.isnot(None))
        .order_by(HealthIncident.updated_at.desc())
        .limit(500)
    )).scalars().all()

    by_status: dict[str, int] = {}
    by_mode: dict[str, int] = {}
    total_cost = 0.0
    total_fix_actions = 0
    for r in rows:
        rem = r.remediation or {}
        st = r.remediation_status or rem.get("status") or "unknown"
        by_status[st] = by_status.get(st, 0) + 1
        mode = rem.get("mode") or "unknown"
        by_mode[mode] = by_mode.get(mode, 0) + 1
        total_cost += float(rem.get("cost_usd") or 0.0)
        for a in (rem.get("actions") or []):
            res = a.get("result")
            if a.get("tool") in _FIX_TOOLS and not (isinstance(res, dict) and res.get("error")):
                total_fix_actions += 1

    last_cycle_row = (await db.execute(
        select(TaskLog)
        .where(TaskLog.task_name == "run_monitoring_cycle")
        .order_by(TaskLog.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    last_cycle = None
    if last_cycle_row:
        last_cycle = {
            "status": last_cycle_row.status,
            "created_at": last_cycle_row.created_at.isoformat(),
            "meta": last_cycle_row.meta,
            "error": last_cycle_row.error,
        }

    runs = []
    for r in rows[:30]:
        rem = r.remediation or {}
        runs.append({
            "incident_id": str(r.id),
            "title": r.title,
            "check_name": r.check_name,
            "severity": r.severity,
            "incident_status": r.status,
            "mode": rem.get("mode"),
            "remediation_status": r.remediation_status,
            "turns": rem.get("turns"),
            "cost_usd": rem.get("cost_usd"),
            "diagnosis": r.diagnosis,
            "actions": rem.get("actions") or [],
            "created_at": r.created_at.isoformat(),
        })

    return {
        "monitoring_enabled": settings.monitoring_enabled,
        "monitoring_interval_minutes": settings.monitoring_interval_minutes,
        "model": "claude-sonnet-4-6",
        "auto_remediation": _auto_state(client),
        "last_cycle": last_cycle,
        "stats": {
            "total_runs": len(rows),
            "by_status": by_status,
            "by_mode": by_mode,
            "total_fix_actions": total_fix_actions,
            "total_cost_usd": round(total_cost, 4),
        },
        "runs": runs,
    }


class AutoRemediationUpdate(BaseModel):
    enabled: bool | None  # true/false to pin; null to clear (revert to env default)


@router.post("/agent/auto-remediation")
async def set_auto_remediation(
    body: AutoRemediationUpdate,
    _: Annotated[Parent, Depends(get_current_admin)],
):
    """Flip the live auto-remediation switch (admin only). Enabling it lets the
    agent take bounded fix actions on new incidents."""
    client = redis.from_url(settings.redis_url)
    set_auto_remediation_override(client, body.enabled)
    return _auto_state(client)


class IncidentStatusUpdate(BaseModel):
    status: str  # "acknowledged" | "resolved" | "open"


@router.post("/incidents/{incident_id}/status")
async def set_incident_status(
    incident_id: str,
    body: IncidentStatusUpdate,
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Manually acknowledge / resolve / reopen an incident."""
    if body.status not in ("open", "acknowledged", "resolved"):
        raise HTTPException(status_code=422, detail="Invalid status.")
    inc = await db.get(HealthIncident, uuid.UUID(incident_id))
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found.")
    inc.status = body.status
    inc.resolved_at = datetime.now(timezone.utc) if body.status == "resolved" else None
    await db.commit()
    await db.refresh(inc)
    return _incident_dict(inc)

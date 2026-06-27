import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_admin, decode_token
from app.models.parent import Parent
from app.services.analytics_events import (
    _build_event, MAX_BATCH,
    compute_overview, compute_acquisition_funnel, compute_activation_funnel,
    compute_events_breakdown,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ── Public ingestion ─────────────────────────────────────────────────────────────

class ClientEvent(BaseModel):
    name: str
    path: str | None = None
    referrer: str | None = None
    utm: dict | None = None
    properties: dict | None = None


class CollectBatch(BaseModel):
    visitor_id: str
    session_id: str | None = None
    events: list[ClientEvent]


def _parent_from_auth(authorization: str | None) -> uuid.UUID | None:
    """Best-effort stitch: if a valid access token rides along, link events to the
    parent. The endpoint stays public, so a missing/invalid token is fine."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        payload = decode_token(authorization.split(" ", 1)[1])
        if payload.get("type") not in (None, "access"):
            return None
        return uuid.UUID(payload["sub"])
    except Exception:
        return None


@router.post("/collect", status_code=202)
async def collect(
    batch: CollectBatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
):
    """Anonymous, first-party event ingestion. No auth required (pre-login visitors
    send events too). Validates names against the allowlist; unknown names are
    dropped. No PII is accepted or stored."""
    parent_id = _parent_from_auth(authorization)
    accepted = 0
    for e in batch.events[:MAX_BATCH]:
        ev = _build_event(
            e.name, visitor_id=batch.visitor_id, source="client",
            session_id=batch.session_id, parent_id=parent_id,
            path=e.path, referrer=e.referrer, utm=e.utm, properties=e.properties,
        )
        if ev is not None:
            db.add(ev)
            accepted += 1
    if accepted:
        await db.commit()
    return {"accepted": accepted, "received": len(batch.events)}


# ── Admin read API ───────────────────────────────────────────────────────────────

def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@router.get("/overview")
async def overview(
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(30, ge=1, le=365),
):
    since = _since(days)
    return {
        "window_days": days,
        **(await compute_overview(db, since)),
        "acquisition_funnel": await compute_acquisition_funnel(db, since),
    }


@router.get("/funnel")
async def funnel(
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(30, ge=1, le=365),
):
    since = _since(days)
    return {
        "window_days": days,
        "acquisition": await compute_acquisition_funnel(db, since),
        "activation": await compute_activation_funnel(db, since),
    }


@router.get("/events")
async def events(
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(30, ge=1, le=365),
):
    since = _since(days)
    return {"window_days": days, **(await compute_events_breakdown(db, since))}

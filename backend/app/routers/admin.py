import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, cast, Integer, Float

from app.config import get_settings
from app.database import get_db
from app.auth import get_current_admin
from app.models.parent import Parent
from app.models.child import Child
from app.models.gmail_connection import GmailConnection
from app.models.alert import Alert
from app.models.task_log import TaskLog
from app.models.allowed_email import AllowedEmail
from app.models.waitlist_entry import WaitlistEntry
from app.services.analysis import (
    CASCADE_MODELS, INPUT_TOKEN_PRICE_PER_M, OUTPUT_TOKEN_PRICE_PER_M,
)
from app.services.allowlist import normalize_email

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()

# Tasks whose task_log.meta carries Claude token usage.
LLM_TASK_NAMES = ["analyze_message", "playground_classify"]


async def _llm_usage(db: AsyncSession, since: datetime | None = None) -> dict:
    # Only count rows that carry token data, so logs written before token
    # tracking existed don't show up as zero-cost calls.
    input_tok_col = cast(TaskLog.meta["input_tokens"].astext, Integer)
    output_tok_col = cast(TaskLog.meta["output_tokens"].astext, Integer)
    # Prefer the per-call cost stored on each row (cascade-aware — a Haiku-only
    # triage is priced at Haiku rates). Fall back to an escalation-model-rate
    # estimate for rows logged before cost tracking existed.
    cost_col = cast(TaskLog.meta["cost_usd"].astext, Float)
    est_cost = (
        input_tok_col / 1_000_000.0 * INPUT_TOKEN_PRICE_PER_M
        + output_tok_col / 1_000_000.0 * OUTPUT_TOKEN_PRICE_PER_M
    )
    filters = [
        TaskLog.task_name.in_(LLM_TASK_NAMES),
        TaskLog.status == "success",
        input_tok_col.isnot(None),
    ]
    if since:
        filters.append(TaskLog.created_at >= since)

    row = (await db.execute(
        select(
            func.count().label("calls"),
            func.coalesce(func.sum(input_tok_col), 0).label("input_tokens"),
            func.coalesce(func.sum(output_tok_col), 0).label("output_tokens"),
            func.coalesce(func.sum(func.coalesce(cost_col, est_cost)), 0.0).label("cost_usd"),
        ).where(and_(*filters))
    )).one()

    return {
        "calls": row.calls,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "cost_usd": round(row.cost_usd or 0.0, 4),
    }


@router.get("/llm-stats")
async def llm_stats(
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    now = datetime.now(timezone.utc)
    return {
        "model": "+".join(CASCADE_MODELS),
        "pricing": {
            "input_per_million": INPUT_TOKEN_PRICE_PER_M,
            "output_per_million": OUTPUT_TOKEN_PRICE_PER_M,
        },
        "last_7d": await _llm_usage(db, now - timedelta(days=7)),
        "last_30d": await _llm_usage(db, now - timedelta(days=30)),
        "all_time": await _llm_usage(db),
    }


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


# ── Invite-only allowlist ──────────────────────────────────────────────────────

class AllowlistAddRequest(BaseModel):
    email: EmailStr
    note: str | None = None


def _allowlist_entry(row: AllowedEmail) -> dict:
    return {
        "id": str(row.id),
        "email": row.email,
        "note": row.note,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/allowlist")
async def list_allowlist(
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    rows = (await db.execute(
        select(AllowedEmail).order_by(AllowedEmail.created_at.desc())
    )).scalars().all()
    return {"data": [_allowlist_entry(r) for r in rows]}


@router.post("/allowlist", status_code=201)
async def add_allowlist(
    body: AllowlistAddRequest,
    admin: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    email = normalize_email(body.email)
    existing = (await db.execute(
        select(AllowedEmail).where(func.lower(AllowedEmail.email) == email)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email is already on the allowlist.")

    entry = AllowedEmail(email=email, note=body.note, added_by=admin.id)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _allowlist_entry(entry)


@router.delete("/allowlist/{entry_id}", status_code=204)
async def remove_allowlist(
    entry_id: str,
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    entry = await db.get(AllowedEmail, uuid.UUID(entry_id))
    if not entry:
        raise HTTPException(status_code=404, detail="Allowlist entry not found.")
    await db.delete(entry)
    await db.commit()


# ── Waitlist (public landing-page invite requests) ─────────────────────────────

def _waitlist_entry(row: WaitlistEntry) -> dict:
    return {
        "id": str(row.id),
        "email": row.email,
        "source": row.source,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/waitlist")
async def list_waitlist(
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    rows = (await db.execute(
        select(WaitlistEntry).order_by(WaitlistEntry.created_at.desc())
    )).scalars().all()
    return {"data": [_waitlist_entry(r) for r in rows]}


@router.post("/waitlist/{entry_id}/approve", status_code=201)
async def approve_waitlist(
    entry_id: str,
    admin: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Promote a waitlist entry to the allowlist, then drop it from the waitlist.

    After this the email can register while invite-only mode is on. Idempotent
    against an email that is already allowlisted (we just clear the waitlist row).
    """
    entry = await db.get(WaitlistEntry, uuid.UUID(entry_id))
    if not entry:
        raise HTTPException(status_code=404, detail="Waitlist entry not found.")

    email = normalize_email(entry.email)
    already = (await db.execute(
        select(AllowedEmail).where(func.lower(AllowedEmail.email) == email)
    )).scalar_one_or_none()
    if not already:
        db.add(AllowedEmail(email=email, note="approved from waitlist", added_by=admin.id))

    await db.delete(entry)
    await db.commit()
    return {"status": "approved", "email": email}


@router.delete("/waitlist/{entry_id}", status_code=204)
async def remove_waitlist(
    entry_id: str,
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    entry = await db.get(WaitlistEntry, uuid.UUID(entry_id))
    if not entry:
        raise HTTPException(status_code=404, detail="Waitlist entry not found.")
    await db.delete(entry)
    await db.commit()


# ── Feedback insights (parent feedback → classifier calibration) ───────────────

@router.get("/feedback-insights")
async def feedback_insights(
    _: Annotated[Parent, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Turn parent feedback into a calibration signal for the classifier.

    Raw email bodies are never stored, so feedback (correct | false_positive) is
    the highest-quality real-world signal we have. Per category we report the
    confirmed false-positive rate and the confidence distribution of FPs vs true
    positives — directly actionable for tuning CONFIDENCE_THRESHOLD (globally or
    per category) and for spotting which categories over-fire.
    """
    rows = (await db.execute(
        select(Alert.category, Alert.confidence, Alert.parent_feedback)
        .where(
            Alert.parent_feedback.isnot(None),
            ~Alert.gmail_message_id.like("fake_%"),
        )
    )).all()

    threshold = settings.confidence_threshold
    by_cat: dict[str, dict] = {}
    total_fp = total_correct = fp_above_threshold = 0

    for cat, confidence, feedback in rows:
        conf = float(confidence)
        b = by_cat.setdefault(cat, {"correct": 0, "false_positive": 0,
                                    "fp_conf_sum": 0.0, "tp_conf_sum": 0.0})
        if feedback == "false_positive":
            b["false_positive"] += 1
            b["fp_conf_sum"] += conf
            total_fp += 1
            if conf >= threshold:
                fp_above_threshold += 1
        elif feedback == "correct":
            b["correct"] += 1
            b["tp_conf_sum"] += conf
            total_correct += 1

    categories = []
    for cat, b in sorted(by_cat.items()):
        labeled = b["correct"] + b["false_positive"]
        fp, tp = b["false_positive"], b["correct"]
        categories.append({
            "category": cat,
            "labeled": labeled,
            "correct": tp,
            "false_positive": fp,
            "fp_rate": round(fp / labeled, 3) if labeled else None,
            "avg_fp_confidence": round(b["fp_conf_sum"] / fp, 3) if fp else None,
            "avg_correct_confidence": round(b["tp_conf_sum"] / tp, 3) if tp else None,
        })

    total_labeled = total_fp + total_correct
    return {
        "confidence_threshold": threshold,
        "overall": {
            "labeled": total_labeled,
            "correct": total_correct,
            "false_positive": total_fp,
            "precision": round(total_correct / total_labeled, 3) if total_labeled else None,
            # FPs that cleared the threshold — these are the alerts a higher bar
            # would have suppressed, the main lever for cutting false positives.
            "false_positives_above_threshold": fp_above_threshold,
        },
        "by_category": categories,
    }

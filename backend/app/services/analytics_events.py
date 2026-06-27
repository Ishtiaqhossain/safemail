"""First-party product-analytics: the event allowlist, recording helpers, and the
funnel/overview computations.

Privacy: events never contain PII (no IP, email, child data, or email content) —
see docs/analytics-spec.md. Names are a fixed allowlist so the data stays clean
(dynamic values go in ``properties``, never in the name).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, distinct, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.analytics_event import AnalyticsEvent
from app.models.parent import Parent
from app.models.child import Child
from app.models.gmail_connection import GmailConnection
from app.models.alert import Alert

logger = logging.getLogger(__name__)

# ── The taxonomy (object_action, snake_case). Names outside this set are dropped.
ALLOWED_EVENTS = {
    # Acquisition
    "page_viewed", "landing_cta_clicked", "waitlist_joined", "waitlist_already_invited",
    # Signup
    "account_registered",
    # Activation
    "email_verified", "onboarding_step_viewed", "consent_given", "child_added",
    "gmail_connect_initiated", "gmail_connected", "gmail_connect_skipped",
    "onboarding_completed",
    # Engagement
    "alerts_viewed", "alert_viewed", "alert_feedback_given",
    # Retention / churn
    "login_succeeded", "gmail_disconnected", "account_deleted",
}

MAX_BATCH = 50
MAX_STR = 512
MAX_PROPS_BYTES = 4000


def _clip(v, n=MAX_STR):
    if v is None:
        return None
    s = str(v)
    return s[:n]


def _build_event(event_name, *, visitor_id, source, session_id=None, parent_id=None,
                 path=None, referrer=None, utm=None, properties=None) -> AnalyticsEvent | None:
    if event_name not in ALLOWED_EVENTS:
        return None
    return AnalyticsEvent(
        event_name=event_name,
        visitor_id=_clip(visitor_id) or "unknown",
        session_id=_clip(session_id),
        parent_id=parent_id,
        path=_clip(path),
        referrer=_clip(referrer),
        utm=utm if isinstance(utm, dict) else None,
        source=source,
        properties=properties if isinstance(properties, dict) else None,
        created_at=datetime.now(timezone.utc),
    )


async def record_event_async(db: AsyncSession, event_name: str, *, parent_id=None,
                             properties=None, visitor_id=None, source="server") -> None:
    """Best-effort server-side event from an async router. Never raises — analytics
    must not break the user action that triggered it. Commits its own row."""
    try:
        ev = _build_event(
            event_name,
            visitor_id=visitor_id or (f"server:{parent_id}" if parent_id else "server"),
            source=source, parent_id=parent_id, properties=properties,
        )
        if ev is None:
            logger.warning("Dropping unknown analytics event: %s", event_name)
            return
        db.add(ev)
        await db.commit()
    except Exception:
        logger.exception("record_event_async failed for %s", event_name)


def record_event_sync(db: Session, event_name: str, *, parent_id=None,
                      properties=None, visitor_id=None, source="server") -> None:
    """Best-effort server-side event from a sync (Celery) context."""
    try:
        ev = _build_event(
            event_name,
            visitor_id=visitor_id or (f"server:{parent_id}" if parent_id else "server"),
            source=source, parent_id=parent_id, properties=properties,
        )
        if ev is None:
            return
        db.add(ev)
        db.commit()
    except Exception:
        logger.exception("record_event_sync failed for %s", event_name)


# ── Read-side computations ───────────────────────────────────────────────────────

async def _count(db: AsyncSession, stmt) -> int:
    return (await db.execute(stmt)).scalar() or 0


async def _event_count(db: AsyncSession, name: str, since: datetime) -> int:
    return await _count(db, select(func.count()).select_from(AnalyticsEvent)
                        .where(AnalyticsEvent.event_name == name, AnalyticsEvent.created_at >= since))


async def _unique_visitors(db: AsyncSession, since: datetime) -> int:
    return await _count(db, select(func.count(distinct(AnalyticsEvent.visitor_id)))
                        .where(AnalyticsEvent.event_name == "page_viewed",
                               AnalyticsEvent.created_at >= since))


def _with_steps(stages: list[dict]) -> list[dict]:
    """Annotate ordered stages with step conversion and drop-off vs the previous,
    and overall conversion vs the first stage."""
    top = stages[0]["count"] if stages and stages[0]["count"] else 0
    out = []
    for i, s in enumerate(stages):
        prev = stages[i - 1]["count"] if i > 0 else None
        step_conv = round(s["count"] / prev, 4) if prev else (1.0 if i == 0 else None)
        out.append({
            **s,
            "step_conversion": step_conv,
            "drop_off": round(1 - step_conv, 4) if step_conv is not None and i > 0 else 0.0,
            "overall_conversion": round(s["count"] / top, 4) if top else None,
        })
    return out


async def compute_acquisition_funnel(db: AsyncSession, since: datetime) -> list[dict]:
    """Top-of-funnel from client/server events, windowed by event time."""
    stages = [
        {"key": "visitors", "label": "Unique visitors", "count": await _unique_visitors(db, since)},
        {"key": "waitlist", "label": "Joined waitlist", "count": await _event_count(db, "waitlist_joined", since)},
        {"key": "registered", "label": "Registered", "count": await _event_count(db, "account_registered", since)},
    ]
    return _with_steps(stages)


async def compute_activation_funnel(db: AsyncSession, since: datetime) -> dict:
    """Single-cohort funnel over parents created in the window — checks how far each
    got regardless of when. Computed from existing timestamps, so it's accurate for
    existing users without waiting on instrumentation."""
    base = Parent.created_at >= since

    registered = await _count(db, select(func.count()).select_from(Parent).where(base))
    verified = await _count(db, select(func.count()).select_from(Parent)
                            .where(base, Parent.is_email_verified.is_(True)))
    consented = await _count(db, select(func.count()).select_from(Parent)
                             .where(base, Parent.monitoring_consent_at.isnot(None)))
    child_added = await _count(db, select(func.count(distinct(Parent.id)))
                               .select_from(Parent).join(Child, Child.parent_id == Parent.id)
                               .where(base))
    gmail_connected = await _count(db, select(func.count(distinct(Parent.id)))
                                   .select_from(Parent).join(Child, Child.parent_id == Parent.id)
                                   .join(GmailConnection, GmailConnection.child_id == Child.id)
                                   .where(base))
    onboarded = await _count(db, select(func.count()).select_from(Parent)
                             .where(base, Parent.onboarding_completed_at.isnot(None)))
    first_alert = await _count(db, select(func.count(distinct(Parent.id)))
                               .select_from(Parent).join(Child, Child.parent_id == Parent.id)
                               .join(Alert, Alert.child_id == Child.id)
                               .where(base, ~Alert.gmail_message_id.like("fake_%")))

    stages = _with_steps([
        {"key": "registered", "label": "Registered", "count": registered},
        {"key": "verified", "label": "Email verified", "count": verified},
        {"key": "consented", "label": "Consent given", "count": consented},
        {"key": "child_added", "label": "Added a child", "count": child_added},
        {"key": "gmail_connected", "label": "Connected Gmail", "count": gmail_connected},
        {"key": "onboarded", "label": "Onboarding completed", "count": onboarded},
        {"key": "first_alert", "label": "Received first alert", "count": first_alert},
    ])

    # Time-to-value: median seconds from signup to onboarding completion.
    ttv_secs = await db.scalar(
        select(func.percentile_cont(0.5).within_group(
            func.extract("epoch", Parent.onboarding_completed_at - Parent.created_at)
        )).where(base, Parent.onboarding_completed_at.isnot(None))
    )

    return {
        "stages": stages,
        "time_to_value_seconds": float(ttv_secs) if ttv_secs is not None else None,
        "activation_rate": round(gmail_connected / registered, 4) if registered else None,
    }


async def compute_overview(db: AsyncSession, since: datetime) -> dict:
    registered = await _count(db, select(func.count()).select_from(Parent).where(Parent.created_at >= since))
    activated = await _count(db, select(func.count(distinct(Parent.id)))
                             .select_from(Parent).join(Child, Child.parent_id == Parent.id)
                             .join(GmailConnection, GmailConnection.child_id == Child.id)
                             .where(Parent.created_at >= since))
    return {
        "unique_visitors": await _unique_visitors(db, since),
        "page_views": await _event_count(db, "page_viewed", since),
        "waitlist_joined": await _event_count(db, "waitlist_joined", since),
        "signups": registered,
        "activated": activated,
        "activation_rate": round(activated / registered, 4) if registered else None,
        "logins": await _event_count(db, "login_succeeded", since),
        "account_deletions": await _event_count(db, "account_deleted", since),
    }


async def compute_events_breakdown(db: AsyncSession, since: datetime) -> dict:
    by_name = (await db.execute(
        select(AnalyticsEvent.event_name, func.count().label("n"))
        .where(AnalyticsEvent.created_at >= since)
        .group_by(AnalyticsEvent.event_name).order_by(func.count().desc())
    )).all()

    top_paths = (await db.execute(
        select(AnalyticsEvent.path, func.count().label("n"))
        .where(AnalyticsEvent.event_name == "page_viewed",
               AnalyticsEvent.created_at >= since, AnalyticsEvent.path.isnot(None))
        .group_by(AnalyticsEvent.path).order_by(func.count().desc()).limit(15)
    )).all()

    top_referrers = (await db.execute(
        select(AnalyticsEvent.referrer, func.count().label("n"))
        .where(AnalyticsEvent.created_at >= since, AnalyticsEvent.referrer.isnot(None))
        .group_by(AnalyticsEvent.referrer).order_by(func.count().desc()).limit(15)
    )).all()

    # Daily page-view + signup timeseries.
    daily = (await db.execute(
        select(
            func.date_trunc("day", AnalyticsEvent.created_at).label("day"),
            func.count().filter(AnalyticsEvent.event_name == "page_viewed").label("page_views"),
            func.count(distinct(AnalyticsEvent.visitor_id))
                .filter(AnalyticsEvent.event_name == "page_viewed").label("visitors"),
            func.count().filter(AnalyticsEvent.event_name == "account_registered").label("signups"),
        )
        .where(AnalyticsEvent.created_at >= since)
        .group_by(func.date_trunc("day", AnalyticsEvent.created_at))
        .order_by(func.date_trunc("day", AnalyticsEvent.created_at))
    )).all()

    return {
        "by_name": [{"event": r.event_name, "count": r.n} for r in by_name],
        "top_paths": [{"path": r.path, "count": r.n} for r in top_paths],
        "top_referrers": [{"referrer": r.referrer, "count": r.n} for r in top_referrers],
        "daily": [
            {"day": r.day.isoformat(), "page_views": r.page_views,
             "visitors": r.visitors, "signups": r.signups}
            for r in daily
        ],
    }

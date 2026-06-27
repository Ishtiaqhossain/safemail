"""Health probes for the agentic self-monitoring system.

Each probe is a small, pure-ish function that inspects one facet of the system
(Redis, the Celery queue, Gmail polling freshness, the AI pipeline) and returns a
``Finding`` when something looks wrong, or ``None`` when it's healthy.

Everything here runs **synchronously**, inside the Celery worker, using the sync
SQLAlchemy session (``SyncSessionLocal``) — never the async FastAPI session. The
orchestration (persisting incidents, alerting, remediation) lives in
``app/tasks/monitoring.py``; this module only decides *what is wrong*.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.gmail_connection import GmailConnection
from app.models.task_log import TaskLog

logger = logging.getLogger(__name__)
settings = get_settings()

# Tasks that, when they fail in a sustained way, mean the core product is broken.
_CORE_TASKS = ("poll_connection", "analyze_message")


@dataclass
class Finding:
    """One detected problem. ``fingerprint`` is the dedup key: while an incident
    is open, the same fingerprint updates it rather than opening a new one."""

    check_name: str
    fingerprint: str
    severity: str            # "warning" | "critical"
    title: str
    detail: str
    metrics: dict = field(default_factory=dict)
    # Plain-language guidance handed to the remediation agent: what this means and
    # which fix actions are worth considering. Not shown to end users.
    remediation_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "check_name": self.check_name,
            "fingerprint": self.fingerprint,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "metrics": self.metrics,
            "remediation_hint": self.remediation_hint,
        }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Individual probes ───────────────────────────────────────────────────────────

def check_redis(redis_client) -> Finding | None:
    """Redis backs both the Celery broker and the Gmail dedup set. If it's down,
    nothing gets processed."""
    try:
        redis_client.ping()
        return None
    except Exception as exc:  # redis.exceptions.* — keep broad, any failure is bad
        return Finding(
            check_name="redis",
            fingerprint="redis_down",
            severity="critical",
            title="Redis is unreachable",
            detail=f"PING to Redis failed: {exc}. The Celery broker and the Gmail "
                   "dedup set both depend on Redis; while it's down no email is polled "
                   "or analyzed.",
            metrics={"error": str(exc)},
            remediation_hint="Redis is infrastructure — this is not auto-fixable from "
                             "inside the app. Escalate: check the Redis service/container is up "
                             "and REDIS_URL is correct.",
        )


def check_queue_backlog(redis_client) -> Finding | None:
    """A growing Celery backlog means tasks are being produced faster than the
    worker drains them (worker down, too few workers, or slow API)."""
    try:
        depth = redis_client.llen("celery")
    except Exception as exc:
        return None  # redis_down probe will have already fired
    if depth <= settings.health_queue_depth_warn:
        return None
    return Finding(
        check_name="queue_backlog",
        fingerprint="celery_queue_backlog",
        severity="warning",
        title=f"Celery queue backlog is high ({depth} pending)",
        detail=f"{depth} tasks are waiting on the default Celery queue, above the "
               f"threshold of {settings.health_queue_depth_warn}. The worker may be "
               "down, under-provisioned, or stuck on slow/erroring API calls.",
        metrics={"queue_depth": depth, "threshold": settings.health_queue_depth_warn},
        remediation_hint="Check that a Celery worker is running and healthy. Do NOT purge "
                         "the queue automatically — those are real emails awaiting analysis.",
    )


def check_polling_liveness(db: Session) -> Finding | None:
    """If active Gmail connections exist but no poll has run recently, the
    scheduler (beat) or worker is likely down — the product has gone silent."""
    active = db.query(GmailConnection).filter(GmailConnection.status == "active").count()
    if active == 0:
        return None  # nothing to poll; liveness is undefined

    # poll_connection writes a TaskLog (success or failure) on every attempt.
    last = (
        db.query(TaskLog)
        .filter(TaskLog.task_name == "poll_connection")
        .order_by(TaskLog.created_at.desc())
        .first()
    )
    # Allow a generous grace window: two poll intervals plus a buffer.
    grace = timedelta(minutes=settings.alert_poll_interval_minutes * 2 + 5)
    cutoff = _utcnow() - grace

    last_at = last.created_at if last else None
    if last_at is not None and last_at.tzinfo is None:
        last_at = last_at.replace(tzinfo=timezone.utc)

    if last_at is not None and last_at >= cutoff:
        return None

    return Finding(
        check_name="polling_liveness",
        fingerprint="polling_stalled",
        severity="critical",
        title="Gmail polling has stalled",
        detail=(
            f"{active} active Gmail connection(s) exist but the last poll ran "
            + (f"at {last_at.isoformat()}" if last_at else "never")
            + f" — past the {int(grace.total_seconds() // 60)}-minute liveness window. "
            "Celery beat or the worker is probably not running, so no new email is "
            "being scanned."
        ),
        metrics={
            "active_connections": active,
            "last_poll_at": last_at.isoformat() if last_at else None,
            "grace_minutes": int(grace.total_seconds() // 60),
        },
        remediation_hint="Re-enqueue a poll cycle (requeue_gmail_polling) to confirm the "
                         "worker can drain it. If polls still don't appear, beat/worker is "
                         "down — escalate.",
    )


def check_stale_connections(db: Session) -> Finding | None:
    """Active connections that haven't synced in a long time — individual Gmail
    accounts silently falling behind even while overall polling runs."""
    cutoff = _utcnow() - timedelta(minutes=settings.health_stale_connection_minutes)
    rows = (
        db.query(GmailConnection)
        .filter(GmailConnection.status == "active")
        .all()
    )
    stale = []
    for c in rows:
        last = c.last_synced_at
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last is None or last < cutoff:
            stale.append({
                "connection_id": str(c.id),
                "gmail_address": c.gmail_address,
                "last_synced_at": last.isoformat() if last else None,
            })

    if not stale:
        return None

    # If every active connection is stale, that's a system-wide stall, not a
    # per-account issue — let the polling-liveness probe own that signal.
    if len(stale) == len(rows):
        return None

    return Finding(
        check_name="stale_connections",
        fingerprint="stale_connections",
        severity="warning",
        title=f"{len(stale)} Gmail connection(s) are stale",
        detail=(
            f"{len(stale)} of {len(rows)} active connection(s) haven't synced in over "
            f"{settings.health_stale_connection_minutes} minutes while others have. "
            "Their individual poll tasks may be failing repeatedly."
        ),
        metrics={"stale_count": len(stale), "active_count": len(rows), "connections": stale},
        remediation_hint="For each stale connection, inspect recent poll_connection failures. "
                         "If a connection is stuck in a transient error (not an auth/invalid_grant "
                         "failure), retry_connection may recover it. Auth failures need the parent "
                         "to reconnect — escalate those.",
    )


def _failures_and_total(db: Session, task_name: str, since: datetime) -> tuple[int, int]:
    total = (
        db.query(TaskLog)
        .filter(TaskLog.task_name == task_name, TaskLog.created_at >= since)
        .count()
    )
    failures = (
        db.query(TaskLog)
        .filter(
            TaskLog.task_name == task_name,
            TaskLog.status == "failure",
            TaskLog.created_at >= since,
        )
        .count()
    )
    return failures, total


def check_task_failure_rate(db: Session) -> Finding | None:
    """A sustained spike in task failures across the core pipeline."""
    since = _utcnow() - timedelta(minutes=settings.health_failure_window_minutes)
    per_task = {}
    agg_failures = agg_total = 0
    for name in _CORE_TASKS:
        failures, total = _failures_and_total(db, name, since)
        per_task[name] = {"failures": failures, "total": total}
        agg_failures += failures
        agg_total += total

    if agg_total == 0 or agg_failures < settings.health_min_failures_to_alert:
        return None

    rate = agg_failures / agg_total
    if rate <= settings.health_max_failure_rate:
        return None

    return Finding(
        check_name="task_failure_rate",
        fingerprint="high_failure_rate",
        severity="warning",
        title=f"Task failure rate is {rate:.0%} over the last "
              f"{settings.health_failure_window_minutes} min",
        detail=(
            f"{agg_failures} of {agg_total} core task runs failed "
            f"(threshold {settings.health_max_failure_rate:.0%}). "
            f"Breakdown: {per_task}."
        ),
        metrics={
            "failure_rate": round(rate, 3),
            "failures": agg_failures,
            "total": agg_total,
            "window_minutes": settings.health_failure_window_minutes,
            "per_task": per_task,
        },
        remediation_hint="Read the recent failure logs to find the common cause. Transient "
                         "(timeouts, 5xx, connection resets) usually self-heal — confirm the rate "
                         "is trending down. A consistent error string points at a config/credential "
                         "problem to escalate.",
    )


def check_terminal_api_failures(db: Session) -> Finding | None:
    """analyze_message logs meta.terminal=true on a non-retryable 4xx from the
    Claude API — almost always a bad/expired ANTHROPIC_API_KEY or a bad request.
    These silently drop emails, so they're critical."""
    since = _utcnow() - timedelta(minutes=settings.health_failure_window_minutes)
    rows = (
        db.query(TaskLog)
        .filter(
            TaskLog.task_name == "analyze_message",
            TaskLog.status == "failure",
            TaskLog.created_at >= since,
        )
        .order_by(TaskLog.created_at.desc())
        .all()
    )
    terminal = [r for r in rows if (r.meta or {}).get("terminal")]
    if not terminal:
        return None

    sample_error = next((r.error for r in terminal if r.error), None)
    return Finding(
        check_name="terminal_api_failures",
        fingerprint="terminal_api_failures",
        severity="critical",
        title=f"{len(terminal)} email(s) dropped on terminal Claude API errors",
        detail=(
            f"{len(terminal)} analyze_message run(s) in the last "
            f"{settings.health_failure_window_minutes} min hit a non-retryable 4xx from "
            "the Claude API and dropped the email without analysis. This is typically an "
            f"invalid/expired ANTHROPIC_API_KEY or a malformed request. Sample error: {sample_error}"
        ),
        metrics={"count": len(terminal), "sample_error": sample_error},
        remediation_hint="Not auto-fixable from inside the app — a 4xx means the request or "
                         "credentials are wrong. Escalate: verify ANTHROPIC_API_KEY is valid and the "
                         "model name is current.",
    )


def check_connections_in_error(db: Session) -> Finding | None:
    """Connections the poller flipped to status='error' (auth/invalid_grant).
    The parent is emailed automatically, but ops should see the trend too."""
    rows = (
        db.query(GmailConnection)
        .filter(GmailConnection.status == "error")
        .all()
    )
    if not rows:
        return None
    return Finding(
        check_name="connections_in_error",
        fingerprint="connections_in_error",
        severity="warning",
        title=f"{len(rows)} Gmail connection(s) in error state",
        detail=(
            f"{len(rows)} connection(s) are in 'error' state, meaning their OAuth grant "
            "was revoked or expired and SafeMail can no longer read that inbox. The parent "
            "has been emailed to reconnect; until they do, that child is unmonitored."
        ),
        metrics={
            "count": len(rows),
            "connections": [
                {"connection_id": str(c.id), "gmail_address": c.gmail_address} for c in rows
            ],
        },
        remediation_hint="Not auto-fixable: only the parent can re-grant Google OAuth. Do NOT "
                         "flip these back to active automatically — that would just fail again. "
                         "Escalate / confirm the parent reconnect email went out.",
    )


# ── Orchestration ──────────────────────────────────────────────────────────────

_PROBES_REDIS = (check_redis, check_queue_backlog)
_PROBES_DB = (
    check_polling_liveness,
    check_stale_connections,
    check_task_failure_rate,
    check_terminal_api_failures,
    check_connections_in_error,
)


def run_health_checks(db: Session, redis_client) -> list[Finding]:
    """Run every probe and return all current findings. A probe that raises is
    isolated (logged, skipped) so one broken check can't blind all the others."""
    findings: list[Finding] = []
    for probe in _PROBES_REDIS:
        try:
            f = probe(redis_client)
            if f:
                findings.append(f)
        except Exception:
            logger.exception("Health probe %s raised", probe.__name__)
    for probe in _PROBES_DB:
        try:
            f = probe(db)
            if f:
                findings.append(f)
        except Exception:
            logger.exception("Health probe %s raised", probe.__name__)
    return findings

"""The scheduled self-monitoring cycle.

Runs every ``MONITORING_INTERVAL_MINUTES`` (Celery beat). Each cycle:

1. Runs every health probe (``app.services.monitoring.run_health_checks``).
2. For each *new* problem, opens a HealthIncident, hands it to the LLM
   remediation agent (``app.services.remediation.remediate``), and emails ops.
3. Re-trips of an already-open incident just bump ``times_seen`` — no duplicate
   alert, no duplicate remediation.
4. Open incidents whose probe no longer trips are auto-resolved (and, if they had
   been alerted, an "all clear" email is sent).

Sync SQLAlchemy session only (Celery side). Never lets a notification or
remediation failure abort the cycle.
"""
import logging
from datetime import datetime, timezone

import redis

from app.worker import celery
from app.database import SyncSessionLocal
from app.config import get_settings
from app.models.health_incident import HealthIncident
from app.models.parent import Parent
from app.services.monitoring import run_health_checks
from app.services.remediation import remediate
from app.services.notifications import send_health_alert
from app.tasks.utils import write_task_log, TaskTimer

logger = logging.getLogger(__name__)
settings = get_settings()

_redis = redis.from_url(settings.redis_url)


def _alert_recipients(db) -> list[str]:
    """Where health alerts go: the configured ops address, else every admin parent."""
    if settings.ops_alert_email:
        return [settings.ops_alert_email]
    admins = db.query(Parent).filter(Parent.is_admin.is_(True)).all()
    return [a.email for a in admins if a.email]


def _incident_to_payload(inc: HealthIncident) -> dict:
    return {
        "title": inc.title,
        "severity": inc.severity,
        "detail": inc.detail,
        "check_name": inc.check_name,
        "diagnosis": inc.diagnosis,
        "remediation_status": inc.remediation_status,
        "remediation": inc.remediation,
    }


@celery.task(name="app.tasks.monitoring.run_monitoring_cycle", bind=True, max_retries=2)
def run_monitoring_cycle(self):
    if not settings.monitoring_enabled:
        return

    timer = TaskTimer()
    opened = reopened_seen = resolved = alerts_sent = 0

    with SyncSessionLocal() as db:
        try:
            findings = run_health_checks(db, _redis)
        except Exception as exc:
            # The probes themselves failing is the one thing we can't self-heal —
            # record it and bail. (Individual probes are already isolated; this
            # guards a failure in the orchestration around them.)
            logger.exception("run_health_checks failed")
            write_task_log(db, "run_monitoring_cycle", "failure",
                           error=str(exc), duration_ms=timer.elapsed_ms())
            return

        fingerprints_now = {f.fingerprint for f in findings}
        recipients = _alert_recipients(db)

        for finding in findings:
            existing = (
                db.query(HealthIncident)
                .filter(HealthIncident.fingerprint == finding.fingerprint,
                        HealthIncident.status == "open")
                .first()
            )
            if existing:
                # Already known and open — refresh, but don't re-alert / re-remediate.
                existing.times_seen += 1
                existing.metrics = finding.metrics
                existing.detail = finding.detail
                existing.severity = finding.severity
                db.commit()
                reopened_seen += 1
                continue

            # New incident.
            inc = HealthIncident(
                fingerprint=finding.fingerprint,
                check_name=finding.check_name,
                severity=finding.severity,
                status="open",
                title=finding.title,
                detail=finding.detail,
                metrics=finding.metrics,
                remediation_status="none",
            )
            db.add(inc)
            db.commit()
            db.refresh(inc)
            opened += 1

            # Hand to the agent (never raises). Persist whatever it produced.
            result = remediate(finding, db=db, redis_client=_redis)
            inc.diagnosis = result.get("diagnosis")
            inc.remediation = result
            inc.remediation_status = result.get("status")
            db.commit()

            # Alert ops.
            if recipients:
                try:
                    send_health_alert(recipients, _incident_to_payload(inc))
                    inc.alerted_at = datetime.now(timezone.utc)
                    db.commit()
                    alerts_sent += 1
                except Exception as e:
                    logger.error("Failed to send health alert for incident %s: %s", inc.id, e)

        # Auto-resolve incidents whose probe no longer trips.
        open_incidents = db.query(HealthIncident).filter(HealthIncident.status == "open").all()
        for inc in open_incidents:
            if inc.fingerprint in fingerprints_now:
                continue
            inc.status = "resolved"
            inc.resolved_at = datetime.now(timezone.utc)
            db.commit()
            resolved += 1
            if inc.alerted_at and recipients:
                try:
                    send_health_alert(recipients, _incident_to_payload(inc), resolved=True)
                except Exception as e:
                    logger.error("Failed to send resolution notice for incident %s: %s", inc.id, e)

        write_task_log(db, "run_monitoring_cycle", "success",
                       duration_ms=timer.elapsed_ms(),
                       meta={"findings": len(findings), "opened": opened,
                             "reopened_seen": reopened_seen, "resolved": resolved,
                             "alerts_sent": alerts_sent})

import logging
import random
import uuid
from datetime import datetime, timezone

import anthropic

from app.worker import celery
from app.database import SyncSessionLocal
from app.models.alert import Alert
from app.models.child import Child
from app.models.gmail_connection import GmailConnection
from app.models.alert_preference import AlertPreference
from app.services.analysis import classify_email
from app.config import get_settings
from app.tasks.utils import write_task_log, TaskTimer

logger = logging.getLogger(__name__)
settings = get_settings()

# Transient failures worth retrying: rate limits (429), 500s, network, timeout.
# Other HTTP errors are decided by status code below (5xx incl. 529 overloaded =
# retry; 4xx = terminal). RateLimitError/InternalServerError are APIStatusError
# subclasses, so this tuple must be caught before the generic APIStatusError.
RETRYABLE_API_ERRORS = (
    anthropic.RateLimitError,        # 429
    anthropic.InternalServerError,   # 500
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
)


def _retry_delay(exc: Exception, retries: int) -> int:
    """Backoff for a retryable error: honor a server Retry-After header when
    present (rate limits), else exponential backoff with jitter capped at 60s."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers:
        val = headers.get("retry-after")
        if val:
            try:
                return max(1, int(float(val)))
            except (TypeError, ValueError):
                pass
    return min(2 ** (retries + 1), 60) + random.randint(0, 2)


@celery.task(name="app.tasks.analysis.analyze_message", bind=True, max_retries=3)
def analyze_message(self, message: dict):
    timer = TaskTimer()
    try:
        result = classify_email(message)
    except RETRYABLE_API_ERRORS as exc:
        delay = _retry_delay(exc, self.request.retries)
        logger.warning("Transient Claude API error (retry %s in %ss): %s",
                       self.request.retries, delay, exc)
        raise self.retry(exc=exc, countdown=delay)
    except anthropic.APIStatusError as exc:
        # 5xx (e.g. 529 overloaded) is transient → retry; 4xx (400/401/403/404/…)
        # will never succeed on retry → dead-letter to the task log and stop.
        if exc.status_code >= 500:
            delay = _retry_delay(exc, self.request.retries)
            logger.warning("Transient Claude API %s (retry %s in %ss): %s",
                           exc.status_code, self.request.retries, delay, exc)
            raise self.retry(exc=exc, countdown=delay)
        logger.error("Non-retryable Claude API %s — dropping message: %s", exc.status_code, exc)
        with SyncSessionLocal() as db:
            write_task_log(db, "analyze_message", "failure",
                           error=str(exc), duration_ms=timer.elapsed_ms(),
                           meta={"child_id": message.get("child_id"), "terminal": True})
        return
    except Exception as exc:
        # Unknown (incl. malformed-JSON parse failures, which may be transient
        # given non-deterministic output) — bounded retry, then give up.
        logger.error("Unexpected analysis error (retry %s): %s", self.request.retries, exc)
        raise self.retry(exc=exc, countdown=30)

    input_tokens = result.pop("input_tokens", 0)
    output_tokens = result.pop("output_tokens", 0)
    cost_usd = result.pop("cost_usd", None)
    model_used = result.pop("model", None)
    escalated = result.pop("escalated", None)
    severity = result.get("severity", "none")
    confidence = float(result.get("confidence", 0))

    # Log token usage on every scan, including those that don't produce an alert,
    # so LLM cost reflects all classification work.
    if severity == "none" or confidence < settings.confidence_threshold:
        with SyncSessionLocal() as db:
            write_task_log(db, "analyze_message", "success",
                           duration_ms=timer.elapsed_ms(),
                           meta={"child_id": message["child_id"], "severity": severity,
                                 "input_tokens": input_tokens, "output_tokens": output_tokens,
                                 "cost_usd": cost_usd, "model": model_used, "escalated": escalated,
                                 "skipped": True})
        return

    with SyncSessionLocal() as db:
        existing = (
            db.query(Alert)
            .filter(Alert.gmail_message_id == message["gmail_message_id"])
            .first()
        )
        if existing:
            return

        alert = Alert(
            child_id=uuid.UUID(message["child_id"]),
            gmail_connection_id=uuid.UUID(message["gmail_connection_id"]),
            gmail_message_id=message["gmail_message_id"],
            direction=message["direction"],
            sender_address=message["sender_address"],
            recipient_addresses=message["recipient_addresses"],
            subject_snippet=message.get("subject", "")[:80],
            received_at=message["received_at"],
            category=result["category"],
            severity=severity,
            confidence=confidence,
            ai_summary=result.get("summary", ""),
            ai_response_script=result.get("response_script"),
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        write_task_log(db, "analyze_message", "success",
                       duration_ms=timer.elapsed_ms(),
                       meta={"child_id": message["child_id"], "severity": severity,
                             "category": result["category"],
                             "input_tokens": input_tokens, "output_tokens": output_tokens,
                             "cost_usd": cost_usd, "model": model_used, "escalated": escalated})

        from app.tasks.analysis import deliver_alert
        deliver_alert.delay(str(alert.id))


@celery.task(name="app.tasks.analysis.deliver_alert", bind=True, max_retries=3)
def deliver_alert(self, alert_id: str):
    from app.models.parent import Parent
    from app.services.notifications import send_alert_email, send_push_notification

    with SyncSessionLocal() as db:
        alert = db.get(Alert, uuid.UUID(alert_id))
        if not alert:
            return

        child = db.get(Child, alert.child_id)
        parent = db.get(Parent, child.parent_id)
        pref = db.query(AlertPreference).filter(
            AlertPreference.child_id == child.id,
            AlertPreference.parent_id == parent.id,
        ).first()

        immediate = pref.immediate_severities if pref else ["critical", "high"]

        channels = []
        if alert.severity in immediate:
            alert_dict = {
                "id": alert.id,
                "severity": alert.severity,
                "category": alert.category,
                "ai_summary": alert.ai_summary,
                "ai_response_script": alert.ai_response_script,
            }
            try:
                send_alert_email(parent.email, child.display_name, alert_dict)
                channels.append("email")
            except Exception as e:
                logger.error("Email delivery failed: %s", e)

            if parent.fcm_token:
                try:
                    send_push_notification(parent.fcm_token, child.display_name, alert_dict)
                    channels.append("push")
                except Exception as e:
                    logger.error("Push delivery failed: %s", e)

            alert.notified_at = datetime.now(timezone.utc)
            db.commit()
        write_task_log(db, "deliver_alert", "success",
                       meta={"alert_id": alert_id, "channels": channels})

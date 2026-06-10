import logging
import uuid
from datetime import datetime, timezone

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


@celery.task(name="app.tasks.analysis.analyze_message", bind=True, max_retries=3)
def analyze_message(self, message: dict):
    timer = TaskTimer()
    try:
        result = classify_email(message)
    except Exception as exc:
        logger.error("Claude API error: %s", exc)
        raise self.retry(exc=exc, countdown=30)

    severity = result.get("severity", "none")
    confidence = float(result.get("confidence", 0))

    if severity == "none" or confidence < settings.confidence_threshold:
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
                       meta={"child_id": message["child_id"], "severity": severity, "category": result["category"]})

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

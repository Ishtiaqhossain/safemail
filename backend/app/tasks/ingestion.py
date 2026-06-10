import logging
from datetime import datetime, timezone

import redis

from app.worker import celery
from app.database import SyncSessionLocal
from app.models.gmail_connection import GmailConnection
from app.services.crypto import decrypt_token, encrypt_token
from app.services.gmail import (
    build_gmail_service, refresh_if_needed, list_message_ids,
    fetch_message, extract_message_data,
)
from app.config import get_settings
from app.tasks.utils import write_task_log, TaskTimer

logger = logging.getLogger(__name__)
settings = get_settings()

_redis = redis.from_url(settings.redis_url)
DEDUP_TTL = 60 * 60 * 24 * 7  # 7 days


@celery.task(name="app.tasks.ingestion.poll_all_connections", bind=True, max_retries=3)
def poll_all_connections(self):
    with SyncSessionLocal() as db:
        connections = db.query(GmailConnection).filter(GmailConnection.status == "active").all()
        connection_ids = [str(c.id) for c in connections]

    for cid in connection_ids:
        poll_connection.delay(cid)


@celery.task(name="app.tasks.ingestion.poll_connection", bind=True, max_retries=3)
def poll_connection(self, connection_id: str):
    timer = TaskTimer()
    with SyncSessionLocal() as db:
        conn = db.get(GmailConnection, connection_id)
        if not conn or conn.status != "active":
            return

        try:
            access_token = decrypt_token(conn.access_token)
            refresh_token = decrypt_token(conn.refresh_token)
            creds, service = build_gmail_service(access_token, refresh_token)

            if creds.expired:
                new_access, new_refresh, expiry = refresh_if_needed(creds)
                conn.access_token = encrypt_token(new_access)
                conn.refresh_token = encrypt_token(new_refresh)
                conn.token_expiry = expiry
                db.commit()
                _, service = build_gmail_service(new_access, new_refresh)

            message_ids = list_message_ids(service)
            new_ids = [mid for mid in message_ids if not _redis.exists(f"dedup:{mid}")]

            for message_id in new_ids:
                try:
                    raw = fetch_message(service, message_id)
                    message_data = extract_message_data(
                        raw,
                        conn.gmail_address,
                        str(conn.id),
                        str(conn.child_id),
                    )
                    from app.tasks.analysis import analyze_message
                    analyze_message.delay(message_data)
                    _redis.setex(f"dedup:{message_id}", DEDUP_TTL, "1")
                except Exception as e:
                    logger.warning("Failed to process message %s: %s", message_id, e)

            conn.last_synced_at = datetime.now(timezone.utc)
            db.commit()
            write_task_log(db, "poll_connection", "success",
                           duration_ms=timer.elapsed_ms(),
                           meta={"connection_id": connection_id, "messages_fetched": len(new_ids)})

        except Exception as exc:
            logger.error("Poll failed for connection %s: %s", connection_id, exc)
            is_auth_failure = "invalid_grant" in str(exc).lower() or "401" in str(exc)
            if is_auth_failure:
                conn.status = "error"
                db.commit()
                # Token revoked/expired — the parent must reconnect, so tell them.
                _notify_reconnect_needed(db, conn)
            write_task_log(db, "poll_connection", "failure",
                           error=str(exc), duration_ms=timer.elapsed_ms(),
                           meta={"connection_id": connection_id, "auth_failure": is_auth_failure})
            if not is_auth_failure:
                raise self.retry(exc=exc, countdown=60)


def _notify_reconnect_needed(db, conn: GmailConnection) -> None:
    """Email the parent that a child's Gmail connection needs reconnecting.

    Best-effort: never let a notification failure mask the original poll error.
    Runs only on the active->error transition, so the parent is emailed once.
    """
    from app.models.child import Child
    from app.models.parent import Parent
    from app.services.notifications import send_reconnect_email

    try:
        child = db.get(Child, conn.child_id)
        if not child:
            return
        parent = db.get(Parent, child.parent_id)
        if not parent:
            return
        reconnect_url = f"{settings.frontend_url}/dashboard"
        send_reconnect_email(parent.email, child.display_name, conn.gmail_address, reconnect_url)
        write_task_log(db, "reconnect_notice", "success",
                       meta={"connection_id": str(conn.id), "parent_email": parent.email})
    except Exception as e:
        logger.error("Reconnect notice failed for connection %s: %s", conn.id, e)

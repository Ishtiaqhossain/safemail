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

        except Exception as exc:
            logger.error("Poll failed for connection %s: %s", connection_id, exc)
            if "invalid_grant" in str(exc).lower() or "401" in str(exc):
                conn.status = "error"
                db.commit()
            else:
                raise self.retry(exc=exc, countdown=60)

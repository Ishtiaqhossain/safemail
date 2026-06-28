import logging
from datetime import datetime, timezone

import redis

from app.worker import celery
from app.database import SyncSessionLocal
from app.models.gmail_connection import GmailConnection
from app.services.crypto import decrypt_token, encrypt_token
from app.services.email_providers import get_provider
from app.services.email_providers.base import ProviderAuthError
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

        provider = None
        service = None
        try:
            provider = get_provider(conn.provider)
            access_token = decrypt_token(conn.access_token)
            refresh_token = decrypt_token(conn.refresh_token)
            creds, service = provider.build_client(access_token, refresh_token,
                                                   conn.gmail_address, conn.token_expiry)

            # Let the provider decide whether a refresh is needed (keeps this loop
            # provider-neutral — no Google-specific creds.expired here). Persist and
            # rebuild only when the tokens actually changed.
            new_access, new_refresh, expiry = provider.refresh_if_needed(creds)
            if new_access != access_token:
                conn.access_token = encrypt_token(new_access)
                conn.refresh_token = encrypt_token(new_refresh)
                conn.token_expiry = expiry
                db.commit()
                provider.close(service)  # release the client built with the stale token
                _, service = provider.build_client(new_access, new_refresh,
                                                   conn.gmail_address, expiry)

            message_ids = provider.list_message_ids(service)
            # Dedup is namespaced per connection so message ids from different
            # accounts (e.g. small IMAP UIDs) can't collide in the shared set.
            new_ids = [mid for mid in message_ids if not _redis.exists(f"dedup:{conn.id}:{mid}")]

            for message_id in new_ids:
                try:
                    raw = provider.fetch_message(service, message_id)
                    message_data = provider.extract_message_data(
                        raw,
                        conn.gmail_address,
                        str(conn.id),
                        str(conn.child_id),
                    )
                    from app.tasks.analysis import analyze_message
                    analyze_message.delay(message_data)
                    _redis.setex(f"dedup:{conn.id}:{message_id}", DEDUP_TTL, "1")
                except Exception as e:
                    logger.warning("Failed to process message %s: %s", message_id, e)

            conn.last_synced_at = datetime.now(timezone.utc)
            db.commit()
            write_task_log(db, "poll_connection", "success",
                           duration_ms=timer.elapsed_ms(),
                           meta={"connection_id": connection_id, "messages_fetched": len(new_ids)})

        except Exception as exc:
            logger.error("Poll failed for connection %s: %s", connection_id, exc)
            # Providers raise ProviderAuthError on a revoked/bad grant; fall back to
            # string matching for providers (Gmail) that surface library errors.
            exc_l = str(exc).lower()
            is_auth_failure = isinstance(exc, ProviderAuthError) or (
                "invalid_grant" in exc_l or "401" in exc_l
                or "authenticationfailed" in exc_l or "invalid credentials" in exc_l
                or "login failed" in exc_l
            )
            if is_auth_failure:
                conn.status = "error"
                db.commit()
                # Token revoked/expired — the parent must reconnect, so tell them.
                _notify_reconnect_needed(db, conn)
            write_task_log(db, "poll_connection", "failure",
                           error=str(exc), duration_ms=timer.elapsed_ms(),
                           meta={"connection_id": connection_id, "auth_failure": is_auth_failure})
            # Transient (non-auth) failures retry; auth failures wait for reconnect.
            if not is_auth_failure:
                raise self.retry(exc=exc, countdown=60)
        finally:
            # Release any persistent connection (IMAP logout); no-op for Gmail.
            # Runs on success, failure, and before a retry propagates.
            if provider is not None and service is not None:
                try:
                    provider.close(service)
                except Exception:
                    pass


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

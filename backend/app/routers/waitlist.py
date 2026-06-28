"""Public landing-page waitlist signup.

Unauthenticated and rate-limited. Captures an email expressing interest while
SafeMail is invite-only. Being on the waitlist grants no access — an admin
promotes an entry to the allowlist (app.routers.admin) before that person can
register. The endpoint is intentionally idempotent and always reports success
so it can't be used to enumerate who has already signed up.

If the email is *already* on the allowlist, the person can register right now,
so we skip the waitlist entirely and return ``status: "already_invited"`` —
the landing page uses this to send them to the register form instead of
showing the "we'll email you a spot" wait message.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.ratelimit import limiter, WAITLIST_LIMIT
from app.models.parent import Parent
from app.models.waitlist_entry import WaitlistEntry
from app.services.allowlist import normalize_email, is_email_allowed
from app.services.analytics_events import record_event_async
from app.services.notifications import send_waitlist_notification

router = APIRouter(prefix="/waitlist", tags=["waitlist"])
logger = logging.getLogger(__name__)
settings = get_settings()


async def _notify_ops_new_signup(db: AsyncSession, email: str, source: str) -> None:
    """Best-effort ops email on a new waitlist signup. Never fails the request.
    Recipients: OPS_ALERT_EMAIL if set, else every admin parent."""
    try:
        if settings.ops_alert_email:
            recipients = [settings.ops_alert_email]
        else:
            recipients = list((await db.execute(
                select(Parent.email).where(Parent.is_admin.is_(True))
            )).scalars().all())
        if not recipients:
            return
        pending = (await db.execute(
            select(func.count()).select_from(WaitlistEntry)
        )).scalar_one()
        # SendGrid client is blocking — run off the event loop.
        await run_in_threadpool(send_waitlist_notification, recipients, email, source, pending)
    except Exception as e:
        logger.warning("Waitlist signup notification failed for %s: %s", email, e)


class WaitlistRequest(BaseModel):
    email: EmailStr
    source: str | None = None


@router.post("", status_code=201)
@limiter.limit(WAITLIST_LIMIT)
async def join_waitlist(
    request: Request,
    body: WaitlistRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    email = normalize_email(body.email)

    # Already invited? They can create an account now — don't park them on the
    # waitlist. Tell the client to route them to registration instead.
    if await is_email_allowed(db, email):
        await record_event_async(db, "waitlist_already_invited")
        return {"status": "already_invited"}

    existing = (await db.execute(
        select(WaitlistEntry.id).where(func.lower(WaitlistEntry.email) == email)
    )).scalar_one_or_none()
    if existing is not None:
        return {"status": "ok"}

    created = False
    db.add(WaitlistEntry(email=email, source=(body.source or "landing")))
    try:
        await db.commit()
        created = True
    except IntegrityError:
        # Concurrent duplicate request — treat as success.
        await db.rollback()

    # Durable top-of-funnel event (waitlist rows are deleted on approval, so the
    # event is the lasting record of the signup). Source = acquisition channel.
    await record_event_async(db, "waitlist_joined", properties={"source": body.source or "landing"})

    # Notify ops only on a genuinely new entry (not duplicates / races).
    if created:
        await _notify_ops_new_signup(db, email, body.source or "landing")
    return {"status": "ok"}

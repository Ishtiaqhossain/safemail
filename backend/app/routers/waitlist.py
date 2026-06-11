"""Public landing-page waitlist signup.

Unauthenticated and rate-limited. Captures an email expressing interest while
SafeMail is invite-only. Being on the waitlist grants no access — an admin
promotes an entry to the allowlist (app.routers.admin) before that person can
register. The endpoint is intentionally idempotent and always reports success
so it can't be used to enumerate who has already signed up.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.ratelimit import limiter, WAITLIST_LIMIT
from app.models.waitlist_entry import WaitlistEntry
from app.services.allowlist import normalize_email

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


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

    existing = (await db.execute(
        select(WaitlistEntry.id).where(func.lower(WaitlistEntry.email) == email)
    )).scalar_one_or_none()
    if existing is not None:
        return {"status": "ok"}

    db.add(WaitlistEntry(email=email, source=(body.source or "landing")))
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent duplicate request — treat as success.
        await db.rollback()

    return {"status": "ok"}

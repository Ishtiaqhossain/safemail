"""DEBUG-only seed endpoints for E2E tests. NEVER mounted in production.

`app/main.py` includes this router only when ``settings.debug AND
settings.e2e_seed_enabled`` are both true, and every request must present the
``X-E2E-Seed-Secret`` header matching ``settings.e2e_seed_secret``. When the gate
is off the routes don't exist (natural 404), so the feature is invisible in prod.

The endpoints create realistic state (a verified, onboarded parent; a child +
active connection + a visible alert) without touching OAuth / Gmail / Anthropic /
SendGrid, so the browser E2E suite stays hermetic.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.auth import hash_password
from app.services.crypto import encrypt_token
from app.models.parent import Parent
from app.models.child import Child
from app.models.gmail_connection import GmailConnection
from app.models.alert import Alert
from app.models.allowed_email import AllowedEmail

router = APIRouter(prefix="/dev", tags=["dev"])
settings = get_settings()

_SEVERITIES = {"critical", "high", "medium", "low"}
_CATEGORIES = {
    "self_harm", "grooming", "bullying", "drugs_alcohol",
    "stranger_contact", "personal_info_sharing",
}


def _guard(x_e2e_seed_secret: Annotated[str | None, Header()] = None) -> None:
    """404 unless the seam is enabled and the request carries the right secret.
    404 (not 403) so the feature appears nonexistent."""
    if not (settings.debug and settings.e2e_seed_enabled and settings.e2e_seed_secret):
        raise HTTPException(status_code=404, detail="Not Found")
    if x_e2e_seed_secret != settings.e2e_seed_secret:
        raise HTTPException(status_code=404, detail="Not Found")


class SeedParentBody(BaseModel):
    email: EmailStr
    password: str
    complete: bool = True          # onboarding_completed_at + monitoring_consent_at populated
    is_admin: bool = False
    is_developer: bool = False


class SeedAlertBody(BaseModel):
    email: EmailStr                # the parent to attach the alert to
    child_name: str = "Test Child"
    severity: str = "high"
    category: str = "grooming"
    summary: str = "An adult repeatedly asked to meet in private and keep it secret."
    direction: str = "inbound"
    sender: str = "stranger@example.com"


class ResetBody(BaseModel):
    email: EmailStr | None = None
    email_prefix: str | None = None   # delete every seeded parent in a namespace


@router.post("/seed-parent", dependencies=[Depends(_guard)])
async def seed_parent(body: SeedParentBody, db: Annotated[AsyncSession, Depends(get_db)]):
    now = datetime.now(timezone.utc)
    email = body.email.strip().lower()
    existing = (await db.execute(
        select(Parent).where(func.lower(Parent.email) == email)
    )).scalar_one_or_none()

    parent = existing or Parent(email=email)
    # Re-set every field on every upsert so reruns are deterministic.
    parent.password_hash = hash_password(body.password)
    parent.is_email_verified = True
    parent.is_admin = body.is_admin
    parent.is_developer = body.is_developer
    parent.onboarding_completed_at = now if body.complete else None
    parent.monitoring_consent_at = now if body.complete else None
    if existing is None:
        db.add(parent)

    # Allowlist the email so login works even if invite-only is left on.
    already_allowed = (await db.execute(
        select(AllowedEmail).where(func.lower(AllowedEmail.email) == email)
    )).scalar_one_or_none()
    if already_allowed is None:
        db.add(AllowedEmail(email=email, note="e2e-seed"))

    await db.commit()
    await db.refresh(parent)
    return {"parent_id": str(parent.id), "email": parent.email}


@router.post("/seed-alert", dependencies=[Depends(_guard)])
async def seed_alert(body: SeedAlertBody, db: Annotated[AsyncSession, Depends(get_db)]):
    if body.severity not in _SEVERITIES:
        raise HTTPException(status_code=422, detail=f"severity must be one of {sorted(_SEVERITIES)}")
    if body.category not in _CATEGORIES:
        raise HTTPException(status_code=422, detail=f"category must be one of {sorted(_CATEGORIES)}")

    email = body.email.strip().lower()
    parent = (await db.execute(
        select(Parent).where(func.lower(Parent.email) == email)
    )).scalar_one_or_none()
    if parent is None:
        raise HTTPException(status_code=404, detail="Seed parent not found")

    now = datetime.now(timezone.utc)
    child = Child(parent_id=parent.id, display_name=body.child_name, birth_year=2014)
    db.add(child)
    await db.flush()  # need child.id

    conn = GmailConnection(
        child_id=child.id,
        provider="google",
        gmail_address=f"{child.id}@seed.example",
        access_token=encrypt_token("seed-access"),
        refresh_token=encrypt_token("seed-refresh"),
        token_expiry=now + timedelta(hours=1),
        status="active",
        last_synced_at=now,
    )
    db.add(conn)
    await db.flush()  # need conn.id

    alert = Alert(
        child_id=child.id,
        gmail_connection_id=conn.id,
        # NOT "fake_..." — ordinary parents can't see fake_ alerts (alerts.py:40).
        gmail_message_id=f"seed-{uuid.uuid4()}",
        direction=body.direction,
        sender_address=body.sender,
        recipient_addresses=[f"{child.id}@seed.example"],
        subject_snippet="Hey, can we talk?",
        received_at=now,
        category=body.category,
        severity=body.severity,
        confidence=0.95,
        ai_summary=body.summary,
        ai_response_script="Talk to your child about who they're messaging.",
    )
    db.add(alert)
    await db.commit()
    return {"child_id": str(child.id), "connection_id": str(conn.id), "alert_id": str(alert.id)}


@router.post("/reset", dependencies=[Depends(_guard)])
async def reset(body: ResetBody, db: Annotated[AsyncSession, Depends(get_db)]):
    """Delete the seeded parent(s) and let Postgres ON DELETE CASCADE wipe their
    children/connections/alerts (mirrors the async-safe pattern in auth.py)."""
    if not body.email and not body.email_prefix:
        raise HTTPException(status_code=422, detail="email or email_prefix required")

    if body.email:
        email = body.email.strip().lower()
        cond = func.lower(Parent.email) == email
        allow_cond = func.lower(AllowedEmail.email) == email
    else:
        prefix = body.email_prefix.strip().lower()
        # Guard against an accidental mass wipe: must be a non-empty E2E namespace,
        # and escape LIKE metacharacters so a literal prefix can't become a wildcard.
        if not prefix.startswith("e2e-"):
            raise HTTPException(status_code=422, detail="email_prefix must start with 'e2e-'")
        esc = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        cond = func.lower(Parent.email).like(esc + "%", escape="\\")
        allow_cond = func.lower(AllowedEmail.email).like(esc + "%", escape="\\")

    await db.execute(sa_delete(AllowedEmail).where(allow_cond))
    result = await db.execute(sa_delete(Parent).where(cond))
    await db.commit()
    return {"deleted": result.rowcount or 0}

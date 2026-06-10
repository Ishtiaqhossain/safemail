"""Invite-only allowlist helpers.

While invite_only_enabled is True, only emails present in the allowed_emails
table may register or log in. Enforcement lives in app.routers.auth; allowlist
management lives in app.routers.admin.
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.allowed_email import AllowedEmail


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def is_email_allowed(db: AsyncSession, email: str) -> bool:
    norm = normalize_email(email)
    result = await db.execute(
        select(AllowedEmail.id).where(func.lower(AllowedEmail.email) == norm)
    )
    return result.scalar_one_or_none() is not None


async def parent_count(db: AsyncSession) -> int:
    from app.models.parent import Parent
    return (await db.execute(select(func.count()).select_from(Parent))).scalar() or 0

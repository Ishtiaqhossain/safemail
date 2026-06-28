from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_parent
from app.models.parent import Parent
from app.services.analytics_events import record_event_async

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/consent", status_code=200)
async def record_consent(
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Record the parent's monitoring-consent attestation from the wizard."""
    if current_parent.monitoring_consent_at is None:
        current_parent.monitoring_consent_at = datetime.now(timezone.utc)
        await db.commit()
        await record_event_async(db, "consent_given", parent_id=current_parent.id)
    return {"monitoring_consent": True}


@router.post("/complete", status_code=200)
async def complete_onboarding(
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Mark onboarding finished (used by both 'Finish' and 'Skip for now')."""
    if current_parent.onboarding_completed_at is None:
        current_parent.onboarding_completed_at = datetime.now(timezone.utc)
        await db.commit()
        await record_event_async(db, "onboarding_completed", parent_id=current_parent.id)
    return {"onboarding_completed": True}

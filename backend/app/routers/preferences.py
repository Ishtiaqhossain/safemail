import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.auth import get_current_parent
from app.models.parent import Parent
from app.models.child import Child
from app.models.alert_preference import AlertPreference
from app.schemas.alerts import AlertPreferenceRequest, AlertPreferenceResponse

router = APIRouter(tags=["preferences"])


@router.get("/children/{child_id}/preferences", response_model=AlertPreferenceResponse)
async def get_preferences(
    child_id: str,
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _assert_owns_child(db, child_id, current_parent.id)
    pref = await _get_or_create_pref(db, child_id, current_parent.id)
    return pref


@router.put("/children/{child_id}/preferences", response_model=AlertPreferenceResponse)
async def update_preferences(
    child_id: str,
    body: AlertPreferenceRequest,
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _assert_owns_child(db, child_id, current_parent.id)
    pref = await _get_or_create_pref(db, child_id, current_parent.id)
    pref.disabled_categories = body.disabled_categories
    pref.immediate_severities = body.immediate_severities
    pref.digest_frequency = body.digest_frequency
    await db.commit()
    await db.refresh(pref)
    return pref


async def _assert_owns_child(db: AsyncSession, child_id: str, parent_id: uuid.UUID) -> None:
    result = await db.execute(
        select(Child).where(Child.id == uuid.UUID(child_id), Child.parent_id == parent_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")


async def _get_or_create_pref(db: AsyncSession, child_id: str, parent_id: uuid.UUID) -> AlertPreference:
    result = await db.execute(
        select(AlertPreference).where(
            AlertPreference.child_id == uuid.UUID(child_id),
            AlertPreference.parent_id == parent_id,
        )
    )
    pref = result.scalar_one_or_none()
    if not pref:
        pref = AlertPreference(parent_id=parent_id, child_id=uuid.UUID(child_id))
        db.add(pref)
        await db.commit()
        await db.refresh(pref)
    return pref

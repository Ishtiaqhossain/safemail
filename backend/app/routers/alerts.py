import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import get_current_parent
from app.models.parent import Parent
from app.models.child import Child
from app.models.alert import Alert
from app.schemas.alerts import AlertResponse, AlertListResponse, AlertListMeta, AlertUpdateRequest, AlertFeedbackRequest

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
    child_id: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    reviewed: bool | None = None,
    from_date: datetime | None = Query(None, alias="from"),
    to_date: datetime | None = Query(None, alias="to"),
    page: int = 1,
    per_page: int = Query(25, le=100),
):
    child_ids = await _get_parent_child_ids(db, current_parent.id)
    if not child_ids:
        return AlertListResponse(data=[], meta=AlertListMeta(total=0, page=page, per_page=per_page))

    q = select(Alert).where(Alert.child_id.in_(child_ids))

    if child_id:
        q = q.where(Alert.child_id == uuid.UUID(child_id))
    if severity:
        q = q.where(Alert.severity.in_(severity.split(",")))
    if category:
        q = q.where(Alert.category == category)
    if reviewed is True:
        q = q.where(Alert.reviewed_at.is_not(None))
    if reviewed is False:
        q = q.where(Alert.reviewed_at.is_(None))
    if from_date:
        q = q.where(Alert.created_at >= from_date)
    if to_date:
        q = q.where(Alert.created_at <= to_date)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar()

    q = q.order_by(Alert.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    q = q.options(selectinload(Alert.child))
    result = await db.execute(q)
    alerts = result.scalars().all()

    data = [_to_response(a) for a in alerts]
    return AlertListResponse(data=data, meta=AlertListMeta(total=total, page=page, per_page=per_page))


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: str,
    body: AlertUpdateRequest,
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    alert = await _get_owned_alert(db, alert_id, current_parent.id)
    if body.reviewed:
        alert.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(alert)
    return _to_response(alert)


@router.post("/{alert_id}/feedback")
async def submit_feedback(
    alert_id: str,
    body: AlertFeedbackRequest,
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if body.feedback not in ("correct", "false_positive"):
        raise HTTPException(status_code=400, detail="feedback must be 'correct' or 'false_positive'")
    alert = await _get_owned_alert(db, alert_id, current_parent.id)
    alert.parent_feedback = body.feedback
    await db.commit()
    return {"detail": "Feedback recorded"}


async def _get_owned_alert(db: AsyncSession, alert_id: str, parent_id: uuid.UUID) -> Alert:
    result = await db.execute(
        select(Alert)
        .join(Child, Child.id == Alert.child_id)
        .where(Alert.id == uuid.UUID(alert_id), Child.parent_id == parent_id)
        .options(selectinload(Alert.child))
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


async def _get_parent_child_ids(db: AsyncSession, parent_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(select(Child.id).where(Child.parent_id == parent_id))
    return result.scalars().all()


def _to_response(alert: Alert) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        child_id=alert.child_id,
        child_name=alert.child.display_name,
        direction=alert.direction,
        sender_address=alert.sender_address,
        recipient_addresses=alert.recipient_addresses,
        subject_snippet=alert.subject_snippet,
        received_at=alert.received_at,
        category=alert.category,
        severity=alert.severity,
        confidence=float(alert.confidence),
        ai_summary=alert.ai_summary,
        ai_response_script=alert.ai_response_script,
        parent_feedback=alert.parent_feedback,
        notified_at=alert.notified_at,
        reviewed_at=alert.reviewed_at,
        created_at=alert.created_at,
    )

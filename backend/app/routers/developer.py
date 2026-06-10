import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated

import redis as redis_lib
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.auth import get_current_developer
from app.config import get_settings
from app.models.parent import Parent
from app.models.child import Child
from app.models.gmail_connection import GmailConnection
from app.models.alert import Alert
from app.services.crypto import encrypt_token

router = APIRouter(prefix="/developer", tags=["developer"])
settings = get_settings()

_FAKE_ALERTS = [
    dict(
        severity="critical", category="self_harm", direction="inbound",
        sender_address="unknown456@gmail.com", subject_snippet=None,
        received_at=datetime.now(timezone.utc) - timedelta(hours=2),
        confidence=0.97,
        ai_summary="Sender expressed thoughts of self-harm and mentioned having a plan. Immediate parental intervention recommended.",
        ai_response_script="Sit down with your child today for an open, non-judgmental conversation. If they confirm distress, contact a mental health professional or call the crisis line (988).",
    ),
    dict(
        severity="critical", category="grooming", direction="inbound",
        sender_address="coolguy2009@hotmail.com", subject_snippet="Re: our secret",
        received_at=datetime.now(timezone.utc) - timedelta(hours=5),
        confidence=0.94,
        ai_summary="Unknown adult repeatedly asking child to keep conversations private and requesting an in-person meeting.",
        ai_response_script="Do not allow this contact to continue. Review the full conversation thread with your child and consider reporting to local authorities.",
    ),
    dict(
        severity="high", category="bullying", direction="inbound",
        sender_address="classmate99@gmail.com", subject_snippet="you're so weird",
        received_at=datetime.now(timezone.utc) - timedelta(hours=10),
        confidence=0.88,
        ai_summary="Multiple students coordinating to exclude and mock the child, with escalating threatening language.",
        ai_response_script="Contact your child's school counsellor and document this email thread. Talk to your child about what's been happening.",
    ),
    dict(
        severity="high", category="stranger_contact", direction="inbound",
        sender_address="noreply_promo@random.io", subject_snippet="You've been selected",
        received_at=datetime.now(timezone.utc) - timedelta(hours=18),
        confidence=0.82,
        ai_summary="Unsolicited contact from unknown sender asking for child's home address and school name.",
        ai_response_script="Block this sender and remind your child never to share personal details with unknown contacts.",
    ),
    dict(
        severity="medium", category="drugs_alcohol", direction="outbound",
        sender_address="bestfriend@gmail.com", subject_snippet="weekend plans",
        received_at=datetime.now(timezone.utc) - timedelta(days=1),
        confidence=0.78,
        ai_summary="Child describing plans to obtain and try alcohol at an unsupervised party this weekend.",
        ai_response_script="Have a calm conversation about alcohol risks. Review the weekend plans and ensure appropriate supervision.",
    ),
    dict(
        severity="medium", category="personal_info_sharing", direction="outbound",
        sender_address="competition_entry@site.com", subject_snippet="My entry",
        received_at=datetime.now(timezone.utc) - timedelta(days=2),
        confidence=0.75,
        ai_summary="Child shared full name, date of birth, home address, and school name in a competition submission email.",
        ai_response_script="Discuss online privacy with your child. Check the competition site's privacy policy and consider withdrawing the entry.",
    ),
    dict(
        severity="low", category="bullying", direction="inbound",
        sender_address="someone@gmail.com", subject_snippet="lol",
        received_at=datetime.now(timezone.utc) - timedelta(days=3),
        confidence=0.71,
        ai_summary="Mildly mocking message from a peer; tone is teasing but not threatening.",
        ai_response_script="Check in with your child about how things are going with this person. No urgent action required.",
    ),
    dict(
        severity="low", category="stranger_contact", direction="inbound",
        sender_address="newsletter@unknown.org", subject_snippet="Welcome!",
        received_at=datetime.now(timezone.utc) - timedelta(days=4),
        confidence=0.72,
        ai_summary="Automated-looking email from an unrecognised sender; low confidence of active grooming intent.",
        ai_response_script="Review your child's newsletter subscriptions together. No urgent action required.",
    ),
]


async def _get_or_create_child_and_connection(
    db: AsyncSession, parent: Parent
) -> tuple[Child, GmailConnection]:
    result = await db.execute(select(Child).where(Child.parent_id == parent.id).limit(1))
    child = result.scalar_one_or_none()
    if not child:
        child = Child(parent_id=parent.id, display_name="Demo Child")
        db.add(child)
        await db.flush()

    result = await db.execute(
        select(GmailConnection).where(GmailConnection.child_id == child.id).limit(1)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        conn = GmailConnection(
            child_id=child.id,
            gmail_address="demo@example.com",
            access_token=encrypt_token("fake"),
            refresh_token=encrypt_token("fake"),
            token_expiry=datetime.now(timezone.utc) + timedelta(days=365),
            status="error",  # prevents Celery poller from trying to use it
        )
        db.add(conn)
        await db.flush()

    return child, conn


@router.post("/fake-alerts")
async def inject_fake_alerts(
    current_parent: Annotated[Parent, Depends(get_current_developer)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    child, conn = await _get_or_create_child_and_connection(db, current_parent)

    inserted = 0
    for i, fixture in enumerate(_FAKE_ALERTS):
        msg_id = f"fake_{uuid.uuid4().hex[:12]}"
        alert = Alert(
            child_id=child.id,
            gmail_connection_id=conn.id,
            gmail_message_id=msg_id,
            recipient_addresses=[child.display_name.lower().replace(" ", "") + "@gmail.com"],
            **fixture,
        )
        db.add(alert)
        inserted += 1

    await db.commit()
    return {"inserted": inserted, "child_name": child.display_name}


@router.delete("/fake-data")
async def clear_fake_data(
    current_parent: Annotated[Parent, Depends(get_current_developer)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    child_ids_result = await db.execute(
        select(Child.id).where(Child.parent_id == current_parent.id)
    )
    child_ids = [r[0] for r in child_ids_result.all()]

    if not child_ids:
        return {"deleted": 0}

    result = await db.execute(
        select(Alert).where(
            Alert.child_id.in_(child_ids),
            Alert.gmail_message_id.like("fake_%"),
        )
    )
    alerts = result.scalars().all()
    for alert in alerts:
        await db.delete(alert)
    await db.commit()
    return {"deleted": len(alerts)}


@router.post("/trigger-poll")
async def trigger_poll(
    _: Annotated[Parent, Depends(get_current_developer)],
):
    from app.tasks.ingestion import poll_all_connections
    poll_all_connections.delay()
    return {"status": "queued"}


class ClassifyRequest(BaseModel):
    email_body: str
    subject: str = ""
    sender: str = "test@example.com"


@router.post("/classify")
async def classify(
    body: ClassifyRequest,
    _: Annotated[Parent, Depends(get_current_developer)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from app.services.analysis import classify_email, token_cost_usd
    from app.models.task_log import TaskLog

    started = datetime.now(timezone.utc)
    result = classify_email({
        "direction": "inbound",
        "sender_address": body.sender,
        "recipient_addresses": ["child@example.com"],
        "subject": body.subject,
        "body_text": body.email_body,
    })

    input_tokens = result.pop("input_tokens", 0)
    output_tokens = result.pop("output_tokens", 0)
    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

    # Log the playground call so its token usage counts toward admin LLM stats.
    db.add(TaskLog(
        task_name="playground_classify",
        status="success",
        duration_ms=duration_ms,
        meta={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "severity": result.get("severity", "none"),
            "playground": True,
        },
    ))
    await db.commit()

    return {
        "classification": result,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": token_cost_usd(input_tokens, output_tokens),
        },
    }


@router.post("/test-notification")
async def test_notification(
    current_parent: Annotated[Parent, Depends(get_current_developer)],
):
    from app.services.notifications import send_alert_email
    send_alert_email(
        current_parent.email,
        "Demo Child",
        {
            "severity": "high",
            "category": "grooming",
            "ai_summary": "This is a test alert from the SafeMail developer tools. No action needed.",
            "ai_response_script": "This was sent by you to verify that email notifications are working correctly.",
        },
    )
    return {"sent_to": current_parent.email}


@router.get("/queue-depth")
async def queue_depth(
    _: Annotated[Parent, Depends(get_current_developer)],
):
    r = redis_lib.from_url(settings.redis_url)
    pending = r.llen("celery")
    return {"pending": pending}

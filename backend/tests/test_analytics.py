"""Tests for the first-party analytics suite: the public collect endpoint
(allowlist governance) and the activation-funnel computation on seeded data.

Uses the async test DB + client fixtures from conftest. No external services.
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select, func

from app.models.parent import Parent
from app.models.child import Child
from app.models.gmail_connection import GmailConnection
from app.models.alert import Alert
from app.models.analytics_event import AnalyticsEvent
from app.services.analytics_events import (
    compute_activation_funnel, compute_acquisition_funnel, compute_events_breakdown,
    record_event_async,
)

pytestmark = pytest.mark.asyncio


# ── Ingestion / governance ────────────────────────────────────────────────────

async def test_collect_accepts_known_and_drops_unknown(client, db):
    resp = await client.post("/v1/analytics/collect", json={
        "visitor_id": "vis-1",
        "session_id": "sess-1",
        "events": [
            {"name": "page_viewed", "path": "/"},
            {"name": "landing_cta_clicked", "properties": {"cta": "waitlist"}},
            {"name": "definitely_not_a_real_event"},
        ],
    })
    assert resp.status_code == 202
    body = resp.json()
    assert body["received"] == 3
    assert body["accepted"] == 2  # the unknown name is dropped by the allowlist

    stored = (await db.execute(select(func.count()).select_from(AnalyticsEvent))).scalar()
    assert stored == 2
    names = set((await db.execute(select(AnalyticsEvent.event_name))).scalars().all())
    assert names == {"page_viewed", "landing_cta_clicked"}


async def test_collect_requires_no_auth(client):
    # Pre-login visitors must be able to send events anonymously.
    resp = await client.post("/v1/analytics/collect", json={
        "visitor_id": "anon", "events": [{"name": "page_viewed", "path": "/"}],
    })
    assert resp.status_code == 202
    assert resp.json()["accepted"] == 1


async def test_record_event_async_drops_unknown(db):
    await record_event_async(db, "not_in_allowlist")
    count = (await db.execute(select(func.count()).select_from(AnalyticsEvent))).scalar()
    assert count == 0

    await record_event_async(db, "account_registered")
    count = (await db.execute(select(func.count()).select_from(AnalyticsEvent))).scalar()
    assert count == 1


# ── Funnel computation ────────────────────────────────────────────────────────

async def _mk_parent(db, email, *, verified=False, consented=False, onboarded=False) -> Parent:
    p = Parent(email=email, password_hash="x", is_email_verified=verified)
    if consented:
        p.monitoring_consent_at = datetime.now(timezone.utc)
    if onboarded:
        p.onboarding_completed_at = datetime.now(timezone.utc)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def _connect_gmail(db, parent) -> GmailConnection:
    child = Child(parent_id=parent.id, display_name="Kid")
    db.add(child)
    await db.commit()
    await db.refresh(child)
    conn = GmailConnection(
        child_id=child.id, gmail_address=f"{uuid.uuid4().hex}@gmail.com",
        access_token="enc", refresh_token="enc",
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return conn


async def _add_alert(db, child_id, conn_id):
    db.add(Alert(
        child_id=child_id, gmail_connection_id=conn_id, gmail_message_id="msg-1",
        direction="inbound", sender_address="a@b.com", recipient_addresses=["kid@gmail.com"],
        received_at=datetime.now(timezone.utc), category="bullying", severity="high",
        confidence=0.9, ai_summary="test",
    ))
    await db.commit()


async def test_activation_funnel_counts_and_dropoff(db):
    # p1: registered only. p2: + verified. p3: full activation. p4: + first alert.
    await _mk_parent(db, "p1@x.com")
    await _mk_parent(db, "p2@x.com", verified=True)
    p3 = await _mk_parent(db, "p3@x.com", verified=True, consented=True, onboarded=True)
    await _connect_gmail(db, p3)
    p4 = await _mk_parent(db, "p4@x.com", verified=True, consented=True, onboarded=True)
    conn4 = await _connect_gmail(db, p4)
    await _add_alert(db, conn4.child_id, conn4.id)

    since = datetime.now(timezone.utc) - timedelta(days=30)
    result = await compute_activation_funnel(db, since)
    counts = {s["key"]: s["count"] for s in result["stages"]}

    assert counts["registered"] == 4
    assert counts["verified"] == 3
    assert counts["consented"] == 2
    assert counts["child_added"] == 2
    assert counts["gmail_connected"] == 2
    assert counts["onboarded"] == 2
    assert counts["first_alert"] == 1

    # Step conversion verified→registered = 3/4; drop-off = 1/4.
    verified_stage = next(s for s in result["stages"] if s["key"] == "verified")
    assert verified_stage["step_conversion"] == 0.75
    assert verified_stage["drop_off"] == 0.25

    # Activation rate = connected / registered = 2/4.
    assert result["activation_rate"] == 0.5
    # Time-to-value is computable for the onboarded cohort.
    assert result["time_to_value_seconds"] is not None


async def test_acquisition_funnel_from_events(db):
    # Two visitors, one waitlist join, one registration — via events.
    db.add(AnalyticsEvent(event_name="page_viewed", visitor_id="v1", source="client"))
    db.add(AnalyticsEvent(event_name="page_viewed", visitor_id="v1", source="client"))
    db.add(AnalyticsEvent(event_name="page_viewed", visitor_id="v2", source="client"))
    db.add(AnalyticsEvent(event_name="waitlist_joined", visitor_id="server", source="server"))
    db.add(AnalyticsEvent(event_name="account_registered", visitor_id="server", source="server"))
    await db.commit()

    since = datetime.now(timezone.utc) - timedelta(days=30)
    stages = {s["key"]: s["count"] for s in await compute_acquisition_funnel(db, since)}
    assert stages["visitors"] == 2      # distinct visitor_id on page_viewed
    assert stages["waitlist"] == 1
    assert stages["registered"] == 1


async def test_events_breakdown(db):
    # Regression: the daily timeseries GROUP BY must not crash on Postgres.
    db.add(AnalyticsEvent(event_name="page_viewed", visitor_id="v1", source="client", path="/"))
    db.add(AnalyticsEvent(event_name="page_viewed", visitor_id="v2", source="client", path="/login",
                          referrer="https://google.com"))
    db.add(AnalyticsEvent(event_name="account_registered", visitor_id="server", source="server"))
    await db.commit()

    since = datetime.now(timezone.utc) - timedelta(days=30)
    result = await compute_events_breakdown(db, since)

    by_name = {r["event"]: r["count"] for r in result["by_name"]}
    assert by_name["page_viewed"] == 2
    assert by_name["account_registered"] == 1
    paths = {r["path"]: r["count"] for r in result["top_paths"]}
    assert paths["/"] == 1 and paths["/login"] == 1
    assert any(r["referrer"] == "https://google.com" for r in result["top_referrers"])
    # Daily timeseries returns at least one bucket and doesn't raise.
    assert len(result["daily"]) >= 1
    assert result["daily"][0]["page_views"] == 2

import pytest
from httpx import AsyncClient

from app.routers import waitlist as waitlist_router
from app.models.allowed_email import AllowedEmail

pytestmark = pytest.mark.asyncio


async def test_signup_notifies_ops_once(client: AsyncClient, monkeypatch):
    calls = []
    monkeypatch.setattr(waitlist_router.settings, "ops_alert_email", "ops@example.com")
    monkeypatch.setattr(waitlist_router, "send_waitlist_notification",
                        lambda *a, **k: calls.append(a))

    r = await client.post("/v1/waitlist", json={"email": "New@Person.com", "source": "ad"})
    assert r.status_code == 201
    assert len(calls) == 1
    recipients, entry_email, source = calls[0][0], calls[0][1], calls[0][2]
    assert recipients == ["ops@example.com"]
    assert entry_email == "new@person.com"   # normalized
    assert source == "ad"

    # A duplicate signup must NOT fire a second notification.
    r2 = await client.post("/v1/waitlist", json={"email": "new@person.com"})
    assert r2.status_code == 201
    assert len(calls) == 1


async def test_already_invited_does_not_notify(client: AsyncClient, db, monkeypatch):
    calls = []
    monkeypatch.setattr(waitlist_router.settings, "ops_alert_email", "ops@example.com")
    monkeypatch.setattr(waitlist_router, "send_waitlist_notification",
                        lambda *a, **k: calls.append(a))

    db.add(AllowedEmail(email="invited@example.com", note="test"))
    await db.commit()

    r = await client.post("/v1/waitlist", json={"email": "invited@example.com"})
    assert r.status_code == 201
    assert r.json()["status"] == "already_invited"
    assert calls == []  # allowlisted users skip the waitlist entirely


async def test_no_recipients_no_crash(client: AsyncClient, monkeypatch):
    # No ops address and no admin parents → signup still succeeds (no notification).
    monkeypatch.setattr(waitlist_router.settings, "ops_alert_email", "")
    sent = []
    monkeypatch.setattr(waitlist_router, "send_waitlist_notification",
                        lambda *a, **k: sent.append(a))
    r = await client.post("/v1/waitlist", json={"email": "lonely@example.com"})
    assert r.status_code == 201
    assert sent == []  # _notify resolves to no recipients and skips the send

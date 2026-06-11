from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, func

from app.models.parent import Parent
from app.models.child import Child
from app.models.gmail_connection import GmailConnection
from app.models.alert import Alert
from app.models.allowed_email import AllowedEmail
from app.services.crypto import encrypt_token

pytestmark = pytest.mark.asyncio


async def test_register(client: AsyncClient):
    resp = await client.post("/v1/auth/register", json={
        "email": "parent@example.com",
        "password": "securepassword123",
        "full_name": "Test Parent",
    })
    assert resp.status_code == 201
    assert "access_token" in resp.json()


async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "pass1234"}
    await client.post("/v1/auth/register", json=payload)
    resp = await client.post("/v1/auth/register", json=payload)
    assert resp.status_code == 409


async def test_login_success(client: AsyncClient):
    await client.post("/v1/auth/register", json={"email": "login@example.com", "password": "pass1234"})
    resp = await client.post("/v1/auth/login", json={"email": "login@example.com", "password": "pass1234"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_wrong_password(client: AsyncClient):
    await client.post("/v1/auth/register", json={"email": "wrongpass@example.com", "password": "correct1"})
    resp = await client.post("/v1/auth/login", json={"email": "wrongpass@example.com", "password": "wrong"})
    assert resp.status_code == 401


async def test_delete_account_wipes_all_data(client: AsyncClient, db, monkeypatch):
    # Don't make a real network call to Google's revoke endpoint.
    revoked = []
    monkeypatch.setattr("app.routers.auth.revoke_token", lambda t: revoked.append(t) or True)

    email = "leaving@example.com"
    reg = await client.post("/v1/auth/register", json={"email": email, "password": "pass1234"})
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Seed an allowlist entry and a full child -> connection -> alert graph.
    db.add(AllowedEmail(email=email))
    parent = (await db.execute(select(Parent).where(Parent.email == email))).scalar_one()
    child = Child(parent_id=parent.id, display_name="Kid")
    db.add(child)
    await db.flush()
    conn = GmailConnection(
        child_id=child.id,
        gmail_address="kid@gmail.com",
        access_token=encrypt_token("access"),
        refresh_token=encrypt_token("refresh-secret"),
        token_expiry=datetime.now(timezone.utc),
    )
    db.add(conn)
    await db.flush()
    db.add(Alert(
        child_id=child.id,
        gmail_connection_id=conn.id,
        gmail_message_id="msg1",
        direction="inbound",
        sender_address="stranger@example.com",
        recipient_addresses=["kid@gmail.com"],
        received_at=datetime.now(timezone.utc),
        category="grooming",
        severity="high",
        confidence=0.91,
        ai_summary="summary",
    ))
    await db.commit()

    resp = await client.request("DELETE", "/v1/auth/account", headers=headers)
    assert resp.status_code == 204

    # The Google grant was revoked using the decrypted refresh token.
    assert revoked == ["refresh-secret"]

    # Nothing tied to the parent survives.
    async def count(model, **where):
        stmt = select(func.count()).select_from(model)
        for k, v in where.items():
            stmt = stmt.where(getattr(model, k) == v)
        return (await db.execute(stmt)).scalar()

    assert await count(Parent, id=parent.id) == 0
    assert await count(Child, parent_id=parent.id) == 0
    assert await count(GmailConnection, child_id=child.id) == 0
    assert await count(Alert, child_id=child.id) == 0
    assert await count(AllowedEmail, email=email) == 0


async def test_delete_account_requires_auth(client: AsyncClient):
    resp = await client.request("DELETE", "/v1/auth/account")
    # HTTPBearer returns 403 when the Authorization header is entirely absent.
    assert resp.status_code in (401, 403)

import pytest
from httpx import AsyncClient

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
    payload = {"email": "dup@example.com", "password": "pass123"}
    await client.post("/v1/auth/register", json=payload)
    resp = await client.post("/v1/auth/register", json=payload)
    assert resp.status_code == 409


async def test_login_success(client: AsyncClient):
    await client.post("/v1/auth/register", json={"email": "login@example.com", "password": "pass123"})
    resp = await client.post("/v1/auth/login", json={"email": "login@example.com", "password": "pass123"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_wrong_password(client: AsyncClient):
    await client.post("/v1/auth/register", json={"email": "wrongpass@example.com", "password": "correct"})
    resp = await client.post("/v1/auth/login", json={"email": "wrongpass@example.com", "password": "wrong"})
    assert resp.status_code == 401

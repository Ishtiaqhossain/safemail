import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _auth_header(client: AsyncClient, email: str = "alert_parent@example.com") -> dict:
    await client.post("/v1/auth/register", json={"email": email, "password": "pass123"})
    resp = await client.post("/v1/auth/login", json={"email": email, "password": "pass123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_list_alerts_empty(client: AsyncClient):
    headers = await _auth_header(client)
    resp = await client.get("/v1/alerts", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"] == []
    assert resp.json()["meta"]["total"] == 0


async def test_create_child_and_list(client: AsyncClient):
    headers = await _auth_header(client, "child_test@example.com")
    resp = await client.post("/v1/children", json={"display_name": "Emma", "birth_year": 2014}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["display_name"] == "Emma"

    resp = await client.get("/v1/children", headers=headers)
    assert len(resp.json()) == 1

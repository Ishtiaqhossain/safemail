"""Prod-safety: the /v1/dev/* seed seam must be invisible unless explicitly enabled.

`get_settings()` is cached and the app is built once at import, so flipping env
inside the test process wouldn't rebuild the routes. Each case therefore runs in a
clean subprocess with its own environment.
"""
import os
import subprocess
import sys

_PROD_SECRETS = {
    "DEBUG": "false",
    "FERNET_KEY": "x", "GOOGLE_CLIENT_SECRET": "x",
    "ANTHROPIC_API_KEY": "x", "SENDGRID_API_KEY": "x",
}

_ROUTE_PRESENT = (
    "import app.main as m;"
    "print('PRESENT' if any(getattr(r,'path','')=='/v1/dev/seed-parent' "
    "for r in m.app.routes) else 'ABSENT')"
)

_GUARD_404 = """
import asyncio, httpx, app.main as m
from httpx import ASGITransport

async def go():
    t = ASGITransport(app=m.app)
    async with httpx.AsyncClient(transport=t, base_url="http://t") as c:
        a = await c.post("/v1/dev/reset", json={"email_prefix": "e2e-"})  # no secret header
        b = await c.post("/v1/dev/reset", json={"email_prefix": "e2e-"},
                         headers={"X-E2E-Seed-Secret": "wrong"})
        print("NOHDR", a.status_code, "WRONG", b.status_code)

asyncio.run(go())
"""


def _run(code: str, env_overrides: dict) -> str:
    env = {**os.environ, **env_overrides}
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        env=env, cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    assert out.returncode == 0, f"subprocess failed:\n{out.stdout}\n{out.stderr}"
    return out.stdout.strip()


def test_seed_routes_absent_in_production():
    # DEBUG=false (and seeding unset) — the seam does not exist.
    assert _run(_ROUTE_PRESENT, _PROD_SECRETS) == "ABSENT"


def test_seed_routes_absent_when_debug_but_seed_disabled():
    # Even in local DEBUG, seeding is off unless explicitly enabled.
    assert _run(_ROUTE_PRESENT, {"DEBUG": "true", "E2E_SEED_ENABLED": "false"}) == "ABSENT"


def test_seed_routes_present_only_when_fully_enabled():
    env = {"DEBUG": "true", "E2E_SEED_ENABLED": "true", "E2E_SEED_SECRET": "s3cret"}
    assert _run(_ROUTE_PRESENT, env) == "PRESENT"


def test_seed_routes_require_secret_header():
    # With the seam on, requests without the right secret are 404 (feature hidden),
    # and the guard rejects before any DB access.
    env = {"DEBUG": "true", "E2E_SEED_ENABLED": "true", "E2E_SEED_SECRET": "s3cret"}
    assert _run(_GUARD_404, env) == "NOHDR 404 WRONG 404"

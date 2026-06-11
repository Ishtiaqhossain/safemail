import os

# Disable auth rate limiting before the app (and its cached settings) load,
# so repeated login/register calls in tests aren't throttled.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

# Disable the invite-only gate too — each test starts from a clean DB, so a
# freshly registered parent wouldn't be on the allowlist and login would 403.
os.environ.setdefault("INVITE_ONLY_ENABLED", "false")

# Run the app in debug so the production secret-validation in config.py doesn't
# fail at import when a CI environment has no .env.
os.environ.setdefault("DEBUG", "true")

import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.main import app
from app.database import Base, get_db

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/safemail_test"


@pytest_asyncio.fixture
async def db():
    # A fresh engine per test, created inside the test's own event loop. NullPool
    # means connections are never pooled across loops — which is what previously
    # caused "attached to a different loop" errors under pytest-asyncio's
    # per-test loops. drop+create gives each test a clean schema.
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
        await session.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

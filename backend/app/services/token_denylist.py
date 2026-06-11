"""Redis-backed denylist for revoked refresh-token JTIs.

On logout we record the refresh token's `jti` with a TTL equal to its remaining
lifetime, so a stolen refresh token can't mint new access tokens after the user
logs out. Entries expire automatically once the token would have expired anyway,
so the set stays bounded with no cleanup job.

Refresh tokens issued before `jti` was added simply have nothing to revoke; they
age out on their own and gain revocation support the next time the user logs in.
"""
import redis.asyncio as aioredis

from app.config import get_settings

settings = get_settings()

_redis: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url)
    return _redis


def _key(jti: str) -> str:
    return f"revoked_refresh:{jti}"


async def revoke(jti: str, ttl_seconds: int) -> None:
    """Mark a refresh-token jti as revoked for `ttl_seconds`."""
    if not jti or ttl_seconds <= 0:
        return
    await _client().setex(_key(jti), ttl_seconds, "1")


async def is_revoked(jti: str | None) -> bool:
    if not jti:
        return False
    return await _client().exists(_key(jti)) == 1

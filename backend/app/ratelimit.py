"""Shared rate limiter for auth endpoints.

Backed by Redis (already required by the app), keyed on client IP. Limits are
applied via @limiter.limit(...) decorators on the relevant routes in
app.routers.auth. Disable globally with RATE_LIMIT_ENABLED=false (used by tests).

NOTE: get_remote_address reads request.client.host. Behind a reverse proxy you
must enable proxy headers (e.g. uvicorn --proxy-headers) so this is the real
client IP and not the proxy's.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    enabled=settings.rate_limit_enabled,
)

# Per-endpoint limits, kept here so they're easy to tune in one place.
LOGIN_LIMIT = "5/minute"
REGISTER_LIMIT = "10/hour"
REFRESH_LIMIT = "60/minute"
FORGOT_PASSWORD_LIMIT = "3/minute"
RESET_PASSWORD_LIMIT = "5/minute"
RESEND_VERIFICATION_LIMIT = "3/minute"

from functools import lru_cache
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/safemail"
    redis_url: str = "redis://localhost:6379/0"

    # JWT keys. In production set the PEM *contents* via these env vars (works on
    # any host without a "secret files" feature); locally we fall back to the
    # file paths below. See app/auth.py::_load_keys.
    jwt_private_key: str = ""
    jwt_public_key: str = ""
    jwt_private_key_path: str = "./keys/private.pem"
    jwt_public_key_path: str = "./keys/public.pem"
    jwt_algorithm: str = "RS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    fernet_key: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/v1/auth/google/callback"

    anthropic_api_key: str = ""
    sendgrid_api_key: str = ""
    fcm_service_account_json: str = ""

    frontend_url: str = "http://localhost:3000"
    cookie_secure: bool = False

    # Production hardening. When False (the production default): Swagger/redoc are
    # disabled, 500s return a generic body instead of the exception text, and
    # startup fails fast if required secrets are missing. Set DEBUG=true locally.
    debug: bool = False

    confidence_threshold: float = 0.70
    max_body_length: int = 8000
    alert_poll_interval_minutes: int = 5

    # Auth rate limiting (slowapi, Redis-backed). Disabled in the test suite.
    rate_limit_enabled: bool = True

    # Invite-only alpha: only allowlisted emails may register / log in.
    # Set False to open registration for public launch.
    invite_only_enabled: bool = True

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        # Managed hosts hand out `postgres://` / `postgresql://`; the app needs the
        # asyncpg driver. Normalize here so any host's connection string works
        # unchanged (the sync engine in database.py derives its URL from this).
        for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
            if v.startswith(prefix):
                return "postgresql+asyncpg://" + v[len(prefix):]
        return v

    _REQUIRED_IN_PROD = ("fernet_key", "google_client_secret", "anthropic_api_key", "sendgrid_api_key")

    @model_validator(mode="after")
    def _require_secrets_in_prod(self) -> "Settings":
        # Fail fast on boot if a production deploy (DEBUG=false) is missing a
        # secret, instead of surfacing as a 500 on the first request that needs it.
        if not self.debug:
            missing = [name for name in self._REQUIRED_IN_PROD if not getattr(self, name)]
            if missing:
                raise ValueError(
                    "Missing required production settings (set these, or DEBUG=true for local dev): "
                    + ", ".join(missing)
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

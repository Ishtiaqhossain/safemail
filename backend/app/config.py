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

    # Microsoft (Outlook / Microsoft 365) OAuth — optional; mailbox connect for
    # this provider only works once these are set (Azure / Microsoft Entra app).
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_uri: str = "http://localhost:8000/v1/auth/oauth/microsoft/callback"

    anthropic_api_key: str = ""
    sendgrid_api_key: str = ""
    fcm_service_account_json: str = ""

    frontend_url: str = "http://localhost:3000"
    cookie_secure: bool = False

    # From-address for all transactional email. Must be a verified SendGrid sender
    # (single sender, or any address on an authenticated domain). Override per env.
    email_from: str = "noreply@safemail.com"

    # When False, all transactional email (verification, reset, alerts, digest,
    # reconnect, health) is skipped — the send_* helpers no-op. Used by E2E/CI so
    # registration etc. never touch SendGrid. Default True (normal behavior).
    transactional_email_enabled: bool = True

    # ── E2E test seam (NEVER enable in production) ─────────────────────────────
    # The /v1/dev/* seed router is mounted only when BOTH debug and e2e_seed_enabled
    # are true, and every seed request must present e2e_seed_secret. Both default
    # off so a misconfigured prod with DEBUG=true still doesn't expose seeding.
    e2e_seed_enabled: bool = False
    e2e_seed_secret: str = ""

    # Production hardening. When False (the production default): Swagger/redoc are
    # disabled, 500s return a generic body instead of the exception text, and
    # startup fails fast if required secrets are missing. Set DEBUG=true locally.
    debug: bool = False

    confidence_threshold: float = 0.70
    max_body_length: int = 8000
    alert_poll_interval_minutes: int = 5

    # Model cascade (Haiku triage → Sonnet escalation). OFF by default: it cuts
    # cost but the live eval showed Haiku over-confidently clears subtle
    # personal_info_sharing disclosures, regressing that category's recall. Keep
    # off until the escalation rule is tuned and re-validated against the eval.
    cascade_enabled: bool = False

    # Auth rate limiting (slowapi, Redis-backed). Disabled in the test suite.
    rate_limit_enabled: bool = True

    # Invite-only alpha: only allowlisted emails may register / log in.
    # Set False to open registration for public launch.
    invite_only_enabled: bool = True

    # ── Agentic self-monitoring ────────────────────────────────────────────────
    # A scheduled Celery task runs health probes over the system (DB, Redis, the
    # Celery queue, Gmail polling freshness, AI failure rate). When a probe trips,
    # it opens a HealthIncident, emails ops, and hands the finding to an
    # LLM remediation agent (app/services/remediation.py).
    monitoring_enabled: bool = True
    monitoring_interval_minutes: int = 10

    # The remediation agent may call read-only investigation tools always; it may
    # call bounded *fix* actions (re-enqueue polling, reset a stuck connection)
    # only when this is on. Off by default — the agent diagnoses and recommends
    # but does not act until an operator opts in.
    auto_remediation_enabled: bool = False

    # Where system-health alerts are sent. Falls back to every Parent.is_admin
    # address when unset, so a fresh deploy still reaches someone.
    ops_alert_email: str = ""

    # Probe thresholds. Tuned conservatively so a single transient blip doesn't
    # page; sustained problems do.
    health_stale_connection_minutes: int = 30   # active conn not synced in this long
    health_failure_window_minutes: int = 30      # window for the failure-rate probe
    health_max_failure_rate: float = 0.30        # task failure ratio that trips a warning
    health_min_failures_to_alert: int = 3        # don't trip on 1/1 failures in a quiet window
    health_queue_depth_warn: int = 200           # Celery backlog that trips a warning

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

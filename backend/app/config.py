from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/safemail"
    redis_url: str = "redis://localhost:6379/0"

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

    confidence_threshold: float = 0.70
    max_body_length: int = 8000
    alert_poll_interval_minutes: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()

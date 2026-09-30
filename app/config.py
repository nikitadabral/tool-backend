from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment / .env file."""

    app_name: str = "Request Triage API"
    debug: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,https://tool-ui.onrender.com/"
    database_url: str = "sqlite:///./app.db"

    # Optional until PlaceholderBriefProvider is replaced by an OpenAI provider.
    openai_api_key: str | None = None

    # Auth / JWT. Override jwt_secret in .env for any real deployment.
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Optional outbound handoff for newly approved requests.
    outbound_webhook_url: str | None = None
    outbound_webhook_secret: str | None = None
    outbound_webhook_timeout_seconds: float = 5.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

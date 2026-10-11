from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

# backend/.env, found relative to this file so it works from any working directory
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Application settings, loaded from environment variables or backend/.env."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8")

    app_name: str = "SkinCare API"
    environment: str = "development"

    db_host: str = "localhost"
    db_port: int = 5433
    db_name: str = "skincare_app"
    db_user: str = "postgres"
    db_password: str

    # Signs the access tokens. Must stay secret: anyone who has it can create valid tokens.
    jwt_secret: str = Field(min_length=32)
    access_token_expire_minutes: int = 15  # short, so a stolen access token is useless quickly
    refresh_token_expire_days: int = 30  # mobile users stay logged in; rotated on every refresh

    # Browser origins allowed to call the API, e.g. ["http://localhost:5173"] for the React admin.
    # Empty = no browser access; the mobile app does not need CORS.
    cors_origins: list[str] = []

    @property
    def database_url(self) -> URL:
        # URL.create escapes special characters in the password safely
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


@lru_cache
def get_settings() -> Settings:
    """Read the settings once and reuse them for the rest of the app's life."""
    return Settings()

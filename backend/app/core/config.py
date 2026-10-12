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

    # bcrypt cost: each +1 doubles the hashing time. 12 (~0.25 s) makes guessing passwords
    # expensive; tests use 4, because they check that hashing works, not how slow it is.
    bcrypt_rounds: int = Field(default=12, ge=4, le=16)

    # Signs the access tokens. Must stay secret: anyone who has it can create valid tokens.
    jwt_secret: str = Field(min_length=32)
    access_token_expire_minutes: int = 15  # short, so a stolen access token is useless quickly
    refresh_token_expire_days: int = 30  # mobile users stay logged in; rotated on every refresh
    # admins can change rules and see all appointments, so a stolen session is more dangerous:
    # one working day, then a fresh login
    admin_refresh_token_expire_hours: int = 12

    # At sign-up, reject emails whose domain cannot receive email (DNS lookup). Off in tests,
    # which must not depend on the internet.
    email_check_deliverability: bool = True

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

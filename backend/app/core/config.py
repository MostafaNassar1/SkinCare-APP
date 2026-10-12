from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
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

    # 6-digit email codes (verification, password reset)
    email_code_expire_minutes: int = 10
    email_code_max_attempts: int = 5  # 6 digits = 1,000,000 options: a script could guess them all
    email_code_resend_seconds: int = 60  # protects inboxes from floods and Gmail's daily limit

    # Outgoing email. "console" prints emails in the server terminal (development, no account
    # needed); "smtp" really sends them through Gmail.
    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587  # STARTTLS: the connection is encrypted before logging in
    smtp_username: str = ""  # the app's Gmail address, also used as the sender
    smtp_password: SecretStr = SecretStr("")  # Gmail App Password; SecretStr hides it in logs
    email_from_name: str = "SkinCare App"

    @field_validator("smtp_password", mode="before")
    @classmethod
    def remove_spaces(cls, value: object) -> object:
        # Google shows App Passwords in groups ("abcd efgh ijkl mnop"); accept them as copied
        return value.replace(" ", "") if isinstance(value, str) else value

    @model_validator(mode="after")
    def smtp_needs_credentials(self) -> "Settings":
        if self.email_backend == "smtp" and not (
            self.smtp_username and self.smtp_password.get_secret_value()
        ):
            raise ValueError("EMAIL_BACKEND=smtp needs SMTP_USERNAME and SMTP_PASSWORD")
        return self

    # Google sign-in: a Google ID token is accepted only if it was issued for one of these OAuth
    # Client IDs (our Web client; later also Android/iOS). Empty = Google sign-in is refused,
    # never "accept any audience".
    google_client_ids: list[str] = []

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

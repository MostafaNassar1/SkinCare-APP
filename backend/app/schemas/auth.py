from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES
from app.schemas.user import UserOut

# NIST SP 800-63B: length matters more than forced symbols/digits; bcrypt caps it at 72 bytes
PASSWORD_MIN_LENGTH = 8


class RegisterRequest(BaseModel):
    full_name: str = Field(max_length=150)
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH)

    @field_validator("full_name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Full name is required")
        return value

    @field_validator("email")
    @classmethod
    def email_lowercase(cls, value: str) -> str:
        # one account per address regardless of case (the database index enforces the same)
        return value.lower()

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        # not stripped: spaces are allowed in passwords
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes")
        return value


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # access token lifetime in seconds, so the app knows when to refresh


class UserAuthResponse(TokenResponse):
    user: UserOut

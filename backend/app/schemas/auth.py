from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES
from app.schemas.user import UserOut

# NIST SP 800-63B: length matters more than forced symbols/digits; bcrypt caps it at 72 bytes
PASSWORD_MIN_LENGTH = 8


# Rules shared by user sign-up and admin creation


def clean_full_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Full name is required")
    return value


def clean_email(value: str) -> str:
    # one account per address regardless of case (the database index enforces the same)
    return value.lower()


def check_password_bytes(value: str) -> str:
    # not stripped: spaces are allowed in passwords
    if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes")
    return value


FullName = Annotated[str, Field(max_length=150), AfterValidator(clean_full_name)]
NewEmail = Annotated[EmailStr, Field(max_length=255), AfterValidator(clean_email)]
# min length is added where it is used (8 for users, 12 for admins)
NewPassword = Annotated[str, AfterValidator(check_password_bytes)]


class RegisterRequest(BaseModel):
    full_name: FullName
    email: NewEmail
    password: Annotated[NewPassword, Field(min_length=PASSWORD_MIN_LENGTH)]


class LoginRequest(BaseModel):
    # no format or length rules here: anything that does not match an account gets the same
    # "invalid credentials" answer, so the response never hints at what was wrong
    email: str = Field(max_length=255)
    password: str

    @field_validator("email")
    @classmethod
    def email_trimmed(cls, value: str) -> str:
        # phone keyboards and autofill often add a trailing space; the password is left as typed
        return value.strip()


class VerifyEmailRequest(LoginRequest):
    """Email + password + code: proving the inbox (code) is not enough on its own, or someone who
    re-registered the unverified email with their own password could get the account."""

    code: str = Field(pattern=r"^\d{6}$")


class CodeSentResponse(BaseModel):
    email: str
    message: str
    code_expires_in: int  # seconds
    resend_available_in: int  # seconds before "Resend code" may be used


class ForgotPasswordRequest(BaseModel):
    email: str = Field(max_length=255)

    @field_validator("email")
    @classmethod
    def email_trimmed(cls, value: str) -> str:
        return value.strip()


class ResetPasswordRequest(ForgotPasswordRequest):
    code: str = Field(pattern=r"^\d{6}$")
    new_password: Annotated[NewPassword, Field(min_length=PASSWORD_MIN_LENGTH)]


class MessageResponse(BaseModel):
    message: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(max_length=255)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # access token lifetime in seconds, so the app knows when to refresh


class UserAuthResponse(TokenResponse):
    user: UserOut

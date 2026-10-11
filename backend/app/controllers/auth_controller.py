from functools import cache

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, account_disabled
from app.core.security import generate_token, hash_password, verify_password
from app.repositories import user_repository
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserAuthResponse,
)
from app.schemas.user import UserOut
from app.services import token_service
from app.services.token_service import TokenPair


def _email_taken() -> AppError:
    return AppError(409, "email_taken", "An account with this email already exists")


def _invalid_credentials() -> AppError:
    # one answer for unknown email, wrong password and Google-only accounts
    return AppError(401, "invalid_credentials", "Incorrect email or password")


@cache
def _dummy_password_hash() -> str:
    """A real bcrypt hash of a random password, computed once and never matched."""
    return hash_password(generate_token())


def _user_auth_response(tokens: TokenPair, user) -> UserAuthResponse:
    return UserAuthResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user=UserOut.model_validate(user),
    )


def register(db: Session, data: RegisterRequest) -> UserAuthResponse:
    """Create an email/password account and log the user in straight away."""
    if user_repository.get_by_email(db, data.email) is not None:
        raise _email_taken()

    try:
        user = user_repository.create_email_user(
            db,
            full_name=data.full_name,
            email=data.email,
            password_hash=hash_password(data.password),
        )
        tokens = token_service.issue_token_pair(db, user.id, "user")
        db.commit()
    except IntegrityError:
        # two sign-ups with the same email at the same moment: the unique index stops the second
        db.rollback()
        raise _email_taken() from None

    return _user_auth_response(tokens, user)


def login(db: Session, data: LoginRequest) -> UserAuthResponse:
    user = user_repository.get_by_email(db, data.email)

    if user is None or user.password_hash is None:
        # Still run a full bcrypt check, so this answer takes as long as a wrong password and the
        # response time does not reveal which emails have an account.
        verify_password(data.password, _dummy_password_hash())
        raise _invalid_credentials()
    if not verify_password(data.password, user.password_hash):
        raise _invalid_credentials()
    # only revealed to someone who knows the password
    if not user.is_active:
        raise account_disabled()

    tokens = token_service.issue_token_pair(db, user.id, "user")
    db.commit()
    return _user_auth_response(tokens, user)


def refresh(db: Session, data: RefreshTokenRequest) -> TokenResponse:
    user_id, tokens = token_service.rotate_refresh_token(db, data.refresh_token, "user")

    user = user_repository.get_by_id(db, user_id)
    if user is None or not user.is_active:
        db.rollback()
        raise account_disabled()

    db.commit()
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


def logout(db: Session, data: RefreshTokenRequest) -> None:
    """Revoke the refresh token. Always succeeds, so it reveals nothing about the token."""
    token_service.revoke_refresh_token(db, data.refresh_token, "user")
    db.commit()

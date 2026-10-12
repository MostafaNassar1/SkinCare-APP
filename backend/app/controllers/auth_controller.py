from datetime import UTC, datetime

from fastapi import BackgroundTasks
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError, account_disabled
from app.core.security import hash_password
from app.models import User
from app.repositories import refresh_token_repository, user_repository
from app.schemas.auth import (
    CodeSentResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserAuthResponse,
    VerifyEmailRequest,
)
from app.schemas.user import UserOut
from app.services import (
    auth_service,
    email_code_service,
    email_domain_service,
    email_service,
    token_service,
)
from app.services.email_code_service import VERIFICATION
from app.services.email_templates import verification_code_email
from app.services.token_service import TokenPair


def _email_taken() -> AppError:
    return AppError(409, "email_taken", "An account with this email already exists")


def _already_verified() -> AppError:
    return AppError(409, "already_verified", "This email is already verified. Please log in.")


def _user_auth_response(tokens: TokenPair, user: User) -> UserAuthResponse:
    return UserAuthResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user=UserOut.model_validate(user),
    )


def _send_verification_code(
    db: Session, user: User, background: BackgroundTasks
) -> CodeSentResponse:
    """Issue a new code, save everything, then email the code after the response is sent."""
    settings = get_settings()
    code = email_code_service.issue_code(db, user.id, VERIFICATION)
    db.commit()
    background.add_task(
        email_service.send_email,
        verification_code_email(
            user.email, user.full_name, code, settings.email_code_expire_minutes
        ),
    )
    return CodeSentResponse(
        email=user.email,
        message=f"We sent a 6-digit code to {user.email}.",
        code_expires_in=settings.email_code_expire_minutes * 60,
        resend_available_in=settings.email_code_resend_seconds,
    )


def register(db: Session, data: RegisterRequest, background: BackgroundTasks) -> CodeSentResponse:
    """Create an unverified account and email it a code (Instagram-style sign-up)."""
    if get_settings().email_check_deliverability and not email_domain_service.can_receive_email(
        data.email
    ):
        raise AppError(
            422,
            "email_undeliverable",
            "This email address cannot receive emails. Please check it.",
            details=[{"field": "email", "message": "Domain does not accept email"}],
        )

    user = user_repository.get_by_email(db, data.email)
    if user is not None:
        if user.email_verified or user.auth_provider != "email":
            raise _email_taken()
        # An unverified account proves nothing yet, so it is not kept from its real owner: the
        # sign-up replaces its name and password. Only someone with the code AND this password
        # can then verify it.
        wait = email_code_service.seconds_until_resend(db, user.id, VERIFICATION)
        if wait:
            raise email_code_service.code_recently_sent(wait)
        user.full_name = data.full_name
        user.password_hash = hash_password(data.password)
        refresh_token_repository.revoke_all_active(
            db, revoked_at=datetime.now(UTC), user_id=user.id
        )
    else:
        try:
            user = user_repository.create_email_user(
                db,
                full_name=data.full_name,
                email=data.email,
                password_hash=hash_password(data.password),
            )
        except IntegrityError:
            # two sign-ups with the same email at the same moment: the unique index stops one
            db.rollback()
            raise _email_taken() from None

    return _send_verification_code(db, user, background)


def verify_email(db: Session, data: VerifyEmailRequest) -> UserAuthResponse:
    """Check the code; the account becomes verified and the user is logged in."""
    user = user_repository.get_by_email(db, data.email)
    auth_service.check_password_login(user, data.password)
    if user.email_verified:
        raise _already_verified()

    email_code_service.check_code(db, user.id, VERIFICATION, data.code)
    user.email_verified = True
    tokens = token_service.issue_token_pair(db, user.id, "user")
    db.commit()
    return _user_auth_response(tokens, user)


def resend_verification_code(
    db: Session, data: LoginRequest, background: BackgroundTasks
) -> CodeSentResponse:
    user = user_repository.get_by_email(db, data.email)
    auth_service.check_password_login(user, data.password)
    if user.email_verified:
        raise _already_verified()

    wait = email_code_service.seconds_until_resend(db, user.id, VERIFICATION)
    if wait:
        raise email_code_service.code_recently_sent(wait)
    return _send_verification_code(db, user, background)


def login(db: Session, data: LoginRequest) -> UserAuthResponse:
    user = user_repository.get_by_email(db, data.email)
    auth_service.check_password_login(user, data.password)
    if not user.email_verified:
        # the app now calls /auth/resend-verification (it has the email and password) and
        # shows the code screen
        raise AppError(403, "email_not_verified", "Please verify your email address first.")

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

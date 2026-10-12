from datetime import UTC, datetime

from fastapi import BackgroundTasks
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError, account_disabled
from app.core.security import hash_password
from app.models import User
from app.repositories import (
    email_token_repository,
    refresh_token_repository,
    user_repository,
)
from app.schemas.auth import (
    CodeSentResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
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
from app.services.email_code_service import PASSWORD_RESET, VERIFICATION
from app.services.email_templates import password_reset_code_email, verification_code_email
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


FORGOT_PASSWORD_MESSAGE = (
    "If an account exists for this email, we sent a code to reset the password."
)


def forgot_password(
    db: Session, data: ForgotPasswordRequest, background: BackgroundTasks
) -> MessageResponse:
    """Email a reset code. The answer is always the same, so it never reveals which emails have an
    account (or that one is waiting before a new code may be sent).

    Google-only accounts get a code too: that is how they add a password (the code proves the
    inbox), after which both login methods work.
    """
    user = user_repository.get_by_email(db, data.email)
    can_reset = user is not None and user.is_active
    if can_reset and not email_code_service.seconds_until_resend(db, user.id, PASSWORD_RESET):
        settings = get_settings()
        code = email_code_service.issue_code(db, user.id, PASSWORD_RESET)
        db.commit()
        background.add_task(
            email_service.send_email,
            password_reset_code_email(
                user.email, user.full_name, code, settings.email_code_expire_minutes
            ),
        )
    return MessageResponse(message=FORGOT_PASSWORD_MESSAGE)


def reset_password(db: Session, data: ResetPasswordRequest) -> UserAuthResponse:
    """Correct code -> new (or first, for Google-only accounts) password, every device logged out,
    and a fresh login. auth_provider is unchanged: it records how the account was created."""
    user = user_repository.get_by_email(db, data.email)
    if user is None:
        raise email_code_service.code_expired()  # same answer as an account without a code

    email_code_service.check_code(db, user.id, PASSWORD_RESET, data.code)
    if not user.is_active:
        db.rollback()
        raise account_disabled()

    now = datetime.now(UTC)
    user.password_hash = hash_password(data.new_password)
    user.email_verified = True  # reading the code proved the inbox belongs to this user
    # the password may have been reset because it was stolen: end every existing session
    refresh_token_repository.revoke_all_active(db, revoked_at=now, user_id=user.id)
    email_token_repository.invalidate_active(
        db, user_id=user.id, purpose=VERIFICATION, used_at=now
    )
    tokens = token_service.issue_token_pair(db, user.id, "user")
    db.commit()
    return _user_auth_response(tokens, user)


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

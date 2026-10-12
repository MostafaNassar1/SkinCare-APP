"""'Continue with Google', with the account-linking policy (see CLAUDE.md)."""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, account_disabled
from app.models import User
from app.repositories import email_token_repository, refresh_token_repository, user_repository
from app.schemas.auth import GoogleAuthResponse, GoogleSignInRequest
from app.schemas.user import UserOut
from app.services import google_auth_service, token_service
from app.services.email_code_service import PASSWORD_RESET, VERIFICATION
from app.services.google_auth_service import (
    GoogleIdentity,
    GoogleSignInUnavailable,
    InvalidGoogleToken,
)


def _verify(id_token: str) -> GoogleIdentity:
    try:
        identity = google_auth_service.verify_id_token(id_token)
    except GoogleSignInUnavailable:
        raise AppError(
            503,
            "google_sign_in_unavailable",
            "Google sign-in is not available right now. Please try again later.",
        ) from None
    except InvalidGoogleToken:
        raise AppError(
            401, "invalid_google_token", "Google sign-in failed. Please try again."
        ) from None
    if not identity.email_verified:
        # possible for Google accounts created with a non-Gmail address that was never confirmed
        raise AppError(
            401, "google_email_not_verified", "The email of this Google account is not verified."
        )
    return identity


def _take_over_unverified(db: Session, user: User, identity: GoogleIdentity) -> None:
    """The Google user has proven this email; whoever registered it with a password never did.

    The unproven password is deleted, otherwise the person who registered first could still log
    in later (pre-account takeover). Their sessions and codes are cancelled too.
    """
    now = datetime.now(UTC)
    user.google_sub = identity.sub
    user.auth_provider = "google"
    user.password_hash = None
    user.email_verified = True
    user.full_name = identity.name
    refresh_token_repository.revoke_all_active(db, revoked_at=now, user_id=user.id)
    for purpose in (VERIFICATION, PASSWORD_RESET):
        email_token_repository.invalidate_active(
            db, user_id=user.id, purpose=purpose, used_at=now
        )


def _find_or_create_user(db: Session, identity: GoogleIdentity) -> tuple[User, bool]:
    """Apply the linking policy; returns the account and whether it is new to the app."""
    user = user_repository.get_by_google_sub(db, identity.sub)
    if user is not None:
        return user, False  # signed in with Google before

    user = user_repository.get_by_email(db, identity.email)
    if user is None:
        try:
            user = user_repository.create_google_user(
                db, full_name=identity.name, email=identity.email, google_sub=identity.sub
            )
        except IntegrityError:
            # the same account signed up at the same moment by another request
            db.rollback()
            raise AppError(409, "email_taken", "Please try signing in again.") from None
        return user, True

    if user.google_sub is not None:
        # the email belongs to a DIFFERENT Google account (e.g. an email moved between accounts)
        raise AppError(
            409,
            "google_account_mismatch",
            "This email is already linked to a different Google account.",
        )
    if user.email_verified:
        # both sides proved the same inbox: link, so both login methods open the same account
        user.google_sub = identity.sub
        return user, False

    _take_over_unverified(db, user, identity)
    return user, True  # the unverified account never used the app


def google_sign_in(db: Session, data: GoogleSignInRequest) -> GoogleAuthResponse:
    identity = _verify(data.id_token)
    user, is_new_user = _find_or_create_user(db, identity)
    if not user.is_active:
        db.rollback()
        raise account_disabled()

    tokens = token_service.issue_token_pair(db, user.id, "user")
    db.commit()
    return GoogleAuthResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user=UserOut.model_validate(user),
        is_new_user=is_new_user,
    )

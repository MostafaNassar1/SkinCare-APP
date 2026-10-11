from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.security import hash_password
from app.repositories import user_repository
from app.schemas.auth import RegisterRequest, UserAuthResponse
from app.schemas.user import UserOut
from app.services import token_service


def _email_taken() -> AppError:
    return AppError(409, "email_taken", "An account with this email already exists")


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

    return UserAuthResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user=UserOut.model_validate(user),
    )

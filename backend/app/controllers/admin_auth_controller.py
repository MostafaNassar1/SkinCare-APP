from sqlalchemy.orm import Session

from app.core.exceptions import account_disabled
from app.repositories import admin_repository
from app.schemas.admin import AdminAuthResponse, AdminOut
from app.schemas.auth import LoginRequest, RefreshTokenRequest, TokenResponse
from app.services import auth_service, token_service


def login(db: Session, data: LoginRequest) -> AdminAuthResponse:
    admin = admin_repository.get_by_email(db, data.email)
    auth_service.check_password_login(admin, data.password)

    tokens = token_service.issue_token_pair(db, admin.id, "admin")
    db.commit()
    return AdminAuthResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        admin=AdminOut.model_validate(admin),
    )


def refresh(db: Session, data: RefreshTokenRequest) -> TokenResponse:
    admin_id, tokens = token_service.rotate_refresh_token(db, data.refresh_token, "admin")

    admin = admin_repository.get_by_id(db, admin_id)
    if admin is None or not admin.is_active:
        db.rollback()
        raise account_disabled()

    db.commit()
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


def logout(db: Session, data: RefreshTokenRequest) -> None:
    token_service.revoke_refresh_token(db, data.refresh_token, "admin")
    db.commit()

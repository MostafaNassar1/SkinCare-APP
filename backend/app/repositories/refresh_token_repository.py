from datetime import datetime

from sqlalchemy.orm import Session

from app.models import RefreshToken


def create(
    db: Session,
    *,
    token_hash: str,
    expires_at: datetime,
    user_id: int | None = None,
    admin_id: int | None = None,
) -> RefreshToken:
    refresh_token = RefreshToken(
        token_hash=token_hash, expires_at=expires_at, user_id=user_id, admin_id=admin_id
    )
    db.add(refresh_token)
    db.flush()
    return refresh_token

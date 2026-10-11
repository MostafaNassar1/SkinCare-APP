from sqlalchemy.orm import Session

from app.models import User


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)

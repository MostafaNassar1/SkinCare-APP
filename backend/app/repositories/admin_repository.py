from sqlalchemy.orm import Session

from app.models import Admin


def get_by_id(db: Session, admin_id: int) -> Admin | None:
    return db.get(Admin, admin_id)

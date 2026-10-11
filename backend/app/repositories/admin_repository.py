from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Admin


def get_by_id(db: Session, admin_id: int) -> Admin | None:
    return db.get(Admin, admin_id)


def get_by_email(db: Session, email: str) -> Admin | None:
    # LOWER(email) matches the case-insensitive unique index uq_admins_email_lower
    return db.scalar(select(Admin).where(func.lower(Admin.email) == email.lower()))


def create(
    db: Session,
    *,
    full_name: str,
    email: str,
    password_hash: str,
    role: str,
    clinic_id: int | None = None,
) -> Admin:
    admin = Admin(
        full_name=full_name,
        email=email,
        password_hash=password_hash,
        role=role,
        clinic_id=clinic_id,
    )
    db.add(admin)
    db.flush()
    return admin

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, IntPK, UpdatedAt, check_in
from app.models.choices import ADMIN_ROLES


class Admin(Base):
    __tablename__ = "admins"
    __table_args__ = (
        check_in("role", ADMIN_ROLES),
        # clinic managers must have a clinic; other roles must not
        CheckConstraint("(role = 'clinic_manager') = (clinic_id IS NOT NULL)", name="check"),
    )

    id: Mapped[IntPK]
    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), server_default="moderator")
    clinic_id: Mapped[int | None] = mapped_column(ForeignKey("clinics.id", ondelete="RESTRICT"))
    # soft delete keeps audit history intact
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


Index("uq_admins_email_lower", func.lower(Admin.email), unique=True)

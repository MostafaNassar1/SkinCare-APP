from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, IntPK, check_in
from app.models.choices import REPORT_TYPES


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("idx_audit_logs_admin_time", "admin_id", "created_at"),)

    id: Mapped[IntPK]
    # history survives admin removal
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(255))
    target_table: Mapped[str | None] = mapped_column(String(100))
    target_id: Mapped[int | None]
    details: Mapped[dict[str, Any] | None]  # e.g. {"old": {...}, "new": {...}}
    ip_address: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[CreatedAt]


class ReportTemplate(Base):
    __tablename__ = "report_templates"
    __table_args__ = (check_in("report_type", REPORT_TYPES),)

    id: Mapped[IntPK]
    admin_id: Mapped[int] = mapped_column(ForeignKey("admins.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    report_type: Mapped[str] = mapped_column(String(50))
    filters: Mapped[dict[str, Any] | None]
    created_at: Mapped[CreatedAt]

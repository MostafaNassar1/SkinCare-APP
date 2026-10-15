from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAt, IntPK, UpdatedAt, check_in
from app.models.choices import APPOINTMENT_STATUSES, CALENDAR_EVENT_TYPES
from app.models.clinic import Clinic


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        check_in("status", APPOINTMENT_STATUSES),
        # the doctor (if any) must work at the chosen clinic;
        # if the doctor is deleted, only doctor_id is cleared (PostgreSQL 15+)
        ForeignKeyConstraint(
            ["doctor_id", "clinic_id"],
            ["doctors.id", "doctors.clinic_id"],
            ondelete="SET NULL (doctor_id)",
        ),
        Index("idx_appointments_user_id", "user_id"),
        Index("idx_appointments_clinic_status", "clinic_id", "status"),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id", ondelete="RESTRICT"))
    doctor_id: Mapped[int | None]  # partner-clinic doctors (future work; unused by the tracker)
    requested_datetime: Mapped[datetime]  # when the appointment is
    status: Mapped[str] = mapped_column(String(20), server_default="scheduled")
    # the doctor the user will see, as free text (migration 0007), e.g. "Dr. Haddad"
    doctor_name: Mapped[str | None] = mapped_column(String(150))
    notes: Mapped[str | None] = mapped_column(Text)  # from the user
    response_note: Mapped[str | None] = mapped_column(Text)  # from the clinic manager
    responded_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL")
    )
    responded_at: Mapped[datetime | None]
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    # the real place (imported from OpenStreetMap) where the appointment is
    clinic: Mapped["Clinic"] = relationship()


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __table_args__ = (
        check_in("event_type", CALENDAR_EVENT_TYPES),
        CheckConstraint("event_type <> 'appointment' OR appointment_id IS NOT NULL", name="check"),
        Index("idx_calendar_events_user_time", "user_id", "event_datetime"),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(150))
    event_type: Mapped[str] = mapped_column(String(20))
    event_datetime: Mapped[datetime]
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[CreatedAt]

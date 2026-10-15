"""Appointments become a personal tracker of real appointments

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-15

There is no in-app booking (no real partner clinics). The user books by phone at a real clinic or
hospital from the map and records the appointment in the app, which reminds them (Step 11).
- status "scheduled" added and made the default; pending/accepted/rejected stay for possible
  future partner clinics.
- doctor_name: optional free text ("Dr. Haddad"); imported places have no doctor list.

Written by hand: autogenerate detects neither CHECK constraint changes nor default changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = "'pending', 'accepted', 'rejected', 'completed', 'cancelled'"
NEW_STATUSES = "'scheduled', " + OLD_STATUSES


def upgrade() -> None:
    op.add_column("appointments", sa.Column("doctor_name", sa.String(length=150), nullable=True))
    op.drop_constraint(op.f("appointments_status_check"), "appointments", type_="check")
    op.create_check_constraint(
        op.f("appointments_status_check"), "appointments", f"status IN ({NEW_STATUSES})"
    )
    op.alter_column("appointments", "status", server_default="scheduled")


def downgrade() -> None:
    # the old rules do not know "scheduled": the closest old meaning is an accepted appointment
    op.execute("UPDATE appointments SET status = 'accepted' WHERE status = 'scheduled'")
    op.alter_column("appointments", "status", server_default="pending")
    op.drop_constraint(op.f("appointments_status_check"), "appointments", type_="check")
    op.create_check_constraint(
        op.f("appointments_status_check"), "appointments", f"status IN ({OLD_STATUSES})"
    )
    op.drop_column("appointments", "doctor_name")

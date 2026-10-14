"""Routine reminders and scheduled days per routine step

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14

- routine_steps.days_of_week: the weekdays a step is done, one bit per day (Monday = 1 ...
  Sunday = 64; 127 = every day, the default). A streak day needs every step scheduled for that
  day, so a retinoid advised "2-3 nights a week" (e.g. Mon, Wed, Fri = 21) never pushes users to
  apply it daily just to keep a streak.
- user_profiles: routine_reminders_enabled (default on), morning_reminder_time (08:00) and
  evening_reminder_time (21:00), in the user's time zone. The scheduler sends them in Step 11.

Generated with `alembic revision --autogenerate`, then reviewed: autogenerate does not detect
CHECK constraints, so routine_steps_days_of_week_check (1-127: at least one day) was added by hand.
Existing rows get the defaults, so nothing breaks.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "routine_steps",
        sa.Column("days_of_week", sa.SmallInteger(), server_default=sa.text("127"), nullable=False),
    )
    op.create_check_constraint(
        op.f("routine_steps_days_of_week_check"), "routine_steps", "days_of_week BETWEEN 1 AND 127"
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "routine_reminders_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "morning_reminder_time", sa.Time(), server_default=sa.text("'08:00'"), nullable=False
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "evening_reminder_time", sa.Time(), server_default=sa.text("'21:00'"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "evening_reminder_time")
    op.drop_column("user_profiles", "morning_reminder_time")
    op.drop_column("user_profiles", "routine_reminders_enabled")
    op.drop_constraint(op.f("routine_steps_days_of_week_check"), "routine_steps", type_="check")
    op.drop_column("routine_steps", "days_of_week")

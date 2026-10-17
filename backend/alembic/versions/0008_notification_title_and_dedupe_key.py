"""Notifications: push title and de-duplication key

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-17

- title: a push notification has a title and a body (message), e.g. "🏆 New badge".
- dedupe_key + UNIQUE (user_id, dedupe_key): each automatic notification has a key such as
  "forecast:2026-10-17" or "appointment-2h:42", so the scheduler can run twice (or restart)
  without the user ever receiving the same notification twice. NULL for one-off notifications
  (PostgreSQL treats NULLs as distinct, so they never collide).

Generated with `alembic revision --autogenerate` and reviewed: correct as generated.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("title", sa.String(length=100), nullable=True))
    op.add_column("notifications", sa.Column("dedupe_key", sa.String(length=100), nullable=True))
    op.create_unique_constraint(
        op.f("notifications_user_id_dedupe_key_key"), "notifications", ["user_id", "dedupe_key"]
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("notifications_user_id_dedupe_key_key"), "notifications", type_="unique"
    )
    op.drop_column("notifications", "dedupe_key")
    op.drop_column("notifications", "title")

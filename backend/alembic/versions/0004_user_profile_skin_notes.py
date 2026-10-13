"""User profile: free-text skin notes

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13

user_profiles.skin_notes (up to 1000 characters): what the user wants to tell about their skin
(e.g. "breakouts before my period", "eczema as a child"). Shown to the user and shared with a
clinic only when they book an appointment. The rule-based engine does not read free text.

Generated with `alembic revision --autogenerate` and reviewed: a single nullable column, so
existing profiles are unaffected.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("skin_notes", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "skin_notes")

"""Baseline: create the 26 tables of schema v2

Revision ID: 0001
Revises:
Create Date: 2026-10-11

Runs database/schema_v2.sql as-is, because some of its features cannot be expressed by
SQLAlchemy models (the set_updated_at() trigger function and triggers). schema_v2.sql is
FROZEN from now on: every later schema change is a new migration.

The development database already had this schema, so it was only stamped (`alembic stamp head`).
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_FILE = Path(__file__).resolve().parents[3] / "database" / "schema_v2.sql"

# children before parents, so no table is dropped while another still references it
TABLES = [
    "audit_logs", "report_templates", "email_tokens", "refresh_tokens", "user_devices",
    "notifications", "calendar_events", "appointments", "admins", "doctors", "clinics",
    "user_achievements", "achievements", "routine_logs", "routine_steps", "routines",
    "concern_recommendation_mapping", "scan_result_concerns", "scan_results",
    "weather_skin_tips", "skin_concerns", "ingredient_conflicts", "user_allergies",
    "ingredients", "user_profiles", "users",
]  # fmt: skip


def upgrade() -> None:
    # run the file through psycopg's own connection (same transaction): with no parameters it is
    # sent to PostgreSQL unchanged, so the '%' in "0.5-2%" is not read as a placeholder
    op.get_bind().connection.driver_connection.execute(SCHEMA_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION set_updated_at()")

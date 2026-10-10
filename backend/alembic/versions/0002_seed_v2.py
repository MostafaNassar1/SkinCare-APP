"""Reference data: skin concerns, ingredients, rules, achievements, weather tips

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11

Runs database/seed_v2.sql as-is. This is permanent reference data the app cannot work without
(e.g. no skin concerns or rules = no routines), so every new database gets it through
`alembic upgrade head`. seed_v2.sql is FROZEN from now on: later data changes are new
migrations (or admin dashboard edits).
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_FILE = Path(__file__).resolve().parents[3] / "database" / "seed_v2.sql"

# children before parents. Plain DELETE (not TRUNCATE ... CASCADE): if user data still points at
# this reference data (e.g. a scan result using a skin concern), PostgreSQL refuses instead of
# silently deleting user data.
SEED_TABLES = [
    "weather_skin_tips", "achievements", "concern_recommendation_mapping",
    "ingredient_conflicts", "ingredients", "skin_concerns",
]  # fmt: skip


def upgrade() -> None:
    # sent unchanged through psycopg (see 0001): the seed contains '%' in concentrations
    op.get_bind().connection.driver_connection.execute(SEED_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    for table in SEED_TABLES:
        op.execute(f"DELETE FROM {table}")

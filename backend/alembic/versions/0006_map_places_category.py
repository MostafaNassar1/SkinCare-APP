"""Map places: category of each place

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-14

The clinics table now holds every place on the map, imported from real OpenStreetMap data for
Lebanon (Geofabrik extract): clinic, doctor, hospital or pharmacy. The API groups the first three
as "clinics" and pharmacies separately. An index on category serves the map filters.

Decided on 2026-10-14 after checking the real data: no in-app booking (no real partner clinics),
no dermatologist filter (0 places are tagged dermatology in Lebanon).

Generated with `alembic revision --autogenerate`, then reviewed: autogenerate does not detect
CHECK constraints, so clinics_category_check was added by hand.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clinics",
        sa.Column("category", sa.String(length=20), server_default="clinic", nullable=False),
    )
    op.create_check_constraint(
        op.f("clinics_category_check"),
        "clinics",
        "category IN ('clinic', 'doctor', 'hospital', 'pharmacy')",
    )
    op.create_index("idx_clinics_category", "clinics", ["category"])


def downgrade() -> None:
    op.drop_index("idx_clinics_category", table_name="clinics")
    op.drop_constraint(op.f("clinics_category_check"), "clinics", type_="check")
    op.drop_column("clinics", "category")

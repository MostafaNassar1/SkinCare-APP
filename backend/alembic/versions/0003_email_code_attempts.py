"""Email codes: attempts counter and non-unique code hash

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12

email_tokens now holds 6-digit codes (Instagram-style verification and password reset):
- attempts: wrong guesses so far; a code stops working after 5, because a 6-digit code has only
  1,000,000 possible values and could otherwise be guessed by a script.
- token_hash is no longer unique: two users can receive the same 6-digit code. Codes are looked up
  by user and purpose instead.

Generated with `alembic revision --autogenerate`, then reviewed: autogenerate does not detect
CHECK constraints, so email_tokens_attempts_check was added by hand.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "email_tokens",
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.create_check_constraint(
        op.f("email_tokens_attempts_check"), "email_tokens", "attempts >= 0"
    )
    op.drop_constraint("email_tokens_token_hash_key", "email_tokens", type_="unique")


def downgrade() -> None:
    # codes live for minutes only; deleting them avoids duplicate hashes blocking the unique rule
    op.execute("DELETE FROM email_tokens")
    op.create_unique_constraint("email_tokens_token_hash_key", "email_tokens", ["token_hash"])
    op.drop_constraint(op.f("email_tokens_attempts_check"), "email_tokens", type_="check")
    op.drop_column("email_tokens", "attempts")

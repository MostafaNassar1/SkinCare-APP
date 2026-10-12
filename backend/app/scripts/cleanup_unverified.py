r"""Delete email sign-ups that were never verified (e.g. made-up or mistyped addresses).

    cd backend; .venv\Scripts\activate
    python -m app.scripts.cleanup_unverified --dry-run    # only shows how many would be deleted
    python -m app.scripts.cleanup_unverified              # deletes them

Such accounts can never be used (nobody received their code), so after 24 hours they are only
clutter. Later the background scheduler will run this every day.
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.repositories import user_repository

DEFAULT_MAX_AGE_HOURS = 24


def cleanup(db: Session, *, max_age_hours: int, dry_run: bool) -> int:
    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
    if dry_run:
        return user_repository.count_never_verified(db, created_before=cutoff)
    deleted = user_repository.delete_never_verified(db, created_before=cutoff)
    db.commit()
    return deleted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delete never-verified email sign-ups.")
    parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_MAX_AGE_HOURS,
        help=f"minimum account age in hours (default {DEFAULT_MAX_AGE_HOURS})",
    )
    parser.add_argument("--dry-run", action="store_true", help="only count, delete nothing")
    args = parser.parse_args(argv)
    if args.hours < 1:
        parser.error("--hours must be at least 1")

    with SessionLocal() as db:
        count = cleanup(db, max_age_hours=args.hours, dry_run=args.dry_run)

    if args.dry_run:
        print(f"{count} never-verified account(s) older than {args.hours} h would be deleted.")
    else:
        print(f"Deleted {count} never-verified account(s) older than {args.hours} h.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

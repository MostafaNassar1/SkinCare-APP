r"""Send the routine and appointment reminders that are due right now (one scheduler run).

    cd backend; .venv\Scripts\activate
    python -m app.scripts.run_scheduler_once
    python -m app.scripts.run_scheduler_once --now 2026-10-17T21:05+03:00   # pretend it is then

For manual testing: the server does the same thing by itself every few minutes. Running it again
sends nothing twice (each reminder is stored once per user and day / appointment).
"""

import argparse
import sys
from datetime import datetime

from app.db.session import SessionLocal
from app.services import scheduler_service


def aware_datetime(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise argparse.ArgumentTypeError("give a time zone, e.g. 2026-10-17T21:05+03:00")
    return moment


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send the reminders that are due.")
    parser.add_argument("--now", type=aware_datetime, help="pretend it is this moment (ISO 8601)")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        summary = scheduler_service.run_due(db, args.now)
    print(
        f"Sent {summary.routine_reminders} routine and {summary.appointment_reminders} "
        f"appointment reminder(s), {summary.pushes_sent} push(es)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

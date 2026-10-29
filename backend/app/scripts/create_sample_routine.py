r"""Give a user the routine the rules engine recommends, choosing every Top pick (development).

    cd backend; .venv\Scripts\activate
    python -m app.scripts.create_sample_routine --email you@example.com

Uses the same path as the app: the user's current concerns (latest scan + skin quiz), every
safe product of each step, the first one ("Top pick") chosen, clashing treatments on different
nights, saved as a new routine version (the previous one is replaced). Before the first scan,
only the quiz concerns and the base routine apply.
"""

import argparse
import sys

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.db.session import SessionLocal
from app.models import Routine, User
from app.repositories import user_repository
from app.services import concern_service, recommendation_service, routine_builder_service
from app.services.routine_builder_service import StepChoice
from app.services.weekdays import from_mask


def create_sample_routine(db: Session, user: User) -> tuple[Routine, dict[str, str]]:
    """Save the Top picks of the user's recommendations; returns the routine and concerns."""
    concerns = concern_service.current_concerns(db, user).concerns
    proposal = recommendation_service.propose(db, user, concerns)
    choices = [
        StepChoice(
            time_of_day=step.time_of_day,
            mapping_id=step.mapping_id,
            product_id=step.products[0].id if step.products else None,
        )
        for step in proposal.steps
    ]
    routine = routine_builder_service.save(db, user, choices).routine
    db.commit()
    return routine, concerns


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Save the recommended routine for a user.")
    parser.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        user = user_repository.get_by_email(db, args.email)
        if user is None:
            print(f"No user with the email {args.email}", file=sys.stderr)
            return 1
        try:
            routine, concerns = create_sample_routine(db, user)
        except AppError as error:  # e.g. steps_conflict: clashing Top picks
            print(f"Could not save the routine: {error.detail}", file=sys.stderr)
            return 1
        found = ", ".join(f"{name} ({severity})" for name, severity in concerns.items())
        print(f"Concerns: {found or 'none (base routine)'}")
        print(f"Created routine #{routine.id} with {len(routine.steps)} steps for {user.email}")
        for step in sorted(routine.steps, key=lambda s: (s.time_of_day != "morning", s.step_order)):
            days = "/".join(from_mask(step.days_of_week))
            print(f"  {step.time_of_day:8} {step.step_order}. {step.title} ({days})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

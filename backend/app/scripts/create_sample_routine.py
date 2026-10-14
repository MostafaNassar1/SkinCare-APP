r"""Give a user a realistic routine for testing (development only).

    cd backend; .venv\Scripts\activate
    python -m app.scripts.create_sample_routine --email you@example.com

The real routine generator (scan -> rules engine -> routine) comes in Phase 3. This builds a
mild-acne routine from the seed rules, with the retinoid (adapalene) on Mon/Wed/Fri nights only,
as its rule advises ("start 2-3 nights a week"). Any previous active routine is deactivated.
"""

import argparse
import sys

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Routine, RoutineStep, User
from app.repositories import ingredient_repository, routine_repository, user_repository
from app.services.weekdays import EVERY_DAY, to_mask

# (time of day, order, category, title, product type, ingredient, concentration, days, note)
SAMPLE_STEPS = [
    ("morning", 1, "cleanse", "Cleanse", "Salicylic acid foaming cleanser", "Salicylic Acid",
     "0.5-2%", None, "Helps unclog pores and reduce breakouts."),
    ("morning", 2, "treat", "Oil Control Serum", "Niacinamide serum", "Niacinamide", "2-5%",
     None, "Regulates sebum production."),
    ("morning", 3, "moisturize", "Moisturize", "Oil-free gel moisturizer", None, None, None,
     "Hydrates without adding shine."),
    ("morning", 4, "protect", "Sunscreen", "Broad-spectrum sunscreen SPF 30+", None, None, None,
     "Daily UV protection."),
    ("evening", 1, "cleanse", "Cleanse", "Salicylic acid foaming cleanser", "Salicylic Acid",
     "0.5-2%", None, "Removes the day's oil and sunscreen."),
    ("evening", 2, "treat", "Acne Treatment", "Adapalene gel", "Adapalene", "0.1%",
     ["mon", "wed", "fri"], "Start 2-3 nights a week; expect some dryness at first."),
    ("evening", 3, "moisturize", "Moisturize", "Oil-free gel moisturizer", None, None, None,
     "Hydrates without adding shine."),
]  # fmt: skip


def create_sample_routine(db: Session, user: User) -> Routine:
    ingredient_ids = {i.name: i.id for i in ingredient_repository.list_all(db)}
    steps = [
        RoutineStep(
            time_of_day=time_of_day,
            step_order=order,
            step_category=category,
            title=title,
            product_type=product_type,
            ingredient_id=ingredient_ids[ingredient] if ingredient else None,
            recommended_concentration=concentration,
            days_of_week=to_mask(days) if days else EVERY_DAY,
            description=note,
        )
        for (time_of_day, order, category, title, product_type, ingredient, concentration, days,
             note) in SAMPLE_STEPS
    ]  # fmt: skip
    routine_repository.deactivate_all(db, user.id)
    routine = routine_repository.create(db, user_id=user.id, steps=steps)
    db.commit()
    return routine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a sample routine for a user.")
    parser.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        user = user_repository.get_by_email(db, args.email)
        if user is None:
            print(f"No user with the email {args.email}", file=sys.stderr)
            return 1
        routine = create_sample_routine(db, user)
        print(f"Created routine #{routine.id} with {len(routine.steps)} steps for {user.email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

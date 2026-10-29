"""A FIXED routine for the routine, streak, reminder and calendar tests.

Not built by the rules engine on purpose: these tests need steps that never change when the
product catalogue or the rules change (e.g. one step on Mon/Wed/Fri only). The engine has its
own tests (tests/recommendations/); the dev command `create_sample_routine` uses the engine.
"""

from sqlalchemy.orm import Session

from app.models import Routine, RoutineStep, User
from app.repositories import ingredient_repository, routine_repository
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
    ("evening", 2, "treat", "Anti-Aging Treatment", "Retinol serum or cream", "Retinol", "0.1%",
     ["mon", "wed", "fri"], "Start 2-3 nights a week; expect some dryness at first."),
    ("evening", 3, "moisturize", "Moisturize", "Oil-free gel moisturizer", None, None, None,
     "Hydrates without adding shine."),
]  # fmt: skip


def create_sample_routine(db: Session, user: User) -> Routine:
    """7 steps; the retinol step only on Mon/Wed/Fri nights. Replaces the active routine."""
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

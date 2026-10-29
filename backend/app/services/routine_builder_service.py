"""The rules engine, part 2: saving the routine from the user's choices (Phase 3 Step 2.3b).

Saving and editing are the same action (decided 2026-10-29): the phone sends the routine as the
user wants it (the product chosen for each step, or their own product, the steps they removed,
the days they changed) and the server:
1. checks every step is one of the user's CURRENT recommendations (latest scan + skin quiz) and
   every chosen product is still safe for them (e.g. a pregnancy declared since removes retinol);
2. keeps an own product ("I'll use my own product") with the ingredients the user ticked, warns
   when one of them is unsafe for the user (they decide), and puts its name on the admin review
   list;
3. puts clashing treatments (ingredient_conflicts, e.g. retinol + an exfoliating acid) of the
   same time of day on different days: a step whose days the user chose keeps them, the others
   take the remaining days (retinol Mon/Wed/Fri -> the acid treatment Tue/Thu/Sat/Sun), and two
   every-day treatments are split Mon/Wed/Fri/Sun + Tue/Thu/Sat. When no day is left, or two steps
   with chosen days clash, the save is refused with both steps named (choose another product).
   Only treatments are checked: cleansers are rinsed off (a moisturizer's acid is a known limit);
4. saves a NEW version of the routine. Past days keep the version that applied then, so the
   calendar and the streak are never rewritten; today's ticks move to the same steps of the new
   version. A version replaced on the day it was made is deleted (one version per day).
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import Routine, RoutineStep, RoutineStepIngredient, RoutineStepProduct, User
from app.models.choices import STEP_TIMES_OF_DAY
from app.repositories import ingredient_repository, product_repository, routine_repository
from app.services import concern_service, recommendation_service
from app.services.local_time import local_date, user_today
from app.services.recommendation_service import ProposedStep
from app.services.routine_service import step_counts_on
from app.services.weekdays import EVERY_DAY, to_mask

MON_WED_FRI_SUN = to_mask(["mon", "wed", "fri", "sun"])  # an every-day treatment split in two:
TUE_THU_SAT = to_mask(["tue", "thu", "sat"])  # 4 + 3 nights


@dataclass(frozen=True)
class StepChoice:
    """What the user wants for one recommended step (identified by its time and rule)."""

    time_of_day: str
    mapping_id: int
    product_id: int | None = None  # one of the step's safe products
    own_product_name: str | None = None  # or their own product...
    own_ingredient_ids: frozenset[int] = frozenset()  # ...and what they ticked it contains
    has_product: bool = True  # False = "I don't have it yet"
    days_of_week: int | None = None  # None = the recommended days


@dataclass(frozen=True)
class OwnProductWarning:
    step_title: str
    ingredient: str
    reason: str  # pregnancy | allergy


@dataclass
class SaveResult:
    routine: Routine
    warnings: list[OwnProductWarning]


@dataclass
class _Planned:
    step: ProposedStep
    choice: StepChoice
    ingredient_ids: set[int] = field(default_factory=set)
    days: int = EVERY_DAY
    fixed: bool = False  # days chosen by the user


def save(db: Session, user: User, choices: list[StepChoice]) -> SaveResult:
    """Validate the choices, schedule clashes, store a new routine version. The caller commits."""
    current = concern_service.current_concerns(db, user)
    proposal = recommendation_service.propose(db, user, current.concerns)
    planned = _check(db, proposal.steps, choices)
    warnings = _own_product_warnings(db, user, planned)
    _schedule(db, planned)
    routine = _store(db, user, current.scan_result_id, planned)
    return SaveResult(routine=routine, warnings=warnings)


def mark_product_ready(db: Session, user: User, step: RoutineStep) -> None:
    """ "I have it now": the step counts from today (never for the days before). Caller commits."""
    step.needs_product = False
    step.product_ready_on = user_today(user)
    db.flush()


# ---------- 1. the choices are recommendations, the products still safe ----------


def _check(db: Session, steps: list[ProposedStep], choices: list[StepChoice]) -> list[_Planned]:
    if not choices:
        raise AppError(422, "empty_routine", "A routine needs at least one step.")
    by_key = {(step.time_of_day, step.mapping_id): step for step in steps}
    chosen: dict[tuple[str, int], StepChoice] = {}
    known_ingredients = {i.id for i in ingredient_repository.list_all(db)}
    for choice in choices:
        key = (choice.time_of_day, choice.mapping_id)
        step = by_key.get(key)
        where = {"time_of_day": choice.time_of_day, "mapping_id": choice.mapping_id}
        if step is None:
            raise AppError(
                422, "unknown_step", "This step is not one of your recommendations.", where
            )
        if key in chosen:
            raise AppError(422, "duplicate_step", "A step was sent twice.", where)
        if choice.product_id is not None and choice.product_id not in {
            p.id for p in step.products
        }:
            raise AppError(
                422,
                "product_not_suitable",
                "This product is not one of the safe choices for this step.",
                where | {"product_id": choice.product_id},
            )
        if not choice.own_ingredient_ids <= known_ingredients:
            raise AppError(422, "unknown_ingredient", "Unknown ingredient.", where)
        chosen[key] = choice

    product_ingredients = product_repository.ingredient_ids_of_products(
        db, {c.product_id for c in chosen.values() if c.product_id is not None}
    )
    planned = []
    for step in steps:  # in routine order
        choice = chosen.get((step.time_of_day, step.mapping_id))
        if choice is None:
            continue  # removed by the user
        ingredient_ids = (
            product_ingredients.get(choice.product_id, set())
            if choice.product_id is not None
            else set(choice.own_ingredient_ids)
        )
        planned.append(
            _Planned(
                step=step,
                choice=choice,
                ingredient_ids=ingredient_ids,
                days=choice.days_of_week or step.days_of_week,
                fixed=choice.days_of_week is not None,
            )
        )
    return planned


# ---------- 2. own products ----------


def _own_product_warnings(
    db: Session, user: User, planned: list[_Planned]
) -> list[OwnProductWarning]:
    safety = recommendation_service.safety_for(db, user)
    ticked = {i for p in planned if p.choice.own_product_name for i in p.ingredient_ids}
    names = {i.id: i.name for i in ingredient_repository.get_by_ids(db, ticked)}
    warnings = []
    for p in planned:
        if not p.choice.own_product_name:
            continue
        for ingredient_id in sorted(p.ingredient_ids):
            if safety.pregnant and ingredient_id in safety.pregnancy_unsafe_ids:
                reason = "pregnancy"
            elif ingredient_id in safety.avoid_ids:
                reason = "allergy"
            else:
                continue
            warnings.append(OwnProductWarning(p.step.title, names[ingredient_id], reason))
    return warnings


# ---------- 3. clashing treatments on different days ----------


def _schedule(db: Session, planned: list[_Planned]) -> None:
    conflicts = product_repository.conflict_pairs(db)

    def clash(a: _Planned, b: _Planned) -> bool:
        return any(
            frozenset((x, y)) in conflicts
            for x in a.ingredient_ids
            for y in b.ingredient_ids
            if x != y
        )

    for time_of_day in STEP_TIMES_OF_DAY:
        treatments = [
            p
            for p in planned
            if (p.step.time_of_day, p.step.step_category) == (time_of_day, "treat")
        ]
        placed: list[_Planned] = []
        # the user's chosen days first, then by priority (the routine order)
        for p in [t for t in treatments if t.fixed] + [t for t in treatments if not t.fixed]:
            clashing = [q for q in placed if clash(p, q)]
            used = _days_of(clashing)
            if p.days & used:
                if p.fixed:
                    raise _clash_error(p, clashing)
                if not p.days & ~used and p.days == EVERY_DAY:
                    for q in clashing:
                        if not q.fixed and q.days == EVERY_DAY:
                            q.days = MON_WED_FRI_SUN
                    used = _days_of(clashing)
                if not p.days & ~used:
                    raise _clash_error(p, clashing)
                p.days &= ~used
            placed.append(p)


def _days_of(steps: list[_Planned]) -> int:
    days = 0
    for step in steps:
        days |= step.days
    return days


def _clash_error(step: _Planned, clashing: list[_Planned]) -> AppError:
    titles = [step.step.title] + [q.step.title for q in clashing]
    return AppError(
        409,
        "steps_conflict",
        f"{step.step.title} cannot be used on the same {step.step.time_of_day}s as "
        f"{', '.join(q.step.title for q in clashing)}. Choose another product for one of them.",
        {"time_of_day": step.step.time_of_day, "steps": titles},
    )


# ---------- 4. a new version of the routine ----------


def _store(
    db: Session, user: User, scan_result_id: int | None, planned: list[_Planned]
) -> Routine:
    today = user_today(user)
    old = routine_repository.get_active(db, user.id)
    order: dict[str, int] = {}
    steps = []
    for p in planned:
        order[p.step.time_of_day] = order.get(p.step.time_of_day, 0) + 1
        choice = p.choice
        has_a_product = choice.product_id is not None or choice.own_product_name is not None
        steps.append(
            RoutineStep(
                mapping_id=p.step.mapping_id,
                time_of_day=p.step.time_of_day,
                step_order=order[p.step.time_of_day],
                step_category=p.step.step_category,
                title=p.step.title,
                description=p.step.description,
                product_type=p.step.product_type,
                ingredient_id=p.step.ingredient_id,
                recommended_concentration=p.step.recommended_concentration,
                days_of_week=p.days,
                product_id=choice.product_id,
                custom_product_name=choice.own_product_name,
                needs_product=has_a_product and not choice.has_product,
            )
        )

    routine_repository.deactivate_all(db, user.id)
    routine = routine_repository.create(
        db, user_id=user.id, steps=steps, scan_result_id=scan_result_id
    )
    for p, step in zip(planned, steps, strict=True):
        # the safe products offered for the step, best first: part of the snapshot
        db.add_all(
            RoutineStepProduct(routine_step_id=step.id, product_id=product.id, rank=rank)
            for rank, product in enumerate(p.step.products, start=1)
        )
        if p.choice.own_product_name:
            db.add_all(
                RoutineStepIngredient(routine_step_id=step.id, ingredient_id=i)
                for i in sorted(p.ingredient_ids)
            )
            product_repository.add_suggestion(
                db,
                user_id=user.id,
                name=p.choice.own_product_name,
                step_category=p.step.step_category,
            )
    db.flush()

    if old is not None:
        _carry_over_today(db, user, old, steps, today)
    return routine


def _carry_over_today(
    db: Session, user: User, old: Routine, new_steps: list[RoutineStep], today: date
) -> None:
    """Today's ticks follow the same steps (same rule and time) into the new version."""
    new_by_key = {
        (s.mapping_id, s.time_of_day): s for s in new_steps if step_counts_on(s, today)
    }
    moves = {
        o.id: new_by_key[(o.mapping_id, o.time_of_day)].id
        for o in old.steps
        if o.mapping_id is not None and (o.mapping_id, o.time_of_day) in new_by_key
    }
    routine_repository.move_logs(db, user_id=user.id, log_date=today, moves=moves)
    if local_date(old.created_at, user) == today:
        routine_repository.delete_routine(db, old)

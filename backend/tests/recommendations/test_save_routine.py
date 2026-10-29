"""Saving (= editing) a routine from the user's choices: safety, own products, clashes, versions."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import (
    Ingredient,
    Product,
    ProductSuggestion,
    Routine,
    RoutineLog,
    RoutineStepIngredient,
    RoutineStepProduct,
    UserAllergy,
)
from app.services import concern_service, recommendation_service, routine_builder_service
from app.services.local_time import user_today
from app.services.routine_builder_service import StepChoice
from app.services.routine_service import scheduled_steps, step_counts_on
from app.services.weekdays import EVERY_DAY, to_mask
from tests.recommendations.conftest import add_scan as scan

MON_WED_FRI = to_mask(["mon", "wed", "fri"])


def ingredient_id(db: Session, name: str) -> int:
    return db.scalar(select(Ingredient.id).where(Ingredient.name == name))


def product_id(db: Session, name: str) -> int:
    return db.scalar(select(Product.id).where(Product.name == name))


def proposal(db: Session, user):
    return recommendation_service.propose(
        db, user, concern_service.current_concerns(db, user).concerns
    )


def top_picks(db: Session, user, **overrides: dict) -> list[StepChoice]:
    """The "Top pick" of every proposed step; overrides by step title change one choice."""
    choices = []
    for step in proposal(db, user).steps:
        fields = {"product_id": step.products[0].id if step.products else None}
        fields |= overrides.get(step.title.replace(" ", "_").replace("-", "_").lower(), {})
        choices.append(StepChoice(time_of_day=step.time_of_day, mapping_id=step.mapping_id,
                                  **fields))  # fmt: skip
    return choices


def save(db: Session, user, choices):
    result = routine_builder_service.save(db, user, choices)
    db.flush()
    return result


def by_title(routine: Routine, time_of_day: str, title: str):
    return next(s for s in routine.steps if (s.time_of_day, s.title) == (time_of_day, title))


# ---------- concerns: latest scan + skin quiz ----------


def test_concerns_come_from_the_latest_scan_and_the_quiz(db: Session, app_user):
    scan(db, app_user, acne="moderate")
    latest = scan(db, app_user, acne="mild", oiliness="moderate")
    app_user.profile.skin_type = "combination"

    current = concern_service.current_concerns(db, app_user)

    assert current.scan_result_id == latest.id
    # the quiz says mild oiliness, the scan moderate: the more severe answer wins
    assert current.concerns == {"acne": "mild", "oiliness": "moderate"}


@pytest.mark.parametrize(
    ("skin_type", "expected"),
    [("oily", {"oiliness": "mild"}), ("dry", {"dryness": "mild"}),
     ("combination", {"oiliness": "mild"}), ("normal", {}), ("sensitive", {}), (None, {})],
)  # fmt: skip
def test_quiz_concerns_by_skin_type(db: Session, app_user, skin_type, expected):
    app_user.profile.skin_type = skin_type

    assert concern_service.current_concerns(db, app_user).concerns == expected


def test_redness_comes_from_the_quiz(db: Session, app_user):
    app_user.profile.skin_type = "dry"
    app_user.profile.skin_quiz_answers = {"version": 2, "answers": {"redness": "often"}}
    scan(db, app_user, redness="mild")

    # the quiz says moderate, the scan mild: the more severe answer wins
    assert concern_service.current_concerns(db, app_user).concerns == {
        "redness": "moderate",
        "dryness": "mild",
    }


def test_severe_redness_from_the_quiz_refers_to_a_dermatologist(db: Session, app_user):
    app_user.profile.skin_quiz_answers = {"version": 2, "answers": {"redness": "most_of_the_time"}}

    result = proposal(db, app_user)

    assert result.see_dermatologist == ["redness"]
    assert all("redness" not in s.concerns for s in result.steps)


# ---------- saving the choices ----------


def test_top_picks_become_the_active_routine(db: Session, app_user):
    result = scan(db, app_user, acne="mild")

    routine = save(db, app_user, top_picks(db, app_user)).routine

    assert routine.is_active and routine.scan_result_id == result.id
    assert sorted((s.time_of_day, s.step_order, s.title) for s in routine.steps) == [
        ("evening", 1, "Cleanse"), ("evening", 2, "Acne Treatment"), ("evening", 3, "Moisturize"),
        ("morning", 1, "Cleanse"), ("morning", 2, "Moisturize"), ("morning", 3, "Sunscreen"),
    ]  # fmt: skip
    treatment = by_title(routine, "evening", "Acne Treatment")
    assert treatment.product_id == product_id(db, "Effaclar Duo+M")
    offered = db.scalars(
        select(RoutineStepProduct.rank).where(RoutineStepProduct.routine_step_id == treatment.id)
    ).all()
    assert sorted(offered) == [1, 2, 3, 4]  # every safe product offered is kept in the snapshot


def test_removed_steps_are_left_out(db: Session, app_user):
    choices = [c for c in top_picks(db, app_user) if c.time_of_day == "morning"]

    routine = save(db, app_user, choices).routine

    assert {s.time_of_day for s in routine.steps} == {"morning"}


@pytest.mark.parametrize(
    ("change", "code"),
    [("empty", "empty_routine"), ("unknown", "unknown_step"), ("twice", "duplicate_step"),
     ("other_product", "product_not_suitable")],
)  # fmt: skip
def test_invalid_choices_are_refused(db: Session, app_user, change, code):
    choices = top_picks(db, app_user)
    if change == "empty":
        choices = []
    elif change == "unknown":  # an acne step without acne in the scan
        acne = recommendation_service.propose(db, app_user, {"acne": "mild"}).steps
        treatment = next(s for s in acne if s.title == "Acne Treatment")
        choices.append(StepChoice(time_of_day="evening", mapping_id=treatment.mapping_id))
    elif change == "twice":
        choices.append(choices[0])
    else:  # a moisturizer chosen for the cleanse step
        choices[0] = StepChoice(time_of_day=choices[0].time_of_day,
                                mapping_id=choices[0].mapping_id,
                                product_id=product_id(db, "Moisturising Cream"))  # fmt: skip

    with pytest.raises(AppError) as error:
        save(db, app_user, choices)

    assert error.value.code == code


def test_a_product_that_became_unsafe_is_refused(db: Session, app_user):
    scan(db, app_user, acne="mild")
    choices = top_picks(db, app_user)  # Effaclar Duo+M: contains fragrance
    db.add(UserAllergy(user_id=app_user.id, ingredient_id=ingredient_id(db, "Fragrance (Parfum)")))
    db.flush()

    with pytest.raises(AppError) as error:
        save(db, app_user, choices)

    assert error.value.code == "product_not_suitable"


# ---------- own products ----------


def test_own_product_with_warnings_and_review_list(db: Session, app_user):
    scan(db, app_user, acne="mild")
    app_user.profile.is_pregnant_or_breastfeeding = True
    db.add(UserAllergy(user_id=app_user.id, ingredient_id=ingredient_id(db, "Parabens")))
    db.flush()
    own = {"product_id": None, "own_product_name": "Cousin's Acne Cream",
           "own_ingredient_ids": frozenset({ingredient_id(db, "Retinol"),
                                            ingredient_id(db, "Parabens"),
                                            ingredient_id(db, "Niacinamide")})}  # fmt: skip

    result = save(db, app_user, top_picks(db, app_user, acne_treatment=own))
    save(db, app_user, top_picks(db, app_user, acne_treatment=own))  # saved again: listed once

    assert [(w.step_title, w.ingredient, w.reason) for w in result.warnings] == [
        ("Acne Treatment", "Retinol", "pregnancy"),
        ("Acne Treatment", "Parabens", "allergy"),
    ]
    routine = db.scalar(select(Routine).where(Routine.user_id == app_user.id, Routine.is_active))
    step = by_title(routine, "evening", "Acne Treatment")
    assert step.product_id is None and step.custom_product_name == "Cousin's Acne Cream"
    ticked = db.scalars(
        select(RoutineStepIngredient.ingredient_id).where(
            RoutineStepIngredient.routine_step_id == step.id
        )
    ).all()
    assert len(ticked) == 3
    suggestions = db.scalars(
        select(ProductSuggestion).where(ProductSuggestion.user_id == app_user.id)
    ).all()
    assert [(s.name, s.step_category, s.status) for s in suggestions] == [
        ("Cousin's Acne Cream", "treat", "pending")
    ]


# ---------- clashing treatments ----------


def test_retinol_and_an_acid_treatment_alternate_nights(db: Session, app_user):
    scan(db, app_user, acne="mild", wrinkles="mild")
    blemish_gel = {"product_id": product_id(db, "Blemish Control Gel")}  # glycolic + salicylic

    routine = save(db, app_user, top_picks(db, app_user, acne_treatment=blemish_gel)).routine

    assert by_title(routine, "evening", "Anti-Aging Treatment").days_of_week == MON_WED_FRI
    assert by_title(routine, "evening", "Acne Treatment").days_of_week == EVERY_DAY - MON_WED_FRI


def test_no_clash_keeps_every_day(db: Session, app_user):
    scan(db, app_user, acne="mild", wrinkles="mild")
    comedomed = {"product_id": product_id(db, "Cleanance Comedomed")}  # no acid, no retinoid

    routine = save(db, app_user, top_picks(db, app_user, acne_treatment=comedomed)).routine

    assert by_title(routine, "evening", "Acne Treatment").days_of_week == EVERY_DAY


def test_two_every_day_treatments_are_split(db: Session, app_user):
    scan(db, app_user, acne="mild", redness="moderate")
    blemish_gel = {"product_id": product_id(db, "Blemish Control Gel")}

    routine = save(db, app_user, top_picks(db, app_user, acne_treatment=blemish_gel)).routine

    # azelaic acid (higher priority) Mon/Wed/Fri/Sun, the acid gel Tue/Thu/Sat
    azelaic = by_title(routine, "evening", "Redness Treatment").days_of_week
    acne = by_title(routine, "evening", "Acne Treatment").days_of_week
    assert azelaic == to_mask(["mon", "wed", "fri", "sun"])
    assert acne == to_mask(["tue", "thu", "sat"])


def test_chosen_days_that_clash_are_refused(db: Session, app_user):
    scan(db, app_user, acne="mild", wrinkles="mild")
    choices = top_picks(
        db, app_user,
        acne_treatment={"product_id": product_id(db, "Blemish Control Gel"),
                        "days_of_week": EVERY_DAY},
        anti_aging_treatment={"days_of_week": EVERY_DAY},
    )  # fmt: skip

    with pytest.raises(AppError) as error:
        save(db, app_user, choices)

    assert error.value.status_code == 409 and error.value.code == "steps_conflict"
    assert set(error.value.details["steps"]) == {"Acne Treatment", "Anti-Aging Treatment"}


def test_a_treatment_with_no_day_left_is_refused(db: Session, app_user):
    # retinol Mon/Wed/Fri, azelaic acid (salicylate) the other nights: no night for an acid gel
    scan(db, app_user, acne="mild", wrinkles="mild", redness="moderate")
    blemish_gel = {"product_id": product_id(db, "Blemish Control Gel")}
    choices = top_picks(db, app_user, acne_treatment=blemish_gel)

    with pytest.raises(AppError) as error:
        save(db, app_user, choices)

    assert error.value.code == "steps_conflict"
    assert error.value.details["steps"][0] == "Acne Treatment"


def test_the_users_days_are_kept_and_the_others_move(db: Session, app_user):
    scan(db, app_user, acne="mild", wrinkles="mild")
    weekend = to_mask(["sat", "sun"])
    choices = top_picks(db, app_user,
                        acne_treatment={"product_id": product_id(db, "Blemish Control Gel"),
                                        "days_of_week": weekend})  # fmt: skip

    routine = save(db, app_user, choices).routine

    assert by_title(routine, "evening", "Acne Treatment").days_of_week == weekend
    assert by_title(routine, "evening", "Anti-Aging Treatment").days_of_week == MON_WED_FRI


# ---------- "I don't have it yet" ----------


def test_a_step_waiting_for_its_product_is_not_counted(db: Session, app_user):
    waiting = {"has_product": False}
    routine = save(db, app_user, top_picks(db, app_user, sunscreen=waiting)).routine
    today = user_today(app_user)
    sunscreen = by_title(routine, "morning", "Sunscreen")

    assert sunscreen.needs_product is True
    assert sunscreen not in scheduled_steps(routine, today)

    routine_builder_service.mark_product_ready(db, app_user, sunscreen)

    assert sunscreen.product_ready_on == today and step_counts_on(sunscreen, today)
    assert not step_counts_on(sunscreen, today - timedelta(days=1))  # never before that day


# ---------- versions ----------


def tick_today(db: Session, user, step) -> None:
    db.add(RoutineLog(routine_step_id=step.id, user_id=user.id, log_date=user_today(user)))
    db.flush()


def test_editing_on_the_same_day_replaces_the_version_and_keeps_ticks(db: Session, app_user):
    first = save(db, app_user, top_picks(db, app_user)).routine
    tick_today(db, app_user, by_title(first, "morning", "Cleanse"))

    sensibio = {"product_id": product_id(db, "Sensibio Gel Moussant")}
    second = save(db, app_user, top_picks(db, app_user, cleanse=sensibio)).routine

    assert db.scalar(select(func.count()).select_from(Routine)
                     .where(Routine.user_id == app_user.id)) == 1  # fmt: skip
    cleanse = by_title(second, "morning", "Cleanse")
    assert cleanse.product_id == product_id(db, "Sensibio Gel Moussant")
    assert db.scalar(select(RoutineLog.routine_step_id)) == cleanse.id


def test_editing_later_keeps_the_old_version_for_past_days(db: Session, app_user):
    first = save(db, app_user, top_picks(db, app_user)).routine
    first.created_at = datetime.now(UTC) - timedelta(days=3)
    old_cleanse = by_title(first, "morning", "Cleanse")
    yesterday = user_today(app_user) - timedelta(days=1)
    db.add(RoutineLog(routine_step_id=old_cleanse.id, user_id=app_user.id, log_date=yesterday))
    tick_today(db, app_user, old_cleanse)

    choices = [c for c in top_picks(db, app_user) if c.time_of_day == "morning"]
    second = save(db, app_user, choices).routine

    db.refresh(first)
    assert first.is_active is False and second.is_active is True
    logs = dict(db.execute(select(RoutineLog.log_date, RoutineLog.routine_step_id)).all())
    assert logs[yesterday] == old_cleanse.id  # the past stays on the old version
    assert logs[user_today(app_user)] == by_title(second, "morning", "Cleanse").id

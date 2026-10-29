"""The rules engine, part 1: the routine PROPOSAL (Phase 3 Step 2.3a, decided 2026-10-28/29).

Input: the user's concerns with their severity (from a scan and/or the skin quiz) and their
profile (pregnancy, allergies, skin type). Output: the steps they need, each with EVERY real
product that is safe for them, best first (the first = "Top pick"). Nothing is saved: the user
chooses one product per step (or their own) and the routine is built from those choices.

1. Rules: the base steps (cleanse, moisturize, sunscreen) + the active rules of each concern whose
   min_severity is reached and whose skin_type is empty or the user's.
2. A SEVERE concern adds no steps: the user keeps the gentle base routine and is referred to a
   dermatologist (see_dermatologist). The app never treats severe cases with cosmetics.
3. "both" rules become a morning and an evening step.
4. cleanse / moisturize / protect: one step per time of day. The product lists of all the rules
   for that slot are merged, highest priority first, the base products last (so when no concern
   product is safe, the base products are still offered).
5. treat: one step per rule, but when every product of one treatment is already offered by
   another at the same time, the two are the same job and are merged (e.g. acne + whiteheads ->
   one evening "Acne Treatment" covering both; redness + dark spots -> one azelaic acid step).
6. Unsafe products are removed, never just moved down: pregnancy (retinoids), declared allergies
   (a fragrance allergy also removes essential oils) and sensitive skin (products marked not
   suitable for it). A treatment left without any safe product is skipped, with the reason, so
   the app can explain it (e.g. retinol in pregnancy: the peptide serum covers wrinkles).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import ConcernRecommendationMapping, Product, User
from app.models.choices import SEVERITIES, STEP_CATEGORIES, STEP_TIMES_OF_DAY
from app.repositories import ingredient_repository, product_repository

SEVERITY_LEVEL = {severity: level for level, severity in enumerate(SEVERITIES)}
FRAGRANCE = "Fragrance (Parfum)"
ESSENTIAL_OILS = "Essential Oils"  # scent too: avoided with a fragrance allergy


@dataclass(frozen=True)
class Safety:
    """What makes a product unsafe for this user."""

    pregnant: bool
    sensitive: bool
    avoid_ids: frozenset[int]  # declared allergies (+ essential oils with fragrance)
    pregnancy_unsafe_ids: frozenset[int]

    def problem(self, product: Product, ingredient_ids: set[int]) -> str | None:
        """Why the product is unsafe for the user, or None when it is safe."""
        if self.pregnant and ingredient_ids & self.pregnancy_unsafe_ids:
            return "pregnancy"
        if ingredient_ids & self.avoid_ids:
            return "allergy"
        if self.sensitive and not product.suitable_for_sensitive:
            return "sensitive_skin"
        return None


@dataclass
class ProposedStep:
    time_of_day: str
    step_category: str
    title: str
    product_type: str
    description: str | None
    ingredient_id: int | None
    recommended_concentration: str | None
    days_of_week: int
    mapping_id: int  # the rule the step comes from (the highest-priority one when merged)
    priority: int
    concerns: list[str]  # the concerns it serves; empty = a base step for everyone
    candidates: list[Product]  # every product of its rules, best first, before the filters
    products: list[Product] = field(default_factory=list)  # the safe ones, best first


@dataclass(frozen=True)
class SkippedStep:
    time_of_day: str
    title: str
    concerns: list[str]
    reason: str  # pregnancy | allergy | sensitive_skin | no_safe_product


@dataclass
class Proposal:
    steps: list[ProposedStep]
    skipped: list[SkippedStep]
    see_dermatologist: list[str]  # the severe concerns


def propose(db: Session, user: User, concerns: Mapping[str, str]) -> Proposal:
    """concerns: concern name -> severity (mild | moderate | severe)."""
    profile = user.profile
    skin_type = profile.skin_type if profile else None
    rules = [
        (rule, concern)
        for rule, concern in product_repository.list_active_rules(db)
        if _applies(rule, concern, concerns, skin_type)
    ]
    products = product_repository.products_of_rules(db, [rule.id for rule, _ in rules])
    steps = _merge(
        [
            _step(rule, concern, time_of_day, products.get(rule.id, []))
            for rule, concern in rules
            for time_of_day in _times(rule)
        ]
    )

    safety = safety_for(db, user)
    ingredient_ids = product_repository.ingredient_ids_of_products(
        db, {product.id for step in steps for product in step.candidates}
    )
    kept, skipped = [], []
    for step in steps:
        problems = {
            product.id: safety.problem(product, ingredient_ids.get(product.id, set()))
            for product in step.candidates
        }
        step.products = [p for p in step.candidates if problems[p.id] is None]
        if step.step_category == "treat" and step.candidates and not step.products:
            reasons = set(problems.values())
            reason = reasons.pop() if len(reasons) == 1 else "no_safe_product"
            skipped.append(SkippedStep(step.time_of_day, step.title, step.concerns, reason))
        else:
            # a cleanse / moisturize / protect step stays even without a safe product (very
            # rare: the user then uses their own product); the base routine is never dropped
            kept.append(step)

    severe = sorted(name for name, severity in concerns.items() if severity == "severe")
    return Proposal(steps=kept, skipped=skipped, see_dermatologist=severe)


def _applies(
    rule: ConcernRecommendationMapping,
    concern: str | None,
    concerns: Mapping[str, str],
    skin_type: str | None,
) -> bool:
    if concern is None:
        return True  # base step
    severity = concerns.get(concern)
    if severity is None or severity == "severe":
        return False
    return (
        SEVERITY_LEVEL[severity] >= SEVERITY_LEVEL[rule.min_severity]
        and rule.skin_type in (None, skin_type)
    )


def _times(rule: ConcernRecommendationMapping) -> tuple[str, ...]:
    return STEP_TIMES_OF_DAY if rule.time_of_day == "both" else (rule.time_of_day,)


def _step(
    rule: ConcernRecommendationMapping, concern: str | None, time_of_day: str, products: list
) -> ProposedStep:
    return ProposedStep(
        time_of_day=time_of_day,
        step_category=rule.step_category,
        title=rule.step_title,
        product_type=rule.product_type,
        description=rule.notes,
        ingredient_id=rule.ingredient_id,
        recommended_concentration=rule.recommended_concentration,
        days_of_week=rule.days_of_week,
        mapping_id=rule.id,
        priority=rule.priority,
        concerns=[concern] if concern else [],
        candidates=list(products),
    )


def _merge(steps: list[ProposedStep]) -> list[ProposedStep]:
    """Rules 4 and 5 of the module docstring; returns the steps in routine order."""
    steps = sorted(steps, key=lambda s: (-s.priority, s.mapping_id))
    merged: list[ProposedStep] = []
    for step in steps:
        same = next((kept for kept in merged if _same_job(kept, step)), None)
        if same is None:
            merged.append(step)
            continue
        ids = {p.id for p in step.candidates}
        if step.step_category == "treat" and {p.id for p in same.candidates} < ids:
            # the lower-priority treatment offers everything the other one does, and more:
            # it becomes the step, covering both concerns
            _absorb(step, same)
            merged[merged.index(same)] = step
        else:
            _absorb(same, step)
    return sorted(
        merged,
        key=lambda s: (
            STEP_TIMES_OF_DAY.index(s.time_of_day),
            STEP_CATEGORIES.index(s.step_category),
            -s.priority,
            s.mapping_id,
        ),
    )


def _same_job(kept: ProposedStep, step: ProposedStep) -> bool:
    if (kept.time_of_day, kept.step_category) != (step.time_of_day, step.step_category):
        return False
    if step.step_category != "treat":
        return True  # one cleanser, one moisturizer and one sunscreen per time of day
    a, b = {p.id for p in kept.candidates}, {p.id for p in step.candidates}
    return bool(a and b) and (a <= b or b <= a)


def _absorb(into: ProposedStep, other: ProposedStep) -> None:
    """`into` keeps its title and order; it gains the other step's concerns and products."""
    into.concerns += [c for c in other.concerns if c not in into.concerns]
    known = {p.id for p in into.candidates}
    into.candidates += [p for p in other.candidates if p.id not in known]
    into.priority = max(into.priority, other.priority)


def safety_for(db: Session, user: User) -> Safety:
    """The user's pregnancy, allergies and skin type, as product filters."""
    profile = user.profile
    allergies = {i.name: i.id for i in ingredient_repository.list_allergies(db, user.id)}
    avoid = set(allergies.values())
    if FRAGRANCE in allergies:
        essential_oils = product_repository.ingredient_ids_by_name(db).get(ESSENTIAL_OILS)
        if essential_oils is not None:
            avoid.add(essential_oils)
    return Safety(
        pregnant=bool(profile and profile.is_pregnant_or_breastfeeding),
        sensitive=bool(profile and profile.skin_type == "sensitive"),
        avoid_ids=frozenset(avoid),
        pregnancy_unsafe_ids=frozenset(product_repository.pregnancy_unsafe_ingredient_ids(db)),
    )

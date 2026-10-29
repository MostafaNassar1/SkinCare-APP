from sqlalchemy.orm import Session

from app.models import SkinConcern, User
from app.repositories import product_repository, skin_concern_repository
from app.schemas.recommendation import (
    ConcernOut,
    ProductOut,
    RecommendationsOut,
    RecommendedStepOut,
    SkippedStepOut,
)
from app.services import concern_explanation_service, concern_service, recommendation_service
from app.services.weekdays import from_mask

DISCLAIMER = (
    "These suggestions are for visible skin concerns only and are not medical advice. Read each "
    "product's label, patch-test new products and stop if your skin is irritated. For a lasting "
    "or severe problem, see a dermatologist."
)
SKIP_MESSAGES = {
    "pregnancy": "Not advised during pregnancy or breastfeeding, so this step is left out.",
    "allergy": "Every product for this step contains an ingredient you are allergic to.",
    "sensitive_skin": "The products for this step are too strong for sensitive skin.",
    "no_safe_product": "None of our products for this step suits your profile.",
}


def get_recommendations(db: Session, user: User) -> RecommendationsOut:
    """The steps the user needs and every safe real product for each (nothing is saved)."""
    current = concern_service.current_concerns(db, user)
    proposal = recommendation_service.propose(db, user, current.concerns)
    shown = {p.id for step in proposal.steps for p in step.products}
    ingredients = product_repository.key_ingredients(db, shown)
    known = {c.name: c for c in skin_concern_repository.list_all(db)}

    return RecommendationsOut(
        concerns=[
            _concern_out(known[name], severity) for name, severity in current.concerns.items()
        ],
        steps=[
            RecommendedStepOut(
                time_of_day=step.time_of_day,
                mapping_id=step.mapping_id,
                step_category=step.step_category,
                title=step.title,
                product_type=step.product_type,
                description=step.description,
                days=from_mask(step.days_of_week),
                concerns=step.concerns,
                products=[
                    ProductOut(
                        id=p.id,
                        brand=p.brand,
                        name=p.name,
                        image_url=p.image_url,
                        directions=p.directions,
                        key_ingredients=ingredients.get(p.id, []),
                        top_pick=rank == 0,
                    )
                    for rank, p in enumerate(step.products)
                ],
            )
            for step in proposal.steps
        ],
        skipped=[
            SkippedStepOut(
                time_of_day=s.time_of_day,
                title=s.title,
                concerns=s.concerns,
                reason=s.reason,
                message=SKIP_MESSAGES[s.reason],
            )
            for s in proposal.skipped
        ],
        see_dermatologist=proposal.see_dermatologist,
        disclaimer=DISCLAIMER,
    )


def _concern_out(concern: SkinConcern, severity: str) -> ConcernOut:
    explanation = concern_explanation_service.explain(concern.name, severity)
    return ConcernOut(
        name=concern.name,
        display_name=concern.display_name,
        severity=severity,
        about=concern.description,
        routine_focus=explanation.routine_focus,
        expect=explanation.expect,
        advice=explanation.advice,
    )

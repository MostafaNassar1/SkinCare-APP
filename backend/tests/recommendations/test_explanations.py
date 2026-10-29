"""What the app says about each concern, by severity, and the wording rules for every text."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.controllers.recommendation_controller import DISCLAIMER, SKIP_MESSAGES
from app.models import ConcernRecommendationMapping, SkinConcern
from app.services import concern_explanation_service as explanations
from app.services.skin_quiz_service import QUESTIONS
from tests.recommendations.conftest import add_scan

# the student's wording rules: "visible concern", never disease / diagnosis / cure, never
# "healthy skin" (the app does not judge skin)
FORBIDDEN = re.compile(r"diseas|diagnos|\bcur(e|es|ed|ing)\b|healthy skin", re.IGNORECASE)


def test_every_concern_has_an_explanation(db: Session):
    names = set(db.scalars(select(SkinConcern.name)))

    assert names == explanations.FOCUS_AND_EXPECT.keys()


@pytest.mark.parametrize("concern", sorted(explanations.FOCUS_AND_EXPECT))
def test_advice_grows_with_severity(concern):
    mild = explanations.explain(concern, "mild")
    moderate = explanations.explain(concern, "moderate")
    severe = explanations.explain(concern, "severe")

    assert mild.advice is None and mild.expect
    assert "pharmacist or dermatologist" in moderate.advice
    assert moderate.routine_focus == mild.routine_focus
    assert "see a dermatologist" in severe.advice
    assert severe.expect is None  # no treatment added: no promise of results


def test_no_user_facing_text_breaks_the_wording_rules(db: Session):
    texts = [DISCLAIMER, *SKIP_MESSAGES.values(), explanations.MODERATE_ADVICE,
             explanations.SEVERE_FOCUS, explanations.SEVERE_ADVICE]  # fmt: skip
    texts += [text for pair in explanations.FOCUS_AND_EXPECT.values() for text in pair]
    texts += [q.text for q in QUESTIONS] + [o.label for q in QUESTIONS for o in q.options]
    texts += [d for d in db.scalars(select(SkinConcern.description)) if d]
    for rule in db.scalars(select(ConcernRecommendationMapping)):
        texts += [rule.step_title, rule.product_type, rule.notes or ""]

    assert [text for text in texts if FORBIDDEN.search(text)] == []


def test_recommendations_explain_each_concern(
    client: TestClient, db: Session, app_user, user_headers
):
    add_scan(db, app_user, acne="moderate", wrinkles="severe")

    body = client.get("/me/recommendations", headers=user_headers).json()

    concerns = {c["name"]: c for c in body["concerns"]}
    assert concerns["acne"]["about"] == (
        "Breakouts caused by clogged pores, excess oil, or bacteria."
    )
    assert concerns["acne"]["advice"] == explanations.MODERATE_ADVICE
    assert concerns["wrinkles"]["routine_focus"] == explanations.SEVERE_FOCUS
    assert concerns["wrinkles"]["expect"] is None
    assert body["see_dermatologist"] == ["wrinkles"]

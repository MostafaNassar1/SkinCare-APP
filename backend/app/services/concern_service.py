"""The user's current concerns, decided by the SERVER (the student's decision, 2026-10-29).

The routine is built from the latest face scan + the skin quiz, never from a list sent by the
phone (it could claim concerns the scan did not find). Quiz concerns (no reliable photo data):
- skin type oily -> oiliness, dry -> dryness, combination -> oiliness (its oily zone is the part
  that needs care), all mild; normal and sensitive add none (sensitive turns on the gentle-product
  filter instead). Redness comes from the quiz v2 redness question (mild / moderate / severe).
When the scan and the quiz report the same concern, the more severe answer wins.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import User
from app.repositories import scan_repository
from app.services import skin_quiz_service
from app.services.recommendation_service import SEVERITY_LEVEL

SKIN_TYPE_CONCERNS = {"oily": "oiliness", "dry": "dryness", "combination": "oiliness"}


@dataclass(frozen=True)
class CurrentConcerns:
    scan_result_id: int | None  # the scan the routine is based on (None before the first scan)
    concerns: dict[str, str]  # concern name -> severity


def current_concerns(db: Session, user: User) -> CurrentConcerns:
    scan_result_id, concerns = scan_repository.latest_scan_concerns(db, user.id)
    concerns = dict(concerns)
    for name, severity in quiz_concerns(user).items():
        if SEVERITY_LEVEL[severity] > SEVERITY_LEVEL.get(concerns.get(name), -1):
            concerns[name] = severity
    return CurrentConcerns(scan_result_id=scan_result_id, concerns=concerns)


def quiz_concerns(user: User) -> dict[str, str]:
    profile = user.profile
    if profile is None:
        return {}
    concerns = {}
    concern = SKIN_TYPE_CONCERNS.get(profile.skin_type)
    if concern:
        concerns[concern] = "mild"
    redness = skin_quiz_service.redness_from_saved(profile.skin_quiz_answers)
    if redness:
        concerns["redness"] = redness
    return concerns

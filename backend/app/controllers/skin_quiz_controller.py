from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import User
from app.repositories import user_repository
from app.schemas.skin_quiz import (
    QuizOptionOut,
    QuizQuestionOut,
    SkinQuizAnswers,
    SkinQuizOut,
    SkinQuizResultOut,
)
from app.services import skin_quiz_service


def get_quiz() -> SkinQuizOut:
    """The questions and options only; the scoring weights stay on the server."""
    return SkinQuizOut(
        version=skin_quiz_service.QUIZ_VERSION,
        questions=[
            QuizQuestionOut(
                id=question.id,
                text=question.text,
                options=[QuizOptionOut(id=o.id, label=o.label) for o in question.options],
            )
            for question in skin_quiz_service.QUESTIONS
        ],
    )


def submit_answers(db: Session, user: User, data: SkinQuizAnswers) -> SkinQuizResultOut:
    """Score the quiz and save the result; taking it again replaces the previous result."""
    errors = skin_quiz_service.answer_errors(data.answers)
    if errors:
        raise AppError(422, "validation_error", "Some answers are missing or invalid", errors)

    result = skin_quiz_service.score(data.answers)
    profile = user_repository.get_or_create_profile(db, user)
    profile.skin_type = result.skin_type
    profile.fitzpatrick_scale = result.fitzpatrick_scale
    if result.is_pregnant_or_breastfeeding is not None:
        # "prefer not to say" leaves the flag as it was (the user's decision, 2026-10-13)
        profile.is_pregnant_or_breastfeeding = result.is_pregnant_or_breastfeeding
    profile.skin_quiz_answers = {
        "version": skin_quiz_service.QUIZ_VERSION,
        "answers": data.answers,
    }
    profile.skin_quiz_completed_at = datetime.now(UTC)
    db.commit()

    return SkinQuizResultOut(
        skin_type=result.skin_type,
        fitzpatrick_scale=result.fitzpatrick_scale,
        is_pregnant_or_breastfeeding=profile.is_pregnant_or_breastfeeding,
        completed_at=profile.skin_quiz_completed_at,
        oil_score=result.oil_score,
        dry_score=result.dry_score,
    )

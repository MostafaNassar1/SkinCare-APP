from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.choices import SKIN_TYPES


class QuizOptionOut(BaseModel):
    id: str
    label: str


class QuizQuestionOut(BaseModel):
    id: str
    text: str
    options: list[QuizOptionOut]


class SkinQuizOut(BaseModel):
    version: int
    questions: list[QuizQuestionOut]


class SkinQuizAnswers(BaseModel):
    # {question id: option id}, e.g. {"after_washing": "tight", ...}; checked against the quiz
    answers: dict[str, str] = Field(max_length=50)


class SkinQuizResultOut(BaseModel):
    skin_type: Literal[SKIN_TYPES]
    fitzpatrick_scale: int
    is_pregnant_or_breastfeeding: bool
    completed_at: datetime
    # shown for transparency: how the skin type was reached
    oil_score: int
    dry_score: int

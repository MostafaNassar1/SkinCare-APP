from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.choices import ACHIEVEMENT_CRITERIA, DETECTION_METHODS


class SkinConcernOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str  # stable code used by the API, e.g. "dark_spots"
    display_name: str  # shown in the app, e.g. "Dark spots"
    description: str | None
    # photo = the AI model alone; hybrid = skin quiz (primary) + photo (oiliness, dryness)
    detection_method: Literal[DETECTION_METHODS]


class AchievementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    icon_url: str | None
    criteria_type: Literal[ACHIEVEMENT_CRITERIA]  # what is counted, e.g. "streak_days"
    criteria_value: int  # the goal, e.g. 7 (days in a row)


class MyAchievementOut(AchievementOut):
    earned: bool
    earned_at: datetime | None
    progress: int  # towards criteria_value, e.g. 4 of 7 (equal to the goal once earned)

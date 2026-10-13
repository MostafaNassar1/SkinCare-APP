from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.choices import DETECTION_METHODS


class SkinConcernOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str  # stable code used by the API, e.g. "dark_spots"
    display_name: str  # shown in the app, e.g. "Dark spots"
    description: str | None
    # photo = the AI model alone; hybrid = skin quiz (primary) + photo (oiliness, dryness)
    detection_method: Literal[DETECTION_METHODS]

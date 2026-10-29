from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.choices import SEVERITIES, STEP_CATEGORIES, STEP_TIMES_OF_DAY
from app.services.weekdays import WEEKDAYS

Weekday = Literal[WEEKDAYS]


class WhereToBuyOut(BaseModel):
    """Never a shop name or a shop link (the student's decision): the app shows this label and a
    button opening the map of the pharmacies nearest to the user's GPS position."""

    label: str = "Available in pharmacies"
    nearby_pharmacies_path: str = "/places/nearby?type=pharmacies"  # + &lat=..&lon=.. (GPS)


class ProductCardOut(BaseModel):
    """A real product as the app shows it (recommendations and the routine screen)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    brand: str
    name: str
    image_url: str | None  # our own copy of the brand's picture (None until it is uploaded)
    directions: str  # how to apply it
    where_to_buy: WhereToBuyOut = WhereToBuyOut()


class ProductOut(ProductCardOut):
    key_ingredients: list[str]  # our active ingredients in it, e.g. ["Niacinamide 15%"]
    top_pick: bool  # the first safe product of the step


class ConcernOut(BaseModel):
    name: str
    display_name: str
    severity: Literal[SEVERITIES]


class RecommendedStepOut(BaseModel):
    time_of_day: Literal[STEP_TIMES_OF_DAY]
    mapping_id: int  # with time_of_day, identifies the step when saving the routine
    step_category: Literal[STEP_CATEGORIES]
    title: str
    product_type: str
    description: str | None
    days: list[str]  # recommended weekdays, e.g. ["mon", "wed", "fri"]
    concerns: list[str]  # the concerns it serves; empty = a base step for everyone
    products: list[ProductOut]  # every safe product, best first


class SkippedStepOut(BaseModel):
    time_of_day: Literal[STEP_TIMES_OF_DAY]
    title: str
    concerns: list[str]
    reason: Literal["pregnancy", "allergy", "sensitive_skin", "no_safe_product"]
    message: str


class RecommendationsOut(BaseModel):
    concerns: list[ConcernOut]  # from the latest scan + the skin quiz
    steps: list[RecommendedStepOut]
    skipped: list[SkippedStepOut]
    see_dermatologist: list[str]  # severe concerns: show the clinic referral
    disclaimer: str


class OwnProductIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=200)
    ingredient_ids: list[int] = Field(default=[], max_length=50)  # "Does it contain...?"


class StepChoiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_of_day: Literal[STEP_TIMES_OF_DAY]
    mapping_id: int
    product_id: int | None = None  # one of the step's products...
    own_product: OwnProductIn | None = None  # ...or the user's own (not both)
    has_product: bool = True  # False = "I don't have it yet"
    days: list[Weekday] | None = Field(default=None, min_length=1)  # None = recommended days

    @model_validator(mode="after")
    def one_product(self) -> "StepChoiceIn":
        if self.product_id is not None and self.own_product is not None:
            raise ValueError("choose a catalogue product or your own product, not both")
        return self


class RoutineIn(BaseModel):
    """The whole routine as the user wants it (saving and editing are the same)."""

    model_config = ConfigDict(extra="forbid")

    steps: list[StepChoiceIn] = Field(max_length=30)


class OwnProductWarningOut(BaseModel):
    step_title: str
    ingredient: str
    reason: Literal["pregnancy", "allergy"]
    message: str

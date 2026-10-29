from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.choices import INGREDIENT_KINDS

OTHER_ALLERGIES_MAX_LENGTH = 1000


class IngredientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    avoid_during_pregnancy: bool
    # active = skincare ingredient (e.g. Retinol); allergen = common cause of product allergies
    # (e.g. Fragrance): the app can show them as two groups on the allergy screen
    kind: Literal[INGREDIENT_KINDS]


class AllergiesOut(BaseModel):
    ingredients: list[IngredientOut]
    other_allergies_notes: str | None  # allergies to things that are not in the ingredient list


class AllergiesUpdate(BaseModel):
    """The complete new allergy list: it replaces the previous one (the app saves the whole
    screen at once, so nothing is ever half-saved)."""

    model_config = ConfigDict(extra="forbid")

    ingredient_ids: list[int] = Field(max_length=100)
    other_allergies_notes: str | None = Field(default=None, max_length=OTHER_ALLERGIES_MAX_LENGTH)

    @field_validator("other_allergies_notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

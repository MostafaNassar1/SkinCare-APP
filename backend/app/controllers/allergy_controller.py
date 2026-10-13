from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models import User
from app.repositories import ingredient_repository, user_repository
from app.schemas.ingredient import AllergiesOut, AllergiesUpdate, IngredientOut


def get_allergies(db: Session, user: User) -> AllergiesOut:
    profile = user_repository.get_or_create_profile(db, user)
    return AllergiesOut(
        ingredients=[
            IngredientOut.model_validate(i)
            for i in ingredient_repository.list_allergies(db, user.id)
        ],
        other_allergies_notes=profile.other_allergies_notes,
    )


def replace_allergies(db: Session, user: User, data: AllergiesUpdate) -> AllergiesOut:
    """The routine generator never recommends an ingredient on this list."""
    wanted = set(data.ingredient_ids)  # duplicates are merged
    found = {i.id for i in ingredient_repository.get_by_ids(db, wanted)}
    unknown = sorted(wanted - found)
    if unknown:
        raise AppError(
            422,
            "validation_error",
            "Some ingredients do not exist",
            [{"field": "ingredient_ids", "message": f"Unknown ingredient ids: {unknown}"}],
        )

    ingredient_repository.replace_allergies(db, user.id, wanted)
    user_repository.get_or_create_profile(db, user).other_allergies_notes = (
        data.other_allergies_notes
    )
    db.commit()
    return get_allergies(db, user)

from sqlalchemy.orm import Session

from app.repositories import skin_concern_repository
from app.schemas.reference import SkinConcernOut


def list_skin_concerns(db: Session) -> list[SkinConcernOut]:
    return [SkinConcernOut.model_validate(c) for c in skin_concern_repository.list_all(db)]

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import reference_controller
from app.core.dependencies import get_db, reference_cache
from app.schemas.reference import SkinConcernOut

# public, read-only lists the app displays
router = APIRouter(tags=["Reference data"], dependencies=[Depends(reference_cache)])

DB = Annotated[Session, Depends(get_db)]


@router.get("/skin-concerns", response_model=list[SkinConcernOut])
def list_skin_concerns(db: DB):
    """The 6 visible skin concerns the app can detect (not diseases)."""
    return reference_controller.list_skin_concerns(db)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import health_controller
from app.core.dependencies import get_db

router = APIRouter(tags=["Health"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    return health_controller.check_health(db)

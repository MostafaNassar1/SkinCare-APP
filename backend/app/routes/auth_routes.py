from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.controllers import auth_controller
from app.core.dependencies import get_db
from app.schemas.auth import RegisterRequest, UserAuthResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserAuthResponse)
def register(data: RegisterRequest, db: Annotated[Session, Depends(get_db)]):
    return auth_controller.register(db, data)

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.controllers import scheduler_controller
from app.core.config import Settings, get_settings
from app.core.dependencies import get_db
from app.schemas.scheduler import SchedulerRunOut

# Not shown in /docs: only the server's own trigger uses it.
router = APIRouter(prefix="/internal", include_in_schema=False)


@router.post("/scheduler/run", response_model=SchedulerRunOut)
def run_scheduler(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    x_scheduler_key: Annotated[str | None, Header()] = None,
):
    return scheduler_controller.run_now(db, settings, x_scheduler_key)

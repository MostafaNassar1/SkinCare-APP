from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status
from sqlalchemy.orm import Session

from app.controllers import profile_controller
from app.core.dependencies import CurrentUser, get_db
from app.schemas.location import LocationOut, LocationUpdate
from app.schemas.profile import DeleteAccountRequest, ProfileOut, ProfileUpdate
from app.schemas.reminders import RemindersOut, RemindersUpdate

router = APIRouter(prefix="/me", tags=["Profile"])

DB = Annotated[Session, Depends(get_db)]


@router.get("/profile", response_model=ProfileOut)
def get_profile(user: CurrentUser, db: DB):
    return profile_controller.get_profile(db, user)


@router.patch("/profile", response_model=ProfileOut)
def update_profile(data: ProfileUpdate, user: CurrentUser, db: DB):
    return profile_controller.update_profile(db, user, data)


@router.get("/reminders", response_model=RemindersOut)
def get_reminders(user: CurrentUser, db: DB):
    return profile_controller.get_reminders(db, user)


@router.patch("/reminders", response_model=RemindersOut)
def update_reminders(data: RemindersUpdate, user: CurrentUser, db: DB):
    """Routine reminder settings: on/off and the morning/evening times (user's time zone)."""
    return profile_controller.update_reminders(db, user, data)


@router.get("/location", response_model=LocationOut)
def get_location(user: CurrentUser):
    return profile_controller.get_location(user)


@router.put("/location", response_model=LocationOut)
def update_location(data: LocationUpdate, user: CurrentUser, db: DB):
    """The phone's location, stored rounded to about 1 km (for weather advice)."""
    return profile_controller.update_location(db, user, data)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    data: DeleteAccountRequest, user: CurrentUser, db: DB, background: BackgroundTasks
):
    """Permanently delete the account and all its data (cannot be undone)."""
    profile_controller.delete_account(db, user, data, background)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

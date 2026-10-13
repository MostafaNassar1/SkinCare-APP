from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.controllers import device_controller
from app.core.dependencies import CurrentUser, get_db
from app.schemas.device import DeviceOut, DeviceRegister

router = APIRouter(prefix="/me/devices", tags=["Push notification devices"])

DB = Annotated[Session, Depends(get_db)]


@router.post("", response_model=DeviceOut)
def register_device(data: DeviceRegister, user: CurrentUser, db: DB):
    """Called by the app after login with the phone's Firebase push token."""
    return device_controller.register_device(db, user, data)


@router.delete("/{fcm_token}", status_code=status.HTTP_204_NO_CONTENT)
def remove_device(fcm_token: str, user: CurrentUser, db: DB):
    """Called by the app at logout."""
    device_controller.remove_device(db, user, fcm_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

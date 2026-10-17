from datetime import UTC, datetime

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.security import verify_password
from app.models import User
from app.repositories import user_repository
from app.schemas.location import LocationOut, LocationUpdate
from app.schemas.profile import DeleteAccountRequest, ProfileOut, ProfileUpdate, SkinProfileOut
from app.schemas.reminders import RemindersOut, RemindersUpdate
from app.services import email_service, google_auth_service
from app.services.email_templates import account_deleted_email

# fields of ProfileUpdate stored in user_profiles; the others are columns of users
SKIN_PROFILE_FIELDS = {"is_pregnant_or_breastfeeding", "skin_notes"}


def get_profile(db: Session, user: User) -> ProfileOut:
    profile = user_repository.get_or_create_profile(db, user)
    return ProfileOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        email_verified=user.email_verified,
        auth_provider=user.auth_provider,
        has_password=user.password_hash is not None,
        phone_number=user.phone_number,
        date_of_birth=user.date_of_birth,
        gender=user.gender,
        timezone=user.timezone,
        profile_picture_url=user.profile_picture_url,
        created_at=user.created_at,
        skin=SkinProfileOut(
            skin_type=profile.skin_type,
            fitzpatrick_scale=profile.fitzpatrick_scale,
            skin_quiz_completed_at=profile.skin_quiz_completed_at,
            is_pregnant_or_breastfeeding=profile.is_pregnant_or_breastfeeding,
            skin_notes=profile.skin_notes,
        ),
    )


def _reauthentication_failed(message: str) -> AppError:
    # 403, not 401: the session itself is valid, so the app must not log the user out
    return AppError(403, "reauthentication_failed", message)


def delete_account(
    db: Session, user: User, data: DeleteAccountRequest, background: BackgroundTasks
) -> None:
    """Permanently delete the account after the owner proves it again, then email them."""
    if data.password:
        if user.password_hash is None or not verify_password(data.password, user.password_hash):
            raise _reauthentication_failed("Incorrect password")
    else:
        identity = google_auth_service.verify_for_sign_in(data.google_id_token)
        if user.google_sub is None or identity.sub != user.google_sub:
            raise _reauthentication_failed("That Google account does not match this account")

    email, name = user.email, user.full_name
    user_repository.delete_account(db, user.id)
    db.commit()
    background.add_task(email_service.send_email, account_deleted_email(email, name))


def get_reminders(db: Session, user: User) -> RemindersOut:
    profile = user_repository.get_or_create_profile(db, user)
    return RemindersOut(
        enabled=profile.routine_reminders_enabled,
        daily_forecast=profile.daily_forecast_enabled,
        morning_time=profile.morning_reminder_time,
        evening_time=profile.evening_reminder_time,
    )


def update_reminders(db: Session, user: User, data: RemindersUpdate) -> RemindersOut:
    profile = user_repository.get_or_create_profile(db, user)
    columns = {
        "enabled": "routine_reminders_enabled",
        "daily_forecast": "daily_forecast_enabled",
        "morning_time": "morning_reminder_time",
        "evening_time": "evening_reminder_time",
    }
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, columns[field], value)
    db.commit()
    return get_reminders(db, user)


def get_location(user: User) -> LocationOut:
    return LocationOut(
        latitude=user.last_latitude,
        longitude=user.last_longitude,
        updated_at=user.location_updated_at,
    )


def update_location(db: Session, user: User, data: LocationUpdate) -> LocationOut:
    """The area used for weather advice (already rounded to about 1 km by the schema)."""
    user.last_latitude = data.latitude
    user.last_longitude = data.longitude
    user.location_updated_at = datetime.now(UTC)
    db.commit()
    return get_location(user)


def update_profile(db: Session, user: User, data: ProfileUpdate) -> ProfileOut:
    profile = user_repository.get_or_create_profile(db, user)
    # only the fields the app sent; an explicit null clears an optional field
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile if field in SKIN_PROFILE_FIELDS else user, field, value)
    db.commit()
    return get_profile(db, user)

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import User
from app.repositories import user_repository
from app.schemas.location import LocationOut, LocationUpdate
from app.schemas.profile import ProfileOut, ProfileUpdate, SkinProfileOut

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

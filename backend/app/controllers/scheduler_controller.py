import secrets

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.schemas.scheduler import SchedulerRunOut
from app.services import scheduler_service


def run_now(db: Session, settings: Settings, key: str | None) -> SchedulerRunOut:
    """Send the reminders and forecasts that are due, for an external trigger (e.g. cron-job.org).

    404 (not 401) without the right key, and when no key is configured: to everyone else the
    endpoint simply does not exist. compare_digest takes the same time whatever the key, so the
    key cannot be guessed character by character from response times.
    """
    expected = settings.scheduler_secret.get_secret_value()
    if not expected or key is None or not secrets.compare_digest(key, expected):
        raise HTTPException(status_code=404, detail="Not found")
    summary = scheduler_service.run_due(db)
    return SchedulerRunOut(
        routine_reminders=summary.routine_reminders,
        appointment_reminders=summary.appointment_reminders,
        forecasts=summary.forecasts,
        pushes_sent=summary.pushes_sent,
    )

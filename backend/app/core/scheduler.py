"""The background scheduler: APScheduler running inside the backend (decided 2026-10-17).

Jobs:
- every few minutes (SCHEDULER_INTERVAL_MINUTES): routine + appointment reminders that are due
- every night at 03:00: delete email sign-ups never verified after 24 h
- every Sunday at 04:00: refresh the clinics and pharmacies from OpenStreetMap

Started and stopped with the app (create_app's lifespan) when SCHEDULER_ENABLED is true. Each job
opens its own database session. If several server processes run it, reminders are still sent
once (dedupe keys); with free hosting that sleeps, an external trigger can call
POST /internal/scheduler/run instead.
"""

import logging
from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import Settings
from app.db.session import SessionLocal
from app.services import maintenance_service, scheduler_service

logger = logging.getLogger("app.scheduler")


def send_due_reminders() -> None:
    with SessionLocal() as db:
        summary = scheduler_service.run_due(db)
    if summary.routine_reminders or summary.appointment_reminders:
        logger.info(
            "Reminders sent: %d routine, %d appointment (%d pushes)",
            summary.routine_reminders,
            summary.appointment_reminders,
            summary.pushes_sent,
        )


def cleanup_unverified() -> None:
    with SessionLocal() as db:
        deleted = maintenance_service.cleanup_unverified(db)
    logger.info("Deleted %d never-verified account(s)", deleted)


def refresh_places() -> None:
    with SessionLocal() as db:
        result = maintenance_service.refresh_places(db)
    logger.info(
        "Places refreshed: %d new, %d updated, %d inactive",
        result.created,
        result.updated,
        result.deactivated,
    )


def _logged(job: Callable[[], None]) -> Callable[[], None]:
    """A failing job is logged and retried at its next run; it never stops the scheduler."""

    def run() -> None:
        try:
            job()
        except Exception:
            logger.exception("Scheduled job %s failed", job.__name__)

    run.__name__ = job.__name__
    return run


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(
        timezone=settings.scheduler_timezone,
        # if runs were missed (server busy or asleep), run once, not once per missed run
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    )
    scheduler.add_job(
        _logged(send_due_reminders),
        IntervalTrigger(minutes=settings.scheduler_interval_minutes),
        id="send_due_reminders",
    )
    scheduler.add_job(
        _logged(cleanup_unverified),
        CronTrigger(hour=3, minute=0),
        id="cleanup_unverified",
    )
    scheduler.add_job(
        _logged(refresh_places),
        CronTrigger(day_of_week="sun", hour=4, minute=0),
        id="refresh_places",
        misfire_grace_time=3600,
    )
    return scheduler

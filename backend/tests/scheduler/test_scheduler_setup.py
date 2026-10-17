"""The scheduled jobs, the trigger endpoint and the manual command."""

import logging
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core import scheduler as scheduler_module
from app.core.config import Settings, get_settings
from app.core.scheduler import build_scheduler
from app.scripts import run_scheduler_once as script
from tests.scheduler.conftest import beirut, saved

# ---------- The jobs ----------


def test_the_scheduled_jobs():
    scheduler = build_scheduler(get_settings())
    jobs = {job.id: str(job.trigger) for job in scheduler.get_jobs()}

    assert jobs == {
        "send_due_reminders": "interval[0:05:00]",
        "cleanup_unverified": "cron[hour='3', minute='0']",
        "refresh_places": "cron[day_of_week='sun', hour='4', minute='0']",
    }
    assert str(scheduler.timezone) == "Asia/Beirut"


def test_on_by_default_but_never_started_in_tests():
    assert Settings.model_fields["scheduler_enabled"].default is True
    assert get_settings().scheduler_enabled is False


def test_a_failing_job_is_logged_not_raised(caplog):
    def broken() -> None:
        raise RuntimeError("database down")

    with caplog.at_level(logging.ERROR, logger="app.scheduler"):
        scheduler_module._logged(broken)()  # must not raise

    assert "Scheduled job broken failed" in caplog.text


# ---------- POST /internal/scheduler/run ----------


def run(client: TestClient, key: str | None = None):
    headers = {"X-Scheduler-Key": key} if key is not None else {}
    return client.post("/internal/scheduler/run", headers=headers)


def test_endpoint_does_not_exist_without_a_configured_key(client: TestClient):
    assert run(client).status_code == 404
    assert run(client, "").status_code == 404
    assert run(client, "anything").status_code == 404


def test_endpoint_needs_the_right_key(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "scheduler_secret", SecretStr("k" * 40))

    assert run(client).status_code == 404
    assert run(client, "wrong").status_code == 404
    response = run(client, "k" * 40)
    assert response.status_code == 200
    assert response.json() == {"routine_reminders": 0, "appointment_reminders": 0, "pushes_sent": 0}


def test_endpoint_is_hidden_from_the_docs(client: TestClient):
    assert "/internal/scheduler/run" not in client.get("/openapi.json").json()["paths"]


# ---------- python -m app.scripts.run_scheduler_once ----------


def test_manual_command(db: Session, app_user, routine, monkeypatch, capsys):
    monkeypatch.setattr(script, "SessionLocal", lambda: nullcontext(db))

    assert script.main(["--now", beirut(19, 21, 0).isoformat()]) == 0

    assert "Sent 1 routine and 0 appointment reminder(s), 0 push(es)." in capsys.readouterr().out
    assert len(saved(db, app_user)) == 1


def test_manual_command_needs_a_time_zone(capsys):
    with pytest.raises(SystemExit) as exit:
        script.main(["--now", "2026-10-19T21:00"])

    assert exit.value.code == 2
    assert "give a time zone" in capsys.readouterr().err

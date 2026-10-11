"""Every error, whatever its cause, uses {"error": {"code", "message", "details"}}."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.exceptions import AppError
from app.main import create_app

# a copy of the real app with test-only routes that fail in different ways
error_app = create_app()


class SignUp(BaseModel):
    email: str
    password: str = Field(min_length=10)
    age: int


@error_app.get("/raise-http")
def raise_http():
    raise HTTPException(status_code=409, detail="Already exists")


@error_app.get("/raise-app-error")
def raise_app_error():
    raise AppError(409, "email_taken", "This email is already registered", details={"x": 1})


@error_app.get("/raise-crash")
def raise_crash():
    raise RuntimeError("database password is hunter2")  # internal details that must not leak


@error_app.post("/sign-up")
def sign_up(body: SignUp):
    return {"ok": True}


@pytest.fixture
def api() -> TestClient:
    return TestClient(error_app)


def test_http_exception_uses_the_format(api: TestClient):
    response = api.get("/raise-http")

    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "conflict", "message": "Already exists", "details": None}
    }


def test_app_error_keeps_its_specific_code(api: TestClient):
    response = api.get("/raise-app-error")

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "email_taken",
        "message": "This email is already registered",
        "details": {"x": 1},
    }


def test_unknown_route_returns_not_found(api: TestClient):
    response = api.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_wrong_method_returns_method_not_allowed(api: TestClient):
    response = api.delete("/raise-http")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_validation_error_lists_the_invalid_fields(api: TestClient):
    response = api.post("/sign-up", json={"password": "short", "age": "not-a-number"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert {detail["field"] for detail in error["details"]} == {"email", "password", "age"}
    assert all(detail.keys() == {"field", "message", "type"} for detail in error["details"])


def test_validation_error_does_not_echo_the_input(api: TestClient):
    response = api.post("/sign-up", json={"email": "a@b.c", "password": "hunter2", "age": 30})

    assert response.status_code == 422
    assert "hunter2" not in response.text


def test_crash_returns_generic_500_and_logs_the_details(api: TestClient, caplog):
    response = api.get("/raise-crash")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "hunter2" not in response.text  # nothing internal reaches the client
    # ...but the full error is in the server log, with the request id the client received
    request_id = response.headers["X-Request-ID"]
    crash_logs = [r for r in caplog.records if r.levelname == "ERROR"]
    assert any(request_id in r.getMessage() and r.exc_info for r in crash_logs)

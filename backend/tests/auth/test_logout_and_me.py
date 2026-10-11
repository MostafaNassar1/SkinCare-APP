from fastapi.testclient import TestClient

from tests.auth.conftest import bearer, login


def logout(client: TestClient, token: str):
    return client.post("/auth/logout", json={"refresh_token": token})


# ---------- Logout ----------


def test_logout_ends_the_session(client: TestClient, registered: dict):
    response = logout(client, registered["refresh_token"])

    assert response.status_code == 204
    assert response.content == b""
    after = client.post("/auth/refresh", json={"refresh_token": registered["refresh_token"]})
    assert after.status_code == 401


def test_logout_keeps_other_devices_logged_in(client: TestClient, registered: dict):
    tablet = login(client).json()["refresh_token"]

    logout(client, registered["refresh_token"])

    assert client.post("/auth/refresh", json={"refresh_token": tablet}).status_code == 200


def test_logout_always_succeeds(client: TestClient, registered: dict):
    # unknown or already used tokens get the same answer, so logout reveals nothing
    assert logout(client, "made-up-token").status_code == 204
    logout(client, registered["refresh_token"])
    assert logout(client, registered["refresh_token"]).status_code == 204


# ---------- /auth/me ----------


def test_me_returns_the_logged_in_user(client: TestClient, registered: dict):
    response = client.get("/auth/me", headers=bearer(registered["access_token"]))

    assert response.status_code == 200
    assert response.json() == registered["user"]


def test_me_requires_a_token(client: TestClient):
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"

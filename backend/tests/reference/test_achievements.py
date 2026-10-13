from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Achievement, User, UserAchievement, UserProfile

SEEDED_TITLES = [
    "First Scan", "3-Day Streak", "7-Day Streak", "30-Day Streak", "Consistent Care",
    "Skin Tracker",
]  # fmt: skip


def achievement(db: Session, title: str) -> Achievement:
    return db.query(Achievement).filter_by(title=title).one()


def earn(db: Session, user: User, title: str) -> None:
    db.add(UserAchievement(user_id=user.id, achievement_id=achievement(db, title).id))
    db.flush()


# ---------- Public list ----------


def test_all_badges_are_listed_publicly_and_cached(client: TestClient):
    response = client.get("/achievements")

    assert response.status_code == 200
    assert [a["title"] for a in response.json()] == SEEDED_TITLES
    assert response.headers["Cache-Control"] == "public, max-age=3600"


def test_each_badge_says_what_it_takes(client: TestClient):
    seven = next(a for a in client.get("/achievements").json() if a["title"] == "7-Day Streak")

    assert (seven["criteria_type"], seven["criteria_value"]) == ("streak_days", 7)
    assert seven["description"]


def test_switched_off_badges_are_hidden(client: TestClient, db: Session):
    achievement(db, "Skin Tracker").is_active = False
    db.flush()

    titles = [a["title"] for a in client.get("/achievements").json()]

    assert "Skin Tracker" not in titles


# ---------- The user's badges ----------


def test_new_user_has_everything_locked(client: TestClient, user_headers):
    response = client.get("/me/achievements", headers=user_headers)

    assert response.status_code == 200
    badges = response.json()
    assert [b["title"] for b in badges] == SEEDED_TITLES
    assert all(b["earned"] is False and b["earned_at"] is None for b in badges)
    assert "Cache-Control" not in response.headers  # personal: never cached


def test_earned_badges_are_unlocked_with_their_date(
    client: TestClient, db: Session, user_headers, app_user: User
):
    earn(db, app_user, "First Scan")

    badges = {b["title"]: b for b in client.get("/me/achievements", headers=user_headers).json()}

    assert badges["First Scan"]["earned"] is True
    assert badges["First Scan"]["earned_at"] is not None
    assert badges["3-Day Streak"]["earned"] is False


def test_badges_of_other_users_are_not_shown(
    client: TestClient, db: Session, user_headers, app_user: User
):
    other = User(
        full_name="Other",
        email="other@example.com",
        password_hash="x",
        email_verified=True,
        profile=UserProfile(),
    )
    db.add(other)
    db.flush()
    earn(db, other, "First Scan")
    other_headers = {"Authorization": f"Bearer {create_access_token(other.id, 'user')}"}

    mine = client.get("/me/achievements", headers=user_headers).json()
    theirs = client.get("/me/achievements", headers=other_headers).json()

    assert not any(b["earned"] for b in mine)
    assert [b["title"] for b in theirs if b["earned"]] == ["First Scan"]


def test_my_achievements_require_login(client: TestClient):
    assert client.get("/me/achievements").status_code == 401

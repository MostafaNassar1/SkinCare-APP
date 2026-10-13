import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from app.services.skin_quiz_service import QUESTIONS, QUIZ_VERSION

# a complete set of answers; each test changes only what it needs
NORMAL = {
    "after_washing": "comfortable",
    "midday_shine": "none",
    "flaking": "rarely",
    "pores": "barely",
    "reactions": "never",
    "sun": "type_3",
    "pregnancy": "no",
}


def submit(client: TestClient, headers: dict, **changes):
    return client.post("/me/skin-quiz", headers=headers, json={"answers": NORMAL | changes})


# ---------- The questions ----------


def test_quiz_lists_seven_questions_without_login(client: TestClient):
    response = client.get("/skin-quiz")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == QUIZ_VERSION
    assert [q["id"] for q in body["questions"]] == [
        "after_washing", "midday_shine", "flaking", "pores", "reactions", "sun", "pregnancy",
    ]  # fmt: skip
    sun = next(q for q in body["questions"] if q["id"] == "sun")
    assert len(sun["options"]) == 6  # one per Fitzpatrick type


def test_scoring_weights_are_not_sent_to_the_app(client: TestClient):
    option = client.get("/skin-quiz").json()["questions"][0]["options"][0]
    assert option.keys() == {"id", "label"}


def test_option_ids_are_unique_within_each_question():
    for question in QUESTIONS:
        ids = [option.id for option in question.options]
        assert len(ids) == len(set(ids)), question.id


# ---------- Skin type rules, as typical people ----------


@pytest.mark.parametrize(
    ("answers", "skin_type"),
    [
        # shiny all day, open pores everywhere
        (
            {"after_washing": "all_shiny", "midday_shine": "everywhere",
             "pores": "nose_and_cheeks"},
            "oily",
        ),
        # tight after washing, never shiny, flaky
        ({"after_washing": "tight", "midday_shine": "none", "flaking": "often"}, "dry"),
        # oily T-zone only, rest comfortable
        (
            {"after_washing": "t_zone_shiny", "midday_shine": "t_zone", "pores": "nose"},
            "combination",
        ),
        # oily T-zone with flaky cheeks: still combination
        (
            {"after_washing": "t_zone_shiny", "midday_shine": "t_zone", "flaking": "often",
             "pores": "nose"},
            "combination",
        ),
        # nothing stands out
        ({}, "normal"),
        # frequent reactions decide over everything else (safety first)
        (
            {"reactions": "often", "after_washing": "all_shiny", "midday_shine": "everywhere",
             "pores": "nose_and_cheeks"},
            "sensitive",
        ),
        # occasional reactions do not make skin "sensitive"
        ({"reactions": "sometimes"}, "normal"),
    ],
)  # fmt: skip
def test_skin_type(client: TestClient, user_headers, answers, skin_type):
    response = submit(client, user_headers, **answers)

    assert response.status_code == 200
    assert response.json()["skin_type"] == skin_type


@pytest.mark.parametrize("fitzpatrick", [1, 2, 3, 4, 5, 6])
def test_sun_answer_gives_the_fitzpatrick_type(client: TestClient, user_headers, fitzpatrick):
    body = submit(client, user_headers, sun=f"type_{fitzpatrick}").json()
    assert body["fitzpatrick_scale"] == fitzpatrick


def test_scores_are_shown(client: TestClient, user_headers):
    body = submit(client, user_headers, after_washing="tight", flaking="often").json()
    assert (body["oil_score"], body["dry_score"]) == (0, 5)


# ---------- Saving ----------


def test_result_and_answers_are_saved(
    client: TestClient, db: Session, user_headers, app_user: User
):
    submit(client, user_headers, after_washing="tight", midday_shine="none", flaking="often")

    profile = db.get(User, app_user.id).profile
    db.refresh(profile)
    assert profile.skin_type == "dry"
    assert profile.fitzpatrick_scale == 3
    assert profile.skin_quiz_completed_at is not None
    assert profile.skin_quiz_answers["version"] == QUIZ_VERSION
    assert profile.skin_quiz_answers["answers"]["flaking"] == "often"
    skin = client.get("/me/profile", headers=user_headers).json()["skin"]
    assert skin["skin_type"] == "dry"


def test_retaking_the_quiz_replaces_the_result(client: TestClient, user_headers):
    submit(client, user_headers, after_washing="tight", flaking="often", midday_shine="none")
    body = submit(client, user_headers, after_washing="all_shiny", midday_shine="everywhere",
                  pores="nose_and_cheeks").json()  # fmt: skip

    assert body["skin_type"] == "oily"


# ---------- Pregnancy question ----------


def test_yes_and_no_set_the_pregnancy_flag(client: TestClient, user_headers):
    assert submit(client, user_headers, pregnancy="yes").json()["is_pregnant_or_breastfeeding"]
    assert not submit(client, user_headers, pregnancy="no").json()["is_pregnant_or_breastfeeding"]


@pytest.mark.parametrize("before", [True, False])
def test_prefer_not_to_say_leaves_the_flag_unchanged(client: TestClient, user_headers, before):
    client.patch("/me/profile", headers=user_headers, json={"is_pregnant_or_breastfeeding": before})

    body = submit(client, user_headers, pregnancy="prefer_not").json()

    assert body["is_pregnant_or_breastfeeding"] is before


# ---------- Invalid answers ----------


def error_fields(response) -> set[str]:
    assert response.status_code == 422
    return {detail["field"] for detail in response.json()["error"]["details"]}


def test_missing_answers_are_listed(client: TestClient, user_headers):
    answers = {key: value for key, value in NORMAL.items() if key not in {"sun", "pores"}}
    response = client.post("/me/skin-quiz", headers=user_headers, json={"answers": answers})

    assert error_fields(response) == {"answers.sun", "answers.pores"}


def test_option_of_another_question_is_rejected(client: TestClient, user_headers):
    assert error_fields(submit(client, user_headers, flaking="type_3")) == {"answers.flaking"}


def test_unknown_question_is_rejected(client: TestClient, user_headers):
    assert error_fields(submit(client, user_headers, favourite_colour="blue")) == {
        "answers.favourite_colour"
    }


def test_invalid_answers_save_nothing(client: TestClient, user_headers):
    submit(client, user_headers, sun="type_9")
    assert client.get("/me/profile", headers=user_headers).json()["skin"]["skin_type"] is None


def test_submitting_requires_login(client: TestClient):
    assert client.post("/me/skin-quiz", json={"answers": NORMAL}).status_code == 401

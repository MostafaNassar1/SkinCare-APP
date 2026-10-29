"""GET /me/recommendations, PUT /me/routine and "I have it now"."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ingredient, Product, UserAllergy
from tests.recommendations.conftest import add_scan


def get_recommendations(client: TestClient, headers: dict) -> dict:
    response = client.get("/me/recommendations", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def top_picks(recommendations: dict, **overrides: dict) -> list[dict]:
    """The body of PUT /me/routine choosing every Top pick; overrides by step title."""
    steps = []
    for step in recommendations["steps"]:
        choice = {"time_of_day": step["time_of_day"], "mapping_id": step["mapping_id"],
                  "product_id": step["products"][0]["id"] if step["products"] else None}  # fmt: skip
        key = step["title"].replace(" ", "_").replace("-", "_").lower()
        choice |= overrides.get(key, {})
        steps.append(choice)
    return steps


def save(client: TestClient, headers: dict, steps: list[dict]):
    return client.put("/me/routine", headers=headers, json={"steps": steps})


def product_id(db: Session, name: str) -> int:
    return db.scalar(select(Product.id).where(Product.name == name))


def ingredient_id(db: Session, name: str) -> int:
    return db.scalar(select(Ingredient.id).where(Ingredient.name == name))


def test_recommendations_need_a_login(client: TestClient):
    assert client.get("/me/recommendations").status_code == 401
    assert client.put("/me/routine", json={"steps": []}).status_code == 401


# ---------- GET /me/recommendations ----------


def test_recommendations_show_real_products_and_where_to_buy(
    client: TestClient, db: Session, app_user, user_headers
):
    add_scan(db, app_user, acne="mild")
    app_user.profile.skin_type = "oily"
    db.flush()

    body = get_recommendations(client, user_headers)

    assert [(c["name"], c["display_name"], c["severity"]) for c in body["concerns"]] == [
        ("acne", "Acne", "mild"),
        ("oiliness", "Oiliness", "mild"),
    ]
    acne = body["concerns"][0]
    assert acne["about"] and acne["routine_focus"] and acne["expect"] and acne["advice"] is None
    serum = next(s for s in body["steps"] if s["title"] == "Oil Control Serum")
    assert serum["concerns"] == ["oiliness"] and serum["days"] == [
        "mon", "tue", "wed", "thu", "fri", "sat", "sun"
    ]  # fmt: skip
    product = serum["products"][0]
    assert product["brand"] == "COSRX" and product["top_pick"] is True
    assert product["key_ingredients"] == ["Niacinamide 15%"]
    assert product["where_to_buy"] == {
        "label": "Available in pharmacies",
        "nearby_pharmacies_path": "/places/nearby?type=pharmacies",
    }
    assert "image_url" in product and product["directions"]
    treatment = next(s for s in body["steps"] if s["title"] == "Acne Treatment")
    assert [p["top_pick"] for p in treatment["products"]] == [True, False, False, False]
    assert body["disclaimer"] and body["skipped"] == [] and body["see_dermatologist"] == []


def test_recommendations_never_name_a_shop(client: TestClient, db: Session, app_user, user_headers):
    add_scan(db, app_user, acne="mild", wrinkles="mild", dark_spots="moderate", dryness="mild")

    text = json.dumps(get_recommendations(client, user_headers)).lower()

    assert not any(shop in text for shop in ("mazen", "drugstore", "skinsociety", "everyoung"))
    assert "source_url" not in text and "image_source_url" not in text


def test_skipped_steps_and_the_referral_are_explained(
    client: TestClient, db: Session, app_user, user_headers
):
    add_scan(db, app_user, wrinkles="mild", acne="severe")
    app_user.profile.is_pregnant_or_breastfeeding = True
    db.flush()

    body = get_recommendations(client, user_headers)

    assert body["see_dermatologist"] == ["acne"]
    assert body["skipped"] == [
        {
            "time_of_day": "evening",
            "title": "Anti-Aging Treatment",
            "concerns": ["wrinkles"],
            "reason": "pregnancy",
            "message": "Not advised during pregnancy or breastfeeding, so this step is left out.",
        }
    ]


# ---------- PUT /me/routine ----------


def test_saving_the_top_picks_shows_the_products_on_the_routine(
    client: TestClient, db: Session, app_user, user_headers
):
    add_scan(db, app_user, acne="mild")
    steps = top_picks(get_recommendations(client, user_headers))

    response = save(client, user_headers, steps)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["warnings"] == []
    evening = {s["title"]: s for s in body["day"]["evening"]}
    assert evening["Acne Treatment"]["product"]["name"] == "Effaclar Duo+M"
    where = evening["Acne Treatment"]["product"]["where_to_buy"]
    assert where["label"] == "Available in pharmacies"
    assert evening["Acne Treatment"]["own_product_name"] is None
    # the routine screen shows the same thing afterwards
    day = client.get("/me/routine", headers=user_headers).json()
    assert day["evening"] == body["day"]["evening"]


def test_own_product_warnings(client: TestClient, db: Session, app_user, user_headers):
    add_scan(db, app_user, acne="mild")
    db.add(UserAllergy(user_id=app_user.id, ingredient_id=ingredient_id(db, "Propylene Glycol")))
    db.flush()
    own = {"product_id": None,
           "own_product": {"name": "  My Acne Gel ",
                           "ingredient_ids": [ingredient_id(db, "Propylene Glycol")]}}  # fmt: skip
    steps = top_picks(get_recommendations(client, user_headers), acne_treatment=own)

    body = save(client, user_headers, steps).json()

    assert body["warnings"] == [
        {
            "step_title": "Acne Treatment",
            "ingredient": "Propylene Glycol",
            "reason": "allergy",
            "message": "You told us you are allergic to Propylene Glycol.",
        }
    ]
    evening = {s["title"]: s for s in body["day"]["evening"]}
    assert evening["Acne Treatment"]["own_product_name"] == "My Acne Gel"
    assert evening["Acne Treatment"]["product"] is None


def test_clashing_choices_are_explained(client: TestClient, db: Session, app_user, user_headers):
    add_scan(db, app_user, acne="mild", wrinkles="mild")
    steps = top_picks(
        get_recommendations(client, user_headers),
        acne_treatment={"product_id": product_id(db, "Blemish Control Gel"),
                        "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]},
        anti_aging_treatment={"days": ["mon", "wed", "fri"]},
    )  # fmt: skip

    response = save(client, user_headers, steps)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "steps_conflict"
    assert set(error["details"]["steps"]) == {"Acne Treatment", "Anti-Aging Treatment"}


def test_chosen_days_are_saved(client: TestClient, db: Session, app_user, user_headers):
    add_scan(db, app_user, wrinkles="mild")
    steps = top_picks(get_recommendations(client, user_headers),
                      anti_aging_treatment={"days": ["tue", "sat"]})  # fmt: skip

    body = save(client, user_headers, steps).json()

    evening = {s["title"]: s for s in body["day"]["evening"]}
    assert evening["Anti-Aging Treatment"]["days"] == ["tue", "sat"]


@pytest.mark.parametrize(
    ("change", "status", "code"),
    [("both_products", 422, "validation_error"), ("unknown_day", 422, "validation_error"),
     ("extra_field", 422, "validation_error"), ("unknown_step", 422, "unknown_step"),
     ("no_steps", 422, "empty_routine")],
)  # fmt: skip
def test_invalid_routines_are_refused(client: TestClient, user_headers, change, status, code):
    steps = top_picks(get_recommendations(client, user_headers))
    if change == "both_products":
        steps[0]["own_product"] = {"name": "Mine"}
    elif change == "unknown_day":
        steps[0]["days"] = ["someday"]
    elif change == "extra_field":
        steps[0]["price"] = 3
    elif change == "unknown_step":
        steps[0]["mapping_id"] = 99999
    else:
        steps = []

    response = save(client, user_headers, steps)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code


# ---------- "I don't have it yet" ----------


def test_waiting_for_a_product_then_i_have_it_now(client: TestClient, user_headers):
    steps = top_picks(get_recommendations(client, user_headers), sunscreen={"has_product": False})
    day = save(client, user_headers, steps).json()["day"]
    sunscreen = next(s for s in day["morning"] if s["title"] == "Sunscreen")
    assert sunscreen["needs_product"] is True and sunscreen["scheduled"] is False
    assert day["scheduled_count"] == 4  # the sunscreen is not counted yet

    tick = client.post(f"/me/routine/steps/{sunscreen['id']}/log", headers=user_headers)
    assert tick.status_code == 409 and tick.json()["error"]["code"] == "product_not_ready"

    ready = client.post(f"/me/routine/steps/{sunscreen['id']}/product-ready", headers=user_headers)

    assert ready.status_code == 200
    sunscreen = next(s for s in ready.json()["morning"] if s["title"] == "Sunscreen")
    assert sunscreen["needs_product"] is False and sunscreen["scheduled"] is True
    assert ready.json()["scheduled_count"] == 5
    tick = client.post(f"/me/routine/steps/{sunscreen['id']}/log", headers=user_headers)
    assert tick.status_code == 200


def test_product_ready_only_for_the_users_own_steps(client: TestClient, user_headers):
    response = client.post("/me/routine/steps/99999/product-ready", headers=user_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "step_not_found"

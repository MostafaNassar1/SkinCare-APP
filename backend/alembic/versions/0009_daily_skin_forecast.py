"""Daily skin forecast: richer weather tips and an on/off setting

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-17

- weather_skin_tips.weather_condition: two new conditions, "windy" and "polluted" (the forecast
  also reads wind and air quality from Open-Meteo).
- weather_skin_tips.skin_type (NULL = any skin type): a tip written for the user's own skin type
  (from the skin quiz) wins over a general one.
- weather_skin_tips.priority: breaks ties; the sunscreen tips have the highest one (safety).
- 12 new tips (reference data, like 0002): skin-type versions of the existing conditions and the
  windy / polluted tips. The thresholds that decide the conditions are in
  app/services/skin_forecast_service.py (facts about the weather, not editable content).
- user_profiles.daily_forecast_enabled (default on): the 11:00 push can be switched off.

Written by hand after `alembic revision --autogenerate`: autogenerate does not see CHECK
constraints, so the condition check is replaced and the skin_type check added explicitly.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_CONDITIONS = "'hot', 'cold', 'humid', 'dry', 'high_uv'"
NEW_CONDITIONS = OLD_CONDITIONS + ", 'windy', 'polluted'"
SKIN_TYPES = "'oily', 'dry', 'combination', 'normal', 'sensitive'"

# (condition, skin type or None, related concern or None, priority, tip)
NEW_TIPS = [
    ("humid", "oily", "oiliness", 2,
     "Humid air makes oily skin feel greasier by midday: blot instead of washing again, and "
     "choose a light gel moisturizer."),
    ("humid", "combination", "oiliness", 2,
     "Humid air adds shine to your T-zone: use a light gel there and keep your usual "
     "moisturizer on the cheeks."),
    ("hot", "oily", "oiliness", 2,
     "Heat boosts oil production: an oil-free gel moisturizer and blotting papers will keep "
     "your skin comfortable."),
    ("hot", "sensitive", "redness", 2,
     "Heat can bring on redness: rinse with cool water and avoid strong exfoliants today."),
    ("dry", "dry", "dryness", 2,
     "Very dry air pulls water from dry skin: apply moisturizer on slightly damp skin and "
     "consider a hydrating serum (e.g. hyaluronic acid)."),
    ("cold", "sensitive", "redness", 2,
     "Cold air can make sensitive skin sting: wash with lukewarm (not hot) water and use a "
     "fragrance-free barrier cream."),
    ("cold", "dry", "dryness", 2,
     "Cold weather dries your skin even more: switch to a richer cream and keep showers short "
     "and warm, not hot."),
    ("high_uv", "sensitive", "redness", 3,
     "Strong UV can trigger redness on sensitive skin: a mineral sunscreen (zinc oxide) is "
     "usually gentler. Reapply every 2 hours outdoors."),
    ("windy", None, "dryness", 1,
     "Strong wind dries and chaps the skin: a slightly richer moisturizer and a lip balm will "
     "protect it today."),
    ("windy", "sensitive", "redness", 2,
     "Wind can irritate sensitive skin: cover up with a scarf outdoors and use a fragrance-free "
     "barrier cream."),
    ("polluted", None, None, 2,
     "Air quality is poor today: cleanse thoroughly tonight to remove pollution particles from "
     "your skin."),
    ("polluted", None, "dark_spots", 2,
     "Pollution and sun together can deepen dark spots: an antioxidant serum (vitamin C) in "
     "the morning, under sunscreen, can help."),
]  # fmt: skip


def upgrade() -> None:
    op.drop_constraint(
        op.f("weather_skin_tips_weather_condition_check"), "weather_skin_tips", type_="check"
    )
    op.create_check_constraint(
        op.f("weather_skin_tips_weather_condition_check"),
        "weather_skin_tips",
        f"weather_condition IN ({NEW_CONDITIONS})",
    )
    op.add_column("weather_skin_tips", sa.Column("skin_type", sa.String(20), nullable=True))
    op.create_check_constraint(
        op.f("weather_skin_tips_skin_type_check"),
        "weather_skin_tips",
        f"skin_type IN ({SKIN_TYPES})",
    )
    op.add_column(
        "weather_skin_tips",
        sa.Column("priority", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "daily_forecast_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )

    # existing tips: sunscreen first (safety), the others above the default
    op.execute(
        "UPDATE weather_skin_tips SET priority = "
        "CASE WHEN weather_condition = 'high_uv' THEN 3 ELSE 1 END"
    )
    insert = sa.text(
        "INSERT INTO weather_skin_tips "
        "(weather_condition, skin_type, related_skin_concern_id, priority, tip_text) "
        "VALUES (:condition, :skin_type, "
        "(SELECT id FROM skin_concerns WHERE name = :concern), :priority, :tip)"
    )
    for condition, skin_type, concern, priority, tip in NEW_TIPS:
        op.get_bind().execute(
            insert,
            {
                "condition": condition,
                "skin_type": skin_type,
                "concern": concern,
                "priority": priority,
                "tip": tip,
            },
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM weather_skin_tips "
        "WHERE skin_type IS NOT NULL OR weather_condition IN ('windy', 'polluted')"
    )
    op.drop_column("user_profiles", "daily_forecast_enabled")
    op.drop_column("weather_skin_tips", "priority")
    op.drop_constraint(
        op.f("weather_skin_tips_skin_type_check"), "weather_skin_tips", type_="check"
    )
    op.drop_column("weather_skin_tips", "skin_type")
    op.drop_constraint(
        op.f("weather_skin_tips_weather_condition_check"), "weather_skin_tips", type_="check"
    )
    op.create_check_constraint(
        op.f("weather_skin_tips_weather_condition_check"),
        "weather_skin_tips",
        f"weather_condition IN ({OLD_CONDITIONS})",
    )

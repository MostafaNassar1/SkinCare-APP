# Allowed values of the VARCHAR columns that have a CHECK constraint in the database.
# Defined once here, used by the models' CHECK constraints and later by the API schemas.

AUTH_PROVIDERS = ("email", "google")
GENDERS = ("male", "female", "other", "prefer_not_to_say")
SKIN_TYPES = ("oily", "dry", "combination", "normal", "sensitive")

# ordered from least to most severe (the rules engine compares positions)
SEVERITIES = ("mild", "moderate", "severe")
DETECTION_METHODS = ("photo", "hybrid")  # hybrid = photo + skin quiz
DETECTION_SOURCES = ("photo", "questionnaire", "photo_and_questionnaire")

# ordered as the steps appear in a routine
STEP_CATEGORIES = ("cleanse", "treat", "moisturize", "protect")
RULE_TIMES_OF_DAY = ("morning", "evening", "both")  # 'both' is expanded into two steps
STEP_TIMES_OF_DAY = ("morning", "evening")

ACHIEVEMENT_CRITERIA = ("streak_days", "scans_completed", "routine_adherence")

CLINIC_SOURCES = ("osm_import", "admin_added")
# exact OpenStreetMap type of a place on the map (migration 0006); the API groups the first three
# as "clinics" and the last as "pharmacies"
PLACE_CATEGORIES = ("clinic", "doctor", "hospital", "pharmacy")
ADMIN_ROLES = ("super_admin", "moderator", "clinic_manager")
# "scheduled" (migration 0007): a real appointment the user booked by phone and recorded in the
# app (no in-app booking). pending/accepted/rejected are kept for possible future partner clinics.
APPOINTMENT_STATUSES = ("scheduled", "pending", "accepted", "rejected", "completed", "cancelled")
CALENDAR_EVENT_TYPES = ("routine_reminder", "appointment", "custom")

NOTIFICATION_TYPES = ("reminder", "weather_alert", "achievement", "appointment_update")
DEVICE_PLATFORMS = ("android", "ios")

EMAIL_TOKEN_PURPOSES = ("password_reset", "email_verification")
REPORT_TYPES = ("user_activity", "scan_trends", "appointments", "achievement_engagement")
# windy and polluted added in migration 0009 (daily skin forecast)
WEATHER_CONDITIONS = ("hot", "cold", "humid", "dry", "high_uv", "windy", "polluted")

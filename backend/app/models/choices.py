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
ADMIN_ROLES = ("super_admin", "moderator", "clinic_manager")
APPOINTMENT_STATUSES = ("pending", "accepted", "rejected", "completed", "cancelled")
CALENDAR_EVENT_TYPES = ("routine_reminder", "appointment", "custom")

NOTIFICATION_TYPES = ("reminder", "weather_alert", "achievement", "appointment_update")
DEVICE_PLATFORMS = ("android", "ios")

EMAIL_TOKEN_PURPOSES = ("password_reset", "email_verification")
REPORT_TYPES = ("user_activity", "scan_trends", "appointments", "achievement_engagement")
WEATHER_CONDITIONS = ("hot", "cold", "humid", "dry", "high_uv")

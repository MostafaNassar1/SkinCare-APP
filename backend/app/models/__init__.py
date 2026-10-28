# Importing every model here registers all 30 tables on Base.metadata,
# which Alembic needs to compare the models with the database.
from app.models.achievement import Achievement, UserAchievement
from app.models.admin import Admin
from app.models.appointment import Appointment, CalendarEvent
from app.models.audit import AuditLog, ReportTemplate
from app.models.auth_token import EmailToken, RefreshToken
from app.models.clinic import Clinic, Doctor
from app.models.ingredient import Ingredient, IngredientConflict, UserAllergy
from app.models.notification import Notification, UserDevice
from app.models.product import Product, ProductIngredient, RoutineStepProduct, RuleProduct
from app.models.routine import ConcernRecommendationMapping, Routine, RoutineLog, RoutineStep
from app.models.scan import ScanResult, ScanResultConcern, SkinConcern
from app.models.user import User, UserProfile
from app.models.weather import WeatherSkinTip

__all__ = [
    "Achievement",
    "Admin",
    "Appointment",
    "AuditLog",
    "CalendarEvent",
    "Clinic",
    "ConcernRecommendationMapping",
    "Doctor",
    "EmailToken",
    "Ingredient",
    "IngredientConflict",
    "Notification",
    "Product",
    "ProductIngredient",
    "RefreshToken",
    "ReportTemplate",
    "Routine",
    "RoutineLog",
    "RoutineStep",
    "RoutineStepProduct",
    "RuleProduct",
    "ScanResult",
    "ScanResultConcern",
    "SkinConcern",
    "User",
    "UserAchievement",
    "UserAllergy",
    "UserDevice",
    "UserProfile",
    "WeatherSkinTip",
]

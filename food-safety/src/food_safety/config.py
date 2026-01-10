"""Configuration settings for Food Safety Service"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://food_safety:food_safety_password@food-safety-postgres:5432/food_safety"
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql://food_safety:food_safety_password@food-safety-postgres:5432/food_safety"
    )

    # Service URLs for cross-service communication
    HR_SERVICE_URL: str = os.getenv("HR_SERVICE_URL", "http://hr-app:8000")
    INVENTORY_SERVICE_URL: str = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-app:8000")
    PORTAL_SERVICE_URL: str = os.getenv("PORTAL_SERVICE_URL", "http://portal-app:8000")
    MAINTENANCE_SERVICE_URL: str = os.getenv("MAINTENANCE_SERVICE_URL", "http://maintenance-service:8000")

    # Application settings
    APP_NAME: str = "Food Safety & Compliance Service"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Alert settings
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    ALERT_EMAIL_FROM: str = os.getenv("ALERT_EMAIL_FROM", "foodsafety@swhgrp.com")
    ALERT_EMAIL_TO: str = os.getenv("ALERT_EMAIL_TO", "")

    # JWT settings (for portal SSO)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "food-safety-secret-key-change-in-production")
    PORTAL_SECRET_KEY: str = os.getenv("PORTAL_SECRET_KEY", "")
    ALGORITHM: str = "HS256"

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


settings = get_settings()

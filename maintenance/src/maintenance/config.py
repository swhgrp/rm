"""Configuration settings for Maintenance Service"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://maintenance_user:maintenance_password@maintenance-db:5432/maintenance_db"
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql://maintenance_user:maintenance_password@maintenance-db:5432/maintenance_db"
    )

    # Service URLs for cross-service communication
    INVENTORY_SERVICE_URL: str = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-app:8000")
    HR_SERVICE_URL: str = os.getenv("HR_SERVICE_URL", "http://hr-app:8000")
    HUB_SERVICE_URL: str = os.getenv("HUB_SERVICE_URL", "http://integration-hub:8000")
    FILES_SERVICE_URL: str = os.getenv("FILES_SERVICE_URL", "http://files-app:8000")
    PORTAL_SERVICE_URL: str = os.getenv("PORTAL_SERVICE_URL", "http://portal-app:8000")

    # Application settings
    APP_NAME: str = "Maintenance Service"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Base URL for QR codes
    BASE_URL: str = os.getenv("BASE_URL", "https://rm.swhgrp.com")

    # JWT settings (for portal SSO)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "maintenance-secret-key-change-in-production")
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

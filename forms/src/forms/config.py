"""Configuration settings for Forms Service"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://forms_user:forms_password@forms-db:5432/forms_db"
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC",
        "postgresql://forms_user:forms_password@forms-db:5432/forms_db"
    )

    # Service URLs for cross-service communication
    PORTAL_SERVICE_URL: str = os.getenv("PORTAL_SERVICE_URL", "http://portal-app:8000")
    HR_SERVICE_URL: str = os.getenv("HR_SERVICE_URL", "http://hr-app:8000")
    FILES_SERVICE_URL: str = os.getenv("FILES_SERVICE_URL", "http://files-app:8000")

    # Application settings
    APP_NAME: str = "Forms Service"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Base URL for links in emails/PDFs
    BASE_URL: str = os.getenv("BASE_URL", "https://rm.swhgrp.com")

    # JWT settings (for portal SSO)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "forms-secret-key-change-in-production")
    PORTAL_SECRET_KEY: str = os.getenv("PORTAL_SECRET_KEY", "")
    ALGORITHM: str = "HS256"

    # File upload settings
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", "10485760"))  # 10MB
    ALLOWED_EXTENSIONS: str = os.getenv("ALLOWED_EXTENSIONS", "pdf,png,jpg,jpeg,doc,docx")

    # Email settings (for notifications)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "forms@swhgrp.com")

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


settings = get_settings()

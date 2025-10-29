"""
Nextcloud service configuration
"""
import os
from typing import List


class Settings:
    """Application settings"""

    # App Info
    APP_NAME: str = os.getenv("APP_NAME", "Nextcloud Integration")
    APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-super-secret-key-change-in-production")
    PORTAL_SECRET_KEY: str = os.getenv("PORTAL_SECRET_KEY", "your-super-secret-key-change-in-production")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://nextcloud_user:nextcloud_pass@nextcloud-db:5432/nextcloud_db"
    )

    # Nextcloud Configuration
    NEXTCLOUD_URL: str = os.getenv("NEXTCLOUD_URL", "https://cloud.swhgrp.com")
    NEXTCLOUD_WEBDAV_PATH: str = os.getenv("NEXTCLOUD_WEBDAV_PATH", "/remote.php/dav")
    NEXTCLOUD_CALDAV_PATH: str = os.getenv("NEXTCLOUD_CALDAV_PATH", "/remote.php/dav")

    # Encryption for storing user credentials
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

    # CORS
    ALLOWED_ORIGINS: List[str] = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8000,https://restaurantsystem.swhgrp.com"
    ).split(",")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # HR Database (for user authentication)
    HR_DATABASE_URL: str = os.getenv(
        "HR_DATABASE_URL",
        "postgresql://hr_user:HR_Pr0d_2024!@hr-db:5432/hr_db"
    )


settings = Settings()

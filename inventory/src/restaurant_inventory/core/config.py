"""
Core configuration settings
"""

import os
import secrets
from typing import List

class Settings:
    """Application settings"""
    
    # App Info
    APP_NAME: str = "Restaurant Inventory Management"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379")
    
    # CORS
    ALLOWED_ORIGINS: List[str] = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8000,http://localhost:3000"
    ).split(",")

    # Email Configuration
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.swhgrp.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "admin@swhgrp.com")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "admin@swhgrp.com")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "SW Hospitality Group")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    # Application URL (for email links)
    APP_URL: str = os.getenv("APP_URL", "https://restaurantsystem.swhgrp.com")

    # Password Reset Token
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 24

# Create global settings instance
settings = Settings()

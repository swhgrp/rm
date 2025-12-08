"""
Application configuration
"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://websites_user:websites_pass@websites-db:5432/websites"

    # Security
    secret_key: str = "change-me-in-production"
    portal_sso_secret: str = "shared-sso-secret"

    # Paths
    upload_dir: str = "/app/uploads"
    generated_dir: str = "/app/generated"

    # Image processing
    max_image_size: int = 10 * 1024 * 1024  # 10MB
    image_sizes: dict = {
        "thumb": 150,
        "medium": 600,
        "large": 1200
    }

    # URLs
    base_url: str = "https://rm.swhgrp.com"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()

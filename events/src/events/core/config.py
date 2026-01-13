"""Application configuration"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # HR Integration
    HR_API_URL: str
    HR_API_KEY: str

    # Email
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USER: str
    SMTP_PASSWORD: str
    SMTP_USE_TLS: bool = True
    FROM_EMAIL: str
    FROM_NAME: str

    # Storage
    S3_ENDPOINT: str
    S3_BUCKET: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_REGION: str = "us-east-1"

    # hCaptcha
    HCAPTCHA_SECRET: str
    HCAPTCHA_SITEKEY: str

    # CalDAV
    CALDAV_URL: Optional[str] = "http://caldav:5232"
    CALDAV_ENABLED: bool = False

    # Application
    APP_NAME: str = "SW Hospitality Events"
    APP_URL: str
    ENVIRONMENT: str = "production"
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

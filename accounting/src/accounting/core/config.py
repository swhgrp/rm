"""
Configuration settings for accounting service
"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Union


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Restaurant Accounting System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str

    # Integration with Inventory
    INVENTORY_API_URL: str
    INVENTORY_API_KEY: str

    # Feature Flags
    ACCOUNTING_ENABLED: bool = True
    AUTO_SYNC_ENABLED: bool = True
    SYNC_INTERVAL_MINUTES: int = 15

    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS
    ALLOWED_ORIGINS: Union[List[str], str] = []

    @field_validator('ALLOWED_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(',')]
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

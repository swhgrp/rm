"""Portal configuration"""
import os

# HR Database connection (for user authentication)
HR_DATABASE_URL = os.getenv(
    "HR_DATABASE_URL",
    "postgresql://hr_user:hr_password@hr-db:5432/hr_db"
)

# Session secret key
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
SESSION_COOKIE_NAME = "portal_session"
SESSION_EXPIRE_MINUTES = 30  # 30 minutes inactivity timeout

# System URLs (for token validation endpoints)
INVENTORY_API_URL = os.getenv("INVENTORY_API_URL", "http://inventory-app:8000")
ACCOUNTING_API_URL = os.getenv("ACCOUNTING_API_URL", "http://accounting-app:8000")
HR_API_URL = os.getenv("HR_API_URL", "http://hr-app:8000")
INTEGRATION_HUB_URL = os.getenv("INTEGRATION_HUB_URL", "http://integration-hub:8000")

# Mailcow API configuration
MAILCOW_API_URL = os.getenv("MAILCOW_API_URL", "https://mail-nginx-mailcow-1:8843")
MAILCOW_API_KEY = os.getenv("MAILCOW_API_KEY", "")
MAIL_DOMAIN = os.getenv("MAIL_DOMAIN", "swhgrp.com")

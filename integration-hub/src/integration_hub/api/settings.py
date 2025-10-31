"""
Settings API endpoints for system configuration
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from pydantic import BaseModel
from integration_hub.db.database import get_db
from integration_hub.models.system_setting import SystemSetting
from integration_hub.core.auth import require_auth
import imaplib
import ssl

router = APIRouter()


class SettingUpdate(BaseModel):
    """Model for updating a single setting"""
    category: str
    key: str
    value: Optional[str] = None
    is_encrypted: bool = False


class BulkSettingsUpdate(BaseModel):
    """Model for bulk settings update"""
    settings: List[SettingUpdate]


class EmailTestRequest(BaseModel):
    """Model for testing email connection"""
    email: str
    password: str
    imap_server: str
    imap_port: int
    use_ssl: bool


@router.get("/")
def get_settings(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    """
    Get all settings or filter by category
    """
    query = db.query(SystemSetting).filter(SystemSetting.is_active == True)

    if category:
        query = query.filter(SystemSetting.category == category)

    settings = query.all()

    # Convert to dict format for frontend
    result = {}
    for setting in settings:
        key = f"{setting.category}.{setting.key}"
        result[key] = {
            "value": setting.value,
            "is_encrypted": setting.is_encrypted,
            "description": setting.description
        }

    return result


@router.post("/bulk")
def save_settings(
    bulk_update: BulkSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    """
    Save multiple settings at once
    """
    updated_count = 0
    created_count = 0

    for setting_data in bulk_update.settings:
        # Check if setting exists
        existing = db.query(SystemSetting).filter(
            SystemSetting.category == setting_data.category,
            SystemSetting.key == setting_data.key
        ).first()

        if existing:
            # Update existing setting
            existing.value = setting_data.value
            existing.is_encrypted = setting_data.is_encrypted
            existing.updated_by = current_user.get("user_id")
            updated_count += 1
        else:
            # Create new setting
            new_setting = SystemSetting(
                category=setting_data.category,
                key=setting_data.key,
                value=setting_data.value,
                is_encrypted=setting_data.is_encrypted,
                updated_by=current_user.get("user_id")
            )
            db.add(new_setting)
            created_count += 1

    db.commit()

    return {
        "success": True,
        "updated": updated_count,
        "created": created_count,
        "total": updated_count + created_count
    }


@router.post("/test-email")
def test_email_connection(
    test_request: EmailTestRequest,
    current_user: dict = Depends(require_auth)
):
    """
    Test IMAP email connection with provided credentials
    """
    try:
        # Create SSL context
        if test_request.use_ssl:
            context = ssl.create_default_context()
            mail = imaplib.IMAP4_SSL(
                test_request.imap_server,
                test_request.imap_port,
                ssl_context=context
            )
        else:
            mail = imaplib.IMAP4(
                test_request.imap_server,
                test_request.imap_port
            )

        # Attempt login
        mail.login(test_request.email, test_request.password)

        # Try to select INBOX to verify full access
        status, messages = mail.select("INBOX")

        if status != "OK":
            raise Exception("Could not access INBOX")

        # Get mailbox info
        message_count = int(messages[0])

        # Logout
        mail.logout()

        return {
            "success": True,
            "message": f"Connection successful! Found {message_count} messages in INBOX.",
            "details": {
                "server": test_request.imap_server,
                "port": test_request.imap_port,
                "ssl": test_request.use_ssl,
                "inbox_count": message_count
            }
        }

    except imaplib.IMAP4.error as e:
        return {
            "success": False,
            "message": f"IMAP error: {str(e)}",
            "error_type": "authentication"
        }

    except ssl.SSLError as e:
        return {
            "success": False,
            "message": f"SSL error: {str(e)}",
            "error_type": "ssl"
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}",
            "error_type": "connection"
        }

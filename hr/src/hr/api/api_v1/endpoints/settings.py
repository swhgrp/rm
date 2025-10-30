"""
System Settings API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from hr.db.database import get_db
from hr.models.settings import SystemSettings
from hr.models.user import User
from hr.api.auth import require_auth
from hr.core.encryption import encrypt_value, decrypt_value
from pydantic import BaseModel
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class SettingCreate(BaseModel):
    category: str
    key: str
    value: Optional[str] = None
    is_encrypted: bool = False
    description: Optional[str] = None


class SettingUpdate(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None


class SettingResponse(BaseModel):
    id: int
    category: str
    key: str
    value: Optional[str]
    is_encrypted: bool
    description: Optional[str]

    class Config:
        from_attributes = True


class TestEmailRequest(BaseModel):
    test_email: str


def require_admin_user(current_user: User = Depends(require_auth)):
    """Require admin access for settings operations"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Admin access required to modify settings"
        )
    return current_user


@router.get("/smtp", response_model=List[SettingResponse])
def get_smtp_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user)
):
    """Get SMTP settings (admin only)"""
    settings = db.query(SystemSettings).filter(
        SystemSettings.category == "smtp"
    ).all()
    
    # Decrypt encrypted values for display
    result = []
    for setting in settings:
        setting_dict = {
            "id": setting.id,
            "category": setting.category,
            "key": setting.key,
            "value": decrypt_value(setting.value) if setting.is_encrypted and setting.value else setting.value,
            "is_encrypted": setting.is_encrypted,
            "description": setting.description
        }
        result.append(setting_dict)
    
    return result


@router.post("/smtp", response_model=SettingResponse)
def create_smtp_setting(
    setting: SettingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user)
):
    """Create a new SMTP setting (admin only)"""
    # Check if setting already exists
    existing = db.query(SystemSettings).filter(
        SystemSettings.key == setting.key
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail=f"Setting {setting.key} already exists")
    
    # Encrypt value if needed
    value_to_store = setting.value
    if setting.is_encrypted and setting.value:
        value_to_store = encrypt_value(setting.value)
    
    db_setting = SystemSettings(
        category=setting.category,
        key=setting.key,
        value=value_to_store,
        is_encrypted=setting.is_encrypted,
        description=setting.description
    )
    
    db.add(db_setting)
    db.commit()
    db.refresh(db_setting)
    
    # Return decrypted value
    return {
        "id": db_setting.id,
        "category": db_setting.category,
        "key": db_setting.key,
        "value": setting.value,  # Return original unencrypted value
        "is_encrypted": db_setting.is_encrypted,
        "description": db_setting.description
    }


@router.put("/smtp/{key}", response_model=SettingResponse)
def update_smtp_setting(
    key: str,
    setting_update: SettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user)
):
    """Update an SMTP setting (admin only)"""
    db_setting = db.query(SystemSettings).filter(
        SystemSettings.key == key,
        SystemSettings.category == "smtp"
    ).first()
    
    if not db_setting:
        raise HTTPException(status_code=404, detail=f"Setting {key} not found")
    
    # Update value
    if setting_update.value is not None:
        if db_setting.is_encrypted:
            db_setting.value = encrypt_value(setting_update.value)
        else:
            db_setting.value = setting_update.value
    
    # Update description
    if setting_update.description is not None:
        db_setting.description = setting_update.description
    
    db.commit()
    db.refresh(db_setting)
    
    # Return decrypted value
    return {
        "id": db_setting.id,
        "category": db_setting.category,
        "key": db_setting.key,
        "value": decrypt_value(db_setting.value) if db_setting.is_encrypted and db_setting.value else db_setting.value,
        "is_encrypted": db_setting.is_encrypted,
        "description": db_setting.description
    }


@router.post("/smtp/test")
def test_smtp_connection(
    test_request: TestEmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user)
):
    """Test SMTP connection by sending a test email (admin only)"""
    from hr.services.email import EmailService
    import os
    
    # Get SMTP settings from database
    settings = db.query(SystemSettings).filter(
        SystemSettings.category == "smtp"
    ).all()
    
    if not settings:
        raise HTTPException(status_code=400, detail="SMTP settings not configured")
    
    # Build config dict
    smtp_config = {}
    for setting in settings:
        value = decrypt_value(setting.value) if setting.is_encrypted and setting.value else setting.value
        # Map database keys to expected config keys
        key_name = setting.key.replace("smtp_", "")
        smtp_config[key_name] = value
    
    # Temporarily set environment variables for email service
    original_env = {}
    try:
        env_mappings = {
            'host': 'SMTP_HOST',
            'port': 'SMTP_PORT',
            'user': 'SMTP_USER',
            'password': 'SMTP_PASSWORD',
            'from_name': 'SMTP_FROM_NAME',
            'from_email': 'SMTP_FROM_EMAIL',
            'use_tls': 'SMTP_USE_TLS'
        }
        
        for key, env_var in env_mappings.items():
            if key in smtp_config:
                original_env[env_var] = os.getenv(env_var)
                os.environ[env_var] = str(smtp_config[key])
        
        # Send test email
        subject = "HR System - SMTP Test Email"
        html_content = """
        <html>
        <body>
            <h2>SMTP Configuration Test</h2>
            <p>This is a test email from the SW Hospitality HR System.</p>
            <p>If you received this email, your SMTP configuration is working correctly!</p>
            <hr>
            <p><small>Sent from HR System</small></p>
        </body>
        </html>
        """
        text_content = "SMTP Configuration Test\n\nThis is a test email from the SW Hospitality HR System.\n\nIf you received this email, your SMTP configuration is working correctly!"
        
        success = EmailService.send_email(
            to_email=test_request.test_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )
        
        if success:
            return {"message": f"Test email sent successfully to {test_request.test_email}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send test email. Check logs for details.")
    
    except Exception as e:
        logger.error(f"SMTP test failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"SMTP test failed: {str(e)}")
    
    finally:
        # Restore original environment variables
        for env_var, original_value in original_env.items():
            if original_value is not None:
                os.environ[env_var] = original_value
            elif env_var in os.environ:
                del os.environ[env_var]


@router.post("/smtp/initialize")
def initialize_smtp_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_user)
):
    """Initialize SMTP settings with default values if they don't exist (admin only)"""
    default_settings = [
        {"key": "smtp_host", "value": "mail.swhgrp.com", "is_encrypted": False, "description": "SMTP server hostname"},
        {"key": "smtp_port", "value": "587", "is_encrypted": False, "description": "SMTP server port (587 for TLS)"},
        {"key": "smtp_user", "value": "", "is_encrypted": False, "description": "SMTP username/email"},
        {"key": "smtp_password", "value": "", "is_encrypted": True, "description": "SMTP password"},
        {"key": "smtp_from_name", "value": "SW Hospitality HR", "is_encrypted": False, "description": "Display name for sent emails"},
        {"key": "smtp_from_email", "value": "hr@swhgrp.com", "is_encrypted": False, "description": "From email address"},
        {"key": "smtp_use_tls", "value": "true", "is_encrypted": False, "description": "Use TLS encryption"},
        {"key": "smtp_hr_recipient", "value": "hr@swhgrp.com", "is_encrypted": False, "description": "HR department email for notifications"}
    ]
    
    created = 0
    for setting_data in default_settings:
        existing = db.query(SystemSettings).filter(
            SystemSettings.key == setting_data["key"]
        ).first()
        
        if not existing:
            value_to_store = setting_data["value"]
            if setting_data["is_encrypted"] and value_to_store:
                value_to_store = encrypt_value(value_to_store)
            
            db_setting = SystemSettings(
                category="smtp",
                key=setting_data["key"],
                value=value_to_store,
                is_encrypted=setting_data["is_encrypted"],
                description=setting_data["description"]
            )
            db.add(db_setting)
            created += 1
    
    db.commit()
    return {"message": f"Initialized {created} SMTP settings"}

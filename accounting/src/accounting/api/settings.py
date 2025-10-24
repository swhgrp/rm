"""
System Settings API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from accounting.db.database import get_db
from accounting.models.system_setting import SystemSetting
from accounting.models.user import User
from accounting.api.auth import require_auth
from accounting.core.permissions import require_permission

router = APIRouter()


@router.get("/")
def get_all_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
) -> List[Dict[str, Any]]:
    """Get all system settings"""
    settings = db.query(SystemSetting).all()
    return [
        {
            "id": s.id,
            "setting_key": s.setting_key,
            "setting_value": s.setting_value,
            "setting_type": s.setting_type,
            "description": s.description,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None
        }
        for s in settings
    ]


@router.get("/{setting_key}")
def get_setting(
    setting_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
) -> Dict[str, Any]:
    """Get a specific setting by key"""
    setting = db.query(SystemSetting).filter(
        SystemSetting.setting_key == setting_key
    ).first()

    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting '{setting_key}' not found")

    return {
        "id": setting.id,
        "setting_key": setting.setting_key,
        "setting_value": setting.setting_value,
        "setting_type": setting.setting_type,
        "description": setting.description,
        "updated_at": setting.updated_at.isoformat() if setting.updated_at else None
    }


@router.put("/{setting_key}")
def update_setting(
    setting_key: str,
    update_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
) -> Dict[str, Any]:
    """Update a system setting (requires admin permission)"""
    # Only admins can update settings
    require_permission(current_user, 'settings:edit')

    setting = db.query(SystemSetting).filter(
        SystemSetting.setting_key == setting_key
    ).first()

    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting '{setting_key}' not found")

    # Update setting value
    if 'setting_value' in update_data:
        setting.setting_value = str(update_data['setting_value'])
        setting.updated_by = current_user.id

    db.commit()
    db.refresh(setting)

    return {
        "id": setting.id,
        "setting_key": setting.setting_key,
        "setting_value": setting.setting_value,
        "setting_type": setting.setting_type,
        "description": setting.description,
        "updated_at": setting.updated_at.isoformat() if setting.updated_at else None
    }

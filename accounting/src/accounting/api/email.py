"""
Email API endpoints for testing email configuration
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any
from accounting.db.database import get_db
from accounting.models.user import User
from accounting.api.auth import require_auth
from accounting.services.email_service import EmailService

router = APIRouter()


@router.post("/test-connection")
def test_email_connection(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
) -> Dict[str, Any]:
    """
    Test SMTP connection with current settings

    Returns:
        Dict with success status and message
    """
    try:
        email_service = EmailService(db)
        success = email_service.test_connection()

        if success:
            return {
                "success": True,
                "message": "Email connection test successful"
            }
        else:
            return {
                "success": False,
                "message": "Email connection test failed. Check your settings."
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection test failed: {str(e)}"
        }

"""
Authentication API endpoints for Integration Hub
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from integration_hub.core.portal_sso import validate_portal_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.get("/sso-login")
async def sso_login(token: str):
    """SSO login from Portal"""
    # Validate Portal token
    portal_user = validate_portal_token(token, "hub")

    if not portal_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired Portal token"
        )

    # Integration Hub doesn't require authentication, so just redirect to home
    # In the future, we could store session for audit logging
    return RedirectResponse(url="/hub/", status_code=303)

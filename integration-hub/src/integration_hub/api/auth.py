"""
Authentication API endpoints for Integration Hub
"""
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from integration_hub.core.portal_sso import validate_portal_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Portal URL for redirects
PORTAL_URL = os.getenv("PORTAL_URL", "https://rm.swhgrp.com/portal")


@router.get("/sso-login")
async def sso_login(token: str):
    """SSO login from Portal"""
    # Validate Portal token
    portal_user = validate_portal_token(token, "hub")

    if not portal_user:
        # Token expired or invalid - redirect to Portal login
        # This provides a better UX than showing an error
        return RedirectResponse(
            url=f"{PORTAL_URL}/login?message=session_expired&redirect=/hub/",
            status_code=303
        )

    # Integration Hub doesn't require authentication, so just redirect to home
    # In the future, we could store session for audit logging
    return RedirectResponse(url="/hub/", status_code=303)

"""
Authentication API endpoints for Integration Hub
"""
import os
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from integration_hub.core.portal_sso import validate_portal_token
from jose import jwt

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)

# Portal URL for redirects
PORTAL_URL = os.getenv("PORTAL_URL", "https://rm.swhgrp.com/portal")


@router.get("/sso-login")
async def sso_login(token: str):
    """SSO login from Portal"""
    # Debug: decode token without verification to see what system it claims
    try:
        unverified = jwt.get_unverified_claims(token)
        logger.info(f"SSO login attempt - token claims: system={unverified.get('system')}, sub={unverified.get('sub')}")
    except Exception as e:
        logger.warning(f"Could not decode token for debug: {e}")

    # Validate Portal token
    portal_user = validate_portal_token(token, "hub")

    if not portal_user:
        # Token expired or invalid - redirect to Portal login
        # This provides a better UX than showing an error
        logger.warning(f"Token validation failed - redirecting to Portal login")
        return RedirectResponse(
            url=f"{PORTAL_URL}/login?message=session_expired&redirect=/hub/",
            status_code=303
        )

    logger.info(f"SSO login successful for user: {portal_user.get('username')}")
    # Integration Hub doesn't require authentication, so just redirect to home
    # In the future, we could store session for audit logging
    return RedirectResponse(url="/hub/", status_code=303)

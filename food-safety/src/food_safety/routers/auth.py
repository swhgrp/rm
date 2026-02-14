"""Authentication router for Food Safety Service.

Provides /auth/me for user context and /auth/login for direct login.
"""
import logging
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from jose import jwt
from pydantic import BaseModel

from food_safety.auth import get_current_user_required, CurrentUser
from food_safety.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

COOKIE_NAME = "portal_session"
SESSION_EXPIRE_MINUTES = 30


class UserResponse(BaseModel):
    user_id: int
    username: str
    full_name: str
    email: str
    is_admin: bool


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/me", response_model=UserResponse)
async def get_me(request: Request):
    """Return the current authenticated user from the portal JWT cookie."""
    user = get_current_user_required(request)
    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        is_admin=user.is_admin,
    )


@router.post("/login")
async def login(data: LoginRequest, response: Response):
    """Authenticate via portal service and set session cookie.

    Proxies credentials to the portal's login API, then creates a local
    JWT cookie so the user can access food-safety pages directly.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.PORTAL_SERVICE_URL}/api/auth/validate",
                json={"username": data.username, "password": data.password},
            )

            if resp.status_code == 200:
                user_data = resp.json()
                # Create JWT matching portal format
                secret = settings.PORTAL_SECRET_KEY or settings.SECRET_KEY
                expire = datetime.utcnow() + timedelta(minutes=SESSION_EXPIRE_MINUTES)
                token_data = {
                    "sub": user_data.get("username", data.username),
                    "email": user_data.get("email", ""),
                    "full_name": user_data.get("full_name", data.username),
                    "user_id": user_data.get("user_id", 0),
                    "is_admin": user_data.get("is_admin", False),
                    "exp": expire,
                }
                token = jwt.encode(token_data, secret, algorithm=settings.ALGORITHM)

                response.set_cookie(
                    key=COOKIE_NAME,
                    value=token,
                    httponly=True,
                    max_age=SESSION_EXPIRE_MINUTES * 60,
                    samesite="lax",
                    path="/",
                )
                return {"status": "ok", "user": {
                    "user_id": token_data["user_id"],
                    "username": token_data["sub"],
                    "full_name": token_data["full_name"],
                }}

            elif resp.status_code in (401, 403):
                raise HTTPException(status_code=401, detail="Invalid username or password")
            else:
                logger.error(f"Portal auth returned {resp.status_code}: {resp.text}")
                raise HTTPException(status_code=502, detail="Authentication service unavailable")

    except httpx.RequestError as e:
        logger.error(f"Portal auth request failed: {e}")
        raise HTTPException(status_code=502, detail="Authentication service unavailable")

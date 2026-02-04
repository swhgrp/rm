"""Authentication endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from datetime import datetime

from files.db.database import get_db
from files.core.config import settings
from files.core.security import create_access_token, verify_token
from files.models.user import User

router = APIRouter()


@router.get("/keepalive")
async def keepalive(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Keep the Files session alive.
    Called periodically by the frontend when user is active to extend the session.
    """
    token = request.cookies.get("session_token")

    if not token:
        raise HTTPException(status_code=401, detail="Session expired")

    user_id = verify_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session expired")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="Session expired")

    # Issue a fresh token with new expiration
    new_token = create_access_token(
        data={"sub": user.username, "user_id": user.id}
    )

    response.set_cookie(
        key="session_token",
        value=new_token,
        httponly=True,
        max_age=1800,
        samesite="lax"
    )

    return {"status": "ok", "session_extended": True}


@router.get("/sso-login")
async def sso_login(
    token: str,
    db: Session = Depends(get_db)
):
    """SSO login from portal"""
    try:
        # Decode portal token
        payload = jwt.decode(
            token,
            settings.PORTAL_SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        
        # Validate expiration (use UTC for both sides of comparison)
        exp = payload.get("exp")
        if exp:
            from datetime import timezone
            exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
            now_dt = datetime.now(timezone.utc)
            if exp_dt < now_dt:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token expired"
                )
        
        # Get user
        user_id = payload.get("user_id")
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # Create session token
        access_token = create_access_token(
            data={"sub": user.username, "user_id": user.id}
        )
        
        # Redirect with cookie
        response = RedirectResponse(url="/files/", status_code=303)
        response.set_cookie(
            key="session_token",
            value=access_token,
            httponly=True,
            max_age=1800,
            samesite="lax"
        )
        
        return response
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

"""Authentication endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from datetime import datetime

from files.db.database import get_db
from files.core.config import settings
from files.core.security import create_access_token
from files.models.user import User

router = APIRouter()


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
        
        # Validate expiration
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp) < datetime.utcnow():
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

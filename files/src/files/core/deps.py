"""Dependencies"""
from typing import Optional
from fastapi import Depends, HTTPException, status, Request, Cookie
from sqlalchemy.orm import Session
from files.db.database import get_db
from files.core.security import verify_token
from files.models.user import User


def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user"""
    token = session_token or request.cookies.get("session_token")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    user_id = verify_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    return user

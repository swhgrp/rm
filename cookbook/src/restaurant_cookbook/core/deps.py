from typing import Optional, Generator
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from restaurant_cookbook.db.database import SessionLocal
from restaurant_cookbook.core.security import verify_token
from restaurant_cookbook.models.user import User

security = HTTPBearer(auto_error=False)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    token = None

    # Try Bearer header first
    if credentials:
        token = credentials.credentials
    else:
        # Try cookie (Portal SSO)
        cookie_token = request.cookies.get("access_token") or request.cookies.get(
            "portal_session"
        )
        if cookie_token:
            token = cookie_token[7:] if cookie_token.startswith("Bearer ") else cookie_token
        # Fallback: query param
        if not token:
            token = request.query_params.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = verify_token(token)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Look up user — try username first (Portal tokens use username as sub)
    user = None
    if "username" in token_data:
        user = db.query(User).filter(User.username == token_data["username"]).first()
    if user is None and "id" in token_data:
        user = db.query(User).filter(User.id == int(token_data["id"])).first()

    # JIT provisioning — auto-create user from Portal token
    if user is None and "username" in token_data:
        user = User(
            username=token_data["username"],
            full_name=token_data.get("full_name", token_data["username"]),
            is_active=True,
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user"
        )

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("admin", "Admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user

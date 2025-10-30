"""
Authentication helper functions for route protection
"""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from hr.db.database import get_db
from hr.models.user import User


def require_login(request: Request, db: Session = Depends(get_db)):
    """Middleware to require login for protected routes"""
    from hr.api.auth import get_current_user
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"Location": "/hr/login"}
        )
    return user


def require_admin(request: Request, db: Session = Depends(get_db)):
    """Middleware to require admin access for protected routes (Admin HR role or is_admin flag)"""
    from hr.api.auth import get_current_user
    from hr.models.user_role import UserRole
    from hr.models.role import Role
    
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"Location": "/hr/login"}
        )
    
    # Check if user has is_admin flag OR has Admin HR role
    has_admin_flag = user.is_admin
    
    # Check if user has Admin HR role (role_id = 1)
    has_admin_role = db.query(UserRole).join(Role).filter(
        UserRole.user_id == user.id,
        Role.name == "Admin"
    ).first() is not None
    
    if not (has_admin_flag or has_admin_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return user

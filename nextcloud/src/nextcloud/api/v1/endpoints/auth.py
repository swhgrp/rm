"""
Authentication and setup API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from datetime import datetime

from nextcloud.core.deps import get_db, get_hr_db, get_current_user
from nextcloud.core.security import encrypt_credential, create_access_token
from nextcloud.core.config import settings
from nextcloud.models.user import User
from nextcloud.schemas.auth import (
    UserResponse,
    NextcloudCredentialsSetup,
    NextcloudCredentialsUpdate,
    SetupResponse
)

router = APIRouter()


@router.get("/sso-login")
async def sso_login(
    token: str,
    response: Response,
    db: Session = Depends(get_hr_db)
):
    """
    SSO login endpoint - authenticates user via portal token

    Args:
        token: JWT token from portal

    Returns:
        Redirects to appropriate page based on setup status
    """
    try:
        # Decode portal token
        payload = jwt.decode(
            token,
            settings.PORTAL_SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        # Validate token expiration
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp) < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired"
            )

        # Get user from HR database
        user_id = payload.get("user_id")
        username = payload.get("sub")

        if not user_id or not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

        # Query HR database for user
        user = db.query(User).filter(User.id == user_id).first()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        # Create session token for nextcloud service
        access_token = create_access_token(
            data={"sub": user.username, "user_id": user.id}
        )

        # Set cookie
        response = RedirectResponse(url="/nextcloud/", status_code=303)
        response.set_cookie(
            key="session_token",
            value=access_token,
            httponly=True,
            max_age=1800,  # 30 minutes
            samesite="lax"
        )

        return response

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication failed: {str(e)}"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current user information including Nextcloud setup status

    Returns:
        User information with Nextcloud credentials status
    """
    has_credentials = bool(
        current_user.nextcloud_username and
        current_user.nextcloud_encrypted_password
    )

    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        is_admin=current_user.is_admin,
        is_active=current_user.is_active,
        nextcloud_username=current_user.nextcloud_username,
        has_nextcloud_credentials=has_credentials,
        created_at=current_user.created_at
    )


@router.post("/setup", response_model=SetupResponse)
async def setup_nextcloud_credentials(
    credentials: NextcloudCredentialsSetup,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Set up Nextcloud credentials for the current user

    This is a one-time setup where users enter their Nextcloud username
    and password. The password is encrypted before storage.

    Args:
        credentials: Nextcloud username and password

    Returns:
        Setup confirmation
    """
    try:
        # Encrypt password
        encrypted_password = encrypt_credential(credentials.nextcloud_password)

        # Update user record
        current_user.nextcloud_username = credentials.nextcloud_username
        current_user.nextcloud_encrypted_password = encrypted_password

        db.commit()
        db.refresh(current_user)

        return SetupResponse(
            success=True,
            message="Nextcloud credentials configured successfully",
            nextcloud_username=credentials.nextcloud_username
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to setup credentials: {str(e)}"
        )


@router.put("/credentials", response_model=SetupResponse)
async def update_nextcloud_credentials(
    credentials: NextcloudCredentialsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update Nextcloud credentials

    Args:
        credentials: Updated Nextcloud username and/or password

    Returns:
        Update confirmation
    """
    try:
        updated = False

        if credentials.nextcloud_username:
            current_user.nextcloud_username = credentials.nextcloud_username
            updated = True

        if credentials.nextcloud_password:
            encrypted_password = encrypt_credential(credentials.nextcloud_password)
            current_user.nextcloud_encrypted_password = encrypted_password
            updated = True

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No credentials provided to update"
            )

        db.commit()
        db.refresh(current_user)

        return SetupResponse(
            success=True,
            message="Nextcloud credentials updated successfully",
            nextcloud_username=current_user.nextcloud_username
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update credentials: {str(e)}"
        )


@router.delete("/credentials", response_model=SetupResponse)
async def delete_nextcloud_credentials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Remove Nextcloud credentials

    Returns:
        Deletion confirmation
    """
    try:
        current_user.nextcloud_username = None
        current_user.nextcloud_encrypted_password = None

        db.commit()

        return SetupResponse(
            success=True,
            message="Nextcloud credentials removed successfully"
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete credentials: {str(e)}"
        )

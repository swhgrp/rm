"""
User management endpoints (Admin only)
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from datetime import datetime, timezone, timedelta
import secrets
import logging

from restaurant_inventory.core.deps import get_db, get_current_user, require_admin
from restaurant_inventory.models.user import User
from restaurant_inventory.models.password_reset_token import PasswordResetToken
from restaurant_inventory.core.security import get_password_hash
from restaurant_inventory.core.config import settings
from restaurant_inventory.schemas.auth import UserCreate, UserResponse, UserUpdate
from restaurant_inventory.core.audit import log_audit_event, create_change_dict
from restaurant_inventory.services.email import EmailService

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/", response_model=List[UserResponse])
async def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List all users (Admin only)"""
    users = db.query(User).all()

    return [
        UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login=user.last_login
        )
        for user in users
    ]

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get specific user (own profile or Admin only)"""
    # Allow users to view their own profile, admins can view any
    if current_user.id != user_id and current_user.role != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this user"
        )

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login=user.last_login
    )

@router.post("/", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Create new user (Admin only)

    If password is not provided, an invitation email will be sent to the user
    with a secure link to set up their account.
    """

    # Check if username already exists
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )

    # Check if email already exists
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Determine if we're using invitation flow or direct password
    using_invitation = user_data.password is None

    # Create new user
    if using_invitation:
        # Generate a temporary placeholder password (user will set their own via invitation)
        temp_password = secrets.token_urlsafe(32)
        new_user = User(
            username=user_data.username,
            email=user_data.email,
            full_name=user_data.full_name,
            hashed_password=get_password_hash(temp_password),
            role=user_data.role,
            is_active=False,  # Inactive until they set their password
            is_verified=False
        )
    else:
        # Direct password provided
        new_user = User(
            username=user_data.username,
            email=user_data.email,
            full_name=user_data.full_name,
            hashed_password=get_password_hash(user_data.password),
            role=user_data.role,
            is_active=True,
            is_verified=True
        )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # If using invitation flow, create token and send email
    if using_invitation:
        try:
            # Generate secure token
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS)

            # Create token record
            reset_token = PasswordResetToken(
                user_id=new_user.id,
                token=token,
                token_type="invitation",
                expires_at=expires_at
            )
            db.add(reset_token)
            db.commit()

            # Build setup URL
            setup_url = f"{settings.APP_URL}/setup-password?token={token}"

            # Send invitation email
            email_sent = EmailService.send_user_invitation(
                to_email=new_user.email,
                full_name=new_user.full_name,
                username=new_user.username,
                setup_url=setup_url
            )

            if not email_sent:
                logger.warning(f"Failed to send invitation email to {new_user.email}")
                # Don't fail the user creation, just log the warning

            logger.info(f"Invitation email sent to {new_user.email} for user {new_user.username}")

        except Exception as e:
            logger.error(f"Error sending invitation email: {str(e)}", exc_info=True)
            # Don't fail the user creation, admin can resend invitation

    # Log audit event
    log_audit_event(
        db=db,
        action="CREATE",
        entity_type="user",
        entity_id=new_user.id,
        user=current_user,
        changes={"new": {
            "username": new_user.username,
            "email": new_user.email,
            "full_name": new_user.full_name,
            "role": new_user.role,
            "invitation_sent": using_invitation
        }},
        request=request
    )

    return UserResponse(
        id=new_user.id,
        username=new_user.username,
        email=new_user.email,
        full_name=new_user.full_name,
        role=new_user.role,
        is_active=new_user.is_active,
        is_verified=new_user.is_verified,
        created_at=new_user.created_at,
        last_login=new_user.last_login
    )

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update user (own profile for basic info, Admin for role/status)"""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Allow users to update their own basic info, admins can update anything
    is_own_profile = current_user.id == user_id
    is_admin = current_user.role == "Admin"

    if not is_own_profile and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this user"
        )

    # Track changes
    old_data = {
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active
    }

    # Update fields if provided
    if user_data.email:
        # Check if email already exists for another user
        existing_email = db.query(User).filter(
            User.email == user_data.email,
            User.id != user_id
        ).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use by another user"
            )
        user.email = user_data.email

    if user_data.full_name is not None:
        user.full_name = user_data.full_name

    # Only admins can change password via this endpoint (users use change-password)
    if user_data.password and is_admin:
        user.hashed_password = get_password_hash(user_data.password)

    # Only admins can change role and status
    if user_data.role and is_admin:
        user.role = user_data.role

    if user_data.is_active is not None and is_admin:
        user.is_active = user_data.is_active

    db.commit()
    db.refresh(user)

    # Track new values
    new_data = {
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active
    }

    # Log audit event
    changes = create_change_dict(old_data, new_data)
    if changes:
        log_audit_event(
            db=db,
            action="UPDATE",
            entity_type="user",
            entity_id=user.id,
            user=current_user,
            changes=changes,
            request=request
        )

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login=user.last_login
    )

@router.put("/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Deactivate user (Admin only)"""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Prevent deactivating yourself
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )

    user.is_active = False
    db.commit()

    return {"message": "User deactivated successfully"}

@router.put("/{user_id}/activate")
async def activate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Activate user (Admin only)"""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.is_active = True
    db.commit()

    return {"message": "User activated successfully"}

@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete user permanently (Admin only)"""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Prevent deleting yourself
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    # Nullify all foreign key references to this user in other tables
    # This preserves the data but removes the foreign key constraints

    # Audit logs
    from restaurant_inventory.models.audit_log import AuditLog
    db.query(AuditLog).filter(AuditLog.user_id == user_id).update(
        {AuditLog.user_id: None}, synchronize_session=False
    )

    # Use raw SQL for tables that might not have models yet
    db.execute(text("UPDATE inventory_transactions SET created_by_id = NULL WHERE created_by_id = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE invoices SET uploaded_by_id = NULL WHERE uploaded_by_id = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE invoices SET reviewed_by_id = NULL WHERE reviewed_by_id = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE invoices SET approved_by_id = NULL WHERE approved_by_id = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE recipes SET created_by_id = NULL WHERE created_by_id = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE count_templates SET created_by = NULL WHERE created_by = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE transfers SET requested_by = NULL WHERE requested_by = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE transfers SET approved_by = NULL WHERE approved_by = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE count_sessions SET started_by = NULL WHERE started_by = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE count_sessions SET completed_by = NULL WHERE completed_by = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE count_sessions SET approved_by = NULL WHERE approved_by = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE waste_records SET recorded_by = NULL WHERE recorded_by = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE invoice_items SET mapped_by_id = NULL WHERE mapped_by_id = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE count_session_items SET counted_by = NULL WHERE counted_by = :user_id"), {"user_id": user_id})
    db.execute(text("UPDATE count_session_storage_areas SET finished_by = NULL WHERE finished_by = :user_id"), {"user_id": user_id})

    # Delete related records that should be removed with the user
    db.execute(text("DELETE FROM user_locations WHERE user_id = :user_id"), {"user_id": user_id})
    db.execute(text("DELETE FROM password_reset_tokens WHERE user_id = :user_id"), {"user_id": user_id})

    # Log before deletion
    log_audit_event(
        db=db,
        action="DELETE",
        entity_type="user",
        entity_id=user.id,
        user=current_user,
        changes={"old": {
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role
        }},
        request=request
    )

    db.delete(user)
    db.commit()

    return {"message": "User deleted successfully"}

@router.post("/{user_id}/change-password")
async def change_password(
    user_id: int,
    password_data: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Change user password (own password only, unless admin)"""
    from restaurant_inventory.core.security import verify_password

    # Only allow users to change their own password (unless admin)
    if current_user.id != user_id and current_user.role != "Admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to change this user's password"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Verify current password if changing own password
    if current_user.id == user_id:
        current_password = password_data.get('current_password')
        if not current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is required"
            )

        if not verify_password(current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )

    # Validate new password
    new_password = password_data.get('new_password')
    if not new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password is required"
        )

    if len(new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters"
        )

    # Update password
    user.hashed_password = get_password_hash(new_password)
    db.commit()

    # Log audit event
    log_audit_event(
        db=db,
        action="UPDATE",
        entity_type="user",
        entity_id=user.id,
        user=current_user,
        changes={"password_changed": True},
        request=request
    )

    return {"message": "Password changed successfully"}


@router.get("/{user_id}/locations")
async def get_user_locations(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get assigned locations for a user (Admin only)"""
    from sqlalchemy.orm import joinedload

    user = db.query(User).options(
        joinedload(User.assigned_locations)
    ).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return {
        "user_id": user.id,
        "username": user.username,
        "assigned_locations": [
            {"id": loc.id, "name": loc.name, "address": loc.address}
            for loc in user.assigned_locations
        ]
    }


@router.post("/{user_id}/locations")
async def assign_user_locations(
    user_id: int,
    location_data: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Assign locations to a user (Admin only)

    Body should be: {"location_ids": [1, 2, 3]}
    Empty array means user has access to all locations (no restrictions)
    """
    from restaurant_inventory.models.location import Location
    from sqlalchemy.orm import joinedload

    user = db.query(User).options(
        joinedload(User.assigned_locations)
    ).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    location_ids = location_data.get('location_ids', [])

    # Validate all location IDs exist
    if location_ids:
        locations = db.query(Location).filter(Location.id.in_(location_ids)).all()
        if len(locations) != len(location_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more location IDs are invalid"
            )
    else:
        locations = []

    # Store old assignments for audit log
    old_location_ids = [loc.id for loc in user.assigned_locations]

    # Update assignments - replace all
    user.assigned_locations = locations
    db.commit()

    # Log audit event
    log_audit_event(
        db=db,
        action="UPDATE",
        entity_type="user_locations",
        entity_id=user.id,
        user=current_user,
        changes={
            "old_locations": old_location_ids,
            "new_locations": location_ids
        },
        request=request
    )

    return {
        "message": "User locations updated successfully",
        "user_id": user.id,
        "assigned_location_count": len(locations),
        "has_restrictions": len(locations) > 0
    }
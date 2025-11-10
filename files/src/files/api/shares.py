"""Share management API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
import secrets

from files.db.database import get_db, get_hr_db
from files.models.user import User
from files.models.file_metadata import Folder, FileMetadata
from files.models.shares import ShareLink, ShareAccessLog, InternalShare, ShareAccessType, ShareLinkType
from files.core.deps import get_current_user
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/shares", tags=["shares"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============================================================================
# Pydantic Models (Request/Response Schemas)
# ============================================================================

class CreateShareLinkRequest(BaseModel):
    """Request to create a new share link"""
    resource_type: ShareLinkType
    resource_id: int = Field(..., description="Folder ID or File ID")
    access_type: ShareAccessType = ShareAccessType.READ_ONLY

    # Security
    password: Optional[str] = None
    require_login: bool = False

    # Limits
    expires_in_days: Optional[int] = Field(None, description="Days until expiration (null = never)")
    max_downloads: Optional[int] = None
    max_uses: Optional[int] = None

    # Settings
    allow_download: bool = True
    allow_preview: bool = True
    notify_on_access: bool = False


class ShareLinkResponse(BaseModel):
    """Response with share link details"""
    id: int
    share_url: str
    share_token: str
    resource_type: str
    resource_name: str
    access_type: str
    expires_at: Optional[datetime]
    is_password_protected: bool
    require_login: bool
    created_at: datetime
    is_active: bool
    download_count: int
    use_count: int

    class Config:
        from_attributes = True


class CreateInternalShareRequest(BaseModel):
    """Request to share with internal HR users"""
    resource_type: ShareLinkType
    resource_id: int

    # Who to share with (at least one required)
    shared_with_user_id: Optional[int] = None
    shared_with_department: Optional[str] = None
    shared_with_role: Optional[str] = None
    shared_with_location: Optional[str] = None

    # Permissions
    can_view: bool = True
    can_download: bool = True
    can_upload: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_share: bool = False
    can_comment: bool = True

    # Settings
    expires_in_days: Optional[int] = None
    message: Optional[str] = None
    notify_by_email: bool = True


class InternalShareResponse(BaseModel):
    """Response with internal share details"""
    id: int
    resource_type: str
    resource_name: str
    resource_id: int  # ID of the folder or file
    shared_by: Optional[str] = None  # Name of user who shared
    shared_with_user: Optional[str] = None
    shared_with_department: Optional[str] = None
    permissions: dict
    shared_at: datetime
    expires_at: Optional[datetime]
    is_active: bool

    class Config:
        from_attributes = True


# ============================================================================
# Share Link Endpoints
# ============================================================================

@router.post("/links", response_model=ShareLinkResponse)
async def create_share_link(
    request: CreateShareLinkRequest,
    req: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new share link for a file or folder"""

    # Verify resource exists and user has permission
    if request.resource_type == ShareLinkType.FOLDER:
        resource = db.query(Folder).filter(Folder.id == request.resource_id).first()
        if not resource:
            raise HTTPException(status_code=404, detail="Folder not found")

        # Check if user owns folder or has share permission
        if resource.owner_id != current_user.id and not current_user.is_admin:
            # TODO: Check folder_permissions for can_share
            raise HTTPException(status_code=403, detail="No permission to share this folder")

        resource_name = resource.name
    else:
        resource = db.query(FileMetadata).filter(FileMetadata.id == request.resource_id).first()
        if not resource:
            raise HTTPException(status_code=404, detail="File not found")

        # Check if user owns file or has share permission
        if resource.owner_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="No permission to share this file")

        resource_name = resource.name

    # Generate unique share token
    share_token = secrets.token_urlsafe(32)

    # Calculate expiration date
    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=request.expires_in_days)

    # Hash password if provided
    password_hash = None
    if request.password:
        password_hash = pwd_context.hash(request.password)

    # Create share link
    share_link = ShareLink(
        resource_type=request.resource_type,
        folder_id=request.resource_id if request.resource_type == ShareLinkType.FOLDER else None,
        file_id=request.resource_id if request.resource_type == ShareLinkType.FILE else None,
        share_token=share_token,
        access_type=request.access_type,
        password_hash=password_hash,
        require_login=request.require_login,
        expires_at=expires_at,
        max_downloads=request.max_downloads,
        max_uses=request.max_uses,
        created_by=current_user.id,
        allow_download=request.allow_download,
        allow_preview=request.allow_preview,
        notify_on_access=request.notify_on_access
    )

    db.add(share_link)
    db.commit()
    db.refresh(share_link)

    # Build share URL
    base_url = str(req.base_url).rstrip('/')
    share_url = f"{base_url}/s/{share_token}"

    return ShareLinkResponse(
        id=share_link.id,
        share_url=share_url,
        share_token=share_token,
        resource_type=request.resource_type.value,
        resource_name=resource_name,
        access_type=request.access_type.value,
        expires_at=expires_at,
        is_password_protected=bool(password_hash),
        require_login=request.require_login,
        created_at=share_link.created_at,
        is_active=share_link.is_active,
        download_count=share_link.download_count,
        use_count=share_link.use_count
    )


@router.get("/links", response_model=List[ShareLinkResponse])
async def list_my_share_links(
    req: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    active_only: bool = Query(True, description="Only show active links")
):
    """List all share links created by current user"""

    query = db.query(ShareLink).filter(ShareLink.created_by == current_user.id)

    if active_only:
        query = query.filter(ShareLink.is_active == True)

    share_links = query.order_by(ShareLink.created_at.desc()).all()

    base_url = str(req.base_url).rstrip('/')

    results = []
    for link in share_links:
        # Get resource name
        if link.resource_type == ShareLinkType.FOLDER:
            resource = link.folder
            resource_name = resource.name if resource else "Unknown"
        else:
            resource = link.file
            resource_name = resource.name if resource else "Unknown"

        results.append(ShareLinkResponse(
            id=link.id,
            share_url=f"{base_url}/s/{link.share_token}",
            share_token=link.share_token,
            resource_type=link.resource_type.value,
            resource_name=resource_name,
            access_type=link.access_type.value,
            expires_at=link.expires_at,
            is_password_protected=bool(link.password_hash),
            require_login=link.require_login,
            created_at=link.created_at,
            is_active=link.is_active,
            download_count=link.download_count,
            use_count=link.use_count
        ))

    return results


@router.delete("/links/{share_link_id}")
async def revoke_share_link(
    share_link_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Revoke (deactivate) a share link"""

    share_link = db.query(ShareLink).filter(ShareLink.id == share_link_id).first()
    if not share_link:
        raise HTTPException(status_code=404, detail="Share link not found")

    # Only creator or admin can revoke
    if share_link.created_by != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="No permission to revoke this share link")

    share_link.is_active = False
    db.commit()

    return {"message": "Share link revoked successfully", "id": share_link_id}


# ============================================================================
# Share Access Endpoints (Public - no auth required for some)
# ============================================================================

@router.get("/access/{share_token}")
async def get_share_info(
    share_token: str,
    db: Session = Depends(get_db)
):
    """Get information about a share link (public endpoint)"""

    share_link = db.query(ShareLink).filter(ShareLink.share_token == share_token).first()
    if not share_link:
        raise HTTPException(status_code=404, detail="Share link not found")

    if not share_link.is_valid:
        raise HTTPException(status_code=410, detail="Share link has expired or is no longer available")

    # Get resource info
    if share_link.resource_type == ShareLinkType.FOLDER:
        resource = share_link.folder
        resource_name = resource.name if resource else "Unknown"
    else:
        resource = share_link.file
        resource_name = resource.name if resource else "Unknown"

    return {
        "resource_type": share_link.resource_type.value,
        "resource_name": resource_name,
        "access_type": share_link.access_type.value,
        "requires_password": bool(share_link.password_hash),
        "requires_login": share_link.require_login,
        "expires_at": share_link.expires_at,
        "allow_download": share_link.allow_download,
        "allow_preview": share_link.allow_preview
    }


@router.post("/access/{share_token}/verify")
async def verify_share_access(
    share_token: str,
    password: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Verify password and access to a share link"""

    share_link = db.query(ShareLink).filter(ShareLink.share_token == share_token).first()
    if not share_link:
        raise HTTPException(status_code=404, detail="Share link not found")

    if not share_link.is_valid:
        raise HTTPException(status_code=410, detail="Share link has expired or is no longer available")

    # Verify password if required
    if share_link.password_hash:
        if not password:
            raise HTTPException(status_code=401, detail="Password required")

        if not pwd_context.verify(password, share_link.password_hash):
            raise HTTPException(status_code=401, detail="Incorrect password")

    # Update last accessed
    share_link.last_accessed_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "message": "Access granted",
        "access_type": share_link.access_type.value,
        "resource_type": share_link.resource_type.value
    }


# ============================================================================
# Internal Share Endpoints
# ============================================================================

@router.post("/internal", response_model=InternalShareResponse)
async def create_internal_share(
    request: CreateInternalShareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Share a file or folder with internal HR users"""

    # Verify at least one target is specified
    if not any([
        request.shared_with_user_id,
        request.shared_with_department,
        request.shared_with_role,
        request.shared_with_location
    ]):
        raise HTTPException(
            status_code=400,
            detail="Must specify at least one target: user, department, role, or location"
        )

    # Verify resource exists and user has permission
    if request.resource_type == ShareLinkType.FOLDER:
        resource = db.query(Folder).filter(Folder.id == request.resource_id).first()
        if not resource:
            raise HTTPException(status_code=404, detail="Folder not found")

        if resource.owner_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="No permission to share this folder")

        resource_name = resource.name
    else:
        resource = db.query(FileMetadata).filter(FileMetadata.id == request.resource_id).first()
        if not resource:
            raise HTTPException(status_code=404, detail="File not found")

        if resource.owner_id != current_user.id and not current_user.is_admin:
            raise HTTPException(status_code=403, detail="No permission to share this file")

        resource_name = resource.name

    # Calculate expiration
    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=request.expires_in_days)

    # Check if share already exists
    existing_share = db.query(InternalShare).filter(
        InternalShare.resource_type == request.resource_type,
        InternalShare.is_active == True
    )

    if request.resource_type == ShareLinkType.FOLDER:
        existing_share = existing_share.filter(InternalShare.folder_id == request.resource_id)
    else:
        existing_share = existing_share.filter(InternalShare.file_id == request.resource_id)

    # Match on the target (user, department, role, or location)
    if request.shared_with_user_id:
        existing_share = existing_share.filter(InternalShare.shared_with_user_id == request.shared_with_user_id)
    if request.shared_with_department:
        existing_share = existing_share.filter(InternalShare.shared_with_department == request.shared_with_department)
    if request.shared_with_role:
        existing_share = existing_share.filter(InternalShare.shared_with_role == request.shared_with_role)
    if request.shared_with_location:
        existing_share = existing_share.filter(InternalShare.shared_with_location == request.shared_with_location)

    existing_share = existing_share.first()

    if existing_share:
        # Update existing share permissions instead of creating duplicate
        existing_share.can_view = request.can_view
        existing_share.can_download = request.can_download
        existing_share.can_upload = request.can_upload
        existing_share.can_edit = request.can_edit
        existing_share.can_delete = request.can_delete
        existing_share.can_share = request.can_share
        existing_share.can_comment = request.can_comment
        existing_share.expires_at = expires_at
        existing_share.message = request.message
        db.commit()
        db.refresh(existing_share)
        internal_share = existing_share
    else:
        # Create new internal share
        internal_share = InternalShare(
            resource_type=request.resource_type,
            folder_id=request.resource_id if request.resource_type == ShareLinkType.FOLDER else None,
            file_id=request.resource_id if request.resource_type == ShareLinkType.FILE else None,
            shared_with_user_id=request.shared_with_user_id,
            shared_with_department=request.shared_with_department,
            shared_with_role=request.shared_with_role,
            shared_with_location=request.shared_with_location,
            can_view=request.can_view,
            can_download=request.can_download,
            can_upload=request.can_upload,
            can_edit=request.can_edit,
            can_delete=request.can_delete,
            can_share=request.can_share,
            can_comment=request.can_comment,
            shared_by=current_user.id,
            expires_at=expires_at,
            message=request.message,
            notify_by_email=request.notify_by_email
        )

        db.add(internal_share)
        db.commit()
        db.refresh(internal_share)

    # Get shared_with name if user
    shared_with_user_name = None
    if internal_share.shared_with_user_id:
        user = internal_share.shared_with_user
        shared_with_user_name = user.full_name if user else "Unknown"

    # Get resource ID
    resource_id = request.resource_id if request.resource_type == ShareLinkType.FOLDER else request.resource_id

    return InternalShareResponse(
        id=internal_share.id,
        resource_type=request.resource_type.value,
        resource_name=resource_name,
        resource_id=resource_id,
        shared_by=current_user.full_name,
        shared_with_user=shared_with_user_name,
        shared_with_department=internal_share.shared_with_department,
        permissions={
            "can_view": internal_share.can_view,
            "can_download": internal_share.can_download,
            "can_upload": internal_share.can_upload,
            "can_edit": internal_share.can_edit,
            "can_delete": internal_share.can_delete,
            "can_share": internal_share.can_share,
            "can_comment": internal_share.can_comment
        },
        shared_at=internal_share.shared_at,
        expires_at=internal_share.expires_at,
        is_active=internal_share.is_active
    )


@router.get("/internal/shared-with-me", response_model=List[InternalShareResponse])
async def get_shared_with_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all files/folders shared with current user"""

    # Query shares directly with user
    query = db.query(InternalShare).filter(
        InternalShare.shared_with_user_id == current_user.id,
        InternalShare.is_active == True
    )

    # TODO: Add department/role/location based sharing when JWT has those fields

    shares = query.order_by(InternalShare.shared_at.desc()).all()

    results = []
    for share in shares:
        # Get resource name and ID
        if share.resource_type == ShareLinkType.FOLDER:
            resource = share.folder
            resource_name = resource.name if resource else "Unknown"
            resource_id = resource.id if resource else 0
        else:
            resource = share.file
            resource_name = resource.name if resource else "Unknown"
            resource_id = resource.id if resource else 0

        # Get sharer name
        sharer = share.sharer
        sharer_name = sharer.full_name if sharer else "Unknown"

        results.append(InternalShareResponse(
            id=share.id,
            resource_type=share.resource_type.value,
            resource_name=resource_name,
            resource_id=resource_id,
            shared_by=sharer_name,
            shared_with_user=current_user.full_name,
            shared_with_department=share.shared_with_department,
            permissions={
                "can_view": share.can_view,
                "can_download": share.can_download,
                "can_upload": share.can_upload,
                "can_edit": share.can_edit,
                "can_delete": share.can_delete,
                "can_share": share.can_share,
                "can_comment": share.can_comment
            },
            shared_at=share.shared_at,
            expires_at=share.expires_at,
            is_active=share.is_active
        ))

    return results


@router.get("/internal/shared-by-me", response_model=List[InternalShareResponse])
async def get_shared_by_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all files/folders shared by current user"""

    shares = db.query(InternalShare).filter(
        InternalShare.shared_by == current_user.id,
        InternalShare.is_active == True
    ).order_by(InternalShare.shared_at.desc()).all()

    results = []
    for share in shares:
        # Get resource name and ID
        if share.resource_type == ShareLinkType.FOLDER:
            resource = share.folder
            resource_name = resource.name if resource else "Unknown"
            resource_id = resource.id if resource else 0
        else:
            resource = share.file
            resource_name = resource.name if resource else "Unknown"
            resource_id = resource.id if resource else 0

        # Get recipient name if shared with specific user
        shared_with_user_name = None
        if share.shared_with_user_id:
            user = share.shared_with_user
            shared_with_user_name = user.full_name if user else "Unknown"

        results.append(InternalShareResponse(
            id=share.id,
            resource_type=share.resource_type.value,
            resource_name=resource_name,
            resource_id=resource_id,
            shared_by=current_user.full_name,
            shared_with_user=shared_with_user_name,
            shared_with_department=share.shared_with_department,
            permissions={
                "can_view": share.can_view,
                "can_download": share.can_download,
                "can_upload": share.can_upload,
                "can_edit": share.can_edit,
                "can_delete": share.can_delete,
                "can_share": share.can_share,
                "can_comment": share.can_comment
            },
            shared_at=share.shared_at,
            expires_at=share.expires_at,
            is_active=share.is_active
        ))

    return results


@router.get("/internal/by-resource")
async def get_internal_shares_by_resource(
    resource_type: str,
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all internal shares for a specific resource"""

    # Verify user owns or has access to the resource
    if resource_type == "folder":
        from files.models.file_metadata import Folder
        resource = db.query(Folder).filter(Folder.id == resource_id).first()
        if not resource or resource.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to view shares for this resource")
    else:
        from files.models.file_metadata import FileMetadata
        resource = db.query(FileMetadata).filter(FileMetadata.id == resource_id).first()
        if not resource or resource.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to view shares for this resource")

    # Get shares for this resource
    query = db.query(InternalShare).filter(
        InternalShare.resource_type == resource_type,
        InternalShare.is_active == True
    )

    if resource_type == "folder":
        query = query.filter(InternalShare.folder_id == resource_id)
    else:
        query = query.filter(InternalShare.file_id == resource_id)

    shares = query.all()

    # Format response
    results = []
    for share in shares:
        shared_with_name = None
        if share.shared_with_user_id:
            user = share.shared_with_user
            shared_with_name = user.full_name if user else "Unknown"

        results.append({
            "id": share.id,
            "resource_type": share.resource_type,
            "shared_with_user_id": share.shared_with_user_id,
            "shared_with_username": shared_with_name,
            "can_view": share.can_view,
            "can_download": share.can_download,
            "can_upload": share.can_upload,
            "can_edit": share.can_edit,
            "can_delete": share.can_delete,
            "can_share": share.can_share,
            "can_comment": share.can_comment,
            "shared_at": share.shared_at.isoformat() if share.shared_at else None
        })

    return {"shares": results}


@router.delete("/internal/{share_id}")
async def revoke_internal_share(
    share_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Revoke an internal share"""

    share = db.query(InternalShare).filter(InternalShare.id == share_id).first()
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")

    # Only creator or admin can revoke
    if share.shared_by != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="No permission to revoke this share")

    share.is_active = False
    db.commit()

    return {"message": "Share revoked successfully", "id": share_id}

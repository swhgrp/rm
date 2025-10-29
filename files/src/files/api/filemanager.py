"""File manager API routes"""
import os
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
import aiofiles
import mimetypes

from files.db.database import get_db, get_hr_db
from files.models.user import User
from files.models.file_metadata import Folder, FileMetadata, folder_permissions
from files.core.deps import get_current_user

router = APIRouter(prefix="/api/files", tags=["filemanager"])

# Base storage path
STORAGE_PATH = Path("/app/storage")
STORAGE_PATH.mkdir(parents=True, exist_ok=True)


def get_user_folder_path(user_id: int, folder_path: str = "") -> Path:
    """Get the full filesystem path for a user's folder"""
    user_path = STORAGE_PATH / f"user_{user_id}" / folder_path
    user_path.mkdir(parents=True, exist_ok=True)
    return user_path


def has_folder_permission(db: Session, user: User, folder: Folder, permission: str = "read") -> bool:
    """Check if user has permission on folder"""
    # Admin has all permissions
    if user.is_admin:
        return True
    
    # Owner has all permissions
    if folder.owner_id == user.id:
        return True
    
    # Check if folder is public and permission is read
    if folder.is_public and permission == "read":
        return True
    
    # Check explicit permissions
    perm = db.query(folder_permissions).filter(
        folder_permissions.c.folder_id == folder.id,
        folder_permissions.c.user_id == user.id
    ).first()
    
    if perm:
        if permission == "read" and perm.can_read:
            return True
        if permission == "write" and perm.can_write:
            return True
        if permission == "delete" and perm.can_delete:
            return True
    
    return False


@router.get("/folders")
async def list_folders(
    parent_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List folders accessible to current user"""
    query = db.query(Folder)
    
    if parent_id:
        query = query.filter(Folder.parent_id == parent_id)
    else:
        query = query.filter(Folder.parent_id.is_(None))
    
    folders = query.all()
    
    # Filter by permissions
    accessible_folders = [
        {
            "id": folder.id,
            "name": folder.name,
            "path": folder.path,
            "parent_id": folder.parent_id,
            "is_public": folder.is_public,
            "created_at": folder.created_at.isoformat() if folder.created_at else None,
            "owner": folder.owner.full_name if folder.owner else "System",
            "can_write": has_folder_permission(db, current_user, folder, "write"),
            "can_delete": has_folder_permission(db, current_user, folder, "delete"),
        }
        for folder in folders
        if has_folder_permission(db, current_user, folder, "read")
    ]
    
    return {"folders": accessible_folders}


@router.post("/folders")
async def create_folder(
    name: str,
    parent_id: Optional[int] = None,
    is_public: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new folder"""
    # Check parent folder permissions if parent_id provided
    if parent_id:
        parent_folder = db.query(Folder).filter(Folder.id == parent_id).first()
        if not parent_folder:
            raise HTTPException(status_code=404, detail="Parent folder not found")
        if not has_folder_permission(db, current_user, parent_folder, "write"):
            raise HTTPException(status_code=403, detail="No write permission on parent folder")
        folder_path = f"{parent_folder.path}/{name}"
    else:
        folder_path = name
    
    # Create folder in database
    folder = Folder(
        name=name,
        path=folder_path,
        parent_id=parent_id,
        owner_id=current_user.id,
        is_public=is_public
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    
    # Create folder on filesystem
    fs_path = get_user_folder_path(current_user.id, folder_path)
    fs_path.mkdir(parents=True, exist_ok=True)
    
    return {
        "id": folder.id,
        "name": folder.name,
        "path": folder.path,
        "message": "Folder created successfully"
    }


@router.get("/folders/{folder_id}/files")
async def list_files(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List files in a folder"""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    if not has_folder_permission(db, current_user, folder, "read"):
        raise HTTPException(status_code=403, detail="No read permission on folder")
    
    files = db.query(FileMetadata).filter(FileMetadata.folder_id == folder_id).all()
    
    return {
        "folder": {
            "id": folder.id,
            "name": folder.name,
            "path": folder.path
        },
        "files": [
            {
                "id": file.id,
                "name": file.name,
                "size": file.size,
                "mime_type": file.mime_type,
                "created_at": file.created_at.isoformat() if file.created_at else None,
                "owner": file.owner.full_name if file.owner else "System"
            }
            for file in files
        ]
    }


@router.post("/folders/{folder_id}/upload")
async def upload_file(
    folder_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a file to a folder"""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    if not has_folder_permission(db, current_user, folder, "write"):
        raise HTTPException(status_code=403, detail="No write permission on folder")
    
    # Generate file path
    file_path = f"{folder.path}/{file.filename}"
    folder_fs_path = get_user_folder_path(current_user.id, folder.path)
    fs_path = folder_fs_path / file.filename
    
    # Save file to filesystem
    async with aiofiles.open(fs_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
    
    # Get file size and mime type
    file_size = fs_path.stat().st_size
    mime_type, _ = mimetypes.guess_type(file.filename)
    
    # Create file metadata in database
    file_metadata = FileMetadata(
        name=file.filename,
        path=file_path,
        folder_id=folder_id,
        owner_id=current_user.id,
        size=file_size,
        mime_type=mime_type
    )
    db.add(file_metadata)
    db.commit()
    db.refresh(file_metadata)
    
    return {
        "id": file_metadata.id,
        "name": file_metadata.name,
        "size": file_metadata.size,
        "message": "File uploaded successfully"
    }


@router.get("/files/{file_id}/download")
async def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download a file"""
    file_metadata = db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
    if not file_metadata:
        raise HTTPException(status_code=404, detail="File not found")
    
    folder = file_metadata.folder
    if not has_folder_permission(db, current_user, folder, "read"):
        raise HTTPException(status_code=403, detail="No read permission on folder")
    
    folder_fs_path = get_user_folder_path(file_metadata.owner_id, file_metadata.folder.path)
    fs_path = folder_fs_path / file_metadata.name
    
    if not fs_path.exists():
        raise HTTPException(status_code=404, detail="File not found on filesystem")
    
    return FileResponse(
        path=fs_path,
        filename=file_metadata.name,
        media_type=file_metadata.mime_type
    )


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a file"""
    file_metadata = db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
    if not file_metadata:
        raise HTTPException(status_code=404, detail="File not found")
    
    folder = file_metadata.folder
    if not has_folder_permission(db, current_user, folder, "delete"):
        raise HTTPException(status_code=403, detail="No delete permission on folder")
    
    # Delete from filesystem
    folder_fs_path = get_user_folder_path(file_metadata.owner_id, file_metadata.folder.path)
    fs_path = folder_fs_path / file_metadata.name
    if fs_path.exists():
        fs_path.unlink()
    
    # Delete from database
    db.delete(file_metadata)
    db.commit()
    
    return {"message": "File deleted successfully"}


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a folder and all its contents"""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    if not has_folder_permission(db, current_user, folder, "delete"):
        raise HTTPException(status_code=403, detail="No delete permission on folder")
    
    # Delete from filesystem
    fs_path = get_user_folder_path(folder.owner_id, folder.path)
    if fs_path.exists():
        shutil.rmtree(fs_path)
    
    # Delete from database (cascade will handle files and subfolders)
    db.delete(folder)
    db.commit()
    
    return {"message": "Folder deleted successfully"}


@router.post("/folders/{folder_id}/permissions")
async def grant_folder_permission(
    folder_id: int,
    user_id: int,
    can_read: bool = True,
    can_write: bool = False,
    can_delete: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Grant folder permissions to a user"""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    # Only owner or admin can grant permissions
    if folder.owner_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only folder owner can grant permissions")
    
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if permission already exists
    existing_perm = db.query(folder_permissions).filter(
        folder_permissions.c.folder_id == folder_id,
        folder_permissions.c.user_id == user_id
    ).first()
    
    if existing_perm:
        # Update existing permission
        db.execute(
            folder_permissions.update()
            .where(folder_permissions.c.folder_id == folder_id)
            .where(folder_permissions.c.user_id == user_id)
            .values(can_read=can_read, can_write=can_write, can_delete=can_delete)
        )
    else:
        # Insert new permission
        db.execute(
            folder_permissions.insert().values(
                folder_id=folder_id,
                user_id=user_id,
                can_read=can_read,
                can_write=can_write,
                can_delete=can_delete
            )
        )
    
    db.commit()
    
    return {"message": f"Permissions granted to {target_user.full_name}"}

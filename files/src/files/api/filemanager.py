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
from files.models.shares import ShareLink, InternalShare
from files.core.deps import get_current_user

router = APIRouter(prefix="/api/files", tags=["filemanager"])

# Base storage path
STORAGE_PATH = Path("/app/storage")
STORAGE_PATH.mkdir(parents=True, exist_ok=True)


def get_user_folder_path(user_id: int, folder_path: str = "") -> Path:
    """Get the full filesystem path for a user's folder

    Note: This function creates directories, so folder_path should be a directory path,
    not a file path. If you need a file path, create the folder first, then append the filename.
    """
    user_path = STORAGE_PATH / f"user_{user_id}" / folder_path

    # Only create directory if the path doesn't already exist as a file
    if not user_path.exists():
        user_path.mkdir(parents=True, exist_ok=True)
    elif user_path.is_file():
        # If it's a file, only create the parent directory
        user_path.parent.mkdir(parents=True, exist_ok=True)

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


def get_share_status(db: Session, resource_type: str, resource_id: int) -> dict:
    """Get share status for a resource (folder or file)"""

    # Check for public share links (query by ID only, not enum type, only active ones)
    if resource_type == "folder":
        public_shares = db.query(ShareLink).filter(
            ShareLink.folder_id == resource_id,
            ShareLink.is_active == True
        ).count()
    else:
        public_shares = db.query(ShareLink).filter(
            ShareLink.file_id == resource_id,
            ShareLink.is_active == True
        ).count()

    # Check for internal shares (only active ones)
    if resource_type == "folder":
        internal_shares = db.query(InternalShare).filter(
            InternalShare.folder_id == resource_id,
            InternalShare.is_active == True
        ).count()
    else:
        internal_shares = db.query(InternalShare).filter(
            InternalShare.file_id == resource_id,
            InternalShare.is_active == True
        ).count()

    return {
        "is_shared": public_shares > 0 or internal_shares > 0,
        "has_public_link": public_shares > 0,
        "has_internal_shares": internal_shares > 0,
        "public_share_count": public_shares,
        "internal_share_count": internal_shares
    }


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
    accessible_folders = []
    for folder in folders:
        if has_folder_permission(db, current_user, folder, "read"):
            share_status = get_share_status(db, "folder", folder.id)
            accessible_folders.append({
                "id": folder.id,
                "name": folder.name,
                "path": folder.path,
                "parent_id": folder.parent_id,
                "is_public": folder.is_public,
                "created_at": folder.created_at.isoformat() if folder.created_at else None,
                "owner": folder.owner.full_name if folder.owner else "System",
                "can_write": has_folder_permission(db, current_user, folder, "write"),
                "can_delete": has_folder_permission(db, current_user, folder, "delete"),
                "share_status": share_status
            })

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
    
    files_with_status = []
    for file in files:
        share_status = get_share_status(db, "file", file.id)
        files_with_status.append({
            "id": file.id,
            "name": file.name,
            "size": file.size,
            "mime_type": file.mime_type,
            "created_at": file.created_at.isoformat() if file.created_at else None,
            "owner": file.owner.full_name if file.owner else "System",
            "share_status": share_status
        })

    return {
        "folder": {
            "id": folder.id,
            "name": folder.name,
            "path": folder.path
        },
        "files": files_with_status
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


@router.get("/files/{file_id}/preview")
async def preview_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Preview a file inline (without Content-Disposition attachment header)"""
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

    # Check if this is a Word or Excel document that needs conversion
    import subprocess
    import tempfile

    mime_type = file_metadata.mime_type or ''
    needs_conversion = (
        mime_type.startswith('application/vnd.openxmlformats-officedocument') or
        mime_type.startswith('application/msword') or
        mime_type.startswith('application/vnd.ms-excel') or
        file_metadata.name.lower().endswith(('.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'))
    )

    if needs_conversion:
        # Convert to PDF using LibreOffice
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Run LibreOffice conversion
                result = subprocess.run([
                    'libreoffice',
                    '--headless',
                    '--convert-to', 'pdf',
                    '--outdir', str(temp_path),
                    str(fs_path)
                ], capture_output=True, timeout=30)

                if result.returncode != 0:
                    raise HTTPException(status_code=500, detail="Failed to convert document to PDF")

                # Find the converted PDF
                pdf_files = list(temp_path.glob('*.pdf'))
                if not pdf_files:
                    raise HTTPException(status_code=500, detail="Conversion produced no output")

                pdf_path = pdf_files[0]

                # Read the PDF into memory since temp file will be deleted
                with open(pdf_path, 'rb') as f:
                    pdf_content = f.read()

                # Return the PDF content
                from fastapi.responses import Response
                return Response(
                    content=pdf_content,
                    media_type='application/pdf',
                    headers={
                        "Content-Disposition": f"inline; filename={Path(file_metadata.name).stem}.pdf"
                    }
                )
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=500, detail="Document conversion timed out")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error converting document: {str(e)}")

    # Return file without Content-Disposition header so it displays inline
    return FileResponse(
        path=fs_path,
        media_type=file_metadata.mime_type,
        headers={
            "Content-Disposition": f"inline; filename={file_metadata.name}"
        }
    )


@router.get("/users")
async def get_users(
    hr_db: Session = Depends(get_hr_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of active users for sharing"""
    from files.models.user import User as HRUser

    # Query active users from HR database
    users = hr_db.query(HRUser).filter(HRUser.is_active == True).order_by(HRUser.username).all()

    return [
        {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email
        }
        for user in users
    ]


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

    # Delete from database
    # We need to delete the folder using a raw query to avoid SQLAlchemy trying to manage relationships
    # The database CASCADE will handle deleting child files and shares
    from sqlalchemy import text
    folder_id_to_delete = folder.id

    # Close the current session to avoid conflicts
    db.expunge(folder)

    # Use raw SQL to delete the folder, letting database CASCADE handle the rest
    db.execute(text("DELETE FROM folders WHERE id = :folder_id"), {"folder_id": folder_id_to_delete})
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


@router.patch("/files/{file_id}/rename")
async def rename_file(
    file_id: int,
    new_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Rename a file"""
    file_metadata = db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
    if not file_metadata:
        raise HTTPException(status_code=404, detail="File not found")

    folder = file_metadata.folder
    if not has_folder_permission(db, current_user, folder, "write"):
        raise HTTPException(status_code=403, detail="No write permission on folder")

    # Get old and new paths
    old_fs_path = get_user_folder_path(file_metadata.owner_id, folder.path) / file_metadata.name
    new_fs_path = get_user_folder_path(file_metadata.owner_id, folder.path) / new_name

    # Check if file exists
    if not old_fs_path.exists():
        raise HTTPException(status_code=404, detail="File not found on filesystem")

    # Check if new name already exists
    if new_fs_path.exists():
        raise HTTPException(status_code=400, detail="A file with this name already exists")

    # Rename on filesystem
    old_fs_path.rename(new_fs_path)

    # Update database
    old_path = file_metadata.path
    new_path = f"{folder.path}/{new_name}"
    file_metadata.name = new_name
    file_metadata.path = new_path
    db.commit()

    return {
        "id": file_metadata.id,
        "name": file_metadata.name,
        "message": "File renamed successfully"
    }


@router.patch("/folders/{folder_id}/rename")
async def rename_folder(
    folder_id: int,
    new_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Rename a folder"""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    if not has_folder_permission(db, current_user, folder, "write"):
        raise HTTPException(status_code=403, detail="No write permission on folder")

    # Get old and new paths
    if folder.parent_id:
        parent = folder.parent
        new_path = f"{parent.path}/{new_name}"
    else:
        new_path = new_name

    old_fs_path = get_user_folder_path(folder.owner_id, folder.path)
    new_fs_path = get_user_folder_path(folder.owner_id, new_path)

    # Check if folder exists
    if not old_fs_path.exists():
        raise HTTPException(status_code=404, detail="Folder not found on filesystem")

    # Check if new name already exists
    if new_fs_path.exists():
        raise HTTPException(status_code=400, detail="A folder with this name already exists")

    # Rename on filesystem
    old_fs_path.rename(new_fs_path)

    # Update database - need to update this folder and all children
    old_path = folder.path
    folder.name = new_name
    folder.path = new_path

    # Update all child folders and files
    def update_children_paths(parent_folder):
        # Update child folders
        child_folders = db.query(Folder).filter(Folder.parent_id == parent_folder.id).all()
        for child in child_folders:
            old_child_path = child.path
            child.path = child.path.replace(old_path, new_path, 1)
            update_children_paths(child)

        # Update files in this folder
        files = db.query(FileMetadata).filter(FileMetadata.folder_id == parent_folder.id).all()
        for file in files:
            file.path = file.path.replace(old_path, new_path, 1)

    update_children_paths(folder)
    db.commit()

    return {
        "id": folder.id,
        "name": folder.name,
        "message": "Folder renamed successfully"
    }


@router.post("/files/{file_id}/move")
async def move_file(
    file_id: int,
    target_folder_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Move a file to a different folder"""
    file_metadata = db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
    if not file_metadata:
        raise HTTPException(status_code=404, detail="File not found")

    source_folder = file_metadata.folder
    target_folder = db.query(Folder).filter(Folder.id == target_folder_id).first()
    if not target_folder:
        raise HTTPException(status_code=404, detail="Target folder not found")

    # Check permissions
    if not has_folder_permission(db, current_user, source_folder, "delete"):
        raise HTTPException(status_code=403, detail="No delete permission on source folder")
    if not has_folder_permission(db, current_user, target_folder, "write"):
        raise HTTPException(status_code=403, detail="No write permission on target folder")

    # Get old and new paths
    old_fs_path = get_user_folder_path(file_metadata.owner_id, source_folder.path) / file_metadata.name
    new_fs_path = get_user_folder_path(file_metadata.owner_id, target_folder.path) / file_metadata.name

    # Check if file exists
    if not old_fs_path.exists():
        raise HTTPException(status_code=404, detail="File not found on filesystem")

    # Check if file with same name exists in target
    if new_fs_path.exists():
        raise HTTPException(status_code=400, detail="A file with this name already exists in target folder")

    # Move on filesystem
    shutil.move(str(old_fs_path), str(new_fs_path))

    # Update database
    file_metadata.folder_id = target_folder_id
    file_metadata.path = f"{target_folder.path}/{file_metadata.name}"
    db.commit()

    return {
        "id": file_metadata.id,
        "name": file_metadata.name,
        "folder_id": target_folder_id,
        "message": "File moved successfully"
    }


@router.post("/folders/{folder_id}/move")
async def move_folder(
    folder_id: int,
    target_parent_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Move a folder to a different location"""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    if not has_folder_permission(db, current_user, folder, "write"):
        raise HTTPException(status_code=403, detail="No write permission on folder")

    # Get target parent
    if target_parent_id:
        target_parent = db.query(Folder).filter(Folder.id == target_parent_id).first()
        if not target_parent:
            raise HTTPException(status_code=404, detail="Target parent folder not found")
        if not has_folder_permission(db, current_user, target_parent, "write"):
            raise HTTPException(status_code=403, detail="No write permission on target folder")
        new_parent_path = target_parent.path
    else:
        new_parent_path = ""

    # Calculate new path
    new_path = f"{new_parent_path}/{folder.name}" if new_parent_path else folder.name

    # Get filesystem paths
    old_fs_path = get_user_folder_path(folder.owner_id, folder.path)
    new_fs_path = get_user_folder_path(folder.owner_id, new_path)

    # Check if folder exists
    if not old_fs_path.exists():
        raise HTTPException(status_code=404, detail="Folder not found on filesystem")

    # Check if target location already has folder with same name
    if new_fs_path.exists():
        raise HTTPException(status_code=400, detail="A folder with this name already exists in target location")

    # Move on filesystem
    shutil.move(str(old_fs_path), str(new_fs_path))

    # Update database
    old_path = folder.path
    folder.parent_id = target_parent_id
    folder.path = new_path

    # Update all children paths
    def update_children_paths(parent_folder):
        child_folders = db.query(Folder).filter(Folder.parent_id == parent_folder.id).all()
        for child in child_folders:
            child.path = child.path.replace(old_path, new_path, 1)
            update_children_paths(child)

        files = db.query(FileMetadata).filter(FileMetadata.folder_id == parent_folder.id).all()
        for file in files:
            file.path = file.path.replace(old_path, new_path, 1)

    update_children_paths(folder)
    db.commit()

    return {
        "id": folder.id,
        "name": folder.name,
        "parent_id": target_parent_id,
        "message": "Folder moved successfully"
    }


@router.post("/files/{file_id}/copy")
async def copy_file(
    file_id: int,
    target_folder_id: int,
    new_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Copy a file to a different folder"""
    file_metadata = db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
    if not file_metadata:
        raise HTTPException(status_code=404, detail="File not found")

    source_folder = file_metadata.folder
    target_folder = db.query(Folder).filter(Folder.id == target_folder_id).first()
    if not target_folder:
        raise HTTPException(status_code=404, detail="Target folder not found")

    # Check permissions
    if not has_folder_permission(db, current_user, source_folder, "read"):
        raise HTTPException(status_code=403, detail="No read permission on source folder")
    if not has_folder_permission(db, current_user, target_folder, "write"):
        raise HTTPException(status_code=403, detail="No write permission on target folder")

    # Determine new name
    copy_name = new_name if new_name else f"{Path(file_metadata.name).stem} (copy){Path(file_metadata.name).suffix}"

    # Get paths
    source_fs_path = get_user_folder_path(file_metadata.owner_id, source_folder.path) / file_metadata.name
    target_fs_path = get_user_folder_path(file_metadata.owner_id, target_folder.path) / copy_name

    # Check if source exists
    if not source_fs_path.exists():
        raise HTTPException(status_code=404, detail="Source file not found on filesystem")

    # Check if target already exists
    if target_fs_path.exists():
        raise HTTPException(status_code=400, detail="A file with this name already exists in target folder")

    # Copy on filesystem
    shutil.copy2(str(source_fs_path), str(target_fs_path))

    # Create new file metadata
    new_file = FileMetadata(
        name=copy_name,
        path=f"{target_folder.path}/{copy_name}",
        folder_id=target_folder_id,
        owner_id=current_user.id,
        size=file_metadata.size,
        mime_type=file_metadata.mime_type
    )
    db.add(new_file)
    db.commit()
    db.refresh(new_file)

    return {
        "id": new_file.id,
        "name": new_file.name,
        "folder_id": target_folder_id,
        "message": "File copied successfully"
    }


@router.get("/search")
async def search_files(
    query: str = Query(..., min_length=1),
    file_type: Optional[str] = Query(None),
    date_range: Optional[str] = Query(None),
    size_range: Optional[str] = Query(None),
    owner_filter: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search files and folders with optional filters"""
    from datetime import datetime, timedelta
    from sqlalchemy import or_, and_

    # Build base query for folders
    folders_query = db.query(Folder).filter(
        or_(
            Folder.owner_id == current_user.id,
            Folder.id.in_(
                db.query(folder_permissions.c.folder_id).filter(
                    folder_permissions.c.user_id == current_user.id
                )
            )
        )
    )

    # Build base query for files
    files_query = db.query(FileMetadata).join(Folder).filter(
        or_(
            FileMetadata.owner_id == current_user.id,
            Folder.id.in_(
                db.query(folder_permissions.c.folder_id).filter(
                    folder_permissions.c.user_id == current_user.id
                )
            )
        )
    )

    # Apply search query
    if query:
        search_term = f"%{query}%"
        folders_query = folders_query.filter(Folder.name.ilike(search_term))
        files_query = files_query.filter(FileMetadata.name.ilike(search_term))

    # Apply owner filter
    if owner_filter == "me":
        folders_query = folders_query.filter(Folder.owner_id == current_user.id)
        files_query = files_query.filter(FileMetadata.owner_id == current_user.id)
    elif owner_filter == "shared":
        folders_query = folders_query.filter(Folder.owner_id != current_user.id)
        files_query = files_query.filter(FileMetadata.owner_id != current_user.id)

    # Apply date range filter
    if date_range:
        now = datetime.utcnow()
        if date_range == "today":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == "week":
            start_date = now - timedelta(days=7)
        elif date_range == "month":
            start_date = now - timedelta(days=30)
        elif date_range == "year":
            start_date = now - timedelta(days=365)
        else:
            start_date = None

        if start_date:
            folders_query = folders_query.filter(Folder.created_at >= start_date)
            files_query = files_query.filter(FileMetadata.created_at >= start_date)

    # Apply size range filter (only for files)
    if size_range:
        if size_range == "small":
            files_query = files_query.filter(FileMetadata.size < 1024 * 1024)  # < 1 MB
        elif size_range == "medium":
            files_query = files_query.filter(
                and_(
                    FileMetadata.size >= 1024 * 1024,
                    FileMetadata.size < 10 * 1024 * 1024
                )
            )  # 1-10 MB
        elif size_range == "large":
            files_query = files_query.filter(
                and_(
                    FileMetadata.size >= 10 * 1024 * 1024,
                    FileMetadata.size < 100 * 1024 * 1024
                )
            )  # 10-100 MB
        elif size_range == "xlarge":
            files_query = files_query.filter(FileMetadata.size >= 100 * 1024 * 1024)  # > 100 MB

    # Apply file type filter
    results_folders = []
    results_files = []

    if not file_type or file_type == "folder":
        folders = folders_query.limit(50).all()
        for folder in folders:
            share_status = get_share_status(db, "folder", folder.id)
            results_folders.append({
                "id": folder.id,
                "name": folder.name,
                "path": folder.path,
                "type": "folder",
                "owner": folder.owner.full_name if folder.owner else "System",
                "created_at": folder.created_at.isoformat() if folder.created_at else None,
                "share_status": share_status
            })

    if file_type != "folder":
        # Apply MIME type filtering
        if file_type == "document":
            files_query = files_query.filter(
                or_(
                    FileMetadata.mime_type.like("application/pdf%"),
                    FileMetadata.mime_type.like("application/msword%"),
                    FileMetadata.mime_type.like("application/vnd.openxmlformats-officedocument%"),
                    FileMetadata.mime_type.like("text/%")
                )
            )
        elif file_type == "image":
            files_query = files_query.filter(FileMetadata.mime_type.like("image/%"))
        elif file_type == "video":
            files_query = files_query.filter(FileMetadata.mime_type.like("video/%"))
        elif file_type == "audio":
            files_query = files_query.filter(FileMetadata.mime_type.like("audio/%"))
        elif file_type == "archive":
            files_query = files_query.filter(
                or_(
                    FileMetadata.mime_type.like("application/zip%"),
                    FileMetadata.mime_type.like("application/x-rar%"),
                    FileMetadata.mime_type.like("application/x-7z%"),
                    FileMetadata.mime_type.like("application/x-tar%")
                )
            )

        files = files_query.limit(50).all()
        for file in files:
            share_status = get_share_status(db, "file", file.id)
            results_files.append({
                "id": file.id,
                "name": file.name,
                "path": file.path,
                "type": "file",
                "size": file.size,
                "mime_type": file.mime_type,
                "owner": file.owner.full_name if file.owner else "System",
                "created_at": file.created_at.isoformat() if file.created_at else None,
                "folder_path": file.folder.path if file.folder else "/",
                "share_status": share_status
            })

    return {
        "query": query,
        "folders": results_folders,
        "files": results_files,
        "total": len(results_folders) + len(results_files)
    }


@router.get("/dashboard")
async def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get dashboard data: recent files, shared items, and stats"""
    from sqlalchemy import func, or_

    # Get recent files (last 15 files modified/created by or shared with user)
    recent_files_query = db.query(FileMetadata).join(
        Folder, FileMetadata.folder_id == Folder.id
    ).filter(
        or_(
            FileMetadata.owner_id == current_user.id,
            Folder.owner_id == current_user.id
        )
    ).order_by(FileMetadata.updated_at.desc()).limit(15)

    recent_files = []
    for file in recent_files_query.all():
        share_status = get_share_status(db, "file", file.id)
        recent_files.append({
            "id": file.id,
            "name": file.name,
            "size": file.size,
            "mime_type": file.mime_type,
            "folder_path": file.folder.path if file.folder else "/",
            "folder_id": file.folder_id,
            "updated_at": file.updated_at.isoformat() if file.updated_at else None,
            "owner": file.owner.full_name if file.owner else "System",
            "share_status": share_status
        })

    # Get items shared with me (limited to 10)
    shared_with_me = db.query(InternalShare).filter(
        InternalShare.shared_with_user_id == current_user.id,
        InternalShare.is_active == True
    ).order_by(InternalShare.shared_at.desc()).limit(10).all()

    shared_items = []
    for share in shared_with_me:
        if share.resource_type.value == "folder" and share.folder:
            shared_items.append({
                "id": share.folder.id,
                "name": share.folder.name,
                "type": "folder",
                "shared_by": share.sharer.full_name if share.sharer else "Unknown",
                "shared_at": share.shared_at.isoformat() if share.shared_at else None
            })
        elif share.resource_type.value == "file" and share.file:
            shared_items.append({
                "id": share.file.id,
                "name": share.file.name,
                "type": "file",
                "size": share.file.size,
                "shared_by": share.sharer.full_name if share.sharer else "Unknown",
                "shared_at": share.shared_at.isoformat() if share.shared_at else None
            })

    # Get stats
    total_files = db.query(func.count(FileMetadata.id)).filter(
        FileMetadata.owner_id == current_user.id
    ).scalar()

    total_storage = db.query(func.sum(FileMetadata.size)).filter(
        FileMetadata.owner_id == current_user.id
    ).scalar() or 0

    items_shared_by_me = db.query(func.count(InternalShare.id)).filter(
        InternalShare.shared_by == current_user.id,
        InternalShare.is_active == True
    ).scalar()

    items_shared_with_me = db.query(func.count(InternalShare.id)).filter(
        InternalShare.shared_with_user_id == current_user.id,
        InternalShare.is_active == True
    ).scalar()

    return {
        "recent_files": recent_files,
        "shared_with_me": shared_items,
        "stats": {
            "total_files": total_files,
            "total_storage": total_storage,
            "items_shared_by_me": items_shared_by_me,
            "items_shared_with_me": items_shared_with_me
        }
    }

"""OnlyOffice Document Server integration endpoints"""
from jose import jwt, JWTError
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from files.db.database import get_db
from files.models.user import User
from files.models.file_metadata import FileMetadata, Folder
from files.models.shares import InternalShare
from files.core.deps import get_current_user
from files.core.config import settings

router = APIRouter()

# OnlyOffice configuration
ONLYOFFICE_URL = "https://rm.swhgrp.com/onlyoffice"
STORAGE_PATH = Path("/app/storage")
# Use centralized configuration for JWT secret


def check_folder_access(db: Session, folder_id: int, user_id: int):
    """
    Check if user has access to a folder or any of its parent folders.
    Returns (has_access, can_edit) tuple.
    """
    current_folder_id = folder_id

    while current_folder_id:
        # Check if this folder is shared with the user
        folder_share = db.query(InternalShare).filter(
            InternalShare.resource_type == "folder",
            InternalShare.folder_id == current_folder_id,
            InternalShare.shared_with_user_id == user_id,
            InternalShare.is_active == True
        ).first()

        if folder_share:
            return (True, folder_share.can_edit)

        # Get parent folder
        folder = db.query(Folder).filter(Folder.id == current_folder_id).first()
        if not folder or not folder.parent_id:
            break

        current_folder_id = folder.parent_id

    return (False, False)


class OnlyOfficeConfig(BaseModel):
    """OnlyOffice editor configuration"""
    documentType: str
    document: dict
    editorConfig: dict
    token: Optional[str] = None


def get_document_type(filename: str) -> str:
    """Determine document type based on file extension"""
    ext = filename.lower().split('.')[-1]

    # Word documents
    if ext in ['doc', 'docx', 'docm', 'dot', 'dotx', 'dotm', 'odt', 'fodt', 'ott', 'rtf', 'txt', 'html', 'htm', 'mht', 'pdf', 'djvu', 'fb2', 'epub', 'xps']:
        return 'word'

    # Spreadsheets
    if ext in ['xls', 'xlsx', 'xlsm', 'xlt', 'xltx', 'xltm', 'ods', 'fods', 'ots', 'csv']:
        return 'cell'

    # Presentations
    if ext in ['pps', 'ppsx', 'ppsm', 'ppt', 'pptx', 'pptm', 'pot', 'potx', 'potm', 'odp', 'fodp', 'otp']:
        return 'slide'

    return 'word'  # Default to word


def can_edit(filename: str) -> bool:
    """Check if file type supports editing"""
    ext = filename.lower().split('.')[-1]
    editable_extensions = [
        # Word
        'docx', 'docm', 'dotx', 'dotm', 'odt', 'fodt', 'ott', 'rtf', 'txt',
        # Spreadsheet
        'xlsx', 'xlsm', 'xltx', 'xltm', 'ods', 'fods', 'ots', 'csv',
        # Presentation
        'pptx', 'pptm', 'potx', 'potm', 'odp', 'fodp', 'otp'
    ]
    return ext in editable_extensions


@router.get("/files/{file_id}/editor-config")
async def get_editor_config(
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get OnlyOffice editor configuration for a file"""

    # Get file metadata
    file_meta = db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
    if not file_meta:
        raise HTTPException(status_code=404, detail="File not found")

    # Check permissions - owner or has internal share with edit permission
    has_access = False
    can_edit_file = False

    if file_meta.owner_id == current_user.id:
        # User owns the file
        has_access = True
        can_edit_file = True
    else:
        # Check if file is directly shared with user
        share = db.query(InternalShare).filter(
            InternalShare.resource_type == "file",
            InternalShare.file_id == file_id,
            InternalShare.shared_with_user_id == current_user.id,
            InternalShare.is_active == True
        ).first()

        if share:
            has_access = True
            can_edit_file = share.can_edit
        else:
            # Check if file is in a shared folder (or any ancestor folder is shared)
            # Files inherit permissions from their parent folders
            if file_meta.folder_id:
                has_access, can_edit_file = check_folder_access(db, file_meta.folder_id, current_user.id)

    if not has_access:
        raise HTTPException(status_code=403, detail="No access to this file")

    # Generate a temporary download token (valid for 24 hours)
    # This allows OnlyOffice to download the file without user session
    download_token_payload = {
        "file_id": file_id,
        "user_id": current_user.id,
        "exp": datetime.now(timezone.utc).timestamp() + 86400  # 24 hours
    }
    download_token = jwt.encode(download_token_payload, settings.ONLYOFFICE_JWT_SECRET, algorithm='HS256')

    # Build file URLs
    download_url = f"https://rm.swhgrp.com/files/api/files/files/{file_id}/download?token={download_token}"
    callback_url = f"https://rm.swhgrp.com/files/api/onlyoffice/callback/{file_id}"

    # Generate document key (unique identifier for the document version)
    # Use file ID + modification time to ensure key changes when file is updated
    mod_time = file_meta.updated_at.timestamp() if file_meta.updated_at else datetime.now(timezone.utc).timestamp()
    doc_key = hashlib.md5(f"{file_id}_{mod_time}".encode()).hexdigest()

    # Determine document type and edit permissions
    doc_type = get_document_type(file_meta.name)
    # File is editable if user has edit permission AND file type supports editing
    editable = can_edit_file and can_edit(file_meta.name)

    # Build editor configuration
    config = {
        "documentType": doc_type,
        "document": {
            "fileType": file_meta.name.split('.')[-1].lower(),
            "key": doc_key,
            "title": file_meta.name,
            "url": download_url,
            "permissions": {
                "edit": editable,
                "download": True,
                "print": True,
                "review": True,
                "comment": editable
            }
        },
        "editorConfig": {
            "callbackUrl": callback_url,
            "mode": "edit" if editable else "view",
            "lang": "en",
            "user": {
                "id": str(current_user.id),
                "name": current_user.full_name or current_user.username
            },
            "customization": {
                "autosave": True,
                "forcesave": True,
                "comments": True,
                "feedback": False,
                "goback": {
                    "url": "https://rm.swhgrp.com/files/"
                },
                "compactHeader": False,
                "compactToolbar": False,
                "toolbar": True
            }
        },
        "width": "100%",
        "height": "100%"
    }

    # Sign the configuration with JWT
    token = jwt.encode(config, settings.ONLYOFFICE_JWT_SECRET, algorithm='HS256')
    config["token"] = token

    return config


@router.post("/onlyoffice/callback/{file_id}")
async def onlyoffice_callback(
    file_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle OnlyOffice callback when document is saved"""

    # Get the callback data
    data = await request.json()

    # Verify JWT token
    token = data.get("token")
    if not token:
        # Try to get token from header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if token:
        try:
            jwt.decode(token, settings.ONLYOFFICE_JWT_SECRET, algorithms=['HS256'])
        except JWTError:
            raise HTTPException(status_code=403, detail="Invalid token")

    # Get file metadata
    file_meta = db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
    if not file_meta:
        raise HTTPException(status_code=404, detail="File not found")

    # Handle different callback statuses
    status = data.get("status")

    # Status codes:
    # 0 - no document with the key identifier could be found
    # 1 - document is being edited
    # 2 - document is ready for saving
    # 3 - document saving error has occurred
    # 4 - document is closed with no changes
    # 6 - document is being edited, but the current document state is saved
    # 7 - error has occurred while force saving the document

    if status in [2, 6]:  # Document ready for saving or force save
        # Download the saved document from OnlyOffice
        download_url = data.get("url")
        if download_url:
            import httpx

            # Download the file
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(download_url)
                if response.status_code == 200:
                    # Build filesystem path
                    folder_path = file_meta.folder.path if file_meta.folder else "/"
                    folder_path = folder_path.lstrip('/')
                    user_storage = STORAGE_PATH / f"user_{file_meta.owner_id}" / folder_path
                    fs_path = user_storage / file_meta.name

                    # Save the file
                    fs_path.write_bytes(response.content)

                    # Update file metadata
                    file_meta.size = len(response.content)
                    file_meta.updated_at = datetime.now(timezone.utc)
                    db.commit()

    # Return success response
    return {"error": 0}

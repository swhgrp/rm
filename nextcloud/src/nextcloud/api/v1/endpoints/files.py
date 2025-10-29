"""
Files API endpoints for Nextcloud WebDAV operations
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from io import BytesIO
from typing import Optional

from nextcloud.core.deps import get_current_user, require_nextcloud_setup
from nextcloud.models.user import User
from nextcloud.schemas.files import (
    FileListResponse,
    FileItem,
    FileUploadResponse,
    FileDeleteRequest,
    FolderCreateRequest,
    FileMoveRequest,
    FileOperationResponse
)
from nextcloud.services.webdav_client import NextcloudWebDAVClient

router = APIRouter()


@router.get("/list", response_model=FileListResponse)
async def list_files(
    path: str = Query("/", description="Directory path to list"),
    current_user: User = Depends(require_nextcloud_setup)
):
    """
    List files and folders in a directory

    Args:
        path: Directory path (default: root)

    Returns:
        List of files and folders with metadata
    """
    try:
        client = NextcloudWebDAVClient(current_user)
        items = client.list_directory(path)

        # Convert to Pydantic models
        file_items = [FileItem(**item) for item in items]

        # Determine parent path
        parent_path = None
        if path != "/" and path != "":
            parent_path = "/".join(path.rstrip("/").split("/")[:-1]) or "/"

        return FileListResponse(
            current_path=path,
            items=file_items,
            parent_path=parent_path
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list directory: {str(e)}"
        )


@router.get("/download")
async def download_file(
    path: str = Query(..., description="File path to download"),
    current_user: User = Depends(require_nextcloud_setup)
):
    """
    Download a file from Nextcloud

    Args:
        path: File path

    Returns:
        File content as streaming response
    """
    try:
        client = NextcloudWebDAVClient(current_user)

        # Download file
        content = client.download_file(path)

        # Get filename from path
        filename = path.split("/")[-1]

        # Return as streaming response
        return StreamingResponse(
            BytesIO(content),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download file: {str(e)}"
        )


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    path: str = Query("/", description="Destination directory path"),
    current_user: User = Depends(require_nextcloud_setup)
):
    """
    Upload a file to Nextcloud

    Args:
        file: File to upload
        path: Destination directory

    Returns:
        Upload confirmation with file info
    """
    try:
        client = NextcloudWebDAVClient(current_user)

        # Construct full file path
        if not path.endswith("/"):
            path += "/"
        remote_path = f"{path}{file.filename}"

        # Upload file
        result = client.upload_file(file.file, remote_path)

        return FileUploadResponse(
            success=True,
            message=f"File '{file.filename}' uploaded successfully",
            path=remote_path,
            size=result.get('size')
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}"
        )


@router.post("/mkdir", response_model=FileOperationResponse)
async def create_folder(
    request: FolderCreateRequest,
    current_user: User = Depends(require_nextcloud_setup)
):
    """
    Create a new folder

    Args:
        request: Folder creation request with path

    Returns:
        Operation confirmation
    """
    try:
        client = NextcloudWebDAVClient(current_user)
        client.create_directory(request.path)

        return FileOperationResponse(
            success=True,
            message=f"Folder created successfully"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create folder: {str(e)}"
        )


@router.delete("/delete", response_model=FileOperationResponse)
async def delete_file_or_folder(
    request: FileDeleteRequest,
    current_user: User = Depends(require_nextcloud_setup)
):
    """
    Delete a file or folder

    Args:
        request: Deletion request with path

    Returns:
        Operation confirmation
    """
    try:
        client = NextcloudWebDAVClient(current_user)
        client.delete(request.path)

        return FileOperationResponse(
            success=True,
            message="Deleted successfully"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete: {str(e)}"
        )


@router.post("/move", response_model=FileOperationResponse)
async def move_file(
    request: FileMoveRequest,
    current_user: User = Depends(require_nextcloud_setup)
):
    """
    Move or rename a file/folder

    Args:
        request: Move request with source and destination paths

    Returns:
        Operation confirmation
    """
    try:
        client = NextcloudWebDAVClient(current_user)
        client.move(request.source_path, request.destination_path)

        return FileOperationResponse(
            success=True,
            message="Moved/renamed successfully"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to move: {str(e)}"
        )

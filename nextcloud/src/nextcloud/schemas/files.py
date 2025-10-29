"""
Pydantic schemas for file operations
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class FileItem(BaseModel):
    """File or folder item"""
    name: str
    path: str
    is_directory: bool
    size: Optional[int] = None
    modified: Optional[datetime] = None
    mime_type: Optional[str] = None
    etag: Optional[str] = None


class FileListResponse(BaseModel):
    """Response for file listing"""
    current_path: str
    items: List[FileItem]
    parent_path: Optional[str] = None


class FileUploadResponse(BaseModel):
    """Response after file upload"""
    success: bool
    message: str
    path: str
    size: Optional[int] = None


class FileDownloadRequest(BaseModel):
    """Request to download a file"""
    path: str


class FileDeleteRequest(BaseModel):
    """Request to delete a file or folder"""
    path: str


class FolderCreateRequest(BaseModel):
    """Request to create a new folder"""
    path: str


class FileMoveRequest(BaseModel):
    """Request to move/rename a file"""
    source_path: str
    destination_path: str


class FileSearchRequest(BaseModel):
    """Request to search files"""
    query: str
    path: Optional[str] = "/"


class FileOperationResponse(BaseModel):
    """Generic response for file operations"""
    success: bool
    message: str

"""
Nextcloud WebDAV client for file operations
"""
from typing import List, Optional, BinaryIO
from webdav3.client import Client
from webdav3.exceptions import WebDavException
import os
from datetime import datetime

from nextcloud.core.config import settings
from nextcloud.core.security import decrypt_credential
from nextcloud.models.user import User


class NextcloudWebDAVClient:
    """
    WebDAV client for Nextcloud file operations

    Handles file browsing, upload, download, and folder management.
    """

    def __init__(self, user: User):
        """
        Initialize WebDAV client with user credentials

        Args:
            user: User object with Nextcloud credentials
        """
        if not user.nextcloud_username or not user.nextcloud_encrypted_password:
            raise ValueError("User does not have Nextcloud credentials configured")

        # Decrypt password
        password = decrypt_credential(user.nextcloud_encrypted_password)

        # WebDAV URL
        webdav_url = f"{settings.NEXTCLOUD_URL}{settings.NEXTCLOUD_WEBDAV_PATH}/files/{user.nextcloud_username}/"

        # Configure WebDAV client
        self.client = Client({
            'webdav_hostname': webdav_url,
            'webdav_login': user.nextcloud_username,
            'webdav_password': password,
            'webdav_timeout': 30
        })

        self.user = user

    def list_directory(self, path: str = "/") -> List[dict]:
        """
        List files and folders in a directory

        Args:
            path: Directory path (relative to user's root)

        Returns:
            List of file/folder dictionaries with metadata
        """
        try:
            # Ensure path starts with /
            if not path.startswith("/"):
                path = f"/{path}"

            # List directory contents
            items = self.client.list(path, get_info=True)

            result = []
            for item in items:
                # Skip the current directory itself
                if item['path'] == path or item['path'] == path + '/':
                    continue

                # Parse item info
                item_info = {
                    'name': os.path.basename(item['path'].rstrip('/')),
                    'path': item['path'].rstrip('/'),
                    'is_directory': item.get('isdir', False),
                    'size': item.get('size'),
                    'modified': item.get('modified'),
                    'mime_type': item.get('content_type'),
                    'etag': item.get('etag')
                }
                result.append(item_info)

            return result

        except WebDavException as e:
            raise Exception(f"Failed to list directory: {str(e)}")

    def download_file(self, remote_path: str) -> bytes:
        """
        Download a file from Nextcloud

        Args:
            remote_path: Path to file on Nextcloud

        Returns:
            File content as bytes
        """
        try:
            if not remote_path.startswith("/"):
                remote_path = f"/{remote_path}"

            # Download to memory
            content = self.client.resource(remote_path).read()
            return content

        except WebDavException as e:
            raise Exception(f"Failed to download file: {str(e)}")

    def upload_file(self, local_file: BinaryIO, remote_path: str) -> dict:
        """
        Upload a file to Nextcloud

        Args:
            local_file: File-like object to upload
            remote_path: Destination path on Nextcloud

        Returns:
            Dictionary with upload info
        """
        try:
            if not remote_path.startswith("/"):
                remote_path = f"/{remote_path}"

            # Upload file
            self.client.upload_to(local_file, remote_path)

            # Get file info
            info = self.client.info(remote_path)

            return {
                'success': True,
                'path': remote_path,
                'size': info.get('size')
            }

        except WebDavException as e:
            raise Exception(f"Failed to upload file: {str(e)}")

    def create_directory(self, path: str) -> bool:
        """
        Create a new directory

        Args:
            path: Directory path to create

        Returns:
            True if successful
        """
        try:
            if not path.startswith("/"):
                path = f"/{path}"

            self.client.mkdir(path)
            return True

        except WebDavException as e:
            raise Exception(f"Failed to create directory: {str(e)}")

    def delete(self, path: str) -> bool:
        """
        Delete a file or directory

        Args:
            path: Path to delete

        Returns:
            True if successful
        """
        try:
            if not path.startswith("/"):
                path = f"/{path}"

            self.client.clean(path)
            return True

        except WebDavException as e:
            raise Exception(f"Failed to delete: {str(e)}")

    def move(self, source_path: str, dest_path: str) -> bool:
        """
        Move or rename a file/directory

        Args:
            source_path: Current path
            dest_path: New path

        Returns:
            True if successful
        """
        try:
            if not source_path.startswith("/"):
                source_path = f"/{source_path}"
            if not dest_path.startswith("/"):
                dest_path = f"/{dest_path}"

            self.client.move(source_path, dest_path)
            return True

        except WebDavException as e:
            raise Exception(f"Failed to move: {str(e)}")

    def file_exists(self, path: str) -> bool:
        """
        Check if a file or directory exists

        Args:
            path: Path to check

        Returns:
            True if exists, False otherwise
        """
        try:
            if not path.startswith("/"):
                path = f"/{path}"

            return self.client.check(path)

        except WebDavException:
            return False

    def get_file_info(self, path: str) -> Optional[dict]:
        """
        Get detailed file information

        Args:
            path: File path

        Returns:
            Dictionary with file metadata or None if not found
        """
        try:
            if not path.startswith("/"):
                path = f"/{path}"

            info = self.client.info(path)
            return {
                'name': os.path.basename(path),
                'path': path,
                'is_directory': info.get('isdir', False),
                'size': info.get('size'),
                'modified': info.get('modified'),
                'mime_type': info.get('content_type'),
                'etag': info.get('etag')
            }

        except WebDavException:
            return None

"""
Custom WebDAV provider integrated with Files system database

This provider ensures WebDAV operations (upload, delete, move, etc.) are tracked
in the Files database, maintaining consistency between WebDAV and web interface.
"""
import os
import mimetypes
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from wsgidav.dav_provider import DAVProvider, DAVCollection, DAVNonCollection
from wsgidav.dav_error import DAVError, HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_CONFLICT
from sqlalchemy.orm import Session

from files.db.database import SessionLocal
from files.models.file_metadata import FileMetadata, Folder
from files.models.user import User
import logging

logger = logging.getLogger(__name__)

# Base storage path
STORAGE_PATH = Path("/app/storage")


class DatabaseBackedDAVResource:
    """Base class for DAV resources backed by database"""

    def __init__(self, path: str, environ: dict, db: Session, user: User):
        self.path = path
        self.environ = environ
        self.db = db
        self.user = user
        self._user_storage_path = STORAGE_PATH / f"user_{user.id}"

    def get_filesystem_path(self) -> Path:
        """Convert DAV path to filesystem path"""
        # Path comes in already normalized (e.g., /file.txt or /subdir/file.txt)
        # Remove leading / and use directly as relative path within user storage
        relative_path = self.path.lstrip('/')

        # Handle root path
        if not relative_path:
            return self._user_storage_path

        full_path = self._user_storage_path / relative_path
        return full_path

    def get_database_path(self) -> str:
        """Get path for database storage (relative to user storage)"""
        fs_path = self.get_filesystem_path()
        return '/' + str(fs_path.relative_to(self._user_storage_path))


class DatabaseBackedDAVCollection(DAVCollection, DatabaseBackedDAVResource):
    """WebDAV collection (folder) backed by database"""

    def __init__(self, path: str, environ: dict, db: Session, user: User, folder: Optional[Folder] = None):
        DAVCollection.__init__(self, path, environ)
        DatabaseBackedDAVResource.__init__(self, path, environ, db, user)
        self.folder = folder

    def get_member_names(self):
        """List folder contents"""
        fs_path = self.get_filesystem_path()

        if not fs_path.exists():
            return []

        try:
            return [item.name for item in fs_path.iterdir() if not item.name.startswith('.')]
        except Exception as e:
            logger.error(f"Error listing directory {fs_path}: {e}")
            return []

    def get_member(self, name):
        """Get a member resource by name"""
        member_path = f"{self.path.rstrip('/')}/{name}"
        fs_path = self.get_filesystem_path() / name

        if not fs_path.exists():
            return None

        if fs_path.is_dir():
            # Try to find folder in database
            db_path = self.get_database_path().rstrip('/') + '/' + name
            folder = self.db.query(Folder).filter(
                Folder.path == db_path,
                Folder.owner_id == self.user.id
            ).first()
            return DatabaseBackedDAVCollection(member_path, self.environ, self.db, self.user, folder)
        else:
            # Try to find file in database
            db_path = self.get_database_path().rstrip('/') + '/' + name
            file_meta = self.db.query(FileMetadata).filter(
                FileMetadata.path == db_path,
                FileMetadata.owner_id == self.user.id
            ).first()
            return DatabaseBackedDAVFile(member_path, self.environ, self.db, self.user, file_meta)

    def create_empty_resource(self, name):
        """Create a new empty file"""
        member_path = f"{self.path.rstrip('/')}/{name}"
        return DatabaseBackedDAVFile(member_path, self.environ, self.db, self.user, None)

    def create_collection(self, name):
        """Create a new subfolder"""
        fs_path = self.get_filesystem_path() / name
        db_path = self.get_database_path().rstrip('/') + '/' + name

        # Create filesystem directory
        fs_path.mkdir(parents=True, exist_ok=True)

        # Create database entry
        try:
            # Find parent folder
            parent_path = self.get_database_path()
            parent_folder = self.db.query(Folder).filter(
                Folder.path == parent_path,
                Folder.owner_id == self.user.id
            ).first()

            # If parent doesn't exist, create it
            if not parent_folder:
                parent_folder = Folder(
                    name=os.path.basename(parent_path.rstrip('/')),
                    path=parent_path,
                    owner_id=self.user.id,
                    parent_id=None
                )
                self.db.add(parent_folder)
                self.db.flush()

            # Create new folder
            new_folder = Folder(
                name=name,
                path=db_path,
                owner_id=self.user.id,
                parent_id=parent_folder.id
            )
            self.db.add(new_folder)
            self.db.commit()

            logger.info(f"Created folder: {db_path} for user {self.user.username}")

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating folder in database: {e}")
            raise DAVError(HTTP_CONFLICT, f"Failed to create folder: {e}")

    def delete(self):
        """Delete this folder"""
        fs_path = self.get_filesystem_path()
        db_path = self.get_database_path()

        # Delete from database
        if self.folder:
            try:
                # Delete all files in folder
                files = self.db.query(FileMetadata).filter(
                    FileMetadata.folder_id == self.folder.id
                ).all()
                for f in files:
                    self.db.delete(f)

                # Delete folder
                self.db.delete(self.folder)
                self.db.commit()
                logger.info(f"Deleted folder from database: {db_path}")
            except Exception as e:
                self.db.rollback()
                logger.error(f"Error deleting folder from database: {e}")

        # Delete from filesystem
        if fs_path.exists():
            import shutil
            shutil.rmtree(fs_path)
            logger.info(f"Deleted folder from filesystem: {fs_path}")

    def get_creation_date(self):
        if self.folder and self.folder.created_at:
            return self.folder.created_at.timestamp()
        fs_path = self.get_filesystem_path()
        if fs_path.exists():
            return fs_path.stat().st_ctime
        return None

    def get_last_modified(self):
        if self.folder and self.folder.updated_at:
            return self.folder.updated_at.timestamp()
        fs_path = self.get_filesystem_path()
        if fs_path.exists():
            return fs_path.stat().st_mtime
        return None

    def get_display_name(self):
        return os.path.basename(self.path.rstrip('/'))


class DatabaseBackedDAVFile(DAVNonCollection, DatabaseBackedDAVResource):
    """WebDAV file backed by database"""

    def __init__(self, path: str, environ: dict, db: Session, user: User, file_meta: Optional[FileMetadata] = None):
        DAVNonCollection.__init__(self, path, environ)
        DatabaseBackedDAVResource.__init__(self, path, environ, db, user)
        self.file_meta = file_meta

    def get_content_length(self):
        if self.file_meta:
            return self.file_meta.size
        fs_path = self.get_filesystem_path()
        if fs_path.exists():
            return fs_path.stat().st_size
        return 0

    def get_content_type(self):
        if self.file_meta and self.file_meta.mime_type:
            return self.file_meta.mime_type

        # Guess from filename
        mime_type, _ = mimetypes.guess_type(self.path)
        return mime_type or 'application/octet-stream'

    def get_creation_date(self):
        if self.file_meta and self.file_meta.created_at:
            return self.file_meta.created_at.timestamp()
        fs_path = self.get_filesystem_path()
        if fs_path.exists():
            return fs_path.stat().st_ctime
        return None

    def get_last_modified(self):
        if self.file_meta and self.file_meta.updated_at:
            return self.file_meta.updated_at.timestamp()
        fs_path = self.get_filesystem_path()
        if fs_path.exists():
            return fs_path.stat().st_mtime
        return None

    def get_display_name(self):
        return os.path.basename(self.path)

    def get_content(self):
        """Stream file content"""
        fs_path = self.get_filesystem_path()
        if not fs_path.exists():
            raise DAVError(HTTP_NOT_FOUND)
        return open(fs_path, 'rb')

    def begin_write(self, content_type=None):
        """Start writing file content"""
        fs_path = self.get_filesystem_path()
        fs_path.parent.mkdir(parents=True, exist_ok=True)
        return open(fs_path, 'wb')

    def end_write(self, with_errors):
        """Finish writing file and update database"""
        if with_errors:
            return

        fs_path = self.get_filesystem_path()
        db_path = self.get_database_path()

        if not fs_path.exists():
            logger.error(f"File not found after write: {fs_path}")
            return

        try:
            # Get file info
            stat = fs_path.stat()
            mime_type, _ = mimetypes.guess_type(str(fs_path))

            # Find or create parent folder
            parent_path = str(Path(db_path).parent)
            if parent_path == '/':
                parent_path = '/'

            parent_folder = self.db.query(Folder).filter(
                Folder.path == parent_path,
                Folder.owner_id == self.user.id
            ).first()

            if not parent_folder:
                # Create root folder for user
                parent_folder = Folder(
                    name=os.path.basename(parent_path) or 'root',
                    path=parent_path,
                    owner_id=self.user.id,
                    parent_id=None
                )
                self.db.add(parent_folder)
                self.db.flush()

            # Update or create file metadata
            if self.file_meta:
                # Update existing
                self.file_meta.size = stat.st_size
                self.file_meta.mime_type = mime_type
                self.file_meta.updated_at = datetime.now(timezone.utc)
            else:
                # Create new
                self.file_meta = FileMetadata(
                    name=os.path.basename(db_path),
                    path=db_path,
                    folder_id=parent_folder.id,
                    owner_id=self.user.id,
                    size=stat.st_size,
                    mime_type=mime_type
                )
                self.db.add(self.file_meta)

            self.db.commit()
            logger.info(f"Saved file to database: {db_path} ({stat.st_size} bytes)")

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving file to database: {e}")
            raise DAVError(HTTP_CONFLICT, f"Failed to save file: {e}")

    def delete(self):
        """Delete this file"""
        fs_path = self.get_filesystem_path()

        # Delete from database first
        if self.file_meta:
            try:
                self.db.delete(self.file_meta)
                self.db.commit()
                logger.info(f"Deleted file from database: {self.file_meta.path}")
            except Exception as e:
                self.db.rollback()
                logger.error(f"Error deleting file from database: {e}")
                raise DAVError(HTTP_CONFLICT, f"Failed to delete from database: {e}")

        # Delete from filesystem
        if fs_path.exists():
            try:
                fs_path.unlink()
                logger.info(f"Deleted file from filesystem: {fs_path}")
            except Exception as e:
                logger.error(f"Error deleting file from filesystem: {e}")
                raise DAVError(HTTP_CONFLICT, f"Failed to delete from filesystem: {e}")
        else:
            logger.warning(f"File not found on filesystem: {fs_path}")

    def copy_move_single(self, dest_path, is_move):
        """Handle file copy/move"""
        # This is handled by the provider's move_resource method
        pass

    def support_ranges(self):
        return True

    def support_etag(self):
        return True

    def get_etag(self):
        fs_path = self.get_filesystem_path()
        if fs_path.exists():
            stat = fs_path.stat()
            # Return without quotes - WsgiDAV will add them
            return f"{stat.st_mtime}-{stat.st_size}"
        return None


class DatabaseBackedDAVProvider(DAVProvider):
    """
    WebDAV provider that integrates with Files system database

    All file operations are tracked in the database, ensuring consistency
    between WebDAV access and the web interface.
    """

    def __init__(self):
        super().__init__()
        self.readonly = False

    def is_readonly(self):
        """Allow write operations"""
        return False

    def _get_user_from_environ(self, environ) -> Optional[User]:
        """Extract user from environ and fetch from database"""
        db = SessionLocal()
        try:
            # Try X-Remote-User header (from Portal SSO via nginx)
            remote_user = environ.get("HTTP_X_REMOTE_USER")
            if remote_user:
                user = db.query(User).filter(User.username == remote_user).first()
                if user:
                    logger.info(f"WebDAV: User '{remote_user}' from X-Remote-User header")
                    return user

            # Try basic auth username
            auth_user = environ.get("http_authenticator.username")
            if auth_user:
                user = db.query(User).filter(User.username == auth_user).first()
                if user:
                    logger.info(f"WebDAV: User '{auth_user}' from basic auth")
                    return user

            # Extract from path /username/...
            path_info = environ.get("PATH_INFO", "")
            if path_info.startswith("/"):
                parts = path_info[1:].split("/")
                if parts and parts[0]:
                    username = parts[0]
                    user = db.query(User).filter(User.username == username).first()
                    if user:
                        logger.info(f"WebDAV: User '{username}' from path")
                        return user

            logger.warning("WebDAV: No user found in request")
            return None

        finally:
            db.close()

    def get_resource_inst(self, path, environ):
        """Get a DAV resource for the given path"""
        db = SessionLocal()

        try:
            # Attach provider to environ (required by WsgiDAV)
            environ['wsgidav.provider'] = self

            # Get authenticated user
            user = self._get_user_from_environ(environ)
            if not user:
                raise DAVError(HTTP_FORBIDDEN, "Authentication required")

            # Attach db session to environ for resource use
            environ['wsgidav.db'] = db

            # Normalize path (remove /username prefix if present)
            if path.startswith(f"/{user.username}/"):
                path = '/' + path[len(f"/{user.username}/"):]
            elif path == f"/{user.username}":
                path = '/'

            # Root collection
            if path == '/' or path == '':
                return DatabaseBackedDAVCollection('/', environ, db, user, None)

            # Determine if it's a file or folder
            user_storage = STORAGE_PATH / f"user_{user.id}"
            relative_path = path.lstrip('/')
            fs_path = user_storage / relative_path

            # Check database first
            db_path = '/' + relative_path

            # If it exists on filesystem, use that to determine type
            if fs_path.exists():
                if fs_path.is_dir():
                    folder = db.query(Folder).filter(
                        Folder.path == db_path,
                        Folder.owner_id == user.id
                    ).first()
                    return DatabaseBackedDAVCollection(path, environ, db, user, folder)
                else:
                    file_meta = db.query(FileMetadata).filter(
                        FileMetadata.path == db_path,
                        FileMetadata.owner_id == user.id
                    ).first()
                    return DatabaseBackedDAVFile(path, environ, db, user, file_meta)

            # Doesn't exist - check database to see if it's a known folder or file
            folder = db.query(Folder).filter(
                Folder.path == db_path,
                Folder.owner_id == user.id
            ).first()
            if folder:
                return DatabaseBackedDAVCollection(path, environ, db, user, folder)

            file_meta = db.query(FileMetadata).filter(
                FileMetadata.path == db_path,
                FileMetadata.owner_id == user.id
            ).first()
            if file_meta:
                return DatabaseBackedDAVFile(path, environ, db, user, file_meta)

            # Not in database either - check if path looks like a file (has extension)
            # If no extension and doesn't end with /, treat as potential folder
            # If has extension or ends with filename pattern, treat as file
            import os
            name = os.path.basename(path)
            if '.' in name or path.endswith('.txt') or path.endswith('.pdf'):
                # Looks like a file
                return DatabaseBackedDAVFile(path, environ, db, user, None)
            else:
                # Looks like a folder
                return DatabaseBackedDAVCollection(path, environ, db, user, None)

        except DAVError:
            db.close()
            raise
        except Exception as e:
            db.close()
            logger.error(f"Error getting resource for path {path}: {e}")
            raise DAVError(HTTP_CONFLICT, str(e))

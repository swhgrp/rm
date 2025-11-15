"""WebDAV server for file synchronization"""
import os
from pathlib import Path
from wsgidav.wsgidav_app import WsgiDAVApp
from wsgidav.dav_provider import DAVProvider
from wsgidav.dav_error import HTTP_FORBIDDEN, DAVError
from wsgidav.fs_dav_provider import FilesystemProvider
import logging

logger = logging.getLogger(__name__)

# Base storage path
STORAGE_PATH = Path("/app/storage")


class UserIsolatedFilesystemProvider(FilesystemProvider):
    """
    Filesystem provider that isolates users to their own storage directories
    Maps /webdav/username/ to /app/storage/user_{id}/
    """

    def __init__(self, root_path):
        super().__init__(root_path)
        self.root_path = Path(root_path)

    def _get_user_from_environ(self, environ):
        """Extract username from environ (either from path or X-Remote-User header)"""
        # Try X-Remote-User header first (set by nginx after Portal auth)
        remote_user = environ.get("HTTP_X_REMOTE_USER")
        if remote_user:
            return remote_user

        # Fallback: extract from path /webdav/username/...
        path_info = environ.get("PATH_INFO", "")
        if path_info.startswith("/"):
            path_parts = path_info[1:].split("/")
            if len(path_parts) > 0 and path_parts[0]:
                return path_parts[0]

        return None

    def _get_user_storage_path(self, username):
        """
        Map username to storage path

        For now, simple mapping: username -> user_2 (main user)
        In production, would query database to get user_id from username
        """
        # TODO: Query database to get user_id from username
        # For now, hardcode to user_2 (main admin user)
        if username == "andy":
            return self.root_path / "user_2"

        # Default: create user folder based on username
        return self.root_path / f"user_{username}"

    def _normalize_path(self, path, environ):
        """
        Normalize path to user's storage directory

        Incoming path: /webdav/andy/Documents/file.pdf
        Maps to: /app/storage/user_2/Documents/file.pdf
        """
        username = self._get_user_from_environ(environ)
        if not username:
            raise DAVError(HTTP_FORBIDDEN, "No username found in request")

        user_storage = self._get_user_storage_path(username)

        # Ensure user storage directory exists
        user_storage.mkdir(parents=True, exist_ok=True)

        # Remove /webdav/username prefix from path
        if path.startswith(f"/{username}/"):
            path = path[len(f"/{username}/"):]
        elif path.startswith(f"/{username}"):
            path = path[len(f"/{username}"):]
        elif path == f"/{username}":
            path = "/"

        # Combine with user storage path
        if path.startswith("/"):
            path = path[1:]

        full_path = user_storage / path

        logger.debug(f"WebDAV path mapping: {environ.get('PATH_INFO')} -> {full_path}")

        return str(full_path)

    def get_resource_inst(self, path, environ):
        """Get resource with user-specific path normalization"""
        normalized_path = self._normalize_path(path, environ)
        return super().get_resource_inst(normalized_path, environ)


def create_webdav_app():
    """Create and configure WsgiDAV application"""

    config = {
        "host": "0.0.0.0",
        "port": 8080,  # WsgiDAV internal port (not exposed, proxied by nginx)
        "provider_mapping": {
            "/": UserIsolatedFilesystemProvider(str(STORAGE_PATH))
        },
        "simple_dc": {
            "user_mapping": {
                "*": True  # Accept all users with any password (auth handled by Portal/nginx)
            }
        },
        "verbose": 2,  # Logging level (1=ERROR, 2=WARN, 3=INFO, 4=DEBUG)
        "logging": {
            "enable_loggers": ["wsgidav"],
        },
        "property_manager": True,  # Enable property manager for metadata
        "lock_storage": True,  # Enable lock storage for file locking
        "dir_browser": {
            "enable": True,  # Enable web browser interface
            "davmount": False,
        },
    }

    return WsgiDAVApp(config)


# For use with uvicorn/gunicorn
app = create_webdav_app()


if __name__ == "__main__":
    # For standalone testing
    from cheroot import wsgi

    server = wsgi.Server(
        bind_addr=("0.0.0.0", 8080),
        wsgi_app=app
    )

    logger.info("Starting WebDAV server on http://0.0.0.0:8080")
    logger.info("Mount at: /webdav/andy/ (maps to /app/storage/user_2/)")

    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()

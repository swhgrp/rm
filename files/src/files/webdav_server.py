"""
WebDAV server for file synchronization - Database-backed version

This implementation ensures all WebDAV operations are tracked in the Files
database, maintaining consistency between WebDAV and web interface.
"""
import logging
from pathlib import Path
from wsgidav.wsgidav_app import WsgiDAVApp

from files.webdav_provider import DatabaseBackedDAVProvider

logger = logging.getLogger(__name__)

# Base storage path
STORAGE_PATH = Path("/app/storage")


def create_webdav_app():
    """
    Create and configure WsgiDAV application with database-backed provider

    This configuration uses our custom DatabaseBackedDAVProvider which:
    - Tracks all file/folder operations in the Files database
    - Maintains consistency between WebDAV and web interface
    - Supports user isolation and permissions
    - Integrates with Portal SSO authentication
    """

    config = {
        "host": "0.0.0.0",
        "port": 8080,  # WsgiDAV internal port (not exposed, proxied by nginx)
        "provider_mapping": {
            "/": DatabaseBackedDAVProvider(),  # Database-backed provider for all paths
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

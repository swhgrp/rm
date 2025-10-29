"""Share link and permission models"""
import secrets
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum
from files.db.database import Base


class ShareAccessType(str, Enum):
    """Types of access for share links"""
    READ_ONLY = "read_only"        # View and download only
    UPLOAD_ONLY = "upload_only"    # Upload files only (for external vendors)
    READ_WRITE = "read_write"      # View, download, and upload
    EDIT = "edit"                  # Full edit permissions
    ADMIN = "admin"                # Full control including resharing


class ShareLinkType(str, Enum):
    """Type of resource being shared"""
    FOLDER = "folder"
    FILE = "file"


class ShareLink(Base):
    """Public share links for files and folders"""
    __tablename__ = "share_links"

    id = Column(Integer, primary_key=True, index=True)

    # What is being shared
    resource_type = Column(SQLEnum(ShareLinkType, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    folder_id = Column(Integer, ForeignKey('folders.id', ondelete='CASCADE'), nullable=True)
    file_id = Column(Integer, ForeignKey('file_metadata.id', ondelete='CASCADE'), nullable=True)

    # Share settings
    share_token = Column(String(64), unique=True, nullable=False, index=True)
    access_type = Column(SQLEnum(ShareAccessType), nullable=False, default=ShareAccessType.READ_ONLY)

    # Security
    password_hash = Column(String(255), nullable=True)  # bcrypt hash if password protected
    require_login = Column(Boolean, default=False)  # Require user to be logged in

    # Limits
    expires_at = Column(DateTime(timezone=True), nullable=True)
    max_downloads = Column(Integer, nullable=True)  # Null = unlimited
    download_count = Column(Integer, default=0)
    max_uses = Column(Integer, nullable=True)  # For upload-only links
    use_count = Column(Integer, default=0)

    # Metadata
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    # Optional settings
    allow_download = Column(Boolean, default=True)
    allow_preview = Column(Boolean, default=True)
    notify_on_access = Column(Boolean, default=False)  # Email creator on access

    # Relationships
    folder = relationship("Folder", backref="share_links", foreign_keys=[folder_id])
    file = relationship("FileMetadata", backref="share_links", foreign_keys=[file_id])
    creator = relationship("User", backref="created_shares")
    access_logs = relationship("ShareAccessLog", back_populates="share_link", cascade="all, delete-orphan")

    @staticmethod
    def generate_token(length: int = 32) -> str:
        """Generate a secure random token for share links"""
        return secrets.token_urlsafe(length)

    @property
    def is_expired(self) -> bool:
        """Check if share link has expired"""
        if not self.expires_at:
            return False
        from datetime import datetime, timezone
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_download_limit_reached(self) -> bool:
        """Check if download limit has been reached"""
        if not self.max_downloads:
            return False
        return self.download_count >= self.max_downloads

    @property
    def is_use_limit_reached(self) -> bool:
        """Check if use limit has been reached"""
        if not self.max_uses:
            return False
        return self.use_count >= self.max_uses

    @property
    def is_valid(self) -> bool:
        """Check if share link is currently valid"""
        return (
            self.is_active
            and not self.is_expired
            and not self.is_download_limit_reached
            and not self.is_use_limit_reached
        )


class ShareAccessLog(Base):
    """Log all access to share links for audit trail"""
    __tablename__ = "share_access_logs"

    id = Column(Integer, primary_key=True, index=True)
    share_link_id = Column(Integer, ForeignKey('share_links.id', ondelete='CASCADE'), nullable=False)

    # Who accessed
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)  # If logged in
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(Text, nullable=True)

    # What they did
    action = Column(String(50), nullable=False)  # 'view', 'download', 'upload', 'preview'
    file_name = Column(String(255), nullable=True)  # For specific file actions
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)

    # When
    accessed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    share_link = relationship("ShareLink", back_populates="access_logs")
    user = relationship("User", backref="share_accesses")


class InternalShare(Base):
    """Internal sharing between HR users (more granular than share links)"""
    __tablename__ = "internal_shares"

    id = Column(Integer, primary_key=True, index=True)

    # What is being shared
    resource_type = Column(SQLEnum(ShareLinkType, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    folder_id = Column(Integer, ForeignKey('folders.id', ondelete='CASCADE'), nullable=True)
    file_id = Column(Integer, ForeignKey('file_metadata.id', ondelete='CASCADE'), nullable=True)

    # Who it's shared with
    shared_with_user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    shared_with_group_id = Column(Integer, nullable=True)  # Future: groups table
    shared_with_role = Column(String(50), nullable=True)  # Future: role-based sharing
    shared_with_department = Column(String(100), nullable=True)  # Department-based sharing
    shared_with_location = Column(String(100), nullable=True)  # Location-based sharing

    # Permissions (granular control)
    can_view = Column(Boolean, default=True)
    can_download = Column(Boolean, default=True)
    can_upload = Column(Boolean, default=False)
    can_edit = Column(Boolean, default=False)
    can_delete = Column(Boolean, default=False)
    can_share = Column(Boolean, default=False)  # Can they reshare with others?
    can_comment = Column(Boolean, default=True)

    # Metadata
    shared_by = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    shared_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    # Optional message
    message = Column(Text, nullable=True)  # Note from sharer
    notify_by_email = Column(Boolean, default=True)

    # Relationships
    folder = relationship("Folder", backref="internal_shares", foreign_keys=[folder_id])
    file = relationship("FileMetadata", backref="internal_shares", foreign_keys=[file_id])
    shared_with_user = relationship("User", foreign_keys=[shared_with_user_id], backref="received_shares")
    sharer = relationship("User", foreign_keys=[shared_by], backref="sent_shares")

    @property
    def is_expired(self) -> bool:
        """Check if internal share has expired"""
        if not self.expires_at:
            return False
        from datetime import datetime, timezone
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if internal share is currently valid"""
        return self.is_active and not self.is_expired

"""
User model - mirrors HR database users table with Nextcloud fields
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from nextcloud.db.database import Base


class User(Base):
    """
    User model

    This mirrors the users table from the HR database but adds
    Nextcloud-specific fields for credential storage.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)

    # Portal access permissions
    can_access_portal = Column(Boolean, default=True)
    can_access_inventory = Column(Boolean, default=True)
    can_access_accounting = Column(Boolean, default=True)
    can_access_integration_hub = Column(Boolean, default=True)
    can_access_hr = Column(Boolean, default=True)
    accounting_role_id = Column(Integer, nullable=True)
    can_access_events = Column(Boolean, default=True)

    # Nextcloud credentials (encrypted)
    nextcloud_username = Column(String, nullable=True)
    nextcloud_encrypted_password = Column(String, nullable=True)
    can_access_nextcloud = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"

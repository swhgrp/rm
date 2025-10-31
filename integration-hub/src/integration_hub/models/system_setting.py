"""
System Settings model - Stores configuration for the Integration Hub
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from integration_hub.db.database import Base


class SystemSetting(Base):
    """System configuration settings"""
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)

    # Setting identification
    category = Column(String(100), nullable=False, index=True)  # 'email', 'ocr', 'api', etc.
    key = Column(String(100), nullable=False, index=True)  # 'imap_host', 'username', etc.
    value = Column(Text, nullable=True)  # The actual setting value

    # Metadata
    description = Column(Text, nullable=True)  # What this setting does
    is_encrypted = Column(Boolean, default=False)  # Is the value encrypted (passwords)
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    updated_by = Column(Integer, nullable=True)  # User ID who last updated

    def __repr__(self):
        return f"<SystemSetting(category={self.category}, key={self.key})>"

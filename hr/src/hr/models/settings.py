"""
Settings model for system configuration
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from hr.db.database import Base


class SystemSettings(Base):
    """System settings model - stores key-value configuration"""
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50), nullable=False, index=True)  # e.g., 'smtp', 'general'
    key = Column(String(100), nullable=False, unique=True, index=True)
    value = Column(Text, nullable=True)
    is_encrypted = Column(Boolean, default=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<SystemSettings(key={self.key}, category={self.category})>"

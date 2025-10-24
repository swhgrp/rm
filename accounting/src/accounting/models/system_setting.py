"""
System Settings Model
Stores application-wide configuration settings
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from accounting.db.database import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String(100), unique=True, nullable=False, index=True)
    setting_value = Column(Text, nullable=True)
    setting_type = Column(String(20), nullable=False, default='string')  # string, integer, boolean, account_id
    description = Column(Text, nullable=True)

    # Audit fields
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    updater = relationship("User", foreign_keys=[updated_by])

    def __repr__(self):
        return f"<SystemSetting {self.setting_key}={self.setting_value}>"

"""
Audit Log Model for tracking all system changes
"""

from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from restaurant_inventory.db.database import Base

from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
def get_now(): return datetime.now(_ET)


class AuditLog(Base):
    """Audit log for tracking all system changes"""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: get_now(), nullable=False)

    # User information
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String, nullable=True)  # Denormalized for history preservation

    # Action details
    action = Column(String(100), nullable=False)  # CREATE, UPDATE, DELETE, LOGIN, etc.
    entity_type = Column(String(50), nullable=False)  # user, location, item, inventory, transfer, etc.
    entity_id = Column(Integer, nullable=True)  # ID of the affected entity

    # Change details (stored as JSONB for flexibility)
    changes = Column(JSON, nullable=True)  # {"old": {...}, "new": {...}} or other relevant data

    # Request metadata
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(255), nullable=True)

    # Relationship to user (optional, as user might be deleted)
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action={self.action}, entity={self.entity_type}:{self.entity_id}, user={self.username})>"
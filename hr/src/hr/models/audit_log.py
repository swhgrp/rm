"""
Audit Log model for tracking sensitive data access
"""

from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from hr.db.database import Base


class AuditLog(Base):
    """Audit log for tracking access to sensitive employee data"""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    # What was accessed
    entity_type = Column(String, nullable=False, index=True)  # e.g., "employee"
    entity_id = Column(Integer, nullable=False, index=True)  # ID of the employee
    action = Column(String, nullable=False, index=True)  # "view", "create", "update", "delete"
    field_name = Column(String, nullable=True)  # Specific field accessed (for sensitive fields)

    # Who accessed it
    user_id = Column(Integer, nullable=True, index=True)  # User who performed action
    username = Column(String, nullable=True)  # Username for easy reference

    # When and where
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    ip_address = Column(String, nullable=True)  # Request IP address
    user_agent = Column(String, nullable=True)  # Browser/client info

    # Additional context
    old_value = Column(Text, nullable=True)  # Previous value (for updates)
    new_value = Column(Text, nullable=True)  # New value (for creates/updates)
    notes = Column(Text, nullable=True)  # Additional notes

    def __repr__(self):
        return f"<AuditLog {self.action} {self.entity_type}:{self.entity_id} by {self.username}>"

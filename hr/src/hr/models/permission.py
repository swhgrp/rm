"""
HR System Permission Model
Defines granular permissions for access control
"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from hr.db.database import Base


class Permission(Base):
    """System permissions for fine-grained access control"""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    resource = Column(String(50), nullable=False, index=True)  # employee, position, document, user, report
    action = Column(String(50), nullable=False, index=True)  # view, create, update, delete, export
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    roles = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Permission {self.name}>"

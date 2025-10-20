"""
Permission model for fine-grained access control
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Table, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base


# Association table for role-permission many-to-many relationship
role_permissions = Table(
    'role_permissions',
    Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', Integer, ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True)
)


class Permission(Base):
    """Fine-grained permissions for system modules and actions"""
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)
    module = Column(String(50), nullable=False, index=True)  # e.g., 'general_ledger', 'accounts_payable'
    action = Column(String(20), nullable=False, index=True)  # e.g., 'view', 'create', 'edit', 'delete', 'approve'
    name = Column(String(100), unique=True, nullable=False, index=True)  # e.g., 'general_ledger:view'
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")

    def __repr__(self):
        return f"<Permission {self.name}>"

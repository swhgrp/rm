"""
HR System User Model
Separate user authentication for HR module
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Table, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from hr.db.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hr.models.user_role import UserRole


# Association table for user-location many-to-many relationship
user_locations = Table(
    'user_locations',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('location_id', Integer, ForeignKey('locations.id', ondelete='CASCADE'), primary_key=True),
    Column('created_at', DateTime(timezone=True), server_default=func.now())
)


class User(Base):
    """HR system users with authentication"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Portal access permissions
    can_access_portal = Column(Boolean, default=True, nullable=False)
    can_access_inventory = Column(Boolean, default=True, nullable=False)
    can_access_accounting = Column(Boolean, default=True, nullable=False)
    can_access_integration_hub = Column(Boolean, default=True, nullable=False)
    can_access_hr = Column(Boolean, default=True, nullable=False)

    # Link to accounting role if user has accounting access
    accounting_role_id = Column(Integer, nullable=True)

    # Relationships
    user_roles = relationship(
        "UserRole",
        foreign_keys="UserRole.user_id",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    assigned_locations = relationship("Location", secondary=user_locations, backref="assigned_users")

    @property
    def roles(self):
        """Get list of Role objects for this user"""
        return [ur.role for ur in self.user_roles if ur.role is not None]

    def __repr__(self):
        return f"<User {self.username}>"

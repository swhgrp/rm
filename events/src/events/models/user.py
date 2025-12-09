"""User and role models"""
from sqlalchemy import Column, String, Boolean, ForeignKey, Table, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import BaseModel
from events.core.database import Base
import sqlalchemy as sa


# Association table for user-role many-to-many relationship
user_roles = Table(
    'user_roles',
    BaseModel.metadata,
    Column('user_id', UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', UUID(as_uuid=True), ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True)
)


class User(BaseModel):
    """User model"""
    __tablename__ = "users"

    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    department = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    source = Column(String(20), default='local', nullable=False)  # 'hr' or 'local'

    # Relationships
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    created_events = relationship("Event", foreign_keys="Event.created_by", back_populates="creator")
    assigned_tasks = relationship("Task", foreign_keys="Task.assignee_user_id", back_populates="assignee")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, department={self.department})>"


class Role(BaseModel):
    """Role model"""
    __tablename__ = "roles"

    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)

    # Relationships
    users = relationship("User", secondary=user_roles, back_populates="roles")

    def __repr__(self):
        return f"<Role(code={self.code}, name={self.name})>"


class UserLocation(Base):
    """User-Location assignment model for location-based permissions.
    This is a join table with composite primary key (user_id, venue_id).
    Does not extend BaseModel since it doesn't need an id column.
    """
    __tablename__ = "user_locations"

    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True, nullable=False)
    venue_id = Column(UUID(as_uuid=True), ForeignKey('venues.id', ondelete='CASCADE'), primary_key=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)

    def __repr__(self):
        return f"<UserLocation(user_id={self.user_id}, venue_id={self.venue_id})>"

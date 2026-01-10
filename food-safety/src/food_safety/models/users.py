"""User permission models for Food Safety Service"""
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, DateTime, Enum, Boolean, Index
from food_safety.database import Base


class UserRole(str, PyEnum):
    """User roles for food safety access"""
    ADMIN = "admin"          # Full access to all features and settings
    MANAGER = "manager"      # Can sign off checklists, manage incidents, view reports
    SUPERVISOR = "supervisor"  # Can log temperatures, complete checklists, create incidents
    STAFF = "staff"          # Can log temperatures and complete assigned checklists
    READONLY = "readonly"    # View-only access to dashboards and reports


class UserPermission(Base):
    """Maps HR users to food safety roles and permissions"""
    __tablename__ = "user_permissions"

    id = Column(Integer, primary_key=True, index=True)
    hr_user_id = Column(Integer, nullable=False, unique=True, index=True)  # From HR service

    # User info cached from HR (for display purposes)
    employee_name = Column(String(200), nullable=True)
    employee_email = Column(String(200), nullable=True)

    # Role and permissions
    role = Column(Enum(UserRole), default=UserRole.STAFF, nullable=False)

    # Location access (NULL means all locations)
    location_ids = Column(String(500), nullable=True)  # Comma-separated location IDs

    # Specific permissions (override role defaults if needed)
    can_manage_templates = Column(Boolean, default=False)  # Create/edit checklist templates
    can_manage_users = Column(Boolean, default=False)      # Manage user permissions
    can_view_reports = Column(Boolean, default=True)       # View reports and dashboards
    can_sign_off = Column(Boolean, default=False)          # Can sign off on checklists requiring manager approval

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, nullable=True)  # HR user ID who created this

    __table_args__ = (
        Index("ix_user_permissions_role_active", "role", "is_active"),
    )

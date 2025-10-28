"""Template models"""
from sqlalchemy import Column, String, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import BaseModel


class EventTemplate(BaseModel):
    """Event template model"""
    __tablename__ = "event_templates"

    name = Column(String(255), nullable=False)
    event_type = Column(String(100), nullable=False)

    # Template configuration
    form_schema_json = Column(JSONB, nullable=True)  # JSON schema for intake form
    default_tasks_json = Column(JSONB, nullable=True)  # Default tasks to create
    default_menu_json = Column(JSONB, nullable=True)  # Default menu items
    default_financials_json = Column(JSONB, nullable=True)  # Default pricing structure
    email_rules_json = Column(JSONB, nullable=True)  # Email notification rules
    doc_templates_json = Column(JSONB, nullable=True)  # Document template keys

    # Audit
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    def __repr__(self):
        return f"<EventTemplate(id={self.id}, name={self.name}, event_type={self.event_type})>"


class NotificationRule(BaseModel):
    """Notification rule model"""
    __tablename__ = "notification_rules"

    name = Column(String(255), nullable=False)
    rule_json = Column(JSONB, nullable=False)  # Rule definition
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<NotificationRule(id={self.id}, name={self.name}, is_active={self.is_active})>"

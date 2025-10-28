"""Audit log model"""
from sqlalchemy import Column, String, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import BaseModel


class AuditLog(BaseModel):
    """Audit log model"""
    __tablename__ = "audit_logs"

    actor_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    entity_table = Column(String(100), nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    action = Column(String(50), nullable=False)  # CREATE, UPDATE, DELETE, etc.
    diff_json = Column(JSONB, nullable=True)  # {"before": {...}, "after": {...}}
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action={self.action}, entity={self.entity_table}/{self.entity_id})>"

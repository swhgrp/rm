"""Task models"""
from sqlalchemy import Column, String, Text, DateTime, Enum as SQLEnum, ForeignKey, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .base import BaseModel
import enum


class TaskStatus(str, enum.Enum):
    """Task status enum"""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


class TaskPriority(str, enum.Enum):
    """Task priority enum"""
    LOW = "low"
    MEDIUM = "med"
    HIGH = "high"


class Task(BaseModel):
    """Task model"""
    __tablename__ = "tasks"

    event_id = Column(UUID(as_uuid=True), ForeignKey('events.id', ondelete='CASCADE'), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.TODO, nullable=False)
    priority = Column(SQLEnum(TaskPriority), default=TaskPriority.MEDIUM, nullable=False)
    department = Column(String(100), nullable=True)  # kitchen, bar, av, floor, sales, admin

    # Assignment
    assignee_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    # Timing
    due_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)

    # Relationships
    event = relationship("Event", back_populates="tasks")
    assignee = relationship("User", foreign_keys=[assignee_user_id], back_populates="assigned_tasks")
    checklist_items = relationship("TaskChecklistItem", back_populates="task", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Task(id={self.id}, title={self.title}, status={self.status}, department={self.department})>"


class TaskChecklistItem(BaseModel):
    """Task checklist item model"""
    __tablename__ = "task_checklist_items"

    task_id = Column(UUID(as_uuid=True), ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    is_done = Column(Boolean, default=False, nullable=False)
    done_at = Column(DateTime(timezone=True), nullable=True)
    done_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    order_index = Column(Integer, default=0)

    # Relationships
    task = relationship("Task", back_populates="checklist_items")

    def __repr__(self):
        return f"<TaskChecklistItem(id={self.id}, label={self.label}, is_done={self.is_done})>"

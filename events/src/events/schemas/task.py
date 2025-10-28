"""Task schemas"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from events.models.task import TaskStatus, TaskPriority


class ChecklistItemBase(BaseModel):
    """Base checklist item schema"""
    label: str = Field(..., min_length=1, max_length=255)
    order_index: int = 0


class ChecklistItemCreate(ChecklistItemBase):
    """Schema for creating checklist item"""
    pass


class ChecklistItemResponse(ChecklistItemBase):
    """Schema for checklist item response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_done: bool
    done_at: Optional[datetime] = None
    done_by: Optional[UUID] = None


class TaskBase(BaseModel):
    """Base task schema"""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    department: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_at: Optional[datetime] = None


class TaskCreate(TaskBase):
    """Schema for creating task"""
    event_id: UUID
    assignee_user_id: Optional[UUID] = None
    checklist: Optional[List[str]] = []


class TaskUpdate(BaseModel):
    """Schema for updating task"""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    department: Optional[str] = None
    assignee_user_id: Optional[UUID] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TaskResponse(TaskBase):
    """Schema for task response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID
    status: TaskStatus
    assignee_user_id: Optional[UUID] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    checklist_items: List[ChecklistItemResponse] = []

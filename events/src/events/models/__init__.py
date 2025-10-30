"""Models package"""
from .base import BaseModel
from .user import User, Role, user_roles
from .client import Client, Venue
from .event import Event, EventPackage, EventStatus
from .task import Task, TaskChecklistItem, TaskStatus, TaskPriority
from .document import Document, Email, DocumentType, EmailStatus
from .template import EventTemplate, NotificationRule
from .audit import AuditLog
from .settings import Location, EventType, BeverageService, MealType

__all__ = [
    "BaseModel",
    "User",
    "Role",
    "user_roles",
    "Client",
    "Venue",
    "Event",
    "EventPackage",
    "EventStatus",
    "Task",
    "TaskChecklistItem",
    "TaskStatus",
    "TaskPriority",
    "Document",
    "Email",
    "DocumentType",
    "EmailStatus",
    "EventTemplate",
    "NotificationRule",
    "AuditLog",
    "Location",
    "EventType",
    "BeverageService",
    "MealType",
]

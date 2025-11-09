"""Settings models for configurable dropdown values"""
from sqlalchemy import Column, String, Boolean, Integer
from .base import BaseModel


class Location(BaseModel):
    """Location model for event locations"""
    __tablename__ = "locations"

    name = Column(String(255), nullable=False, unique=True)
    description = Column(String(500), nullable=True)
    color = Column(String(7), nullable=True)  # Hex color code for calendar display
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    def __repr__(self):
        return f"<Location(id={self.id}, name={self.name})>"


class EventType(BaseModel):
    """Event type model for categorizing events"""
    __tablename__ = "event_types"

    name = Column(String(255), nullable=False, unique=True)
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    def __repr__(self):
        return f"<EventType(id={self.id}, name={self.name})>"


class BeverageService(BaseModel):
    """Beverage service options for events"""
    __tablename__ = "beverage_services"

    name = Column(String(255), nullable=False, unique=True)
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    def __repr__(self):
        return f"<BeverageService(id={self.id}, name={self.name})>"


class MealType(BaseModel):
    """Meal type options for events"""
    __tablename__ = "meal_types"

    name = Column(String(255), nullable=False, unique=True)
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    def __repr__(self):
        return f"<MealType(id={self.id}, name={self.name})>"

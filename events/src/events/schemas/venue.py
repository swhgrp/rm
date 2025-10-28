"""Venue schemas"""
from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime


class VenueBase(BaseModel):
    """Base venue schema"""
    name: str
    address: Optional[str] = None
    rooms_json: Optional[Dict[str, Any]] = None


class VenueCreate(VenueBase):
    """Schema for creating venue"""
    pass


class VenueResponse(VenueBase):
    """Schema for venue response"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime

"""Client and venue models"""
from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .base import BaseModel


class Client(BaseModel):
    """Client model"""
    __tablename__ = "clients"

    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(50), nullable=True)
    org = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    events = relationship("Event", back_populates="client")

    def __repr__(self):
        return f"<Client(id={self.id}, name={self.name}, email={self.email})>"


class Venue(BaseModel):
    """Venue model"""
    __tablename__ = "venues"

    name = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    color = Column(String(7), nullable=True)  # Hex color code for calendar display
    rooms_json = Column(JSONB, nullable=True)  # {"rooms": [{"name": "Ballroom", "capacity": 200}]}

    # Relationships
    events = relationship("Event", back_populates="venue")

    def __repr__(self):
        return f"<Venue(id={self.id}, name={self.name})>"

"""
Vendor model for Integration Hub

Stores vendor information synced from Inventory and Accounting systems,
and allows creating new vendors to push to both systems.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from integration_hub.db.database import Base


class Vendor(Base):
    """
    Vendor model - synced across Hub, Inventory, and Accounting systems
    """
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)

    # Basic vendor information
    name = Column(String(200), nullable=False, index=True)
    contact_name = Column(String(200))
    email = Column(String(200))
    phone = Column(String(50))

    # Address information
    address = Column(String(500))
    city = Column(String(100))
    state = Column(String(50))
    zip_code = Column(String(20))

    # Payment terms
    payment_terms = Column(String(100))  # e.g., "Net 30", "Due on Receipt"

    # Tax information
    tax_id = Column(String(50))  # EIN or other tax ID

    # Notes
    notes = Column(Text)

    # Status
    is_active = Column(Boolean, default=True)

    # System sync tracking
    inventory_vendor_id = Column(Integer, index=True)  # ID in inventory system
    accounting_vendor_id = Column(Integer, index=True)  # ID in accounting system

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Vendor(id={self.id}, name='{self.name}')>"

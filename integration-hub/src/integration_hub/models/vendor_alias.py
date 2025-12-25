"""
Vendor Alias model for Hub

Maps various vendor name variations (from OCR, different invoice formats, etc.)
to a canonical vendor in the Hub vendors table. This is now the source of truth
for vendor name normalization.

Examples:
- "Gordon Food Service Inc." -> Gordon Food Service (vendor_id=5)
- "Gordon Food Service, Inc." -> Gordon Food Service (vendor_id=5)
- "GORDON FOOD SERVICE, INC." -> Gordon Food Service (vendor_id=5)
- "GFS" -> Gordon Food Service (vendor_id=5)
"""

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from integration_hub.db.database import Base


class VendorAlias(Base):
    """
    Maps alternative vendor names to canonical vendor records.
    Hub is the source of truth for vendor aliases.
    """
    __tablename__ = "vendor_aliases"

    id = Column(Integer, primary_key=True, index=True)

    # The alias name (as it appears on invoices)
    alias_name = Column(String(300), nullable=False, unique=True, index=True)

    # The normalized version for matching (lowercase, trimmed)
    alias_name_normalized = Column(String(300), nullable=False, index=True)

    # The canonical vendor this maps to (Hub vendor ID)
    vendor_id = Column(Integer, ForeignKey('vendors.id', ondelete='CASCADE'), nullable=False, index=True)

    # Whether this alias is active
    is_active = Column(Boolean, nullable=False, default=True)

    # Match settings
    case_insensitive = Column(Boolean, nullable=False, default=True)

    # Source tracking (where did this alias come from)
    source = Column(String(50), nullable=True)  # 'manual', 'auto', 'migrated', 'ocr'

    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship
    vendor = relationship("Vendor", backref="aliases")

    def __repr__(self):
        return f"<VendorAlias '{self.alias_name}' -> vendor_id={self.vendor_id}>"

"""
Vendor Alias model for normalizing vendor names from invoices

Maps various vendor name variations (from OCR, different invoice formats, etc.)
to a canonical vendor in the vendors table.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base


class VendorAlias(Base):
    """
    Maps alternative vendor names to canonical vendor records.

    Examples:
    - "Gordon Food Service Inc." -> Gordon Food Service (vendor_id=1)
    - "Gordon Food Service, Inc." -> Gordon Food Service (vendor_id=1)
    - "GORDON FOOD SERVICE, INC." -> Gordon Food Service (vendor_id=1)
    - "GFS" -> Gordon Food Service (vendor_id=1)
    """
    __tablename__ = "vendor_aliases"

    id = Column(Integer, primary_key=True, index=True)

    # The alias name (as it appears on invoices)
    alias_name = Column(String(200), nullable=False, unique=True, index=True)

    # The canonical vendor this maps to
    vendor_id = Column(Integer, ForeignKey('vendors.id'), nullable=False, index=True)

    # Whether to match case-insensitively (default True)
    case_insensitive = Column(Boolean, nullable=False, default=True)

    # Audit fields
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)

    # Relationships
    vendor = relationship("Vendor", backref="aliases")

    def __repr__(self):
        return f"<VendorAlias '{self.alias_name}' -> vendor_id={self.vendor_id}>"

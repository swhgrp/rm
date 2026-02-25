"""
Vendor Alias model for Hub

Maps various vendor name variations (from OCR, different invoice formats, etc.)
to a canonical vendor in the Hub vendors table. This is now the source of truth
for vendor name normalization.

Supports persistent learning: when a user manually corrects a vendor match,
the raw OCR name is stored as an alias so future invoices auto-match.

Examples:
- "Gordon Food Service Inc." -> Gordon Food Service (vendor_id=5)
- "SYSCO CHICAGO 847" -> Sysco (vendor_id=3) [learned from manual correction]
- "GFS DISTRIB CTR" -> Gordon Food Service (vendor_id=5) [learned from OCR]
"""

import re
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from integration_hub.db.database import Base


def normalize_vendor_alias(raw_name: str) -> str:
    """
    Normalize a vendor name for alias matching.
    - Lowercase
    - Strip leading/trailing whitespace
    - Remove punctuation except hyphens
    - Collapse multiple spaces to single space
    - Preserve numbers (they distinguish locations like "SYSCO 847")
    """
    if not raw_name:
        return ""
    text = raw_name.lower().strip()
    # Remove punctuation except hyphens and alphanumerics
    text = re.sub(r'[^a-z0-9\s\-]', '', text)
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text


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
    # Values: 'manual', 'manual_correction', 'auto_confirmed', 'manual_entry', 'migrated', 'ocr'
    source = Column(String(50), nullable=True)

    # Learning fields
    confidence = Column(Float, nullable=False, default=1.0, server_default='1.0')
    match_count = Column(Integer, nullable=False, default=1, server_default='1')
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(100), nullable=True)

    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship
    vendor = relationship("Vendor", backref="aliases")

    def __repr__(self):
        return f"<VendorAlias '{self.alias_name}' -> vendor_id={self.vendor_id}>"

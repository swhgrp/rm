"""
Vendor Parsing Rule model - Vendor-specific invoice parsing configuration
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from integration_hub.db.database import Base


class VendorParsingRule(Base):
    """
    Vendor-specific parsing rules for invoice processing.

    Each vendor can have custom rules that guide the AI parser and
    post-processing to correctly interpret their invoice format.
    """
    __tablename__ = "vendor_parsing_rules"

    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False, unique=True)

    # Column identification rules
    quantity_column = Column(String(100), nullable=True,
                            comment='Which column to use for quantity (e.g., "Qty Ship")')
    item_code_column = Column(String(100), nullable=True,
                             comment='Which column has item SKU (e.g., "Item Code")')
    price_column = Column(String(100), nullable=True,
                         comment='Which column has unit price')

    # Format hints
    pack_size_format = Column(String(100), nullable=True,
                             comment='Pack size format (e.g., "NxM UNIT" for "2x5 LB")')
    date_format = Column(String(50), nullable=True,
                        comment='Invoice date format if non-standard')

    # AI prompt additions
    ai_instructions = Column(Text, nullable=True,
                            comment='Additional AI prompt instructions for this vendor')

    # Post-parse corrections (JSON string)
    post_parse_rules = Column(Text, nullable=True,
                             comment='JSON rules for post-parse corrections')

    # Notes
    notes = Column(Text, nullable=True,
                  comment='Human-readable notes about this vendor format')

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    vendor = relationship("Vendor", backref="parsing_rules")

    def __repr__(self):
        return f"<VendorParsingRule(id={self.id}, vendor_id={self.vendor_id})>"

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor.name if self.vendor else None,
            "quantity_column": self.quantity_column,
            "item_code_column": self.item_code_column,
            "price_column": self.price_column,
            "pack_size_format": self.pack_size_format,
            "date_format": self.date_format,
            "ai_instructions": self.ai_instructions,
            "post_parse_rules": self.post_parse_rules,
            "notes": self.notes,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

"""
Area/Location model for accounting system
Areas represent different business units, locations, or departments
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from accounting.db.database import Base
from accounting.models.role import role_areas


class Area(Base):
    """Business areas/locations for accounting segmentation"""
    __tablename__ = "areas"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)  # DBA name
    code = Column(String(20), unique=True, nullable=False, index=True)  # Short code like "MAIN", "BAR", "KITCHEN"
    description = Column(Text, nullable=True)

    # Legal entity information
    legal_name = Column(String(200), nullable=True)  # Legal business name
    ein = Column(String(20), nullable=True)  # Employer Identification Number
    entity_type = Column(String(50), nullable=True)  # LLC, Corporation, Partnership, etc.

    # Address information
    address_line1 = Column(String(200), nullable=True)
    address_line2 = Column(String(200), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    zip_code = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True, default="United States")

    # Contact information
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    website = Column(String(200), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

    # Relationships
    roles = relationship("Role", secondary=role_areas, back_populates="areas")
    journal_entry_lines = relationship("JournalEntryLine", back_populates="area")
    vendor_bills = relationship("VendorBill", back_populates="area")
    daily_sales_summaries = relationship("DailySalesSummary", back_populates="area")
    bank_accounts = relationship("BankAccount", back_populates="area")
    budgets = relationship("Budget", back_populates="area")
    pos_configuration = relationship("POSConfiguration", back_populates="area", uselist=False)

    def __repr__(self):
        return f"<Area {self.code}: {self.name}>"

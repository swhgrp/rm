"""
Journal Entry schemas
"""
from pydantic import BaseModel, Field, field_validator
from datetime import date, datetime
from typing import Optional, List
from decimal import Decimal


class JournalEntryLineCreate(BaseModel):
    account_id: int = Field(..., gt=0)
    area_id: Optional[int] = Field(None, gt=0)  # Location/area for multi-location accounting
    debit_amount: Optional[Decimal] = Field(default=Decimal('0.00'), ge=0)
    credit_amount: Optional[Decimal] = Field(default=Decimal('0.00'), ge=0)
    description: Optional[str] = None
    line_number: Optional[int] = None

    @field_validator('debit_amount', 'credit_amount')
    @classmethod
    def validate_amounts(cls, v):
        if v is None:
            return Decimal('0.00')
        return v


class JournalEntryLineUpdate(BaseModel):
    account_id: Optional[int] = Field(None, gt=0)
    area_id: Optional[int] = Field(None, gt=0)  # Location/area for multi-location accounting
    debit_amount: Optional[Decimal] = Field(None, ge=0)
    credit_amount: Optional[Decimal] = Field(None, ge=0)
    description: Optional[str] = None
    line_number: Optional[int] = None


class AccountInLine(BaseModel):
    """Simplified account info for line responses"""
    id: int
    account_number: str
    account_name: str
    account_type: str

    class Config:
        from_attributes = True


class AreaInLine(BaseModel):
    """Simplified area/location info for line responses"""
    id: int
    code: str
    name: str

    class Config:
        from_attributes = True


class JournalEntryLineResponse(BaseModel):
    id: int
    journal_entry_id: int
    account_id: int
    area_id: Optional[int] = None
    account: Optional[AccountInLine] = None
    area: Optional[AreaInLine] = None  # Location/area details
    debit_amount: Decimal
    credit_amount: Decimal
    description: Optional[str] = None
    line_number: Optional[int] = None

    class Config:
        from_attributes = True


class JournalEntryCreate(BaseModel):
    entry_date: date
    description: Optional[str] = None
    reference_type: Optional[str] = Field(None, max_length=50)
    reference_id: Optional[int] = None
    location_id: Optional[int] = None
    lines: List[JournalEntryLineCreate] = Field(..., min_length=2)

    @field_validator('lines')
    @classmethod
    def validate_balanced_entry(cls, v):
        """Ensure debits equal credits (double-entry validation)"""
        if len(v) < 2:
            raise ValueError("Journal entry must have at least 2 lines")

        total_debits = sum(line.debit_amount or Decimal('0.00') for line in v)
        total_credits = sum(line.credit_amount or Decimal('0.00') for line in v)

        if total_debits != total_credits:
            raise ValueError(
                f"Journal entry is not balanced: Debits ({total_debits}) must equal Credits ({total_credits})"
            )

        if total_debits == 0:
            raise ValueError("Journal entry cannot have zero amounts")

        # Validate each line has either debit or credit, not both
        for i, line in enumerate(v):
            debit = line.debit_amount or Decimal('0.00')
            credit = line.credit_amount or Decimal('0.00')

            if debit > 0 and credit > 0:
                raise ValueError(f"Line {i+1}: Cannot have both debit and credit amounts")

            if debit == 0 and credit == 0:
                raise ValueError(f"Line {i+1}: Must have either debit or credit amount")

        return v


class JournalEntryUpdate(BaseModel):
    entry_date: Optional[date] = None
    description: Optional[str] = None
    reference_type: Optional[str] = Field(None, max_length=50)
    reference_id: Optional[int] = None
    location_id: Optional[int] = None


class JournalEntryResponse(BaseModel):
    id: int
    entry_number: str
    entry_date: date
    description: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None
    location_id: Optional[int] = None
    created_by: Optional[int] = None
    approved_by: Optional[int] = None
    status: str
    created_at: datetime
    posted_at: Optional[datetime] = None
    lines: List[JournalEntryLineResponse] = []

    # Computed fields
    total_debits: Optional[Decimal] = None
    total_credits: Optional[Decimal] = None

    class Config:
        from_attributes = True


class JournalEntryListResponse(BaseModel):
    """Simplified response for list views"""
    id: int
    entry_number: str
    entry_date: date
    description: Optional[str] = None
    status: str
    created_at: datetime
    posted_at: Optional[datetime] = None
    total_amount: Decimal  # Total debits (or credits, they're equal)

    class Config:
        from_attributes = True

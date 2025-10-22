"""
Pydantic schemas for composite matching (Phase 1B)
Handles matching one bank transaction to multiple journal entry lines
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal


# ============================================================================
# Composite Match Schemas
# ============================================================================

class CompositeMatchLineBase(BaseModel):
    """Base schema for a single line in a composite match"""
    journal_entry_line_id: int
    amount: Decimal


class CompositeMatchLineCreate(CompositeMatchLineBase):
    """Schema for creating a composite match line"""
    notes: Optional[str] = None


class CompositeMatchLineResponse(CompositeMatchLineBase):
    """Response schema for a composite match line"""
    id: int
    bank_transaction_id: int
    match_type: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    created_by: Optional[int] = None

    # Journal Entry Line details
    je_number: Optional[str] = None
    je_date: Optional[date] = None
    je_description: Optional[str] = None
    account_code: Optional[str] = None
    account_name: Optional[str] = None

    class Config:
        from_attributes = True


class CompositeMatchRequest(BaseModel):
    """Request to create composite match (many JE lines → one bank transaction)"""
    bank_transaction_id: int
    journal_entry_line_ids: List[int] = Field(..., min_length=1, description="List of JE line IDs to match")
    create_clearing_entry: bool = Field(default=True, description="Create clearing journal entry")
    notes: Optional[str] = None

    @field_validator('journal_entry_line_ids')
    @classmethod
    def validate_line_ids(cls, v):
        if not v or len(v) == 0:
            raise ValueError("Must provide at least one journal entry line ID")
        if len(v) != len(set(v)):
            raise ValueError("Duplicate journal entry line IDs not allowed")
        return v


class CompositeMatchResponse(BaseModel):
    """Response after creating composite match"""
    success: bool
    bank_transaction_id: int
    matched_lines_count: int
    total_matched_amount: Decimal
    bank_amount: Decimal
    difference: Decimal
    clearing_journal_entry_id: Optional[int] = None
    clearing_entry_number: Optional[str] = None
    matches: List[CompositeMatchLineResponse]
    message: str


class CompositeMatchSummary(BaseModel):
    """Summary of a composite match for display"""
    bank_transaction_id: int
    transaction_date: date
    description: str
    bank_amount: Decimal
    matched_lines_count: int
    total_matched_amount: Decimal
    difference: Decimal
    is_balanced: bool

    class Config:
        from_attributes = True


# ============================================================================
# Undeposited Funds Schemas (for finding GL lines to match)
# ============================================================================

class UndepositedFundsLine(BaseModel):
    """Journal entry line from Undeposited Funds accounts"""
    id: int
    journal_entry_id: int
    journal_entry_number: str
    journal_entry_date: date
    description: str
    account_id: int
    account_code: str
    account_name: str
    debit_amount: Optional[Decimal] = None
    credit_amount: Optional[Decimal] = None
    amount: Decimal  # Absolute value for display
    area_id: Optional[int] = None
    area_name: Optional[str] = None

    class Config:
        from_attributes = True


class UndepositedFundsRequest(BaseModel):
    """Request to get undeposited funds lines"""
    account_ids: Optional[List[int]] = Field(default=None, description="Filter by GL account IDs (1090, 1091, 1095)")
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    area_id: Optional[int] = None
    only_unmatched: bool = Field(default=True, description="Only show unmatched lines")


class UndepositedFundsResponse(BaseModel):
    """Response with undeposited funds lines"""
    lines: List[UndepositedFundsLine]
    total_amount: Decimal
    total_count: int
    accounts_summary: dict  # {account_id: {account_name, total_amount, count}}


# ============================================================================
# Composite Match Suggestions
# ============================================================================

class CompositeMatchSuggestion(BaseModel):
    """Suggested composite match for a bank transaction"""
    bank_transaction_id: int
    suggested_lines: List[UndepositedFundsLine]
    total_suggested_amount: Decimal
    bank_amount: Decimal
    difference: Decimal
    confidence_score: Decimal = Field(..., ge=0, le=100, description="0-100 confidence score")
    match_reason: str


class CompositeMatchSuggestionsResponse(BaseModel):
    """Response with composite match suggestions"""
    bank_transaction_id: int
    bank_description: str
    bank_amount: Decimal
    bank_date: date
    suggestions: List[CompositeMatchSuggestion]
    has_perfect_match: bool


# ============================================================================
# Unmatch Composite Schema
# ============================================================================

class UnmatchCompositeRequest(BaseModel):
    """Request to unmatch a composite match"""
    bank_transaction_id: int
    reverse_clearing_entry: bool = Field(default=True, description="Reverse the clearing journal entry")


class UnmatchCompositeResponse(BaseModel):
    """Response after unmatching"""
    success: bool
    bank_transaction_id: int
    unmatched_lines_count: int
    reversal_entry_id: Optional[int] = None
    reversal_entry_number: Optional[str] = None
    message: str

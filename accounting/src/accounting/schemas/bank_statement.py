"""Pydantic schemas for bank statements and matching"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal


# Bank Statement schemas
class BankStatementBase(BaseModel):
    bank_account_id: int
    statement_period_start: date
    statement_period_end: date
    statement_date: date
    opening_balance: Decimal
    closing_balance: Decimal
    notes: Optional[str] = None


class BankStatementCreate(BankStatementBase):
    pass


class BankStatementUpdate(BaseModel):
    statement_period_start: Optional[date] = None
    statement_period_end: Optional[date] = None
    statement_date: Optional[date] = None
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class BankStatement(BankStatementBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    gl_balance: Optional[Decimal] = None
    difference: Optional[Decimal] = None
    reconciled_by: Optional[int] = None
    reconciled_at: Optional[datetime] = None
    locked_by: Optional[int] = None
    locked_at: Optional[datetime] = None
    locked_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int] = None


# Match Suggestion schemas
class JournalEntryLineInfo(BaseModel):
    """Simplified JE line info for match suggestions"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    journal_entry_id: int
    account_id: int
    account_code: str
    account_name: str
    debit_amount: Decimal
    credit_amount: Decimal
    description: Optional[str] = None
    entry_date: date


class MatchSuggestionResponse(BaseModel):
    """Response for a single match suggestion"""
    match_type: str  # exact, fuzzy, composite, manual, rule_based
    confidence_score: float
    match_reason: str
    journal_entry_lines: List[JournalEntryLineInfo]
    amount_difference: Decimal
    date_difference: int
    suggested_fee_account_id: Optional[int] = None
    suggested_fee_amount: Optional[Decimal] = None
    composite_group_id: Optional[str] = None


class MatchSuggestionsResponse(BaseModel):
    """Response containing all match suggestions for a transaction"""
    bank_transaction_id: int
    bank_amount: Decimal
    bank_date: date
    bank_description: Optional[str] = None
    suggestions: List[MatchSuggestionResponse]
    total_suggestions: int


# Match Confirmation schemas
class ConfirmMatchRequest(BaseModel):
    """Request to confirm a match"""
    suggestion_index: int  # Which suggestion from the list
    create_fee_adjustment: bool = False
    fee_account_id: Optional[int] = None
    fee_amount: Optional[Decimal] = None
    notes: Optional[str] = None


class ConfirmMatchResponse(BaseModel):
    """Response after confirming a match"""
    model_config = ConfigDict(from_attributes=True)

    match_id: int
    bank_transaction_id: int
    match_type: str
    status: str
    clearing_journal_entry_id: Optional[int] = None
    adjustment_journal_entry_id: Optional[int] = None
    message: str


# Composite Match schemas
class CompositeMatchRequest(BaseModel):
    """Request to create a composite match"""
    journal_entry_line_ids: List[int]
    composite_type: str = "many_to_one"  # many_to_one or one_to_many
    create_fee_adjustment: bool = False
    fee_account_id: Optional[int] = None
    fee_amount: Optional[Decimal] = None


# Matching Rule schemas
class MatchingRuleConditions(BaseModel):
    """Flexible conditions for matching rules"""
    description_contains: Optional[str] = None
    description_starts_with: Optional[str] = None
    description_ends_with: Optional[str] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    amount_equals: Optional[Decimal] = None
    transaction_type: Optional[str] = None
    payee_contains: Optional[str] = None


class BankMatchingRuleBase(BaseModel):
    rule_name: str
    rule_type: str  # recurring_deposit, recurring_expense, vendor_match, composite_match
    priority: int = 0
    conditions: dict  # Will be validated as MatchingRuleConditions
    action_type: str  # suggest_gl_account, auto_match, create_expense
    target_account_id: Optional[int] = None
    requires_confirmation: bool = True
    fee_account_id: Optional[int] = None
    fee_calculation: Optional[str] = None  # fixed_amount, percentage, difference
    fee_amount: Optional[Decimal] = None
    fee_percentage: Optional[Decimal] = None
    active: bool = True
    notes: Optional[str] = None


class BankMatchingRuleCreate(BankMatchingRuleBase):
    bank_account_id: Optional[int] = None
    area_id: Optional[int] = None


class BankMatchingRuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    rule_type: Optional[str] = None
    priority: Optional[int] = None
    conditions: Optional[dict] = None
    action_type: Optional[str] = None
    target_account_id: Optional[int] = None
    requires_confirmation: Optional[bool] = None
    fee_account_id: Optional[int] = None
    fee_calculation: Optional[str] = None
    fee_amount: Optional[Decimal] = None
    fee_percentage: Optional[Decimal] = None
    active: Optional[bool] = None
    notes: Optional[str] = None


class BankMatchingRule(BankMatchingRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bank_account_id: Optional[int] = None
    area_id: Optional[int] = None
    times_suggested: int
    times_confirmed: int
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int] = None


# Statement Summary schema
class StatementSummary(BaseModel):
    """Summary information for a statement"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    bank_account_id: int
    bank_account_name: str
    statement_period_start: date
    statement_period_end: date
    opening_balance: Decimal
    closing_balance: Decimal
    status: str
    transaction_count: int
    matched_count: int
    unmatched_count: int
    difference: Optional[Decimal] = None


# Quick Match Rule from Match
class CreateRuleFromMatchRequest(BaseModel):
    """Request to create a rule from a confirmed match"""
    rule_name: str
    rule_type: str = "recurring_expense"
    priority: int = 0
    apply_to_all_accounts: bool = False  # If true, bank_account_id = None
    notes: Optional[str] = None


# Vendor Recognition schemas
class VendorInfo(BaseModel):
    """Vendor information for recognition"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    vendor_name: str
    vendor_code: Optional[str] = None


class VendorRecognitionResponse(BaseModel):
    """Response for vendor recognition from transaction description"""
    extracted_vendor_name: Optional[str] = None
    matched_vendor: Optional[VendorInfo] = None
    open_bills_count: int = 0
    has_exact_match: bool = False
    confidence: float = 0.0


class OpenBillInfo(BaseModel):
    """Information about an open vendor bill"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    bill_number: str
    bill_date: date
    due_date: Optional[date] = None
    total_amount: Decimal
    paid_amount: Decimal
    amount_due: Decimal  # Calculated: total_amount - paid_amount
    description: Optional[str] = None
    match_confidence: float = 0.0
    is_exact_match: bool = False
    amount_difference: Decimal = Decimal("0.00")
    date_difference: int = 0


class OpenBillsResponse(BaseModel):
    """Response containing all open bills for a vendor"""
    bank_transaction_id: int
    bank_amount: Decimal
    bank_date: date
    bank_description: Optional[str] = None
    vendor: Optional[VendorInfo] = None
    open_bills: List[OpenBillInfo]
    total_bills: int
    exact_matches: int


class MatchBillsRequest(BaseModel):
    """Request to match bank transaction to vendor bills"""
    bill_ids: List[int]
    create_clearing_entry: bool = True
    notes: Optional[str] = None


class MatchBillsResponse(BaseModel):
    """Response after matching bills"""
    bank_transaction_id: int
    matched_bill_ids: List[int]
    total_amount_matched: Decimal
    clearing_journal_entry_id: Optional[int] = None
    adjustment_journal_entry_id: Optional[int] = None
    status: str
    message: str


class GLAssignmentRequest(BaseModel):
    """Request to assign bank transaction to GL account"""
    account_id: int
    memo: Optional[str] = None
    area_id: Optional[int] = None


class GLAssignmentResponse(BaseModel):
    """Response after GL assignment"""
    bank_transaction_id: int
    journal_entry_id: int
    account_id: int
    status: str
    message: str

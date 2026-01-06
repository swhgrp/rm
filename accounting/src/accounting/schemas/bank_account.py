"""Bank account schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal


# Bank Account Schemas
class BankAccountBase(BaseModel):
    """Base bank account schema"""
    account_name: str = Field(..., max_length=255)
    account_number: Optional[str] = Field(None, max_length=50)
    account_type: Optional[str] = Field(None, max_length=50)
    institution_name: Optional[str] = Field(None, max_length=255)
    routing_number: Optional[str] = Field(None, max_length=20)
    gl_account_id: Optional[int] = None
    opening_balance: Optional[Decimal] = None
    notes: Optional[str] = None


class BankAccountCreate(BankAccountBase):
    """Schema for creating a bank account"""
    area_id: Optional[int] = None
    sync_method: str = Field(default="manual", max_length=20)
    auto_sync_enabled: bool = False
    # Plaid integration fields
    plaid_access_token: Optional[str] = None
    plaid_item_id: Optional[str] = None
    plaid_account_id: Optional[str] = None


class BankAccountUpdate(BaseModel):
    """Schema for updating a bank account"""
    account_name: Optional[str] = Field(None, max_length=255)
    account_number: Optional[str] = Field(None, max_length=50)
    account_type: Optional[str] = Field(None, max_length=50)
    institution_name: Optional[str] = Field(None, max_length=255)
    routing_number: Optional[str] = Field(None, max_length=20)
    gl_account_id: Optional[int] = None
    current_balance: Optional[Decimal] = None
    status: Optional[str] = Field(None, max_length=20)
    sync_method: Optional[str] = Field(None, max_length=20)
    auto_sync_enabled: Optional[bool] = None
    notes: Optional[str] = None
    # Plaid integration fields
    plaid_access_token: Optional[str] = None
    plaid_item_id: Optional[str] = None
    plaid_account_id: Optional[str] = None


class BankAccountResponse(BankAccountBase):
    """Schema for bank account response"""
    id: int
    area_id: Optional[int]
    current_balance: Optional[Decimal]
    status: str
    sync_method: str
    auto_sync_enabled: bool
    last_sync_date: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    # Calculated fields
    unreconciled_count: Optional[int] = 0
    last_reconciliation_date: Optional[date] = None

    class Config:
        from_attributes = True


# Bank Transaction Schemas
class BankTransactionBase(BaseModel):
    """Base bank transaction schema"""
    transaction_date: date
    description: Optional[str] = None
    payee: Optional[str] = Field(None, max_length=255)
    amount: Decimal
    transaction_type: Optional[str] = Field(None, max_length=50)
    check_number: Optional[str] = Field(None, max_length=50)
    memo: Optional[str] = None


class BankTransactionCreate(BankTransactionBase):
    """Schema for creating a bank transaction"""
    bank_account_id: int
    post_date: Optional[date] = None
    reference_number: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=100)


class BankTransactionUpdate(BaseModel):
    """Schema for updating a bank transaction"""
    transaction_date: Optional[date] = None
    description: Optional[str] = None
    payee: Optional[str] = Field(None, max_length=255)
    amount: Optional[Decimal] = None
    transaction_type: Optional[str] = Field(None, max_length=50)
    check_number: Optional[str] = Field(None, max_length=50)
    category: Optional[str] = Field(None, max_length=100)
    memo: Optional[str] = None
    status: Optional[str] = Field(None, max_length=20)
    matched_journal_line_id: Optional[int] = None


class AccountInfo(BaseModel):
    """Minimal account info for display"""
    id: int
    account_number: str
    account_name: str

    class Config:
        from_attributes = True


class BankTransactionResponse(BankTransactionBase):
    """Schema for bank transaction response"""
    id: int
    bank_account_id: int
    import_id: Optional[int]
    post_date: Optional[date]
    reference_number: Optional[str]
    category: Optional[str]
    status: str
    reconciled_date: Optional[date]
    matched_journal_entry_id: Optional[int]
    matched_journal_line_id: Optional[int]
    match_type: Optional[str]
    match_confidence: Optional[Decimal]
    plaid_transaction_id: Optional[str]
    plaid_pending: Optional[bool]
    created_at: datetime

    # Suggested matches
    suggested_matches: Optional[List[dict]] = []

    # GL account assignment (populated when transaction is assigned to a GL)
    suggested_account: Optional[AccountInfo] = None
    suggested_account_id: Optional[int] = None
    suggestion_confidence: Optional[Decimal] = None

    # Auto-match confirmation tracking
    confirmed_at: Optional[datetime] = None
    confirmed_by: Optional[int] = None

    class Config:
        from_attributes = True


# Bank Statement Import Schemas
class BankStatementImportCreate(BaseModel):
    """Schema for creating a bank statement import"""
    bank_account_id: int
    file_format: str = Field(..., max_length=20)
    statement_date: Optional[date] = None
    beginning_balance: Optional[Decimal] = None
    ending_balance: Optional[Decimal] = None


class BankStatementImportResponse(BaseModel):
    """Schema for bank statement import response"""
    id: int
    bank_account_id: int
    import_date: datetime
    file_name: Optional[str]
    file_format: Optional[str]
    import_method: str
    statement_date: Optional[date]
    beginning_balance: Optional[Decimal]
    ending_balance: Optional[Decimal]
    transaction_count: Optional[int]
    imported_by: Optional[int]
    notes: Optional[str]

    class Config:
        from_attributes = True


# Bank Reconciliation Schemas
class BankReconciliationBase(BaseModel):
    """Base bank reconciliation schema"""
    statement_date: date
    beginning_balance: Decimal
    ending_balance: Decimal
    notes: Optional[str] = None


class BankReconciliationCreate(BankReconciliationBase):
    """Schema for creating a bank reconciliation"""
    bank_account_id: int
    reconciliation_date: date = Field(default_factory=date.today)


class BankReconciliationUpdate(BaseModel):
    """Schema for updating a bank reconciliation"""
    statement_date: Optional[date] = None
    beginning_balance: Optional[Decimal] = None
    ending_balance: Optional[Decimal] = None
    cleared_balance: Optional[Decimal] = None
    book_balance: Optional[Decimal] = None
    difference: Optional[Decimal] = None
    status: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = None


class BankReconciliationItemCreate(BaseModel):
    """Schema for creating a reconciliation item"""
    reconciliation_id: int
    bank_transaction_id: Optional[int] = None
    journal_entry_line_id: Optional[int] = None
    cleared_date: Optional[date] = None
    amount: Decimal
    item_type: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None


class BankReconciliationItemResponse(BaseModel):
    """Schema for reconciliation item response"""
    id: int
    reconciliation_id: int
    bank_transaction_id: Optional[int]
    journal_entry_line_id: Optional[int]
    cleared_date: Optional[date]
    amount: Decimal
    item_type: Optional[str]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class BankReconciliationResponse(BankReconciliationBase):
    """Schema for bank reconciliation response"""
    id: int
    bank_account_id: int
    reconciliation_date: date
    cleared_balance: Optional[Decimal]
    book_balance: Optional[Decimal]
    difference: Optional[Decimal]
    status: str
    reconciled_by: Optional[int]
    reconciled_at: Optional[datetime]
    locked_by: Optional[int]
    locked_at: Optional[datetime]
    created_at: datetime

    # Calculated fields
    cleared_count: Optional[int] = 0
    outstanding_checks: Optional[Decimal] = Decimal("0.00")
    deposits_in_transit: Optional[Decimal] = Decimal("0.00")

    items: List[BankReconciliationItemResponse] = []

    class Config:
        from_attributes = True


# Bank Matching Rule Schemas
class BankMatchingRuleBase(BaseModel):
    """Base bank matching rule schema"""
    rule_name: str = Field(..., max_length=255)
    match_field: str = Field(..., max_length=50)
    match_operator: str = Field(..., max_length=20)
    match_value: str
    target_account_id: Optional[int] = None
    target_payee: Optional[str] = Field(None, max_length=255)
    auto_apply: bool = False
    priority: int = 0
    active: bool = True


class BankMatchingRuleCreate(BankMatchingRuleBase):
    """Schema for creating a bank matching rule"""
    bank_account_id: Optional[int] = None


class BankMatchingRuleUpdate(BaseModel):
    """Schema for updating a bank matching rule"""
    rule_name: Optional[str] = Field(None, max_length=255)
    match_field: Optional[str] = Field(None, max_length=50)
    match_operator: Optional[str] = Field(None, max_length=20)
    match_value: Optional[str] = None
    target_account_id: Optional[int] = None
    target_payee: Optional[str] = Field(None, max_length=255)
    auto_apply: Optional[bool] = None
    priority: Optional[int] = None
    active: Optional[bool] = None


class BankMatchingRuleResponse(BankMatchingRuleBase):
    """Schema for bank matching rule response"""
    id: int
    bank_account_id: Optional[int]
    times_used: int
    created_at: datetime
    created_by: Optional[int]

    class Config:
        from_attributes = True


# Plaid-specific schemas
class PlaidLinkTokenRequest(BaseModel):
    """Schema for requesting a Plaid link token"""
    # user_id is optional since it's extracted from current_user on the server
    pass


class PlaidLinkTokenResponse(BaseModel):
    """Schema for Plaid link token response"""
    link_token: str
    expiration: datetime


class PlaidPublicTokenExchange(BaseModel):
    """Schema for exchanging Plaid public token"""
    public_token: str
    bank_account_id: Optional[int] = None
    account_name: Optional[str] = None


class PlaidAccountResponse(BaseModel):
    """Schema for Plaid account response"""
    account_id: str
    name: str
    mask: Optional[str]
    type: str
    subtype: Optional[str]
    current_balance: Optional[Decimal]
    available_balance: Optional[Decimal]


class PlaidExchangeResponse(BaseModel):
    """Schema for Plaid token exchange response with credentials"""
    access_token: str
    item_id: str
    accounts: List[PlaidAccountResponse]


class PlaidSyncRequest(BaseModel):
    """Schema for requesting Plaid sync"""
    # bank_account_id comes from URL path, not body
    days: int = Field(default=30, ge=1, le=730)


class PlaidSyncResponse(BaseModel):
    """Schema for Plaid sync response"""
    success: bool
    transactions_added: int
    transactions_updated: int
    transactions_removed: int
    last_sync_date: datetime


# Transaction matching schemas
class TransactionMatchSuggestion(BaseModel):
    """Schema for transaction match suggestion"""
    bank_transaction_id: int
    journal_line_id: int
    match_score: Decimal
    match_reason: str
    amount_difference: Decimal = Decimal("0.00")
    date_difference: int = 0


class TransactionMatchRequest(BaseModel):
    """Schema for matching transactions"""
    bank_transaction_id: int
    journal_line_id: int
    match_type: str = "manual"


class TransactionUnmatchRequest(BaseModel):
    """Schema for unmatching transactions"""
    bank_transaction_id: int


# File upload schemas
class FileUploadResponse(BaseModel):
    """Schema for file upload response"""
    success: bool
    import_id: int
    transactions_imported: int
    duplicates_skipped: int
    errors: List[str] = []
    warnings: List[str] = []

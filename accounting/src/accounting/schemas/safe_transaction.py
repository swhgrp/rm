"""
Pydantic schemas for Safe Transaction management
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal


class SafeTransactionBase(BaseModel):
    """Base schema for safe transaction"""
    transaction_date: date
    area_id: int
    transaction_type: str = Field(description="deposit, withdrawal, or adjustment")
    amount: Decimal = Field(gt=0)
    description: str
    notes: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None


class SafeTransactionCreate(SafeTransactionBase):
    """Schema for creating a safe transaction"""
    pass


class SafeTransactionUpdate(BaseModel):
    """Schema for updating a safe transaction"""
    transaction_date: Optional[date] = None
    amount: Optional[Decimal] = Field(None, gt=0)
    description: Optional[str] = None
    notes: Optional[str] = None


class SafeTransactionResponse(SafeTransactionBase):
    """Schema for safe transaction response"""
    id: int
    balance_after: Optional[Decimal] = None
    journal_entry_id: Optional[int] = None
    is_posted: bool
    created_by: int
    created_at: datetime
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    posted_by: Optional[int] = None
    posted_at: Optional[datetime] = None

    # Populated from relationships
    area_name: Optional[str] = None
    creator_name: Optional[str] = None
    approver_name: Optional[str] = None

    class Config:
        from_attributes = True


class SafeBalanceResponse(BaseModel):
    """Current safe balance for a location"""
    area_id: int
    area_name: str
    current_balance: Decimal
    last_transaction_date: Optional[date] = None
    unposted_count: int
    pending_approvals: int


class SafeDashboardResponse(BaseModel):
    """Dashboard summary for safe management"""
    balances: List[SafeBalanceResponse]
    recent_transactions: List[SafeTransactionResponse]
    alerts: List[str] = []


class SafePostRequest(BaseModel):
    """Request to post safe transaction to GL"""
    transaction_ids: List[int] = Field(description="IDs of transactions to post")


class SafeReconciliationRequest(BaseModel):
    """Request to perform safe count/reconciliation"""
    area_id: int
    count_date: date
    counted_amount: Decimal
    counted_by: str
    notes: Optional[str] = None

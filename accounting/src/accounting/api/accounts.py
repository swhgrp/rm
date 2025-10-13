"""
Chart of Accounts API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from accounting.db.database import get_db
from accounting.models.account import Account, AccountType
from pydantic import BaseModel, Field
from datetime import datetime


# Pydantic schemas
class AccountCreate(BaseModel):
    account_number: str = Field(..., max_length=20)
    account_name: str = Field(..., max_length=200)
    account_type: AccountType
    parent_account_id: Optional[int] = None
    description: Optional[str] = Field(None, max_length=500)


class AccountUpdate(BaseModel):
    account_name: Optional[str] = Field(None, max_length=200)
    parent_account_id: Optional[int] = None
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


class AccountResponse(BaseModel):
    id: int
    account_number: str
    account_name: str
    account_type: AccountType
    parent_account_id: Optional[int]
    description: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


router = APIRouter(prefix="/api/accounts", tags=["Accounts"])


@router.get("/", response_model=List[AccountResponse])
def list_accounts(
    account_type: Optional[AccountType] = None,
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by account number or name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """
    List all accounts with optional filters
    """
    query = db.query(Account)

    if account_type:
        query = query.filter(Account.account_type == account_type)

    if is_active is not None:
        query = query.filter(Account.is_active == is_active)

    if search:
        query = query.filter(
            (Account.account_number.ilike(f"%{search}%")) |
            (Account.account_name.ilike(f"%{search}%"))
        )

    accounts = query.order_by(Account.account_number).offset(skip).limit(limit).all()
    return accounts


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: int, db: Session = Depends(get_db)):
    """
    Get a specific account by ID
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.get("/number/{account_number}", response_model=AccountResponse)
def get_account_by_number(account_number: str, db: Session = Depends(get_db)):
    """
    Get a specific account by account number
    """
    account = db.query(Account).filter(Account.account_number == account_number).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("/", response_model=AccountResponse, status_code=201)
def create_account(account: AccountCreate, db: Session = Depends(get_db)):
    """
    Create a new account
    """
    # Check if account number already exists
    existing = db.query(Account).filter(Account.account_number == account.account_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Account number already exists")

    # Check if parent account exists
    if account.parent_account_id:
        parent = db.query(Account).filter(Account.id == account.parent_account_id).first()
        if not parent:
            raise HTTPException(status_code=400, detail="Parent account not found")

    new_account = Account(**account.model_dump())
    db.add(new_account)
    db.commit()
    db.refresh(new_account)
    return new_account


@router.put("/{account_id}", response_model=AccountResponse)
def update_account(account_id: int, account: AccountUpdate, db: Session = Depends(get_db)):
    """
    Update an existing account
    """
    db_account = db.query(Account).filter(Account.id == account_id).first()
    if not db_account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Check if parent account exists
    if account.parent_account_id:
        parent = db.query(Account).filter(Account.id == account.parent_account_id).first()
        if not parent:
            raise HTTPException(status_code=400, detail="Parent account not found")

        # Prevent circular references
        if account.parent_account_id == account_id:
            raise HTTPException(status_code=400, detail="Account cannot be its own parent")

    update_data = account.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_account, field, value)

    db.commit()
    db.refresh(db_account)
    return db_account


@router.delete("/{account_id}")
def deactivate_account(account_id: int, db: Session = Depends(get_db)):
    """
    Deactivate an account (soft delete)
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Check if account has journal entries
    if account.journal_entry_lines:
        raise HTTPException(
            status_code=400,
            detail="Cannot deactivate account with existing journal entries. Mark as inactive instead."
        )

    account.is_active = False
    db.commit()
    return {"message": "Account deactivated successfully"}

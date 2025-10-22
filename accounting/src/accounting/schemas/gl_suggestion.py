"""Schemas for GL account suggestions and learning"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from decimal import Decimal


class GLSuggestion(BaseModel):
    """A suggested GL account for a transaction"""
    model_config = ConfigDict(from_attributes=True)

    account_id: int
    account_number: str
    account_name: str
    confidence_score: Decimal = Field(..., description="Confidence percentage (0-100)")
    suggestion_type: str = Field(..., description="vendor, pattern, or hybrid")
    reason: str = Field(..., description="Human-readable explanation of why this was suggested")
    times_used: int = Field(default=0, description="How many times this mapping has been used")


class GLSuggestionsResponse(BaseModel):
    """Response containing all GL suggestions for a transaction"""
    bank_transaction_id: int
    description: str
    amount: Decimal
    vendor_id: Optional[int] = None
    vendor_name: Optional[str] = None
    suggestions: List[GLSuggestion]
    total_suggestions: int
    auto_assign_enabled: bool = Field(default=False, description="True if highest confidence >90% and auto-assignment should occur")
    auto_assign_account_id: Optional[int] = Field(default=None, description="Account ID to auto-assign if enabled")


class LearningFeedback(BaseModel):
    """Feedback on whether a suggestion was accepted or rejected"""
    bank_transaction_id: int
    suggested_account_id: int
    actual_account_id: int
    was_accepted: bool = Field(..., description="True if user accepted the suggestion")
    suggestion_type: str = Field(..., description="vendor, pattern, or hybrid")

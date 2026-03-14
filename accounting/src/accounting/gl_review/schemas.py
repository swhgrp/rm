"""
Pydantic request/response schemas for GL Anomaly Review system.
"""
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

from accounting.gl_review.models import ALL_FLAG_TYPES, STATUS_OPEN, STATUS_REVIEWED, STATUS_DISMISSED, STATUS_ESCALATED


class GLReviewRunRequest(BaseModel):
    area_id: int
    date_from: date
    date_to: date
    use_ai: bool = True

    @field_validator("date_to")
    @classmethod
    def date_to_after_date_from(cls, v, info):
        if info.data.get("date_from") and v < info.data["date_from"]:
            raise ValueError("date_to must be on or after date_from")
        return v


class GLReviewRunResponse(BaseModel):
    run_id: str
    area_id: int
    status: str = "completed"
    step: Optional[str] = None
    total_flags: int
    by_severity: dict[str, int]
    by_flag_type: dict[str, int]


class GLFlagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    area_id: Optional[int] = None
    journal_entry_id: Optional[int] = None
    journal_entry_line_id: Optional[int] = None
    account_id: Optional[int] = None
    flag_type: str
    severity: str
    title: str
    detail: Optional[str] = None
    flagged_value: Optional[Decimal] = None
    expected_range_low: Optional[Decimal] = None
    expected_range_high: Optional[Decimal] = None
    period_date: Optional[date] = None
    status: str
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    ai_reasoning: Optional[str] = None
    ai_confidence: Optional[str] = None
    run_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GLFlagReviewRequest(BaseModel):
    status: str
    review_note: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        allowed = [STATUS_REVIEWED, STATUS_DISMISSED, STATUS_ESCALATED]
        if v not in allowed:
            raise ValueError(f"status must be one of: {', '.join(allowed)}")
        return v


class GLFlagBulkReviewRequest(BaseModel):
    flag_ids: list[int]
    status: str
    review_note: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        allowed = [STATUS_REVIEWED, STATUS_DISMISSED, STATUS_ESCALATED]
        if v not in allowed:
            raise ValueError(f"status must be one of: {', '.join(allowed)}")
        return v

    @field_validator("flag_ids")
    @classmethod
    def validate_flag_ids(cls, v):
        if not v:
            raise ValueError("flag_ids must not be empty")
        return v


class GLBaselineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    area_id: int
    account_id: int
    account_code: Optional[str] = None
    months_of_data: Optional[int] = None
    avg_monthly_balance: Optional[Decimal] = None
    stddev_monthly_balance: Optional[Decimal] = None
    avg_monthly_activity: Optional[Decimal] = None
    stddev_monthly_activity: Optional[Decimal] = None
    min_observed: Optional[Decimal] = None
    max_observed: Optional[Decimal] = None
    last_computed_at: Optional[datetime] = None


class GLReviewSummaryResponse(BaseModel):
    area_id: int
    open_flags: dict[str, int]
    last_run_date: Optional[datetime] = None
    top_flag_types: list[dict]
    top_flagged_accounts: list[dict]
    this_month_count: int
    last_month_count: int


class PaginatedFlagsResponse(BaseModel):
    items: list[GLFlagResponse]
    total: int
    page: int
    per_page: int
    pages: int

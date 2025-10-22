"""
Pydantic schemas for Cash Flow Statement
"""
from pydantic import BaseModel, Field
from decimal import Decimal
from datetime import date
from typing import List, Optional


class CashFlowLineItem(BaseModel):
    """Individual line item in the cash flow statement"""
    account_number: str
    account_name: str
    amount: Decimal
    description: Optional[str] = None

    class Config:
        from_attributes = True


class CashFlowSection(BaseModel):
    """A section of the cash flow statement (Operating, Investing, or Financing)"""
    section_name: str
    line_items: List[CashFlowLineItem]
    subtotal: Decimal


class CashFlowStatementResponse(BaseModel):
    """
    Complete Cash Flow Statement using the Indirect Method

    The indirect method starts with net income and adjusts for:
    1. Non-cash expenses (depreciation, amortization)
    2. Changes in working capital (AR, inventory, AP)
    3. Investing activities (asset purchases/sales)
    4. Financing activities (loans, equity, distributions)
    """
    # Report metadata
    start_date: date
    end_date: date
    area_name: Optional[str] = None  # Location name, or "All Locations" for consolidated
    area_id: Optional[int] = None

    # Starting point
    net_income: Decimal = Field(description="Net income from P&L")

    # Operating Activities (Indirect Method)
    operating_adjustments: List[CashFlowLineItem] = Field(
        description="Adjustments to reconcile net income to cash from operations"
    )
    operating_working_capital_changes: List[CashFlowLineItem] = Field(
        description="Changes in working capital accounts (AR, Inventory, AP, etc.)"
    )
    net_cash_from_operating: Decimal

    # Investing Activities
    investing_activities: List[CashFlowLineItem] = Field(
        description="Cash flows from investing (equipment, assets, etc.)"
    )
    net_cash_from_investing: Decimal

    # Financing Activities
    financing_activities: List[CashFlowLineItem] = Field(
        description="Cash flows from financing (loans, equity, distributions)"
    )
    net_cash_from_financing: Decimal

    # Summary
    net_increase_in_cash: Decimal
    cash_beginning_of_period: Decimal
    cash_end_of_period: Decimal

    class Config:
        from_attributes = True


class CashFlowSummary(BaseModel):
    """Summary metrics for cash flow analysis"""
    period_start: date
    period_end: date
    area_name: Optional[str] = None

    # Key metrics
    operating_cash_flow: Decimal
    investing_cash_flow: Decimal
    financing_cash_flow: Decimal
    net_cash_change: Decimal

    # Ratios
    operating_cash_flow_ratio: Optional[Decimal] = Field(
        None,
        description="Operating cash flow / Current liabilities"
    )
    cash_flow_margin: Optional[Decimal] = Field(
        None,
        description="Operating cash flow / Revenue"
    )
    free_cash_flow: Optional[Decimal] = Field(
        None,
        description="Operating cash flow - Capital expenditures"
    )

    class Config:
        from_attributes = True


class CashFlowComparison(BaseModel):
    """Multi-period cash flow comparison"""
    periods: List[str]  # Period labels (e.g., ["Jan 2025", "Feb 2025", "Mar 2025"])
    operating_cash_flows: List[Decimal]
    investing_cash_flows: List[Decimal]
    financing_cash_flows: List[Decimal]
    net_cash_changes: List[Decimal]
    ending_cash_balances: List[Decimal]

    class Config:
        from_attributes = True

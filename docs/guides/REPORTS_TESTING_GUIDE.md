# Accounting Reports Testing Guide

## Overview
This guide explains how to test the financial reports in the accounting system.

## Test Data Available
We have 3 test journal entries for October 2025:

### Entry 1: Cash Sale (Oct 18, 2025)
- **Debit**: 1590 - Accumulated Depreciation (ASSET) - $500.00
- **Credit**: 4000 - Sales (REVENUE) - $500.00
- **Status**: POSTED

### Entry 2: Office Supplies Purchase (Oct 17, 2025)
- **Debit**: 9000 - Corporate Overhead (EXPENSE) - $150.00
- **Credit**: 1590 - Accumulated Depreciation (ASSET) - $150.00
- **Status**: POSTED

### Entry 3: Accounts Payable Payment (Oct 16, 2025)
- **Debit**: 2100 - Accounts Payable (LIABILITY) - $300.00
- **Credit**: 1590 - Accumulated Depreciation (ASSET) - $300.00
- **Status**: POSTED

## Expected Report Results

### 1. Profit & Loss (Oct 1-31, 2025)
```
REVENUE
  4000 - Sales: $500.00
  Total Revenue: $500.00

COST OF GOODS SOLD
  (None)
  Total COGS: $0.00

GROSS PROFIT: $500.00

EXPENSES
  9000 - Corporate Overhead: $150.00
  Total Expenses: $150.00

NET INCOME: $350.00
```

### 2. Balance Sheet (As of Oct 31, 2025)
```
ASSETS
  1590 - Accumulated Depreciation: $50.00 Debit
    (500 debit - 150 credit - 300 credit = 50 debit)
  Total Assets: $50.00

LIABILITIES
  2100 - Accounts Payable: $300.00 Credit
    (300 debit = -300 or 0, started at some balance)
  Total Liabilities: $0.00 (if no beginning balance)

EQUITY
  Retained Earnings + YTD Net Income: $350.00
  Total Equity: $350.00

TOTAL ASSETS: $50.00
TOTAL LIABILITIES + EQUITY: $350.00

Note: Should balance if we include beginning balances
```

### 3. Trial Balance (As of Oct 31, 2025)
```
Account                         Debit      Credit
--------------------------------------------------------
1590 - Accumulated Deprec.     $500.00    $450.00
2100 - Accounts Payable        $300.00    $0.00
4000 - Sales                   $0.00      $500.00
9000 - Corporate Overhead      $150.00    $0.00
--------------------------------------------------------
TOTALS:                        $950.00    $950.00
Difference: $0.00 ✓ BALANCED
```

## How to Test Reports

### Via Web UI (Recommended)
1. Log in to https://rm.swhgrp.com/accounting/
2. Click "Reports" in the sidebar
3. Select the report tab you want to test
4. Enter date range (Oct 1-31, 2025)
5. Click "Generate Report"
6. Verify calculations match expected results above

### Via API (Requires Authentication)
```bash
# P&L Report
curl "https://rm.swhgrp.com/accounting/api/reports/profit-loss?start_date=2025-10-01&end_date=2025-10-31"

# Balance Sheet
curl "https://rm.swhgrp.com/accounting/api/reports/balance-sheet?as_of_date=2025-10-31"

# Trial Balance
curl "https://rm.swhgrp.com/accounting/api/reports/trial-balance?as_of_date=2025-10-31"

# General Ledger (account ID required)
curl "https://rm.swhgrp.com/accounting/api/reports/general-ledger/1?start_date=2025-10-01&end_date=2025-10-31"
```

## Validation Checklist

- [ ] **P&L Report**
  - [ ] Revenue section shows $500.00 from Sales
  - [ ] Expenses section shows $150.00 from Corporate Overhead
  - [ ] Net Income calculates to $350.00
  - [ ] Report displays properly with dark theme
  - [ ] Date range filters work correctly

- [ ] **Balance Sheet**
  - [ ] Assets section includes all asset accounts with balances
  - [ ] Liabilities section shows accounts payable
  - [ ] Equity includes YTD net income
  - [ ] Accounting equation balances (Assets = Liabilities + Equity)
  - [ ] Report displays properly with dark theme

- [ ] **Trial Balance**
  - [ ] All accounts with activity are listed
  - [ ] Debit and credit columns sum correctly
  - [ ] Total debits equal total credits
  - [ ] "Balanced" indicator shows correctly
  - [ ] Report displays properly with dark theme

- [ ] **General Ledger**
  - [ ] Transactions display in chronological order
  - [ ] Running balance calculates correctly
  - [ ] Beginning and ending balances are accurate
  - [ ] Only POSTED entries are included
  - [ ] Report displays properly with dark theme

- [ ] **Account Activity**
  - [ ] Filters work correctly
  - [ ] Date range selection functions properly
  - [ ] Account selection dropdown populated
  - [ ] Report displays properly with dark theme

## Next Steps

### Export Functionality
- Add CSV export for all reports
- Add PDF export option
- Include export date/time stamp
- Format numbers properly in exports

### Report Enhancements
- Add drill-down capability (click account to see details)
- Add comparison periods (current vs prior year)
- Add graphical representations
- Add notes and footnotes section

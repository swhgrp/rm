# Accounting System - Financial Management

## Overview

The Accounting System is a comprehensive double-entry accounting platform providing complete financial management including chart of accounts, journal entries, accounts payable/receivable, banking, and sophisticated financial reporting. This is the **most complex system** in the restaurant management platform with 157 Python files.

## Status: 97% Production Ready ✅

**Last Updated:** March 26, 2026

## Recent Updates

### March 26, 2026 - Daily Automated Accounting Review 🔥

**Daily Review System:**
- ✅ **Cross-system audit** — scans Accounting, Hub, and Inventory databases daily at 5 AM
- ✅ **10 check categories** — invoice accuracy, GL integrity, inventory costs, duplicate detection, Hub↔Accounting sync, pipeline health, beverage pricing, linen parse quality, delivery fee completeness
- ✅ **Email report** — HTML summary with critical/warning/info findings emailed to admin@swhgrp.com
- ✅ **Finding persistence** — `daily_review_runs` and `daily_review_findings` tables track all findings
- ✅ **Review spec** — `REVIEW_SPEC.md` defines all checks, auto-correction rules, duplicate resolution, and report format
- ✅ **Thread-safe** — runs in `asyncio.to_thread()` to avoid blocking the web server

**Vendor Bill Validation (4-layer defense-in-depth):**
- ✅ **Layer 1**: Post-parse validator catches total mismatches in Hub
- ✅ **Layer 2**: Hub sender rejects bills where lines don't sum to total (>$0.10)
- ✅ **Layer 3**: Accounting receiver rejects mismatched payloads
- ✅ **Layer 4**: JE balance check prevents unbalanced journal entries

**GL Sweep Fix:**
- ✅ **Thread pool execution** — nightly GL sweep and monthly baseline rebuild now run via `asyncio.to_thread()` to prevent blocking the async event loop

---

### January 15, 2026 - Dashboard Reorganization & GL Enhancements 📊

**Dashboard Reorganization:**
- ✅ **AP/AR Aging side-by-side** - Accounts Payable and Receivable aging now next to each other for easy comparison
- ✅ **Cash Position full-width** - Bank accounts displayed in responsive grid (4/row on large, 3/medium, 2/small)
- ✅ **Cleaner layout** - Total Available Cash moved to header row for better visual hierarchy
- ✅ **Top 5 Sales** - Limited sales breakdown to top 5 categories (matching Top 5 Expenses)

**Chart of Accounts Enhancements:**
- ✅ **View Transactions button** - Navigate directly to GL account transactions from chart of accounts
- ✅ **Both views supported** - Works in hierarchy view and flat list view

**Bank Account Fixes:**
- ✅ **Opening Balance Equity (3350)** - New account for bank opening balances (cleaner closing)
- ✅ **Area assignment fix** - SW Grill bank account now properly grouped on dashboard
- ✅ **Opening balance JE** - Auto-creates JE when opening balance is set

**POS Auto-Sync Reliability:**
- ✅ **Startup catchup function** - Automatically syncs missed days when container restarts
- ✅ **No sync gaps** - Handles container downtime during scheduled sync window

**Check Payments Page:**
- ✅ **Searchable vendor selection** - Type-ahead vendor search instead of dropdown
- ✅ **Vendor bills filtering** - Shows only selected vendor's bills
- ✅ **View bill button** - Quick access to bill details for reference
- ✅ **Fixed date display** - Correct EST timezone handling

---

### January 5, 2026 - Plaid Integration & Scheduler Service 🏦

**Plaid Bank Integration:**
- ✅ **Plaid Link integration** - Connect bank accounts via Plaid UI
- ✅ **Transaction sync** - Automated import of bank transactions
- ✅ **Account mapping** - Map Plaid accounts to GL bank accounts
- ✅ **Plaid service module** - `/src/accounting/services/plaid_service.py`
- ✅ **Environment configuration** - `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENVIRONMENT`

**Background Scheduler:**
- ✅ **APScheduler service** - Background job processing
- ✅ **Scheduled bank sync** - Periodic transaction import
- ✅ **Job monitoring** - Track scheduled task execution

**Database:**
- ✅ **23 Alembic migrations** - Full schema versioning tracked
- ✅ **26+ tables** - Comprehensive accounting data model

---

### November 30, 2025 - Journal Entry Corrections & Vendor Aliases 🔧

**Journal Entry Correction Feature:**
- ✅ Correct posted journal entries via reversal + re-entry
- ✅ Deferred reversal pattern (reversal only on save, not on form open)
- ✅ Reversal entries auto-post (POSTED status, not DRAFT)
- ✅ Pre-populated form for corrections

**Vendor Alias System:**
- ✅ New `VendorAlias` model for name normalization
- ✅ Map multiple vendor names to canonical vendors (e.g., "Gordon Food Service Inc." → "Gordon Food Service")
- ✅ Case-insensitive matching with unique index
- ✅ VendorService for alias resolution
- ✅ UI for managing aliases on vendors page

**Credit Memo Indicator:**
- ✅ Dashboard shows credit memos vs regular entries
- ✅ PDF link feature for viewing source invoices from Hub

### November 28, 2025 - Banking Dashboard v2 📊

- ✅ Real-time cash position reporting
- ✅ Cash flow trend analysis
- ✅ Account-level reconciliation status

## Purpose

- Full double-entry accounting system
- Chart of accounts management
- Journal entry processing
- Accounts Payable (AP) and Accounts Receivable (AR)
- Bank account reconciliation
- Financial reporting (Balance Sheet, P&L, Cash Flow)
- Multi-entity accounting (if needed)
- Budget management and variance analysis
- Fiscal period and year-end close
- Complete audit trail

## Technology Stack

- **Framework:** FastAPI (Python) with SQLAlchemy ORM
- **Database:** PostgreSQL 15
- **Migrations:** Alembic (not Django migrations)
- **Reporting:** ReportLab (PDF), openpyxl (Excel)
- **Frontend:** Bootstrap 5, Chart.js
- **Calculations:** Complex financial logic with decimal precision
- **API Documentation:** OpenAPI/Swagger (auto-generated)

## Features

### ✅ Implemented (95%)

**Chart of Accounts:**
- [x] Account hierarchy (parent-child relationships)
- [x] Account types (Asset, Liability, Equity, Revenue, Expense)
- [x] Account subtypes for detailed classification
- [x] Account codes and numbering
- [x] Active/inactive accounts
- [x] Account balance tracking
- [x] Account groups for reporting
- [x] Default accounts configuration

**Journal Entries:**
- [x] Manual journal entry creation
- [x] Auto-posting from other systems
- [x] Entry validation (debits = credits)
- [x] Multi-line entries
- [x] Reversal entries
- [x] Recurring entries
- [x] Entry approval workflow
- [x] Entry status (Draft, Posted, Reversed)
- [x] Entry attachments and documentation
- [x] Batch entry processing

**Accounts Payable:**
- [x] Vendor management
- [x] Bill entry and approval
- [x] Bill payment processing
- [x] Payment methods (check, ACH, wire, credit card)
- [x] Payment tracking and status
- [x] Aging reports (30/60/90 days)
- [x] Vendor statements
- [x] 1099 tracking and reporting
- [x] Recurring bills
- [x] Purchase order integration (from Inventory)

**Accounts Receivable:**
- [x] Customer management
- [x] Invoice creation and editing
- [x] Invoice templates
- [x] Payment receipt and application
- [x] Payment methods
- [x] Collections tracking
- [x] Aging reports
- [x] Customer statements
- [x] Credit memos and adjustments
- [x] Recurring invoices

**Banking:**
- [x] Bank account management
- [x] Bank transaction import
- [x] Bank reconciliation
- [x] Reconciliation workflow
- [x] Check printing
- [x] Deposit tracking
- [x] Bank feed integration (partial)
- [x] Transaction categorization
- [x] Cleared transaction tracking

**Financial Reporting:**
- [x] Balance Sheet
- [x] Profit & Loss Statement (Income Statement)
- [x] Cash Flow Statement
- [x] Trial Balance
- [x] General Ledger
- [x] Account transaction history
- [x] Custom date range reporting
- [x] Comparison reports (period over period)
- [x] Department/location reporting
- [x] Budget vs Actual reports
- [x] PDF and Excel export
- [x] Email report delivery

**Fiscal Management:**
- [x] Fiscal year definition
- [x] Fiscal period management
- [x] Period open/close
- [x] Year-end close process
- [x] Prior period adjustment handling
- [x] Audit trail for all transactions

**Budgeting (Partial - 40%):**
- [x] Budget creation and entry
- [x] Budget by account and period
- [x] Budget vs Actual reporting
- [ ] Variance analysis and alerts ❌
- [ ] Budget forecasting ❌
- [ ] Multi-year budgets ❌

**Cost of Goods Sold (COGS):**
- [x] COGS tracking
- [x] Inventory cost integration
- [x] Food cost percentage calculations
- [x] Recipe costing (basic)
- [x] Waste tracking

**Sales Analysis:**
- [x] Daily sales summary
- [x] Sales by category
- [x] Sales by location
- [x] Revenue analysis
- [x] Sales trends and reporting

**Multi-Entity Support:**
- [x] Separate books per entity/location
- [x] Consolidated reporting
- [x] Inter-company transactions
- [x] Entity-specific chart of accounts

**Dashboards:**
- [x] General accounting dashboard
- [x] Banking dashboard
- [x] AP/AR summary
- [x] Cash position
- [x] Key metrics and KPIs
- [x] Visual charts and graphs

**Role-Based Access Control:**
- [x] Admin - Full access
- [x] Accountant - All except period close
- [x] AP Clerk - Bills and payments only
- [x] AR Clerk - Invoices and receipts only
- [x] Read Only - Reports only
- [x] Manager - Department-specific access

### ❌ Missing (5%)

**Advanced Features:**
- [ ] Complete bank feed automation
- [ ] Advanced variance analysis with alerts
- [ ] Multi-year budget planning
- [ ] Forecasting and projections
- [ ] Fixed asset management (depreciation)
- [ ] Job costing
- [ ] Project accounting
- [ ] Advanced consolidation features

## Architecture

### Database Schema (26 Models - Most Complex System)

**Core Accounting:**
- `accounts` - Chart of accounts
- `account_types` - Asset, Liability, Equity, Revenue, Expense
- `account_subtypes` - Detailed classification
- `account_groups` - Reporting groups
- `account_balances` - Current balances by period
- `journal_entries` - JE headers
- `journal_entry_lines` - JE line items (debits/credits)

**AP/AR:**
- `vendors` - Vendor directory
- `customers` - Customer directory
- `bills` - Vendor bills
- `bill_items` - Bill line items
- `bill_payments` - Payment records
- `invoices` - Customer invoices
- `invoice_items` - Invoice line items
- `payments` - Payment receipts
- `credit_memos` - Customer credits

**Banking:**
- `bank_accounts` - Bank account master
- `bank_transactions` - Imported transactions
- `bank_reconciliations` - Reconciliation records
- `checks` - Check register

**Fiscal Management:**
- `fiscal_years` - Fiscal year definitions
- `fiscal_periods` - Accounting periods
- `period_locks` - Period close status

**Budgeting:**
- `budgets` - Budget headers
- `budget_items` - Budget by account and period

**Other:**
- `areas` - Department/location codes
- `daily_sales_summary` - Sales tracking
- `cogs` - Cost of goods sold
- `gl_learning` - Auto-categorization ML (future)

**Total:** 26+ database tables, 157 Python files

### Key SQLAlchemy Models

**Main Models:**
```python
# Core
Account - Chart of accounts entries
AccountType - ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE
JournalEntry - Header for journal entries
JournalEntryLine - Individual debits/credits

# AP/AR
Vendor - Supplier information
VendorAlias - Vendor name aliases (NEW - Nov 30, 2025)
VendorBill - Vendor bills/invoices
BillPayment - Payment records
Customer - Customer directory
CustomerInvoice - Customer invoices/bills
Payment - Customer payments

# Banking
BankAccount - Bank account master
BankTransaction - Transaction imports
BankReconciliation - Reconciliation process
SafeTransaction - Physical cash tracking (safe float)

# Fiscal
FiscalYear, FiscalPeriod - Period management

# Reporting
AccountBalance - Pre-calculated balances
DailySalesSummary - Sales data
Budget - Budget planning
```

## API Endpoints (28 API Files)

### Chart of Accounts

**GET /accounting/api/accounts/**
- List all accounts
- Query: `?type=ASSET&active=true`

**POST /accounting/api/accounts/**
- Create account

**GET /accounting/api/accounts/{id}/**
- Get account details with balance

**PUT /accounting/api/accounts/{id}/**
- Update account

**GET /accounting/api/accounts/{id}/transactions/**
- Get account transaction history

**GET /accounting/api/accounts/{id}/balance/**
- Get current balance

### Journal Entries

**GET /accounting/api/journal-entries/**
- List entries with filters

**POST /accounting/api/journal-entries/**
- Create journal entry

**POST /accounting/api/journal-entries/{id}/post/**
- Post entry (make permanent)

**POST /accounting/api/journal-entries/{id}/reverse/**
- Create reversal entry

**GET /accounting/api/journal-entries/{id}/audit/**
- Get entry audit trail

### Accounts Payable

**GET /accounting/api/vendors/**
- List vendors

**GET /accounting/api/bills/**
- List bills with aging

**POST /accounting/api/bills/**
- Create bill

**GET /accounting/api/bills/{id}/**
- Get bill details

**POST /accounting/api/bills/{id}/pay/**
- Record payment

**GET /accounting/api/bills/aging/**
- AP aging report

**POST /accounting/api/bills/payments/batch/**
- Batch payment processing

### Accounts Receivable

**GET /accounting/api/customers/**
- List customers

**GET /accounting/api/invoices/**
- List invoices

**POST /accounting/api/invoices/**
- Create invoice

**GET /accounting/api/invoices/{id}/**
- Get invoice details

**POST /accounting/api/invoices/{id}/send/**
- Email invoice to customer

**POST /accounting/api/payments/**
- Record customer payment

**GET /accounting/api/invoices/aging/**
- AR aging report

### Banking

**GET /accounting/api/bank-accounts/**
- List bank accounts

**POST /accounting/api/bank-transactions/import/**
- Import bank transactions

**GET /accounting/api/bank-accounts/{id}/reconcile/**
- Start reconciliation

**POST /accounting/api/bank-accounts/{id}/reconcile/complete/**
- Complete reconciliation

**GET /accounting/api/checks/**
- Check register

**POST /accounting/api/checks/print/**
- Generate check PDF

### Reporting

**GET /accounting/api/reports/balance-sheet/**
- Balance sheet report
- Query: `?as_of=YYYY-MM-DD&format=pdf`

**GET /accounting/api/reports/profit-loss/**
- P&L statement
- Query: `?start=YYYY-MM-DD&end=YYYY-MM-DD`

**GET /accounting/api/reports/cash-flow/**
- Cash flow statement

**GET /accounting/api/reports/trial-balance/**
- Trial balance

**GET /accounting/api/reports/general-ledger/**
- General ledger
- Query: `?account=X&start=YYYY-MM-DD&end=YYYY-MM-DD`

**GET /accounting/api/reports/budget-vs-actual/**
- Budget comparison

### Fiscal Management

**GET /accounting/api/fiscal-periods/**
- List fiscal periods

**POST /accounting/api/fiscal-periods/{id}/close/**
- Close accounting period

**POST /accounting/api/fiscal-years/{id}/close/**
- Year-end close

### Health

**GET /accounting/health**
- System health check

## Configuration

### Environment Variables (.env)

```bash
# Database
DATABASE_URL=postgresql://accounting_user:password@accounting-db:5432/accounting_db

# FastAPI Settings
SECRET_KEY=your-secret-key
DEBUG=False

# Portal Integration
PORTAL_URL=https://rm.swhgrp.com/portal
PORTAL_SECRET_KEY=same-as-portal-secret

# Multi-Currency (if needed)
DEFAULT_CURRENCY=USD
ENABLE_MULTICURRENCY=False

# Tax Settings
DEFAULT_TAX_RATE=0.08
TAX_CALCULATION_METHOD=inclusive

# Banking
PLAID_CLIENT_ID=your-plaid-client-id
PLAID_SECRET=your-plaid-secret
PLAID_ENV=sandbox  # or production

# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=accounting@example.com
EMAIL_HOST_PASSWORD=your-password

# File Storage
MEDIA_ROOT=/app/media
MEDIA_URL=/media/

# Reporting
ENABLE_PDF_REPORTS=True
ENABLE_EXCEL_EXPORT=True

# Audit Settings
ENABLE_AUDIT_LOG=True
AUDIT_RETENTION_DAYS=2555  # 7 years

# Feature Flags
ENABLE_BUDGETING=True
ENABLE_MULTI_ENTITY=True
ENABLE_JOB_COSTING=False
```

## Installation & Setup

### Prerequisites
- Docker and Docker Compose
- PostgreSQL 15
- Understanding of double-entry accounting

### Quick Start

1. **Set up environment:**
```bash
cd /opt/restaurant-system/accounting
cp .env.example .env
# Edit .env with configuration
```

2. **Build and start:**
```bash
docker compose up -d accounting-app accounting-db
```

3. **Run migrations:**
```bash
docker compose exec accounting-app alembic upgrade head
```

4. **Load chart of accounts:**
```bash
# Load default restaurant COA via Python script
docker compose exec accounting-app python -c "from accounting.fixtures.load_coa import load_default_coa; load_default_coa()"
```

5. **Create fiscal year:**
```bash
# Access via API or UI - no CLI command
# Use the Fiscal Periods page in the UI
```

6. **Create admin users:**
```bash
# Admin users are created in HR system (Portal reads from hr_db)
# Use HR system interface or direct SQL
```

7. **Access system:**
```
https://rm.swhgrp.com/accounting/
```

## Usage

### Setting Up Chart of Accounts

1. Navigate to Chart of Accounts
2. Review default accounts
3. Add custom accounts as needed
4. Set account codes (numbering system)
5. Define account types and subtypes
6. Configure default accounts (AR, AP, Cash, etc.)

### Recording a Journal Entry

1. Go to Journal Entries
2. Click "New Entry"
3. Enter date and description
4. Add debit lines (increase assets/expenses)
5. Add credit lines (increase liabilities/equity/revenue)
6. Verify debits = credits
7. Save as draft or post immediately

### Entering a Bill

1. Navigate to Accounts Payable
2. Click "New Bill"
3. Select vendor
4. Enter bill date and due date
5. Add line items with accounts
6. Add applicable taxes
7. Save bill

### Paying Bills

1. Go to Accounts Payable > Pay Bills
2. Select bills to pay
3. Choose payment method
4. Enter payment date
5. Print checks or record electronic payment
6. Post payments

### Creating an Invoice

1. Navigate to Accounts Receivable
2. Click "New Invoice"
3. Select customer
4. Enter invoice date and due date
5. Add line items with revenue accounts
6. Calculate taxes
7. Save and send to customer

### Bank Reconciliation

1. Go to Banking > Reconciliations
2. Select bank account
3. Enter statement ending date and balance
4. Import bank transactions (if available)
5. Match transactions to journal entries
6. Mark cleared transactions
7. Reconcile difference to zero
8. Complete reconciliation

### Running Reports

1. Navigate to Reports
2. Select report type
3. Choose date range
4. Apply filters (account, department, etc.)
5. Preview on screen
6. Export to PDF or Excel
7. Email or download

### Closing a Period

1. Ensure all transactions are posted
2. Run trial balance to verify accuracy
3. Make any adjusting entries
4. Run final reports
5. Go to Fiscal Periods
6. Select period to close
7. Click "Close Period"
8. Period is locked from further entries

## File Structure

```
accounting/
├── src/
│   └── accounting/
│       ├── models/              # 26 model files
│       │   ├── account.py
│       │   ├── journal_entry.py
│       │   ├── vendor.py
│       │   ├── bill.py
│       │   ├── customer.py
│       │   ├── invoice.py
│       │   ├── bank_account.py
│       │   ├── fiscal_period.py
│       │   └── ...
│       ├── api/                 # 28 API route files
│       │   ├── accounts.py
│       │   ├── journal_entries.py
│       │   ├── bills.py
│       │   ├── invoices.py
│       │   ├── banking.py
│       │   ├── reports.py
│       │   └── ...
│       ├── services/            # 17 service files
│       │   ├── accounting_service.py
│       │   ├── posting_service.py
│       │   ├── reporting_service.py
│       │   ├── reconciliation_service.py
│       │   ├── tax_service.py
│       │   └── ...
│       ├── templates/           # 38 HTML templates
│       │   ├── accounts/
│       │   ├── journal_entries/
│       │   ├── vendors/
│       │   ├── bills/
│       │   ├── customers/
│       │   ├── invoices/
│       │   ├── banking/
│       │   ├── reports/
│       │   └── dashboards/
│       ├── static/              # CSS, JS
│       ├── core/                # Settings
│       ├── main.py
│       └── __init__.py
├── migrations/                  # 50+ migrations
├── fixtures/                    # Default data
│   └── default_coa.json
├── Dockerfile
├── requirements.txt
├── .env
└── README.md
```

## Integration with Other Systems

### Inventory System
- **Receives:** Product cost data for COGS
- **Receives:** Purchase order data for AP
- **Sends:** Vendor payment status

### Events System (Future)
- **Receives:** Event revenue data
- **Receives:** Deposits and payments
- **Sends:** Financial reports

### HR System (Future)
- **Receives:** Payroll expenses
- **Receives:** Employee reimbursements
- **Sends:** Labor cost reports

### Integration Hub
- **Can sync:** QuickBooks Online
- **Can sync:** Xero
- **Can sync:** Bank feeds
- **Can sync:** Payment processors

## Troubleshooting

### Issue: Trial Balance doesn't balance
**Solution:**
- Review unposted journal entries
- Check for entry with debits ≠ credits
- Look for deleted/modified posted entries
- Run data integrity check

### Issue: Bank reconciliation won't complete
**Solution:**
- Verify all transactions are categorized
- Check for duplicate transactions
- Ensure statement balance is correct
- Look for pending/uncleared items

### Issue: Reports show incorrect balances
**Solution:**
- Verify fiscal periods are correctly set up
- Check account types are correct
- Ensure all entries are posted
- Rebuild account balances cache

### Issue: Can't close period
**Solution:**
- Check for unposted transactions in period
- Verify all reconciliations are complete
- Ensure user has permission
- Review period dependency chain

## Development

### Running Locally

```bash
cd /opt/restaurant-system/accounting
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set up database
cd src
alembic upgrade head

# Run server
uvicorn accounting.main:app --reload --port 8000
```

### Running Tests

```bash
pytest tests/
```

### Creating Custom Reports

```python
# In services/custom_reports.py
class CustomReportService:
    def generate_report(self, start_date, end_date):
        # Custom query logic
        return report_data
```

## Monitoring

### Health Check
```bash
curl https://rm.swhgrp.com/accounting/health
```

### Performance Monitoring
```bash
docker compose logs -f accounting-app
```

### Database Queries
Monitor slow queries in PostgreSQL logs

## Dependencies

Key packages (see requirements.txt):
- FastAPI 0.104+
- SQLAlchemy 2.0+
- Alembic (database migrations)
- psycopg2-binary (PostgreSQL driver)
- reportlab (PDF generation)
- openpyxl (Excel export)
- APScheduler (background jobs)
- Pydantic 2.0+
- python-jose (JWT authentication)
- Jinja2 (HTML templates)

## Security & Compliance

**Implemented:**
- Role-based access control (RBAC)
- Audit trail for all financial transactions
- Period locking to prevent changes
- User activity logging
- Data encryption at rest and in transit
- CSRF and XSS protection

**Compliance:**
- GAAP (Generally Accepted Accounting Principles)
- Double-entry accounting
- Audit trail retention
- Data backup and recovery
- Access controls and segregation of duties

## Best Practices

1. **Always verify debits = credits** before posting
2. **Close periods monthly** to prevent backdated entries
3. **Reconcile bank accounts monthly**
4. **Run trial balance regularly** to ensure accuracy
5. **Backup database daily** (critical financial data)
6. **Use batch operations** for performance
7. **Review audit logs** for unusual activity
8. **Test reports** before period close
9. **Document all adjusting entries**
10. **Maintain chart of accounts discipline**

## Future Enhancements

### Short-Term
- [ ] Complete bank feed automation
- [ ] Advanced variance analysis
- [ ] Automated alerts and notifications

### Medium-Term
- [ ] Fixed asset management with depreciation
- [ ] Job/project costing
- [ ] Multi-year budgeting
- [ ] Advanced forecasting

### Long-Term
- [ ] AI-powered categorization
- [ ] Predictive analytics
- [ ] Blockchain integration for audit trail
- [ ] Real-time consolidation
- [ ] Advanced workflow automation

## Support

For issues or questions:
- Check logs: `docker compose logs accounting-app`
- API docs: https://rm.swhgrp.com/accounting/docs (FastAPI Swagger UI)
- Health check: https://rm.swhgrp.com/accounting/health
- Trial balance: Always run to verify data integrity
- Contact: Finance Team / Development Team

## Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [GAAP Guidelines](https://www.fasb.org/)
- Internal Training: Accounting System Training Manual

## License

Proprietary - SW Hospitality Group Internal Use Only

---

**Note:** This is the most sophisticated system in the platform with 157 Python files and 38 templates and complex financial logic. Proper accounting knowledge is recommended for advanced usage.

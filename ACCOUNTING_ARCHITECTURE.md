# Restaurant Accounting System Architecture

## Overview
Separate microservice for restaurant accounting that integrates with the inventory system via API calls. Complete data isolation with independent database and deployment.

## System Architecture

### Services
```
┌─────────────────────────────────────────────────────────┐
│                    Nginx (Port 80/443)                  │
│  Routes: /api/* → inventory, /accounting/* → accounting │
└─────────────────────────────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
        ┌───────▼────────┐      ┌──────▼──────────┐
        │   Inventory    │      │   Accounting    │
        │   Service      │◄─────│   Service       │
        │  (Existing)    │ API  │    (New)        │
        └───────┬────────┘      └────────┬────────┘
                │                        │
        ┌───────▼────────┐      ┌────────▼────────┐
        │  Inventory DB  │      │  Accounting DB  │
        │  PostgreSQL    │      │  PostgreSQL     │
        └────────────────┘      └─────────────────┘
```

### Data Flow
- **One-way integration:** Accounting reads from Inventory via REST API
- **No direct DB access:** Accounting never touches inventory database
- **Read-only:** Inventory data is immutable from accounting perspective
- **Event-driven sync:** Accounting pulls data on-demand or scheduled

## Database Schema (Accounting)

### Core Tables

#### 1. Chart of Accounts
```sql
accounts (
  id SERIAL PRIMARY KEY,
  account_number VARCHAR(20) UNIQUE,
  account_name VARCHAR(200),
  account_type ENUM('ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE', 'COGS'),
  parent_account_id INTEGER REFERENCES accounts(id),
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)
```

#### 2. Journal Entries
```sql
journal_entries (
  id SERIAL PRIMARY KEY,
  entry_date DATE,
  entry_number VARCHAR(50) UNIQUE,
  description TEXT,
  reference_type VARCHAR(50), -- 'INVOICE', 'TRANSFER', 'WASTE', 'SALE'
  reference_id INTEGER,
  location_id INTEGER, -- links to inventory.locations via API
  created_by INTEGER, -- links to inventory.users via API
  approved_by INTEGER,
  status ENUM('DRAFT', 'POSTED', 'REVERSED'),
  created_at TIMESTAMP,
  posted_at TIMESTAMP
)
```

#### 3. Journal Entry Lines
```sql
journal_entry_lines (
  id SERIAL PRIMARY KEY,
  journal_entry_id INTEGER REFERENCES journal_entries(id),
  account_id INTEGER REFERENCES accounts(id),
  debit_amount DECIMAL(15,2),
  credit_amount DECIMAL(15,2),
  description TEXT,
  line_number INTEGER
)
```

#### 4. Fiscal Periods
```sql
fiscal_periods (
  id SERIAL PRIMARY KEY,
  period_name VARCHAR(50),
  start_date DATE,
  end_date DATE,
  year INTEGER,
  quarter INTEGER,
  status ENUM('OPEN', 'CLOSED', 'LOCKED'),
  closed_by INTEGER,
  closed_at TIMESTAMP
)
```

#### 5. Account Balances (cached)
```sql
account_balances (
  id SERIAL PRIMARY KEY,
  account_id INTEGER REFERENCES accounts(id),
  fiscal_period_id INTEGER REFERENCES fiscal_periods(id),
  location_id INTEGER,
  debit_balance DECIMAL(15,2),
  credit_balance DECIMAL(15,2),
  net_balance DECIMAL(15,2),
  updated_at TIMESTAMP
)
```

#### 6. Inventory Sync Log
```sql
inventory_sync_log (
  id SERIAL PRIMARY KEY,
  sync_type VARCHAR(50), -- 'INVOICE', 'TRANSFER', 'WASTE', 'COUNT'
  inventory_reference_id INTEGER,
  journal_entry_id INTEGER REFERENCES journal_entries(id),
  synced_at TIMESTAMP,
  status ENUM('SUCCESS', 'FAILED', 'PENDING'),
  error_message TEXT
)
```

#### 7. Vendors (mirrored for reporting)
```sql
vendors (
  id SERIAL PRIMARY KEY,
  inventory_vendor_id INTEGER UNIQUE, -- reference to inventory system
  vendor_name VARCHAR(200),
  account_payable_account_id INTEGER REFERENCES accounts(id),
  last_synced TIMESTAMP
)
```

#### 8. Cost of Goods Sold Tracking
```sql
cogs_transactions (
  id SERIAL PRIMARY KEY,
  transaction_date DATE,
  item_id INTEGER, -- from inventory system
  item_name VARCHAR(200),
  quantity DECIMAL(10,3),
  unit_cost DECIMAL(10,2),
  total_cost DECIMAL(12,2),
  location_id INTEGER,
  transaction_type ENUM('SALE', 'WASTE', 'TRANSFER_OUT'),
  journal_entry_id INTEGER REFERENCES journal_entries(id),
  created_at TIMESTAMP
)
```

## Integration Points with Inventory System

### API Endpoints Consumed from Inventory
```python
# Inventory Service endpoints that accounting will call
GET /api/invoices/{id}          # Get invoice details
GET /api/transfers/{id}         # Get transfer details
GET /api/waste/{id}             # Get waste record details
GET /api/pos/sales/{id}         # Get POS sale details
GET /api/items/{id}             # Get item details
GET /api/locations              # Get all locations
GET /api/vendors                # Get all vendors
```

### Automatic Journal Entry Creation

#### 1. From Invoices (Accounts Payable)
```
Debit:  Inventory Asset (by category)
Credit: Accounts Payable - Vendor
```

#### 2. From Transfers
```
Debit:  Inventory - Receiving Location
Credit: Inventory - Sending Location
```

#### 3. From Waste
```
Debit:  Waste Expense (by reason)
Credit: Inventory Asset
```

#### 4. From POS Sales (COGS)
```
Debit:  Cost of Goods Sold
Credit: Inventory Asset

Debit:  Cash/Accounts Receivable
Credit: Sales Revenue
```

## Feature Flag System

### Environment Variables
```bash
# .env for accounting service
ACCOUNTING_ENABLED=true
ACCOUNTING_DATABASE_URL=postgresql://accounting_user:accounting_pass@accounting-db:5432/accounting_db
INVENTORY_API_URL=http://app:8000/api
INVENTORY_API_KEY=shared-secret-key
AUTO_SYNC_ENABLED=true
SYNC_INTERVAL_MINUTES=15
```

### Control Mechanisms
1. **Docker Level:** Stop accounting containers to disable
2. **Application Level:** Check ACCOUNTING_ENABLED flag
3. **Frontend Level:** Hide accounting menu when disabled
4. **API Level:** Return 503 if accounting disabled

## API Structure (Accounting Service)

### Endpoints
```
/accounting/api/v1/
  ├── /accounts              # Chart of accounts CRUD
  ├── /journal-entries       # Journal entries
  ├── /fiscal-periods        # Period management
  ├── /reports
  │   ├── /balance-sheet
  │   ├── /income-statement
  │   ├── /trial-balance
  │   ├── /general-ledger
  │   └── /cogs-analysis
  ├── /sync
  │   ├── /invoices          # Manual sync trigger
  │   ├── /transfers
  │   ├── /waste
  │   └── /sales
  └── /settings              # Accounting settings
```

## Security & Data Integrity

### Measures
1. **Separate Database:** Complete isolation from inventory
2. **Read-only API Access:** Inventory data is immutable
3. **Audit Trail:** All entries logged with user/timestamp
4. **Period Locking:** Prevent changes to closed periods
5. **Journal Entry Validation:** Debits must equal credits
6. **Reconciliation Tools:** Compare inventory values to GL
7. **Independent Backups:** Different schedule from inventory

### Backup Strategy
```bash
# Accounting DB backup (more frequent, longer retention)
- Daily backups: 90 days retention
- Monthly backups: 7 years retention
- Before period close: permanent retention
```

## Deployment

### Docker Compose Addition
```yaml
accounting-db:
  image: postgres:15
  environment:
    POSTGRES_USER: accounting_user
    POSTGRES_PASSWORD: accounting_pass
    POSTGRES_DB: accounting_db
  volumes:
    - accounting_data:/var/lib/postgresql/data

accounting-app:
  build: ./accounting
  environment:
    - ACCOUNTING_ENABLED=true
    - DATABASE_URL=postgresql://accounting_user:accounting_pass@accounting-db:5432/accounting_db
    - INVENTORY_API_URL=http://app:8000/api
  depends_on:
    - accounting-db

volumes:
  accounting_data:
```

### Nginx Routing
```nginx
# Route accounting requests to accounting service
location /accounting/ {
    proxy_pass http://accounting-app:8000/;
}
```

## Migration Strategy

1. **Phase 1:** Deploy accounting service (disabled)
2. **Phase 2:** Create chart of accounts and configure
3. **Phase 3:** Enable auto-sync for new transactions
4. **Phase 4:** Backfill historical data (optional)
5. **Phase 5:** Enable accounting module in frontend

## Reporting Capabilities

### Financial Reports
- Balance Sheet (by location, consolidated)
- Income Statement (P&L)
- Trial Balance
- General Ledger
- Cash Flow Statement

### Operational Reports
- COGS by Item/Category
- Inventory Value Reconciliation
- Vendor Payables Aging
- Cost Analysis by Location
- Variance Analysis

## Technology Stack

### Backend
- **Framework:** FastAPI (Python 3.11)
- **Database:** PostgreSQL 15
- **ORM:** SQLAlchemy
- **Migrations:** Alembic
- **API Client:** httpx (for inventory API calls)

### Frontend
- **Same as inventory:** HTML5, JavaScript, Bootstrap 5
- **Charts:** Chart.js for financial visualizations
- **Tables:** DataTables for reports

## Development Roadmap

1. ✅ Architecture design (this document)
2. ⏳ Database schema and models
3. ⏳ Core API endpoints
4. ⏳ Inventory integration layer
5. ⏳ Automatic journal entry creation
6. ⏳ Financial reports
7. ⏳ Frontend interface
8. ⏳ Testing and validation

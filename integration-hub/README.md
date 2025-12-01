# Integration Hub - Invoice Processing & GL Mapping

## Overview

The Integration Hub is an **invoice processing and general ledger (GL) mapping system** that receives vendor invoices, maps line items to inventory items and GL accounts, and routes the processed invoices to both the Inventory and Accounting systems.

## Status: Production Ready (Core Features + Advanced Workflow) ✅

**Last Updated:** November 30, 2025

**Note:** This is NOT a vendor API integration platform. It does NOT connect to third-party vendor APIs like US Foods or Sysco. It is an internal hub for processing invoices and creating accounting journal entries.

## Recent Updates

### November 30, 2025 - Tax Double-Counting Fix 🔥

**Critical Accounting Fix:**
- ✅ Fixed tax being added twice when invoices have tax line items
- ✅ Detection logic: checks if items_total ≈ invoice_total (within $0.02)
- ✅ If tax already in items: skip proportional tax distribution
- ✅ Prevents "Bill total mismatch" errors in accounting

**Vendor Alias Integration:**
- ✅ Supports Accounting's new vendor alias system
- ✅ Better vendor name normalization from OCR

### November 25, 2025 - OCR Item Code Validation 🔧

**OCR Auto-Correction System:**
- ✅ Post-parse validation compares extracted codes against verified codes
- ✅ Digit similarity scoring for common OCR confusions (0↔6↔8, 1↔7↔I)
- ✅ Requires ≥80% similarity AND matching description words
- ✅ Only corrects against verified codes (is_verified=true OR occurrence_count≥3)

**Item Codes Page Filters:**
- ✅ "Unverified Only" filter - shows items needing review
- ✅ "Verified Only" filter - shows confirmed mappings
- ✅ Sorted by occurrence count DESC (review high-frequency first)

### November 11, 2025 - Multi-Page Invoice Parsing & Tax Handling 🔥

**Multi-Page OCR Fixed:**
- ✅ Fixed parser only reading page 1 of multi-page invoices
- ✅ Now processes ALL pages and converts each to base64 for GPT-4o Vision
- ✅ Increased max_tokens from 4096 to 8192 for multi-page responses
- ✅ Added "TOTALS FROM LAST PAGE ONLY" to system prompt

**Re-parse Invoice Button:**
- ✅ Manual re-parsing with updated OCR
- ✅ Non-blocking JavaScript (navigate away during 30-60 second parse)

**Tax Capitalization Fixed:**
- ✅ Vendor invoice tax is capitalized into item costs
- ✅ Tax distributed proportionally across GL accounts
- ✅ Changed validation to compare total_amount (with tax) vs invoice_total

**UI Improvements:**
- ✅ Compact "Mark as Statement" button (icon-only with tooltip)

### November 8, 2025 - Major Workflow Improvements 🚀

**Bulk Mapping System:**
- Bulk mapping by description - map once, apply to all occurrences
- Unmapped items page redesigned with unique item grouping
- Shows frequency count and affected invoices
- Orders by most common items first (10x faster workflow)

**Statement Handling:**
- Mark/unmark invoices as statements
- Statements blocked from routing to Inventory/Accounting
- New status: 'statement'

**Smart Auto-Send:**
- Only sends to Inventory if items have inventory categories
- Always sends to Accounting (all items have GL accounts)
- Auto-triggers send when invoice fully mapped via bulk action
- Better validation for inventory vs expense items

**UI Improvements:**
- Mapped items review page (view/edit all mapped items)
- Category mappings show full GL account names (1000 - Cash)
- Vendor selection/creation in invoice detail
- Invoice deletion with cascade cleanup
- PDF preview/download

**API Enhancements:**
- New inventory sync endpoints: `/_hub/sync` (no auth for internal calls)
- Bulk mapping endpoint: `POST /api/items/map-by-description`
- Statement marking: `POST /api/invoices/{id}/mark-statement`
- Invoice deletion: `DELETE /api/invoices/{id}`

### October 31, 2025 - Automated Email Intake 📧

- IMAP email monitoring (checks every 15 minutes)
- OpenAI GPT-4o Vision PDF parsing
- SHA-256 PDF deduplication
- Intelligent auto-mapping (vendor codes, fuzzy matching, category fallbacks)
- Email settings UI with connection testing

## Purpose

- **Automated email monitoring** - Check inbox every 15 minutes for invoice PDFs 📧
- **AI-powered parsing** - Extract invoice data using GPT-4o Vision 🤖
- Receive vendor invoices (email, manual upload, or API)
- Map invoice line items to inventory items (with bulk mapping) 🚀
- Map items to general ledger accounts (Asset, COGS, Waste, Revenue)
- **Smart routing** - Send to Inventory (inventory items) and/or Accounting (all items) 🧠
- Create and send journal entries to Accounting system via REST API
- Manage vendor master data across systems
- Track invoice processing status and errors
- **Statement handling** - Mark statements to prevent system routing 📋

## Technology Stack

- **Framework:** FastAPI (Python async)
- **Database:** PostgreSQL 15
- **AI/ML:** OpenAI GPT-4o Vision (invoice parsing) 🤖
- **PDF Processing:** PyPDF2, pdf2image 📄
- **Background Jobs:** APScheduler (email monitoring) ⏰
- **HTTP Client:** httpx (async)
- **Frontend:** Bootstrap 5, jQuery
- **Authentication:** Portal SSO integration (JWT tokens)
- **Server:** Uvicorn (ASGI)

## Features

### ✅ IMPLEMENTED

**Invoice Processing:**
- ✅ Manual invoice upload (PDF/data entry)
- ✅ **Automated email monitoring** (IMAP, checks every 15 minutes) 📧
- ✅ **AI-powered PDF parsing** (OpenAI GPT-4o Vision) 🤖
- ✅ **Statement detection** - Mark as statement to prevent sending to systems 🆕
- ✅ **Invoice deletion** - Cascade delete with PDF file cleanup 🆕
- ✅ **Vendor selection/creation** in invoice detail view 🆕
- ✅ API endpoint for invoice creation
- ✅ Invoice storage with vendor info, date, total amount
- ✅ Line item tracking (description, quantity, price, extended amount)
- ✅ Invoice status workflow (unmapped → ready → sent/partial/error/statement) 🆕

**Item Mapping:**
- ✅ Manual mapping of invoice items to inventory items
- ✅ **Bulk mapping by description** - Map once, apply to all occurrences 🆕
- ✅ **Unique item grouping** - Shows unmapped items grouped by description with frequency 🆕
- ✅ **Mapped items review page** - View and edit all mapped items 🆕
- ✅ GL account assignment (Asset, COGS, Waste, Revenue accounts)
- ✅ **Smart GL validation** - Different requirements for inventory vs expense items 🆕
- ✅ Mapping confidence tracking (Manual, Category Default, etc.)
- ✅ Category-level GL mapping fallbacks with full account names 🆕
- ✅ Unmapped items review UI (redesigned with aggregation) 🆕
- ✅ Support for non-inventory items (propane, linen, janitorial) 🆕

**System Integration:**
- ✅ **Smart auto-send logic** - Only sends to inventory if items have categories 🆕
- ✅ Send invoices to Inventory system (REST API) - Only for inventory items 🆕
  - Creates/updates vendors
  - Creates invoice records
  - Links items to inventory master data
- ✅ Send journal entries to Accounting system (REST API) - For all items 🆕
  - Groups items by GL asset account
  - Creates balanced journal entries (Dr = Cr)
  - Sends to accounting API
- ✅ Parallel sending to both systems (when applicable) 🆕
- ✅ **Auto-trigger send** when invoice fully mapped via bulk mapping 🆕
- ✅ Retry logic for failed sends
- ✅ Status tracking (sent_to_inventory, sent_to_accounting)
- ✅ **Statement prevention** - Statements blocked from system routing 🆕

**Vendor Management:**
- ✅ Vendor master data storage (name, email, phone, addresses)
- ✅ Vendor sync from Inventory system
- ✅ Vendor sync from Accounting system
- ✅ Bi-directional vendor sync (Hub → systems where missing)
- ✅ Duplicate detection by name matching
- ✅ Cross-reference tracking (inventory_vendor_id, accounting_vendor_id)

**Category GL Mappings:**
- ✅ Define GL accounts by invoice item category
- ✅ Fallback mapping when item not found in inventory
- ✅ Four GL account types:
  - Asset Account (Dr on receipt)
  - COGS Account (Dr when used/sold)
  - Waste Account (Dr when wasted)
  - Revenue Account (Cr when sold)

**User Interface:**
- ✅ Dashboard with invoice statistics
- ✅ Invoice list view with filters
- ✅ Invoice detail view with line item mapping
- ✅ Unmapped items review page
- ✅ Category GL mapping management
- ✅ Vendor management UI
- ✅ Bootstrap 5 responsive design
- ✅ Dark GitHub theme styling

**Security & Authentication:**
- ✅ Portal SSO integration
- ✅ JWT token validation
- ✅ User session management
- ✅ Role-based access (via Portal)

### ❌ NOT IMPLEMENTED

**Vendor API Integrations (Claimed but NOT Real):**
- ❌ US Foods API integration - Does NOT exist
- ❌ Sysco API integration - Does NOT exist
- ❌ Restaurant Depot API integration - Does NOT exist
- ❌ Any third-party vendor product catalog sync - NOT implemented
- ❌ Automated pricing updates from vendors - NOT implemented
- ❌ Vendor order submission - NOT implemented
- ❌ OAuth2 vendor authentication - NOT implemented

**Background Jobs & Scheduling:**
- ❌ Celery task queue - NOT installed
- ❌ Redis - NOT used
- ❌ Scheduled sync jobs - NOT implemented
- ❌ Automated background processing - NOT implemented
- Note: All operations are synchronous/async within FastAPI process

**Webhook System:**
- ❌ Webhook endpoint registration - NOT implemented
- ❌ Email invoice webhook - Stub only, not functional
- ❌ Payload validation - NOT implemented
- ❌ Event routing - NOT implemented
- ❌ Signature verification - NOT implemented
- Note: Only a placeholder endpoint exists

**Advanced Data Sync:**
- ❌ Product catalog sync from vendors - NOT applicable
- ❌ Inventory level updates - NOT implemented
- ❌ Pricing feeds - NOT implemented
- ❌ Order status tracking - NOT implemented
- ❌ Sync logging database tables - NOT implemented

**Advanced Features:**
- ❌ Rate limiting per vendor - NOT implemented
- ❌ Request throttling - NOT implemented
- ❌ Circuit breaker pattern - NOT implemented
- ❌ Advanced data transformation - NOT implemented
- ✅ **Fuzzy matching for items** - IMPLEMENTED (Nov 25) - OCR digit similarity scoring
- ❌ Machine learning suggestions - NOT implemented (uses rule-based matching)

## Architecture

### Database Schema (4 Models)

**Implemented Tables:**
- `hub_invoice` - Invoice headers (vendor, date, amounts, status)
- `hub_invoice_item` - Invoice line items with mapping data
- `item_gl_mapping` - Master GL account mappings for inventory items
- `category_gl_mapping` - Fallback GL mappings by category
- `vendor` - Vendor master data with system cross-references

**Key Models:**

```python
class HubInvoice:
    """Invoice header"""
    id: int
    vendor_id: int  # FK to Vendor
    invoice_number: str
    invoice_date: date
    total_amount: Decimal
    status: str  # 'unmapped', 'ready', 'sent', 'partial', 'error', 'statement' 🆕
    is_statement: bool  # Mark as statement (won't route to systems) 🆕
    sent_to_inventory: bool
    sent_to_accounting: bool
    inventory_invoice_id: int (nullable)
    accounting_invoice_id: int (nullable)
    error_message: str (nullable)
    pdf_path: str (nullable)  # Path to uploaded PDF file 🆕

class HubInvoiceItem:
    """Invoice line item with mapping"""
    id: int
    invoice_id: int  # FK to HubInvoice
    line_number: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    extended_amount: Decimal
    inventory_item_id: int (nullable)
    gl_asset_account: str (nullable)
    gl_cogs_account: str (nullable)
    gl_waste_account: str (nullable)
    gl_revenue_account: str (nullable)
    mapping_confidence: str  # 'Manual', 'Category Default', etc.
    mapping_method: str (nullable)

class ItemGLMapping:
    """Master GL mapping for inventory items"""
    id: int
    inventory_item_id: int (unique)
    inventory_item_name: str
    gl_asset_account: str
    gl_cogs_account: str
    gl_waste_account: str
    gl_revenue_account: str
    last_updated: datetime

class CategoryGLMapping:
    """Fallback GL mapping by category"""
    id: int
    category_name: str (unique)
    gl_asset_account: str
    gl_cogs_account: str
    gl_waste_account: str
    gl_revenue_account: str

class Vendor:
    """Vendor master data"""
    id: int
    name: str
    email: str (nullable)
    phone: str (nullable)
    address: str (nullable)
    city: str (nullable)
    state: str (nullable)
    zip_code: str (nullable)
    inventory_vendor_id: int (nullable)
    accounting_vendor_id: int (nullable)
```

## API Endpoints

### HTML Pages (FastAPI Templates)

**GET /**
- Dashboard with invoice statistics

**GET /invoices**
- Invoice list view

**GET /invoices/{invoice_id}**
- Invoice detail with item mapping UI

**POST /invoices/upload**
- Upload new invoice

**GET /unmapped-items**
- Review all unmapped items (grouped by unique description) 🆕

**GET /mapped-items** 🆕
- Review all mapped items with edit capability

**GET /category-mappings**
- Manage category GL mappings (with full GL account names) 🆕

**GET /vendors**
- Vendor management page

### API Endpoints (JSON)

**POST /api/items/{item_id}/map**
- Map single invoice item to inventory + GL accounts
- Body: `{"inventory_item_id": 123, "gl_asset": "1200", "gl_cogs": "5000", ...}`

**POST /api/items/map-by-description** 🆕
- Bulk map ALL items with matching description
- Body: `{"item_description": "...", "inventory_item_id": 123, "gl_cogs_account": "5000", ...}`
- Returns: `{"items_mapped": 15, "invoices_affected": 3, "invoices_ready": ["INV-001"]}`

**GET /api/items/{item_id}/suggestions**
- Get mapping suggestions (TODO - not implemented)

**POST /api/category-mappings**
- Create/update category GL mapping
- Body: `{"category": "Produce", "gl_asset": "1210", ...}`

**POST /api/invoices/{invoice_id}/send**
- Send invoice to Inventory/Accounting systems (smart routing) 🆕
- Returns: `{"status": "sent|partial|error", "inventory_sent": bool, "accounting_sent": bool}`

**POST /api/invoices/{invoice_id}/retry**
- Retry failed invoice send

**DELETE /api/invoices/{invoice_id}** 🆕
- Delete invoice, all items, and PDF file (cascade)
- Returns: `{"success": true, "items_deleted": 5}`

**POST /api/invoices/{invoice_id}/mark-statement** 🆕
- Mark/unmark invoice as statement
- Body: `{"is_statement": true}`
- Returns: `{"success": true, "status": "statement"}`

**GET /api/invoices/{invoice_id}/pdf** 🆕
- Download invoice PDF file

**GET /api/vendors/**
- List all vendors

**POST /api/vendors/**
- Create new vendor
- Body: `{"name": "US Foods", "email": "...", ...}`

**POST /api/vendors/sync**
- Sync vendors from Inventory and Accounting systems
- Returns: `{"synced": 15, "created": 3, "updated": 2}`

**GET /api/auth/sso-login**
- Portal SSO login endpoint
- Query params: `?token=<jwt_token>`

**GET /health**
- Health check endpoint

## Configuration

### Environment Variables (.env)

```bash
# Database
DATABASE_URL=postgresql://integration_user:password@integration-db:5432/integration_db

# Portal Integration
PORTAL_URL=https://rm.swhgrp.com/portal
PORTAL_SECRET_KEY=same-as-portal-secret

# System URLs (internal Docker network)
INVENTORY_URL=http://inventory-app:8000
ACCOUNTING_URL=http://accounting-app:8001

# Internal Service Authentication
X_PORTAL_AUTH=your-internal-service-secret
```

## Installation & Setup

### Prerequisites
- Docker and Docker Compose
- PostgreSQL 15

### Quick Start

1. **Environment setup:**
```bash
cd /opt/restaurant-system/integration-hub
cp .env.example .env
# Edit .env with your configuration
```

2. **Build and start:**
```bash
docker compose up -d integration-hub integration-db
```

3. **Run migrations:**
```bash
docker compose exec integration-hub alembic upgrade head
```

4. **Access system:**
```
https://rm.swhgrp.com/hub/
```

## Usage

### Processing an Invoice

1. Navigate to https://rm.swhgrp.com/hub/
2. Click "Upload Invoice" or use API to create invoice
3. System creates invoice record with line items
4. Go to "Unmapped Items" to map items:
   - Select inventory item from dropdown
   - GL accounts auto-populate from ItemGLMapping
   - Or manually enter GL account codes
5. Once all items mapped, invoice status → "ready"
6. Click "Send to Systems" button
7. Hub sends invoice to Inventory system (creates vendor + invoice)
8. Hub creates journal entry and sends to Accounting system
9. Status updates to "sent" (or "partial" if one system fails)

### Managing Category Mappings

1. Go to "Category Mappings" page
2. Click "Add Category Mapping"
3. Enter category name (e.g., "Produce")
4. Enter GL account codes:
   - Asset Account (e.g., "1210" - Produce Inventory)
   - COGS Account (e.g., "5010" - Food Cost - Produce)
   - Waste Account (e.g., "5900" - Waste)
   - Revenue Account (e.g., "4000" - Food Sales)
5. Save
6. When invoice items don't match inventory, system uses category mapping as fallback

### Syncing Vendors

1. Go to "Vendors" page
2. Click "Sync Vendors from Systems"
3. Hub fetches vendors from Inventory and Accounting APIs
4. Matches vendors by name
5. Creates Hub vendor records
6. Updates cross-references (inventory_vendor_id, accounting_vendor_id)
7. Pushes Hub vendors back to systems where missing

## Integration with Other Systems

### Inventory System Integration

Hub sends invoices to Inventory via POST request:

**Endpoint:** `POST {INVENTORY_URL}/api/invoices/from-hub`

**Payload:**
```json
{
  "hub_invoice_id": 123,
  "vendor": {
    "name": "US Foods",
    "email": "orders@usfoods.com"
  },
  "invoice_number": "INV-12345",
  "invoice_date": "2025-10-30",
  "total_amount": 1234.56,
  "items": [
    {
      "hub_item_id": 456,
      "inventory_item_id": 789,
      "description": "Roma Tomatoes",
      "quantity": 10,
      "unit_price": 2.50,
      "extended_amount": 25.00
    }
  ]
}
```

**Response:**
```json
{
  "inventory_invoice_id": 789,
  "status": "created"
}
```

### Accounting System Integration

Hub creates journal entries for Accounting via POST request:

**Endpoint:** `POST {ACCOUNTING_URL}/api/journal-entries/from-hub`

**Payload:**
```json
{
  "hub_invoice_id": 123,
  "invoice_number": "INV-12345",
  "invoice_date": "2025-10-30",
  "vendor_name": "US Foods",
  "description": "Invoice INV-12345 from US Foods",
  "lines": [
    {
      "account": "1210",
      "description": "Produce inventory",
      "debit": 250.00,
      "credit": 0
    },
    {
      "account": "2000",
      "description": "Accounts Payable - US Foods",
      "debit": 0,
      "credit": 250.00
    }
  ]
}
```

**Business Logic:**
- Groups invoice items by GL asset account
- Creates one Dr line per asset account (total extended amount)
- Creates one Cr line to Accounts Payable (total invoice amount)
- Validates Dr = Cr before sending

**Response:**
```json
{
  "journal_entry_id": 456,
  "status": "posted"
}
```

### Portal Integration

- Users authenticate via Portal SSO
- Portal generates JWT token
- User clicks "Integration Hub" link in Portal
- Link includes `?token=<jwt>` query parameter
- Hub validates token with Portal
- Creates/updates local user session

## File Structure

```
integration-hub/
├── src/
│   └── integration_hub/
│       ├── models/              # SQLAlchemy models (4 files)
│       │   ├── hub_invoice.py
│       │   ├── hub_invoice_item.py
│       │   ├── item_gl_mapping.py  (includes CategoryGLMapping)
│       │   └── vendor.py
│       ├── services/            # Business logic (5 files)
│       │   ├── inventory_sender.py    (180 lines)
│       │   ├── accounting_sender.py   (223 lines)
│       │   ├── auto_send.py           (290 lines)
│       │   ├── vendor_sync.py         (310 lines)
│       │   └── __init__.py
│       ├── templates/           # Jinja2 HTML templates (7 files)
│       │   ├── base.html
│       │   ├── dashboard.html
│       │   ├── invoices.html
│       │   ├── invoice_detail.html
│       │   ├── unmapped_items.html
│       │   ├── category_mappings.html
│       │   └── vendors.html
│       ├── static/              # CSS, JS, images
│       ├── database.py          # Database connection
│       ├── main.py              # FastAPI application (511 lines)
│       └── __init__.py
├── migrations/                  # Alembic migrations
├── Dockerfile
├── requirements.txt
├── .env
└── README.md
```

## Troubleshooting

### Issue: Invoice won't send - stuck in "ready" status
**Solution:**
- Check all items are mapped (inventory_item_id set)
- Check all items have GL accounts assigned
- Review error_message field on invoice record
- Check Inventory and Accounting systems are running
- Verify API URLs in .env are correct

### Issue: Journal entry not balanced
**Solution:**
- Total debits must equal total credits
- Check invoice total_amount matches sum of line item extended_amounts
- Review accounting_sender.py logic for grouping by asset account
- Check for rounding errors in decimal calculations

### Issue: Vendor sync not finding matches
**Solution:**
- Vendor names must match exactly (case-sensitive)
- Check vendor exists in both Inventory and Accounting systems
- Try manual vendor creation in Hub first
- Review vendor_sync.py logs for errors

### Issue: Can't access via Portal SSO
**Solution:**
- Verify PORTAL_SECRET_KEY matches Portal .env
- Check JWT token is valid (not expired)
- Ensure user exists in HR system
- Check Portal URL is correct in .env

### Issue: Items not auto-mapping to GL accounts
**Solution:**
- Check if inventory_item_id exists in item_gl_mapping table
- If not, either:
  - Create ItemGLMapping record manually, or
  - Create CategoryGLMapping for the item's category
- Review mapping_confidence and mapping_method fields for debugging

## Development

### Running Locally

```bash
cd /opt/restaurant-system/integration-hub

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Run development server
uvicorn integration_hub.main:app --reload --port 8000
```

### Creating Migrations

```bash
alembic revision --autogenerate -m "Description of changes"
alembic upgrade head
```

## Monitoring

### Health Check
```bash
curl https://rm.swhgrp.com/hub/health
```

### Logs
```bash
docker compose logs -f integration-hub
```

## Dependencies

Key packages (see requirements.txt for complete list):
- fastapi==0.104.1
- uvicorn[standard]==0.24.0
- sqlalchemy==2.0.23
- httpx==0.25.2 (async HTTP client)
- pydantic==2.5.0
- python-jose[cryptography]==3.3.0
- jinja2==3.1.2
- alembic (database migrations)

**Note:** Does NOT include Celery, Redis, pandas, or OAuth2 libraries despite previous claims.

## Security

**Authentication:**
- Portal SSO via JWT tokens
- Internal service authentication with X-Portal-Auth header

**Data Protection:**
- SQL injection prevention (SQLAlchemy ORM)
- XSS protection (Jinja2 auto-escaping)
- HTTPS only (via Nginx reverse proxy)

**Network Security:**
- Internal Docker network for service communication
- Public access only via Nginx reverse proxy
- No direct database access from outside

## Future Enhancements

### Potential Features

**Email Invoice Processing:**
- [ ] Email webhook implementation (currently stub only)
- [ ] PDF parsing for automatic line item extraction
- [ ] OCR for scanned invoices
- [ ] Email forwarding rules

**Automation:**
- [ ] Background job queue (Celery + Redis)
- [ ] Scheduled invoice processing
- [ ] Automated vendor matching
- [ ] Auto-send when fully mapped

**Advanced Mapping:**
- [ ] Fuzzy matching for inventory items
- [ ] Machine learning suggestions
- [ ] Mapping history and learning
- [ ] Bulk import of mappings

**Vendor API Integrations (Not Currently Implemented):**
- [ ] US Foods API - Product catalog, pricing, order submission
- [ ] Sysco API - Product catalog, pricing, order submission
- [ ] Restaurant Depot - Product catalog
- [ ] EDI (Electronic Data Interchange) for invoices
- [ ] Automated invoice receipt from vendor systems

**Reporting:**
- [ ] Invoice processing analytics
- [ ] Mapping accuracy metrics
- [ ] GL distribution reports
- [ ] Vendor spending analysis

**Webhook System:**
- [ ] Generic webhook registration
- [ ] Event routing
- [ ] Retry logic with exponential backoff
- [ ] Webhook event history

## Support

For issues or questions:
- Check logs: `docker compose logs integration-hub`
- Health check: https://rm.swhgrp.com/hub/health
- Contact: Development Team

## License

Proprietary - SW Hospitality Group Internal Use Only

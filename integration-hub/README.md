# Integration Hub - Invoice Processing & GL Mapping

## Overview

The Integration Hub is an **invoice processing and general ledger (GL) mapping system** that receives vendor invoices, maps line items to inventory items and GL accounts, and routes the processed invoices to both the Inventory and Accounting systems. It also serves as the **source of truth** for vendor items, UOM, and categories.

## Status: Production Ready (~98% Complete) ✅

**Last Updated:** February 11, 2026

**Note:** This is NOT a vendor API integration platform. It does NOT connect to third-party vendor APIs like US Foods or Sysco. It is an internal hub for processing invoices and creating accounting journal entries.

### Source of Truth Architecture (Dec 27, 2025)

The Integration Hub is the **source of truth** for:
- **Invoices** - All invoice data, processing, and routing
- **Vendor Items** - Vendor-specific product catalog with location-aware pricing
- **Vendors** - Canonical vendor records with alias normalization
- **GL Mappings** - Item and category GL account mappings
- **UOM (Units of Measure)** - Global units with MeasureType (each, weight, volume)
- **Categories** - Hierarchical product categories

The Inventory system owns:
- **Master Items** - Central item catalog
- **Count Units** - Per-item counting units with conversion factors
- **Location Costs** - Weighted average cost per item per location
- **Locations** - Restaurant locations (source of truth for all systems)

## Recent Updates

### February 11, 2026 - Multi-UOM System, Catch-Weight Support & UI Redesign 📏🥩🎨

**Multi-UOM Architecture (replaces `price_is_per_unit` guessing):**
- ✅ **`vendor_item_uoms` table** — Multiple purchase UOMs per vendor item with `conversion_factor`
- ✅ **`matched_uom_id`** on `hub_invoice_items` — FK to `vendor_item_uoms`, set at mapping time
- ✅ **Deterministic cost calculation** — `cost_per_primary = unit_price / conversion_factor` (no guessing)
- ✅ **UOM normalizer** (`uom_normalizer.py`) — Normalizes invoice UOM strings → standard abbreviations
- ✅ **Auto-mapper UOM matching** — `match_invoice_uom_to_vendor_uom()`: exact → normalized → default fallback
- ✅ **UOM CRUD API** — GET/POST/PUT/DELETE at `/api/v1/vendor-items/{id}/uoms`
- ✅ **Last cost tracking** — `vendor_item_uoms.last_cost` / `last_cost_date` auto-populated from invoices
- ✅ **Legacy fallback** — `price_is_per_unit` flag still set during transition; cost updater prefers `matched_uom_id`

**Catch-Weight Item Support:**
- ✅ **GFS catch-weight detection** — Vendor parsing rule detects "WEIGHT:" pattern on GFS invoices
- ✅ **LB as default UOM** — Catch-weight items use LB (cf=1) as default, not CS
- ✅ **Weight extracted as quantity** — Parser extracts actual weight from invoice text
- ✅ **GFS UOM import script** (`scripts/import_gfs_uoms.py`) — Handles multiple CSV formats
- ✅ **Catch-weight fix script** (`scripts/fix_catchweight_uoms.py`) — Corrects existing items
- ✅ **Invoice re-parse script** (`scripts/reparse_gfs_catchweight_invoices.py`)

**Vendor Parsing Rules:**
- ✅ **Breakthru Beverage** — AI instructions for Case/Btles/Pieces column disambiguation
- ✅ **Gordon Food Service** — Catch-weight detection via "WEIGHT:" pattern

**Compact UI Redesign:**
- ✅ **All pages compacted** — Smaller headers, tighter cards, reduced padding across Dashboard, Invoices, Vendor Items, Vendors, Expense Items, Unmapped Items
- ✅ **Icon-only action buttons** — Invoices page uses compact icon buttons instead of text labels
- ✅ **Simplified upload modal** — Dashboard upload matches Invoices page (file-only, AI extracts everything)

**Inventory Service Changes:**
- ✅ **Vendor items read-only** — Inventory UI is now read-only for vendor item data (Hub is source of truth)
- ✅ **Removed CRUD endpoints** — POST/PUT/DELETE vendor item endpoints removed from Inventory API

**User Manual:**
- ✅ **`INTEGRATION_HUB_MANUAL.md`** — Comprehensive user manual covering all Hub pages and workflows

**Database Migrations:**
- `20260211_0001_add_price_is_per_unit.py` — price_is_per_unit column
- `20260212_0001_add_vendor_item_uoms.py` — vendor_item_uoms table + matched_uom_id
- `20260212_0002_seed_vendor_item_uoms.py` — Data migration from existing vendor items
- `20260212_0003_add_last_cost_to_vendor_item_uoms.py` — last_cost/last_cost_date columns

**New Files:**
- `models/vendor_item_uom.py` — VendorItemUOM model
- `services/uom_normalizer.py` — UOM string normalization
- `scripts/import_gfs_uoms.py` — GFS UOM CSV import
- `scripts/fix_catchweight_uoms.py` — Catch-weight UOM corrections
- `scripts/reparse_gfs_catchweight_invoices.py` — GFS invoice re-parse
- `scripts/update_gfs_catchweight_rules.py` — GFS parsing rule updates
- `INTEGRATION_HUB_MANUAL.md` — User manual

---

### December 28, 2025 - Expense Items vs Vendor Items Separation 📦💰

**IMPORTANT: Clear distinction between Vendor Items and Expense Items:**

**Vendor Items** (`hub_vendor_items` table):
- Items linked to Inventory master items (`inventory_master_item_id IS NOT NULL`)
- Tracked inventory items that get counted
- Appear on Vendor Items page
- Have pricing history, location costs, sizing

**Expense Items** (`invoice_item_mapping_deprecated` table):
- Items mapped only to expense GL accounts (no inventory tracking)
- Supplies, services, non-inventory purchases (janitorial, linen, propane, office supplies)
- Appear on Expense Items page ONLY
- Map to COGS/Expense GL accounts

**Key Behavior:**
- When a vendor item is "converted to expense", it is **deleted** from `hub_vendor_items`
- A new mapping is created in `invoice_item_mapping_deprecated` with the expense GL account
- Items cannot appear in both lists - they are mutually exclusive
- Vendor Items page filters: `WHERE inventory_master_item_id IS NOT NULL`

**UI Changes:**
- ✅ "Map to Expense" button on vendor item detail page
- ✅ Searchable expense account dropdown (type-to-filter)
- ✅ Expense Items page at `/expense-items`
- ✅ Confirmation modal before conversion

---

### December 28, 2025 - AI Semantic Search & Backbar-Style Sizing 🤖📦

**NEW: AI-Powered Semantic Search for Vendor Items**
- ✅ **OpenAI Embeddings** - Uses text-embedding-3-small model (1536 dimensions)
- ✅ **Semantic similarity search** - Find similar items across vendors using natural language
- ✅ **pgvector integration** - HNSW index for fast similarity lookups
- ✅ **Confidence levels** - High (85%+), Medium (70%+), Low (55%+) matches
- ✅ **Batch embedding generation** - Efficient bulk processing for existing items
- ✅ **AI Search UI** - Search bar on vendor items page with real-time results
- ✅ **Similar items finder** - Find duplicates or related items from any vendor item

**API Endpoints (`/api/v1/similarity/`):**
- `GET /stats` - Embedding coverage statistics
- `POST /search` - Search by text description
- `GET /item/{id}` - Find items similar to existing vendor item
- `POST /generate` - Batch generate embeddings for items
- `POST /item/{id}/generate` - Generate embedding for single item

**NEW: Backbar-Style Sizing System**
- ✅ **Size Units table** (`hub_size_units`) - L, ml, lb, oz, g, kg, etc. with conversion factors
- ✅ **Containers table** (`hub_containers`) - bottle, can, bag, box, keg, etc.
- ✅ **Structured sizing** - Size = [Quantity] [Unit] [Container] (e.g., "750 ml bottle", "25 lb bag")
- ✅ **Units per case** - How many individual units in a purchasing case
- ✅ **Case cost tracking** - Price per case from invoices
- ✅ **Auto-calculated unit cost** - `case_cost / units_per_case`

**Size Settings Management UI (`/settings/size`):**
- ✅ **Size Units CRUD** - Manage measurement units with conversion factors
- ✅ **Containers CRUD** - Manage container types
- ✅ **Measure type grouping** - Volume, Weight, Count categories
- ✅ **Sort order management** - Control dropdown display order

**Vendor Item Detail Page (`/vendor-item-detail?id=X`):**
- ✅ **Comprehensive view** - All product details, pricing, location costs
- ✅ **Edit modal** - Update sizing, pricing, and mappings
- ✅ **Price history** - Track cost changes over time (30/60/90/180/365 days)
- ✅ **AI mapping suggestions** - Semantic search for master item matches
- ✅ **Review workflow** - Approve/reject items needing review

**Database Migrations (Dec 27):**
- `20251227_0001_add_embedding_columns.py` - pgvector embedding support
- `20251227_0002_add_unit_uom_columns.py` - Unit UOM fields
- `20251227_0003_add_backbar_size_fields.py` - Size system tables and fields

**New Models:**
- `SizeUnit` - Size measurement units (ml, L, oz, lb, g, kg, each, pack, case, etc.)
- `Container` - Container types (bottle, can, bag, box, keg, jug, pack, etc.)

**HubVendorItem New Fields:**
- `size_quantity` - Numeric size value (e.g., 750, 1, 25)
- `size_unit_id` - FK to hub_size_units
- `container_id` - FK to hub_containers
- `units_per_case` - Units per purchasing case
- `case_cost` - Cost per case
- `embedding` - Vector(1536) for semantic search
- `embedding_generated_at` - Embedding timestamp

**Configuration Required:**
- `OPENAI_API_KEY` - Required for embedding generation (optional - feature disabled without it)
- PostgreSQL with pgvector extension - Required for similarity search

---

### December 27, 2025 - Location-Aware Costing Architecture 🏗️

**Major Architecture Refactor:**
- ✅ **Inventory owns Locations** - All location data managed in Inventory
- ✅ **Accounting syncs from Inventory** - New sync endpoint for locations
- ✅ **Hub vendor items location-aware** - VendorItemStatus enum (active, needs_review, inactive)
- ✅ **Invoice-derived pricing** - Prices per location from invoice history

**New Hub Models:**
- ✅ **MeasureType enum** - each, weight, volume for UOM categorization
- ✅ **VendorItemStatus enum** - active, needs_review, inactive
- ✅ **Location-aware fields** - `location_id`, `last_purchase_price`, `previous_purchase_price`
- ✅ **Pack conversion** - `pack_to_primary_factor` for unit conversions

**New Inventory Models (updated by Hub):**
- ✅ **MasterItemCountUnit** - Multiple count units per item
- ✅ **MasterItemLocationCost** - Weighted average cost per location
- ✅ **MasterItemLocationCostHistory** - Cost change audit trail

**Migration Stats:**
- Hub: 23 UOMs with measure_type (10 each, 9 volume, 4 weight)
- Hub: 908 vendor items with location_id and status
- Inventory: 409 count units created
- Inventory: 372 location cost records (62 items × 6 locations)

---

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
- **Database:** PostgreSQL 15 with pgvector extension
- **AI/ML:**
  - OpenAI GPT-4o Vision (invoice parsing) 🤖
  - OpenAI text-embedding-3-small (semantic search) 🔍
- **Vector Search:** pgvector with HNSW index (similarity search) 🎯
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

**AI-Powered Features (Dec 28, 2025):** 🤖
- ✅ **Semantic search** - Find vendor items using natural language descriptions
- ✅ **Similar item detection** - Find duplicates/related items across vendors
- ✅ **AI mapping suggestions** - Semantic search for master item matching
- ✅ **Embedding coverage stats** - Track which items have embeddings
- ✅ **Batch embedding generation** - Efficiently process existing items
- ✅ **Confidence scoring** - High/Medium/Low match indicators

**Vendor Item Management (Dec 28, 2025):** 📦
- ✅ **Vendor item detail page** - Comprehensive view with pricing, history, mappings
- ✅ **Backbar-style sizing** - [Quantity] [Unit] [Container] format
- ✅ **Size units management** - Volume, weight, count units with conversions
- ✅ **Container types** - Bottle, can, bag, box, keg, etc.
- ✅ **Units per case** - Track case quantities
- ✅ **Case cost tracking** - Invoice-derived pricing
- ✅ **Auto unit cost** - Calculated from case cost / units per case
- ✅ **Price history** - Track cost changes over time (30/60/90/180/365 days)
- ✅ **Review workflow** - Approve/reject items needing review
- ✅ **Size settings UI** - Manage units and containers at `/settings/size`

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

**GET /vendor-items** 🆕
- Vendor items list with AI search bar
- Only shows items with inventory master item link

**GET /vendor-item-detail?id=X** 🆕
- Comprehensive vendor item detail page
- "Map to Expense" button with searchable GL account dropdown

**GET /expense-items** 🆕
- Expense items list (items mapped to expense GL accounts only)
- Shows items NOT tracked in inventory

**GET /settings/size** 🆕
- Size units and containers management

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

**POST /api/vendor-items/{id}/convert-to-expense** 🆕
- Convert vendor item to expense (deletes from vendor items, creates expense mapping)
- Body: `{"gl_cogs_account": 5200}`
- Returns: `{"success": true, "message": "...", "mapping_id": 123}`

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

### AI Similarity Search API (Dec 28, 2025) 🤖

**GET /api/v1/similarity/stats**
- Get embedding coverage statistics
- Returns: `{"total_items": 908, "with_embedding": 450, "coverage_percent": 49.6, "pgvector_available": true, "openai_configured": true}`

**POST /api/v1/similarity/search**
- Search vendor items by text description
- Body: `{"text": "red wine", "limit": 15, "min_similarity": 0.35}`
- Returns: `{"query": "red wine", "results": [{...similarity_results...}]}`

**GET /api/v1/similarity/search?text=X&limit=15&min_similarity=0.35**
- GET version of similarity search

**GET /api/v1/similarity/item/{vendor_item_id}**
- Find items similar to an existing vendor item
- Query params: `?limit=10&min_similarity=0.4`
- Returns: Similar items with confidence levels (high/medium/low)

**POST /api/v1/similarity/generate**
- Batch generate embeddings for items without them
- Body: `{"batch_size": 100}`
- Returns: `{"generated": 100, "failed": 0, "remaining": 358}`

**POST /api/v1/similarity/item/{vendor_item_id}/generate**
- Generate/regenerate embedding for single item
- Returns: Updated vendor item with new embedding

### Size Settings API (Dec 28, 2025) 📦

**GET /api/v1/size-settings/units**
- List all size units with measure type grouping

**POST /api/v1/size-settings/units**
- Create new size unit
- Body: `{"name": "gallon", "symbol": "gal", "measure_type": "volume", "conversion_to_base": 3785.41}`

**PATCH /api/v1/size-settings/units/{id}**
- Update size unit

**GET /api/v1/size-settings/containers**
- List all container types

**POST /api/v1/size-settings/containers**
- Create new container type
- Body: `{"name": "keg", "is_active": true, "sort_order": 10}`

**PATCH /api/v1/size-settings/containers/{id}**
- Update container type

### Vendor Item UOM API (Feb 11, 2026) 📏

**GET /api/v1/vendor-items/{id}/uoms**
- List all purchase UOMs for a vendor item
- Returns: `[{"id": 1, "uom_abbreviation": "cs", "conversion_factor": 12, "is_default": true, "last_cost": 306.00, ...}]`

**POST /api/v1/vendor-items/{id}/uoms**
- Add a purchase UOM
- Body: `{"uom_id": 3, "conversion_factor": 12.0, "is_default": true}`

**PUT /api/v1/vendor-items/{id}/uoms/{uom_entry_id}**
- Update a purchase UOM (conversion factor, default, expected price)

**DELETE /api/v1/vendor-items/{id}/uoms/{uom_entry_id}**
- Deactivate a purchase UOM

### Vendor Items API (Dec 28, 2025) 📦

**GET /api/v1/vendor-items/**
- List vendor items with pagination and filters

**GET /api/v1/vendor-items/{id}**
- Get vendor item details

**PATCH /api/v1/vendor-items/{id}**
- Update vendor item (sizing, pricing, mappings)
- Supports new Backbar-style fields: `size_quantity`, `size_unit_id`, `container_id`, `units_per_case`, `case_cost`

**GET /api/v1/vendor-items/lookup/size-units**
- Get size units for dropdowns

**GET /api/v1/vendor-items/lookup/containers**
- Get containers for dropdowns

**POST /api/v1/vendor-items/review/{id}/approve**
- Approve vendor item (changes status to active)

**POST /api/v1/vendor-items/review/{id}/reject**
- Reject vendor item
- Query params: `?reason=duplicate`

**POST /api/v1/vendor-items/review/bulk-approve**
- Bulk approve multiple items
- Body: `{"item_ids": [1, 2, 3]}`

## Configuration

### Environment Variables (.env)

```bash
# Database (with pgvector extension for AI search)
DATABASE_URL=postgresql://integration_user:password@integration-db:5432/integration_db
INVENTORY_DATABASE_URL=postgresql://inventory_user:password@inventory-db:5432/inventory_db

# Portal Integration
PORTAL_URL=https://rm.swhgrp.com/portal
PORTAL_SECRET_KEY=same-as-portal-secret

# System URLs (internal Docker network)
INVENTORY_URL=http://inventory-app:8000
ACCOUNTING_URL=http://accounting-app:8001

# Internal Service Authentication
X_PORTAL_AUTH=your-internal-service-secret

# AI Features (Dec 28, 2025)
OPENAI_API_KEY=sk-...  # Required for AI semantic search (optional - feature disabled without it)
```

### Database Requirements

The Integration Hub requires PostgreSQL with the **pgvector** extension for AI semantic search:

```sql
-- Enable pgvector extension (run as superuser)
CREATE EXTENSION IF NOT EXISTS vector;

-- The migration will create the embedding column and HNSW index automatically
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
│       ├── api/                 # API routers (NEW Dec 28)
│       │   ├── similarity.py        # AI semantic search endpoints
│       │   ├── size_settings.py     # Size units & containers CRUD
│       │   ├── vendor_items.py      # Vendor item management
│       │   └── reporting.py         # Report endpoints
│       ├── models/              # SQLAlchemy models (9 files)
│       │   ├── hub_invoice.py
│       │   ├── hub_invoice_item.py  # matched_uom_id FK to vendor_item_uoms
│       │   ├── hub_vendor_item.py   # Vendor items with sizing & embeddings
│       │   ├── vendor_item_uom.py   # Multi-UOM per vendor item (NEW Feb 2026)
│       │   ├── item_gl_mapping.py   # (includes CategoryGLMapping)
│       │   ├── vendor.py
│       │   ├── size_unit.py         # Size units
│       │   ├── container.py         # Container types
│       │   └── __init__.py
│       ├── services/            # Business logic (8 files)
│       │   ├── inventory_sender.py
│       │   ├── accounting_sender.py
│       │   ├── auto_send.py
│       │   ├── vendor_sync.py
│       │   ├── uom_normalizer.py    # UOM string normalization (NEW Feb 2026)
│       │   ├── embedding_service.py # OpenAI embeddings
│       │   ├── reporting.py
│       │   └── __init__.py
│       ├── templates/           # Jinja2 HTML templates (12 files)
│       │   ├── base.html
│       │   ├── dashboard.html
│       │   ├── invoices.html
│       │   ├── invoice_detail.html
│       │   ├── unmapped_items.html
│       │   ├── mapped_items.html
│       │   ├── category_mappings.html
│       │   ├── vendors.html
│       │   ├── hub_vendor_items.html    # Vendor items list with AI search
│       │   ├── vendor_item_detail.html  # Vendor item detail page (NEW)
│       │   ├── size_settings.html       # Size units & containers (NEW)
│       │   └── settings.html
│       ├── static/              # CSS, JS, images
│       ├── db/
│       │   └── database.py      # Database connection
│       ├── main.py              # FastAPI application
│       └── __init__.py
├── alembic/                     # Alembic migrations
│   └── versions/
│       ├── 20251227_0001_add_embedding_columns.py     # pgvector
│       ├── 20251227_0002_add_unit_uom_columns.py      # Unit UOM
│       ├── 20251227_0003_add_backbar_size_fields.py   # Sizing system
│       ├── 20260211_0001_add_price_is_per_unit.py     # price_is_per_unit flag
│       ├── 20260212_0001_add_vendor_item_uoms.py      # Multi-UOM table + matched_uom_id
│       ├── 20260212_0002_seed_vendor_item_uoms.py     # Data migration
│       └── 20260212_0003_add_last_cost_to_vendor_item_uoms.py  # Last cost tracking
├── scripts/                     # Utility scripts
│   ├── import_gfs_uoms.py           # GFS UOM CSV import
│   ├── fix_catchweight_uoms.py      # Catch-weight UOM corrections
│   ├── reparse_gfs_catchweight_invoices.py  # Re-parse GFS invoices
│   └── update_gfs_catchweight_rules.py      # Update GFS parsing rules
├── INTEGRATION_HUB_MANUAL.md   # User manual
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

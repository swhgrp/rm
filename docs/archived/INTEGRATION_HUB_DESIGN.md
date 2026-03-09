# Integration Hub - Complete Design Document

**Created:** 2025-10-19
**Status:** In Development
**Priority:** Tier 1 - Critical for Inventory-Accounting Integration

---

## 🎯 PURPOSE

The Integration Hub is a **centralized microservice** that:
1. Receives invoices from multiple sources (email, upload, API)
2. Manages mappings between inventory items and GL accounts
3. Routes data to Inventory and Accounting systems
4. Maintains system independence (each can run standalone)
5. Provides UI for reviewing and approving unmapped items

---

## 🏗️ ARCHITECTURE

```
┌──────────────────────────────────────────────────────────────┐
│                     INTEGRATION HUB                          │
│                  (Central Orchestrator)                      │
│                                                              │
│  ┌────────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Invoice        │  │ Item-GL      │  │ Auto-Send       │ │
│  │ Receiver       │→ │ Mapper       │→ │ Service         │ │
│  │ (Email/Upload) │  │ (UI + Auto)  │  │                 │ │
│  └────────────────┘  └──────────────┘  └────────┬────────┘ │
│                                                   │          │
└───────────────────────────────────────────────────┼──────────┘
                                                    │
                        ┌───────────────────────────┴─────────────────┐
                        │                                             │
                        ▼                                             ▼
            ┌──────────────────────┐                    ┌──────────────────────┐
            │  INVENTORY SYSTEM    │                    │  ACCOUNTING SYSTEM   │
            │  ✅ Independent       │                    │  ✅ Independent        │
            │                      │                    │                      │
            │  - Items             │                    │  - Journal Entries   │
            │  - Categories        │                    │  - GL Accounts       │
            │  - Invoices          │                    │  - Vendor Bills      │
            │  - Counts            │                    │  - Reports           │
            └──────────────────────┘                    └──────────────────────┘
```

---

## 📊 DATABASE SCHEMA

### **Hub Database: `integration_hub_db`**

#### **Table: hub_invoices**
Centralized storage for all incoming invoices

```sql
CREATE TABLE hub_invoices (
    id SERIAL PRIMARY KEY,

    -- Vendor
    vendor_id INTEGER,
    vendor_name VARCHAR(200) NOT NULL,
    vendor_account_number VARCHAR(100),

    -- Invoice details
    invoice_number VARCHAR(100) NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE,
    total_amount NUMERIC(12, 2) NOT NULL,
    tax_amount NUMERIC(12, 2),

    -- Source
    source VARCHAR(50) NOT NULL,  -- 'email', 'upload', 'api'
    source_email VARCHAR(200),
    source_filename VARCHAR(500),
    raw_data JSONB,

    -- Location
    location_id INTEGER,
    location_name VARCHAR(100),

    -- Routing status
    sent_to_inventory BOOLEAN DEFAULT FALSE,
    sent_to_accounting BOOLEAN DEFAULT FALSE,
    inventory_sync_at TIMESTAMP WITH TIME ZONE,
    accounting_sync_at TIMESTAMP WITH TIME ZONE,
    inventory_sync_error TEXT,
    accounting_sync_error TEXT,

    -- Status: 'pending', 'mapping', 'ready', 'sent', 'error', 'partial'
    status VARCHAR(50) DEFAULT 'pending',

    -- Approval (for future use)
    approved_by INTEGER,
    approved_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,

    INDEX idx_invoice_status (status),
    INDEX idx_invoice_date (invoice_date),
    INDEX idx_invoice_number (invoice_number)
);
```

#### **Table: hub_invoice_items**
Line items with mapping to inventory items and GL accounts

```sql
CREATE TABLE hub_invoice_items (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER REFERENCES hub_invoices(id) ON DELETE CASCADE,

    -- Item details from invoice
    line_number INTEGER,
    item_description VARCHAR(500) NOT NULL,
    item_code VARCHAR(100),  -- Vendor's item code
    quantity NUMERIC(10, 3) NOT NULL,
    unit_of_measure VARCHAR(50),
    unit_price NUMERIC(10, 4) NOT NULL,
    total_amount NUMERIC(12, 4) NOT NULL,

    -- Mapping to inventory
    inventory_item_id INTEGER,
    inventory_item_name VARCHAR(200),
    inventory_category VARCHAR(100),

    -- Mapping to GL accounts
    gl_asset_account INTEGER,    -- 1418 Poultry Inventory
    gl_cogs_account INTEGER,     -- 5118 Poultry Cost
    gl_waste_account INTEGER,    -- 7180 Waste Expense

    -- Mapping status
    is_mapped BOOLEAN DEFAULT FALSE,
    mapped_by INTEGER,
    mapped_at TIMESTAMP WITH TIME ZONE,
    mapping_method VARCHAR(50),  -- 'auto', 'manual', 'suggested'
    mapping_confidence NUMERIC(3, 2),  -- 0.00 to 1.00
    suggested_item_id INTEGER,

    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,

    INDEX idx_item_invoice (invoice_id),
    INDEX idx_item_mapped (is_mapped),
    INDEX idx_item_inventory (inventory_item_id)
);
```

#### **Table: item_gl_mapping**
Master mapping: Inventory Item ID → GL Accounts

```sql
CREATE TABLE item_gl_mapping (
    id SERIAL PRIMARY KEY,

    -- Inventory reference
    inventory_item_id INTEGER NOT NULL UNIQUE,
    inventory_item_name VARCHAR(200) NOT NULL,
    inventory_category VARCHAR(100) NOT NULL,

    -- Vendor-specific (optional)
    vendor_id INTEGER,
    vendor_item_code VARCHAR(100),

    -- GL accounts
    gl_asset_account INTEGER NOT NULL,
    gl_cogs_account INTEGER NOT NULL,
    gl_waste_account INTEGER,
    gl_revenue_account INTEGER,

    -- Account names (for display)
    asset_account_name VARCHAR(200),
    cogs_account_name VARCHAR(200),

    -- Metadata
    is_active BOOLEAN DEFAULT TRUE,
    created_by INTEGER,
    notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,

    INDEX idx_mapping_item (inventory_item_id),
    INDEX idx_mapping_category (inventory_category),
    INDEX idx_mapping_active (is_active)
);
```

#### **Table: category_gl_mapping**
Category-level default GL accounts (fallback)

```sql
CREATE TABLE category_gl_mapping (
    id SERIAL PRIMARY KEY,
    inventory_category VARCHAR(100) UNIQUE NOT NULL,

    -- Default GL accounts for category
    gl_asset_account INTEGER NOT NULL,
    gl_cogs_account INTEGER NOT NULL,
    gl_waste_account INTEGER,
    gl_revenue_account INTEGER,

    -- Account names
    asset_account_name VARCHAR(200),
    cogs_account_name VARCHAR(200),

    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,

    INDEX idx_category (inventory_category)
);
```

---

## 🔄 DATA FLOW

### **1. Invoice Arrives**

**Sources:**
- Email: ap@swhgrp.com (email forwarding)
- Manual Upload: Web UI
- API: Vendor integrations (future)

**Process:**
1. Receive invoice (PDF, email, JSON)
2. Parse/OCR invoice data
3. Create `hub_invoices` record
4. Create `hub_invoice_items` records for each line
5. Set status = 'pending'

### **2. Auto-Mapping Attempt**

For each line item:
1. Try exact match: `inventory_item_id` from previous mappings
2. Try fuzzy match: Similar item description
3. Try vendor item code match
4. If match found → Set `is_mapped = TRUE`, populate GL accounts
5. If no match → Add to unmapped queue

### **3. Manual Mapping (if needed)**

**UI: `/hub/unmapped-items`**
- Show all items where `is_mapped = FALSE`
- Allow admin to:
  - Search inventory items
  - Select item
  - Auto-populate GL accounts from category
  - Override GL accounts if needed
  - Save mapping

**On Save:**
1. Update `hub_invoice_items` with mapping
2. Create/update `item_gl_mapping` for future auto-mapping
3. Set `is_mapped = TRUE`

### **4. Auto-Send to Systems**

**Trigger:** When ALL items on invoice are mapped

**Send to Inventory:**
```python
POST http://inventory-app:8000/api/invoices/from-hub
{
    "vendor_name": "Sysco Foods",
    "invoice_number": "12345",
    "invoice_date": "2025-10-19",
    "location_id": 1,
    "line_items": [
        {
            "master_item_id": 123,
            "quantity": 100,
            "unit_cost": 2.50,
            "total": 250.00
        }
    ]
}
```

**Send to Accounting:**
```python
POST http://accounting-app:8000/api/journal-entries/from-hub
{
    "entry_date": "2025-10-19",
    "entry_number": "INV-12345",
    "description": "Purchase - Sysco Foods - Invoice #12345",
    "reference_type": "INVOICE",
    "reference_id": "HUB-456",
    "status": "POSTED",
    "lines": [
        {
            "account_id": 1418,  # Poultry Inventory
            "debit_amount": 250.00,
            "description": "Chicken Breast - 100 units"
        },
        {
            "account_id": 2100,  # Accounts Payable
            "credit_amount": 250.00,
            "description": "Sysco Foods - Invoice #12345"
        }
    ]
}
```

**On Success:**
- Set `sent_to_inventory = TRUE`, `inventory_sync_at = NOW()`
- Set `sent_to_accounting = TRUE`, `accounting_sync_at = NOW()`
- Set `status = 'sent'`

**On Failure:**
- Log error in `inventory_sync_error` or `accounting_sync_error`
- Set `status = 'error'` or `'partial'`
- Retry after 5 minutes (up to 3 retries)

---

## 🖥️ USER INTERFACES

### **1. Dashboard** (`/hub/`)

```
┌─────────────────────────────────────────────────────────────┐
│ Integration Hub Dashboard                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Summary                                                      │
│ ┌─────────────┬─────────────┬─────────────┬─────────────┐ │
│ │ Pending     │ Unmapped    │ Ready       │ Sent        │ │
│ │ Invoices    │ Items       │ to Send     │ Today       │ │
│ │    5        │    12       │    3        │    23       │ │
│ └─────────────┴─────────────┴─────────────┴─────────────┘ │
│                                                             │
│ Recent Invoices                                             │
│ ┌───────────────────────────────────────────────────────┐  │
│ │ Date       Vendor        Invoice#  Total    Status    │  │
│ │ 10/19/25   Sysco Foods   12345    $1,500   ⚠️ Mapping │  │
│ │ 10/19/25   US Foods      67890    $2,300   ✅ Sent    │  │
│ │ 10/18/25   Southern Wine  WN-123   $850    ✅ Sent    │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│ [Upload Invoice]  [View Unmapped Items (12)]               │
└─────────────────────────────────────────────────────────────┘
```

### **2. Unmapped Items** (`/hub/unmapped-items`)

```
┌──────────────────────────────────────────────────────────────┐
│ Review Unmapped Items                                  [?]   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ ⚠️  12 items need mapping before they can be sent           │
│                                                              │
│ Filter: [All Vendors ▼] [Last 7 days ▼] [Search...]        │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐  │
│ │ Invoice #12345 - Sysco Foods - 10/19/2025 - $1,500    │  │
│ │────────────────────────────────────────────────────────│  │
│ │                                                        │  │
│ │ Line 1: Chicken Breast, Boneless, 40lb Case          │  │
│ │ Qty: 40 lbs @ $2.50/lb = $100.00                      │  │
│ │                                                        │  │
│ │ ▼ Map to Inventory Item:                              │  │
│ │   [Search items.......................................] │  │
│ │                                                        │  │
│ │   AI Suggestions:                                      │  │
│ │   ● Chicken Breast (Poultry) - 95% match ✓           │  │
│ │   ○ Whole Chicken (Poultry) - 60% match              │  │
│ │   ○ Create New Item                                   │  │
│ │                                                        │  │
│ │ ✅ GL Accounts (auto-filled from category "Poultry"): │  │
│ │   Asset:  [1418 - Poultry Inventory  ▼]              │  │
│ │   COGS:   [5118 - Poultry Cost       ▼]              │  │
│ │   Waste:  [7180 - Waste Expense      ▼]              │  │
│ │                                                        │  │
│ │ [✓ Save & Map]  [Skip]  [Create New Item]            │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ [Map All & Send Invoice]  [Save Progress]                   │
└──────────────────────────────────────────────────────────────┘
```

### **3. Item Mappings** (`/hub/mappings`)

**View/Edit existing item-to-GL mappings**

```
┌──────────────────────────────────────────────────────────────┐
│ Item to GL Account Mappings                                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ [Search items...]                     [+ Add New Mapping]   │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐  │
│ │ Inventory Item        Category   Asset   COGS   Actions│  │
│ ├────────────────────────────────────────────────────────┤  │
│ │ Chicken Breast        Poultry    1418    5118   [Edit] │  │
│ │ Ground Beef 80/20     Beef       1417    5117   [Edit] │  │
│ │ Cabernet Sauvignon    Wine       1455    5155   [Edit] │  │
│ └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔧 API ENDPOINTS

### **Invoice Management**

```
POST   /hub/api/invoices/upload          # Manual upload
POST   /hub/api/invoices/from-email      # Email receiver webhook
GET    /hub/api/invoices                 # List invoices
GET    /hub/api/invoices/{id}            # Get invoice details
DELETE /hub/api/invoices/{id}            # Delete invoice
```

### **Mapping Management**

```
GET    /hub/api/unmapped-items            # Get all unmapped items
POST   /hub/api/items/{id}/map            # Map an item
GET    /hub/api/mappings                  # Get all item-GL mappings
POST   /hub/api/mappings                  # Create new mapping
PUT    /hub/api/mappings/{id}             # Update mapping
DELETE /hub/api/mappings/{id}             # Delete mapping
GET    /hub/api/category-mappings         # Get category mappings
```

### **Auto-Send**

```
POST   /hub/api/invoices/{id}/send        # Manually trigger send
POST   /hub/api/invoices/{id}/retry       # Retry failed send
```

### **Inventory Integration**

```
GET    /hub/api/inventory/items           # Search inventory items
GET    /hub/api/inventory/categories      # Get categories
```

---

## ⚙️ CONFIGURATION

### **Initial Setup: Category Mappings**

Based on your existing GL accounts, pre-populate `category_gl_mapping`:

| Category | Asset Account | COGS Account | Waste Account |
|----------|--------------|--------------|---------------|
| Produce | 1405 | 5105 | 7180 |
| Dairy | 1410 | 5110 | 7180 |
| Grocery | 1411 | 5111 | 7180 |
| Meat | 1415 | 5115 | 7180 |
| Pork | 1416 | 5116 | 7180 |
| Beef | 1417 | 5117 | 7180 |
| Poultry | 1418 | 5118 | 7180 |
| Seafood | 1419 | 5119 | 7180 |
| Bakery | 1420 | 5120 | 7180 |
| Beverage | 1430 | 5130 | 7181 |
| Alcohol | 1440 | 5140 | 7182 |
| Liquor | 1445 | 5145 | 7182 |
| Beer | 1450 | 5150 | 7182 |
| Bottled Beer | 1451 | 5151 | 7182 |
| Draft Beer | 1452 | 5152 | 7182 |
| Wine | 1455 | 5155 | 7182 |
| Merchandise | 1465 | 5200 | 7183 |

---

## 🚀 DEPLOYMENT

### **Docker Compose Addition**

```yaml
services:
  integration-hub:
    build: ./integration-hub
    container_name: integration-hub
    ports:
      - "8004:8000"
    environment:
      - DATABASE_URL=postgresql://hub_user:hub_password@hub-db:5432/integration_hub_db
      - INVENTORY_API_URL=http://inventory-app:8000
      - ACCOUNTING_API_URL=http://accounting-app:8000
      - AUTO_SEND_ENABLED=true
    depends_on:
      - hub-db
      - inventory-app
      - accounting-app
    restart: unless-stopped
    networks:
      - restaurant-network

  hub-db:
    image: postgres:15
    container_name: hub-db
    environment:
      - POSTGRES_DB=integration_hub_db
      - POSTGRES_USER=hub_user
      - POSTGRES_PASSWORD=hub_password
    volumes:
      - hub-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hub_user"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - restaurant-network

volumes:
  hub-db-data:

networks:
  restaurant-network:
    driver: bridge
```

---

## ✅ IMPLEMENTATION PHASES

### **Phase 1: Core Infrastructure** (Day 1)
- [x] Create Integration Hub directory structure
- [x] Create database models
- [ ] Create database migrations
- [ ] Set up FastAPI application
- [ ] Add to docker-compose
- [ ] Test basic deployment

### **Phase 2: Invoice Receiver** (Day 1-2)
- [ ] Build manual upload UI
- [ ] Build email receiver webhook (for ap@swhgrp.com)
- [ ] Build invoice parser/OCR
- [ ] Test invoice ingestion

### **Phase 3: Mapping System** (Day 2-3)
- [ ] Build unmapped items UI
- [ ] Build item search (query inventory API)
- [ ] Build mapping save logic
- [ ] Build category mapping seed script
- [ ] Test mapping workflow

### **Phase 4: Auto-Send** (Day 3-4)
- [ ] Build inventory sender service
- [ ] Build accounting sender service
- [ ] Build retry logic
- [ ] Test end-to-end flow

### **Phase 5: Integration Endpoints** (Day 4)
- [ ] Add endpoint in inventory: `/api/invoices/from-hub`
- [ ] Add endpoint in accounting: `/api/journal-entries/from-hub`
- [ ] Test bidirectional communication

### **Phase 6: Monitoring & Polish** (Day 5)
- [ ] Add dashboard UI
- [ ] Add error notifications
- [ ] Add sync status monitoring
- [ ] Create user documentation

---

## 🎓 SUCCESS CRITERIA

✅ Invoice arrives via email or upload
✅ System auto-maps items (if previously mapped)
✅ Admin can review and map unmapped items
✅ System auto-sends to Inventory and Accounting
✅ Inventory system receives and creates invoice
✅ Accounting system receives and creates journal entry
✅ All systems can operate independently
✅ Failed syncs retry automatically
✅ Admin can view sync status

---

## 📝 NEXT STEPS

**Immediate:**
1. Complete database migration files
2. Build FastAPI main application
3. Deploy Integration Hub container
4. Seed category mappings

**After Hub is Running:**
1. Build unmapped items UI
2. Test invoice upload
3. Test end-to-end flow
4. Set up email forwarding to ap@swhgrp.com

---

**Status:** Models created, ready for implementation
**Completion:** ~15% (models done, need APIs and UI)
**ETA:** 5 days for full implementation

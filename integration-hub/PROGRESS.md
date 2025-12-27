# Integration Hub - Progress

**Last Updated:** December 27, 2025
**Status:** Location-Aware Costing Complete (80%)

---

## System Overview

The Integration Hub is an invoice processing and GL mapping system. It receives vendor invoices via email or manual upload, maps line items to inventory items and GL accounts, and routes processed invoices to both Inventory and Accounting systems.

**Important:** This is NOT a vendor API integration platform. It does not connect to US Foods, Sysco, etc.

---

## Current Focus: Location-Aware Costing Architecture

### Design Principles (MarginEdge/R365 Hybrid)

1. **Hub is Source of Truth** for:
   - Units of Measure (global, shared across systems)
   - Categories (global, hierarchical)
   - Vendor Items (per location, with review workflow)

2. **Inventory is Source of Truth** for:
   - Master Items (product definitions)
   - Count Units (how items are counted)
   - Location Costs (weighted average per location)

3. **Key Concepts**:
   - **measure_type**: Only 3 types - EACH, WEIGHT, VOLUME (no LENGTH)
   - **pack_to_primary_factor**: Converts purchase units to primary count units
   - **Location-specific costs**: Each location maintains own weighted average
   - **Review workflow**: New vendor items start as `needs_review`

### Data Architecture

```
Hub (Source of Truth)                    Inventory (Costing)
├── UnitOfMeasure (global)               ├── MasterItem (no costs)
│   ├── measure_type: enum               │   ├── name, description
│   └── to_base_factor                   │   └── shelf_life_days
│                                        │
├── Category (global)                    ├── MasterItemCountUnit
│   └── hierarchical names               │   ├── uom_id → Hub.UOM
│                                        │   ├── is_primary
└── VendorItem (per location)            │   └── conversion_to_primary
    ├── location_id                      │
    ├── status: active/needs_review      └── MasterItemLocationCost
    ├── pack_to_primary_factor               ├── location_id
    └── last_purchase_price                  ├── current_weighted_avg_cost
                                             └── cost_history[]
```

---

## Completion Status

| Module | Status | Completion |
|--------|--------|------------|
| Invoice Processing | Complete | 100% |
| AI OCR Parsing | Complete | 100% |
| Item Mapping | Complete | 100% |
| GL Mapping | Complete | 100% |
| Inventory Sync | Complete | 100% |
| Accounting Sync | Complete | 100% |
| Vendor Management | Complete | 100% |
| Email Intake | Complete | 100% |
| Batch Operations | Complete | 100% |
| Reporting | Complete | 100% |
| Duplicate Detection | Complete | 100% |
| Vendor Normalization | Complete | 100% |
| **Location-Aware Costing** | **Mostly Complete** | **80%** |

**Overall: 100% of original scope, 80% of new architecture**

### Location-Aware Costing Progress
- [x] Schema Design (100%)
- [x] Migration Script (100%)
- [x] Run Migration (100%) - Dec 27
  - Hub: 23 UOMs with measure_type, 908 vendor items with location_id/status
  - Inventory: 409 count units, 372 location costs (62 items × 6 locations)
- [x] Invoice Processing Updates (100%)
  - Location-aware auto_mapper with vendor + location + SKU matching
  - Cross-location fallback matching with tracking
  - LocationCostUpdaterService for weighted average updates
- [x] Costing Engine (100%)
  - Weighted average calculation per location
  - Cost history tracking with audit trail
- [x] Hub UI Updates (100%)
  - Location filter, status column, review actions
- [ ] Inventory UI Updates (0%)
  - Master item location cost display pending

---

## What's Working

### Invoice Processing
- Manual PDF upload
- Automated email monitoring (IMAP, 15-min intervals)
- AI-powered PDF parsing (OpenAI GPT-4o Vision)
- Multi-page invoice support
- Statement detection and marking
- Invoice deletion with cascade cleanup

### OCR & Parsing
- GPT-4o Vision extraction
- Vendor identification
- Line item extraction
- Tax capitalization into item costs
- OCR digit similarity scoring for error correction
- Item code auto-correction (80%+ similarity match)
- UPC vs item code detection

### Item Mapping
- Manual mapping interface
- Bulk mapping by description (map once, apply everywhere)
- Unique item grouping with frequency counts
- Verified/unverified item code tracking
- Category fallback mappings

### GL Mapping
- 4 GL account types per item (Asset, COGS, Waste, Revenue)
- Category-level GL defaults
- Smart validation (inventory vs expense items)
- Full GL account names display

### System Integration
- Smart auto-send logic (Inventory only if inventory items exist)
- Parallel sending to Inventory and Accounting
- Retry logic for failed sends
- Status tracking per system
- Tax double-counting prevention

### Vendor Management
- Vendor master data
- Bidirectional sync (Hub ↔ Inventory ↔ Accounting)
- Vendor aliases for name normalization (Dec 25)
- Duplicate vendor detection

### Batch Operations (Dec 25)
- Batch approve invoices
- Batch auto-map unmapped items
- Batch status update
- Batch mark as sent
- Batch reset sync
- Batch delete
- Summary for selected invoices

### Reporting (Dec 25)
- Overall system summary stats
- Vendor spend with period filtering
- Item mapping statistics
- System sync health metrics
- Daily invoice volume
- Category breakdown

### Duplicate Detection (Dec 25)
- Exact invoice number matching (95% confidence)
- Vendor + date + amount matching (70-80% confidence)
- Duplicate groups visualization
- Bulk delete/keep actions
- Configurable thresholds

---

## Recent Milestones

### December 27, 2025 (Afternoon)
- **Invoice Processing Updates Complete**:
  - Updated `auto_mapper.py` with location-aware vendor item lookup
  - Two-pass matching: location-specific first, then cross-location fallback
  - Tracks cross-location matches for potential vendor item creation
  - Added `location_id` parameter to `match_by_sku()` and `match_by_fuzzy_name()`

- **Location Cost Updater Service Created**:
  - New file: `services/location_cost_updater.py`
  - Updates `MasterItemLocationCost` with weighted average on invoice send
  - Creates new location cost records for first-time purchases
  - Records full history in `MasterItemLocationCostHistory`
  - Integrated into `auto_send.py` after successful inventory send

- **Vendor Item Review Workflow Created**:
  - New file: `services/vendor_item_review.py`
  - `VendorItemReviewService` with approve/reject/bulk approve
  - Clone to location for cross-location item discovery
  - Create from invoice for unmapped items

- **API Endpoints Added**:
  - `GET /review/stats` - Review workflow statistics
  - `GET /review/needs-review` - Items pending review
  - `POST /review/{id}/approve` - Approve single item
  - `POST /review/{id}/reject` - Reject single item
  - `POST /review/bulk-approve` - Bulk approve
  - `POST /{id}/clone-to-location` - Clone to new location
  - `POST /create-from-invoice` - Create from unmapped invoice item
  - `GET /{id}/location-cost` - Get current location cost
  - `GET /{id}/cost-history` - Get cost change history

- **Hub Vendor Items UI Updated**:
  - Added location filter dropdown
  - Status filter: active/needs_review/inactive
  - New "Review" badge for needs_review items
  - Approve/Reject buttons for review items
  - Bulk approve button
  - Pack Factor column (shows pack_to_primary_factor)
  - Stats cards: Total, Active, Needs Review, Inactive, Synced, Vendors

### December 27, 2025 (Morning)
- **Architecture Analysis Complete** - Examined current data state:
  - Hub: 908 vendor items, 23 UOMs (dimension-based with `to_base_factor`)
  - Inventory: 38 UOMs (reference-based), master items with embedded costs
  - No vendor_items table in Inventory (model exists but never created)

- **Schema Design Complete** - All model updates implemented:
  - Hub: `MeasureType` enum, `VendorItemStatus` enum
  - Hub: `HubVendorItem` with `location_id`, `status`, `pack_to_primary_factor`
  - Inventory: `MasterItemCountUnit` model (primary/secondary count units)
  - Inventory: `MasterItemLocationCost` model (weighted avg per location)
  - Inventory: `MasterItemLocationCostHistory` model (audit trail)

- **Migration Script Created** - `scripts/migrate_location_aware_costing.py`:
  - Adds `measure_type` to Hub UOMs
  - Adds `location_id`, `status`, `pack_to_primary_factor` to Hub Vendor Items
  - Creates new Inventory tables
  - Migrates existing cost data to location costs

### December 26, 2025
- **Centralized invoice status service** - New `/services/invoice_status.py` for consistent status transitions
- **GL validation fix** - Expense-only invoices no longer blocked (checks `inventory_item_id` not `inventory_category`)
- **Inventory send logic fix** - Expense-only invoices no longer incorrectly sent to Inventory (404 fix)
- **Category mismatch fix** - Fixed 25 invoice items with wrong categories/GL accounts
- **Vendor items normalized** - 489 vendor items updated to hierarchical category names (e.g., "Food - Poultry")
- Removed redundant "Mapped Items" page from sidebar
- Reorganized sidebar navigation for better workflow
- Changed Vendors icon to truck (`bi-truck`) for consistency
- Clarified data model: Vendor Items vs Mapping Rules vs Invoice Items

### December 25, 2025
- Invoice Batch Operations API
- Reporting Dashboard API
- Vendor Normalization (Hub as source of truth)
- Duplicate Invoice Detection with UI

### December 23, 2025
- OCR error fixes
- Invoice parser enhancements (UPC detection, description-based OCR fix)
- 99.5% mapping rate achieved

### November 30, 2025
- Tax double-counting fix (critical)
- Vendor alias integration support

### November 25, 2025
- OCR item code auto-correction
- Digit similarity scoring
- Item codes page filters

### November 11, 2025
- Multi-page invoice parsing fix
- Re-parse invoice button
- Tax capitalization fix

---

## Key Statistics

| Metric | Value |
|--------|-------|
| Vendor Items (Hub) | 908 active |
| Hub UOMs | 23 |
| Inventory UOMs | 38 |
| Mapping Rules | 196 active |
| Total Invoices | 46 |
| Invoice Items | 393 |
| Mapped Invoice Items | 351 |
| Unmapped Invoice Items | 42 |
| Unique Unmapped Descriptions | ~36 |
| Vendors | 18 |

**Note:** After architecture refactor, UOMs will be consolidated in Hub only.

---

## What's NOT Implemented (Clarification)

These were claimed in old docs but never built:
- ❌ Vendor API integrations (US Foods, Sysco, etc.)
- ❌ Product catalog sync from vendors
- ❌ Automated ordering to vendors
- ❌ Celery task queue (uses APScheduler)
- ❌ Webhook event system (stub only)

---

## Integration Points

| System | Direction | Status |
|--------|-----------|--------|
| Inventory | Hub → Inventory | Working |
| Accounting | Hub → Accounting | Working |
| Email (IMAP) | Inbound | Working |
| Portal | SSO Auth | Working |

---

## Goals for Next Phase

1. ~~**Create Hub UOM Schema** - Simplified with `measure_type` enum~~ ✅ Done
2. ~~**Create Hub Vendor Item Schema** - Add `location_id`, `status`, `pack_to_primary_factor`~~ ✅ Done
3. ~~**Create Inventory Location Cost Schema** - Weighted average per location~~ ✅ Done
4. ~~**Write Migration Scripts** - UOM consolidation, cost extraction~~ ✅ Done
5. ~~**Run Migration** - Execute migration script on staging/production~~ ✅ Done (Dec 27)
6. **Update Invoice Processing** - Location detection, review workflow
7. **Build Costing Engine** - Weighted average calculations
8. **Update UIs** - Location filters, cost displays

---

## Files Changed (Dec 27, 2025 - Afternoon)

### Hub Services (NEW)
- `integration-hub/src/integration_hub/services/location_cost_updater.py` **NEW**
  - `LocationCostUpdaterService` for updating Inventory's location costs
  - Weighted average calculation with history tracking
- `integration-hub/src/integration_hub/services/vendor_item_review.py` **NEW**
  - `VendorItemReviewService` for review workflow
  - Approve/reject/bulk approve/clone to location

### Hub Updates
- `integration-hub/src/integration_hub/services/auto_mapper.py`
  - Added `location_id` to `match_by_sku()` and `match_by_fuzzy_name()`
  - Two-pass location-aware matching strategy
  - Cross-location match tracking
- `integration-hub/src/integration_hub/services/auto_send.py`
  - Integrated `LocationCostUpdaterService` after inventory send
- `integration-hub/src/integration_hub/api/vendor_items.py`
  - Added review workflow API endpoints
  - Added location cost API endpoints
  - Updated list endpoint with location/status filters
- `integration-hub/src/integration_hub/templates/hub_vendor_items.html`
  - Location filter, status filter, review actions UI
  - Approve/reject buttons, bulk approve

---

## Files Changed (Dec 27, 2025 - Morning)

### Hub Schema Updates
- `integration-hub/src/integration_hub/models/unit_of_measure.py`
  - Added `MeasureType` enum (each, weight, volume)
  - Added `measure_type` field to `UnitOfMeasure`
  - Added `effective_measure_type` property for backward compatibility
- `integration-hub/src/integration_hub/models/hub_vendor_item.py`
  - Added `VendorItemStatus` enum (active, needs_review, inactive)
  - Added `location_id`, `status`, `pack_to_primary_factor` fields
  - Added `last_purchase_price`, `previous_purchase_price` fields
  - Added `cost_per_primary_unit` property
- `integration-hub/src/integration_hub/models/__init__.py`
  - Updated exports for new enums and models

### Inventory Schema Updates
- `inventory/src/restaurant_inventory/models/master_item_count_unit.py` **NEW**
  - `MasterItemCountUnit` model for primary/secondary count units
- `inventory/src/restaurant_inventory/models/master_item_location_cost.py` **NEW**
  - `MasterItemLocationCost` model for per-location weighted avg costs
  - `MasterItemLocationCostHistory` model for audit trail
- `inventory/src/restaurant_inventory/models/item.py`
  - Added `category_id`, `primary_uom_id`, `primary_uom_name`, `primary_uom_abbr`, `shelf_life_days`
  - Added `count_units` and `location_costs` relationships
  - Added `get_cost_at_location()` and `get_primary_count_unit()` methods
- `inventory/src/restaurant_inventory/models/__init__.py`
  - Updated exports for new models

### Migration Script
- `scripts/migrate_location_aware_costing.py` **NEW**
  - Phase 1a: Hub UOM measure_type migration
  - Phase 1b: Hub Vendor Items schema updates
  - Phase 2: Inventory table creation
  - Phase 3: Data migration (costs to location costs)

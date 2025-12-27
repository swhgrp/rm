# Integration Hub - TODO

**Last Updated:** December 27, 2025

## Priority Legend
- P0: Critical - Blocking production use
- P1: High - Important for daily operations
- P2: Medium - Nice to have improvements
- P3: Low - Future enhancements

---

## Important Note

This is an **invoice processing and GL mapping system**, NOT a vendor API integration platform. It processes invoices received via email/upload and routes them to Inventory and Accounting.

---

## Major Architecture Refactor (P0) - Location-Aware Costing

### System Boundaries
- **Hub owns:** UOM (global), Categories (global), Vendor Items (per location)
- **Inventory owns:** Master Items, Count Units, Location Costs

### Phase 1: Schema Design - COMPLETE
- [x] **Hub UOM Consolidation** - Added `MeasureType` enum (each, weight, volume)
  - Added `measure_type` field to UnitOfMeasure model
  - Kept `dimension` for backward compatibility
  - Added `effective_measure_type` property for migration period

- [x] **Hub Category Model** - Already hierarchical, no changes needed

- [x] **Hub Vendor Item Refactor** - Updated `HubVendorItem` model:
  - Added `location_id` (references Inventory.locations)
  - Added `status` enum (active, needs_review, inactive) with `VendorItemStatus`
  - Added `pack_to_primary_factor` for purchase unit conversion
  - Added `last_purchase_price`, `previous_purchase_price`
  - Added `cost_per_primary_unit` property
  - Deprecated old fields (conversion_factor, unit_price, is_active)

- [x] **Inventory Master Item Refactor** - Updated `MasterItem` model:
  - Added `category_id`, `primary_uom_id`, `primary_uom_name`, `primary_uom_abbr`
  - Added `shelf_life_days`
  - Added `count_units` and `location_costs` relationships
  - Added `get_cost_at_location()` and `get_primary_count_unit()` methods
  - Deprecated cost fields (current_cost, average_cost)

- [x] **Inventory Master Item Count Units** - NEW `MasterItemCountUnit` model:
  - `master_item_id` + `uom_id` + `is_primary` flag
  - `conversion_to_primary` factor
  - `convert_to_primary()` and `convert_from_primary()` methods

- [x] **Inventory Master Item Location Cost** - NEW `MasterItemLocationCost` model:
  - `master_item_id` + `location_id` (unique together)
  - `current_weighted_avg_cost`, `total_qty_on_hand`
  - `apply_purchase()` and `apply_usage()` methods
  - `MasterItemLocationCostHistory` for audit trail

### Phase 2: Migration - COMPLETE
- [x] **Migration Script Created** - `scripts/migrate_location_aware_costing.py`
  - Phase 1a: Hub UOM measure_type migration
  - Phase 1b: Hub Vendor Items schema updates
  - Phase 2: Inventory tables creation
  - Phase 3: Data migration
- [x] **Run Migration** - Executed Dec 27, 2025
- [x] **Verify Data** - Confirmed:
  - Hub: 23 UOMs with measure_type (10 each, 9 volume, 4 weight)
  - Hub: 908 vendor items with location_id=1 and status (907 active, 1 inactive)
  - Inventory: 409 count units created
  - Inventory: 372 location cost records (62 items × 6 locations)

### Phase 3: Invoice Processing Updates - COMPLETE
- [x] **Location Detection** - Invoice parser extracts location from "Ship To" field
- [x] **Vendor Item Lookup** - Location-aware matching: vendor + item_code + location first, then cross-location
- [x] **Review Workflow** - New `VendorItemReviewService` with approve/reject/bulk approve
- [x] **Cost Update Logic** - `LocationCostUpdaterService` updates `MasterItemLocationCost` on invoice send

### Phase 4: Costing Engine - COMPLETE
- [x] **Weighted Average Calculation** - `MasterItemLocationCost.apply_purchase()` method:
  ```
  new_cost = (old_cost * old_qty + new_cost * new_qty) / (old_qty + new_qty)
  ```
- [x] **Cost History Tracking** - `MasterItemLocationCostHistory` table with full audit trail
- [ ] **Cost Propagation** - Update derived calculations (menu costing, etc.) - Future

### Phase 5: UI Updates - PARTIAL
- [x] **Hub Vendor Items Page** - Added location filter, status column (active/needs_review/inactive), review actions (approve/reject/bulk approve)
- [ ] **Inventory Master Item Detail** - Show cost per location (read-only from Hub)
- [ ] **Location Cost Grid** - View/compare costs across locations

---

## Outstanding Issues

### P1 - High Priority

- [ ] **OCR accuracy improvements** - Complete the 67 auto-correctable matches identified in fuzzy match analysis
- [ ] **Invoice 217 re-parse** - Bad parse (line items $340 vs invoice $42), needs manual re-parse
- [ ] **Duplicate invoice cleanup** - 257 potential duplicates detected (53 high-confidence groups)

### P2 - Medium Priority

- [ ] **OCR fuzzy matching enhancement** - Apply ML or better fuzzy logic for future invoice parsing
- [ ] **Vendor item auto-creation** - Auto-create vendor items for frequently seen unmapped items
- [ ] **Invoice approval workflow** - Multi-step approval for high-value invoices
- [ ] **Batch processing UI** - Better UI for batch operations on multiple invoices

### P3 - Low Priority / Future

- [ ] **Machine learning item mapping** - Train model on historical mappings
- [ ] **Advanced duplicate detection** - Cross-invoice matching for credits/adjustments
- [ ] **Vendor API integration** - Actually connect to vendor portals (US Foods, Sysco) - aspirational

---

## Completed (Dec 27, 2025)

- [x] **Vendor Items UI Update** - Corrected vendor item architecture:
  - Removed location dropdown from vendor items (location belongs to invoices, not vendor items)
  - Removed status dropdown - status is now auto-calculated based on completeness
  - Added "Prices by Location" section showing invoice-derived prices per location
  - Created `/api/v1/vendor-items/{id}/location-prices` endpoint

- [x] **Location Sync Architecture** - Inventory is now source of truth for locations:
  - Updated Inventory Location model with `code`, `legal_name`, `ein` fields
  - Created Inventory `/_sync` endpoint for Accounting to fetch locations
  - Created Accounting `sync-from-inventory` endpoint to pull locations
  - Updated Inventory Settings → Locations page with full entity fields
  - Added "Sync from Inventory" button to Accounting Locations page

- [x] **Architecture Analysis** - Examined current data architecture:
  - Hub has `hub_vendor_items` (908 items), `units_of_measure` (23 units)
  - Inventory has `units_of_measure` (38 units), `master_items` with cost fields
  - No `vendor_items` table in Inventory (model exists but never migrated)
  - Identified need for location-aware costing refactor

- [x] **Hub UOM Schema** - Added `MeasureType` enum and `measure_type` field:
  - File: `integration-hub/src/integration_hub/models/unit_of_measure.py`
  - Added `effective_measure_type` property for backward compatibility

- [x] **Hub Vendor Item Schema** - Added location-aware fields:
  - File: `integration-hub/src/integration_hub/models/hub_vendor_item.py`
  - Added `VendorItemStatus` enum, `location_id`, `status`, `pack_to_primary_factor`
  - Added `last_purchase_price`, `previous_purchase_price`, `cost_per_primary_unit` property

- [x] **Inventory Count Units Schema** - NEW model:
  - File: `inventory/src/restaurant_inventory/models/master_item_count_unit.py`
  - `MasterItemCountUnit` with `is_primary`, `conversion_to_primary`

- [x] **Inventory Location Cost Schema** - NEW model:
  - File: `inventory/src/restaurant_inventory/models/master_item_location_cost.py`
  - `MasterItemLocationCost` with weighted average costing
  - `MasterItemLocationCostHistory` for audit trail

- [x] **Master Item Updates** - Added new relationships:
  - File: `inventory/src/restaurant_inventory/models/item.py`
  - Added `count_units`, `location_costs` relationships
  - Added `get_cost_at_location()`, `get_primary_count_unit()` methods

- [x] **Migration Script** - Created comprehensive migration:
  - File: `scripts/migrate_location_aware_costing.py`
  - Supports `--dry-run` mode for testing

## Completed (Dec 26, 2025)

- [x] **UOM + Pricing Model Refactor** - Implemented comprehensive dimension-based UOM model:
  - Added `dimension` enum (count, volume, weight, length) and `to_base_factor` to UnitOfMeasure
  - Added `is_base_unit` flag for base units in each dimension (each, fl oz, oz, inch)
  - Item model: Added `stock_uom_id`, `stock_content_qty`, `stock_content_uom_id`
  - VendorItem model: Added `purchase_uom_id`, `stock_units_per_purchase_unit`, `last_purchase_price`
  - Created migration script: `scripts/migrate_uom_pricing_model.py`
  - Created pricing service: `integration_hub/services/pricing.py` with:
    - Unit conversion functions using dimension-based factors
    - Cost per stock unit calculation
    - Cost per content base calculation (e.g., $/fl oz)
    - Invoice line price parsing
  - Added 10 unit tests for pricing logic (all passing)
  - Legacy fields kept for backward compatibility (deprecated but functional)

- [x] **Inventory master items UI update** - Updated Inventory system's item_detail page with new pricing model (unit_cost, unit_size, container_type) - matches Hub vendor items UI
- [x] **New pricing model** - Vendor items now use unit_cost as primary (like Backbar):
  - `unit_cost` - Cost per single unit (e.g., $25.50 for one bottle)
  - `unit_size` + `unit_size_uom` - Size of unit (e.g., 750 ml)
  - `container_type` - Physical container (bottle, can, keg, box, bag, etc.)
  - `units_per_case` - How many units in a case (e.g., 12)
  - `case_cost` - Auto-calculated (unit_cost × units_per_case)
  - Schema updated in both Hub and Inventory databases
  - UI updated in Hub vendor items (Add/Edit modals)
  - Migrated 301 existing items to calculate unit_cost from case_cost
- [x] **Category mismatch fix** - Fixed 25 invoice items with wrong categories (e.g., "Uncategorized" → "Food - Poultry")
- [x] **Vendor items category normalization** - Updated 489 vendor items to use hierarchical category names
- [x] **Invoice status auto-update** - Created centralized `invoice_status.py` service for consistent status transitions
- [x] **GL validation fix** - Fixed expense-only invoices being blocked (now only checks `inventory_item_id`)
- [x] **Inventory send fix** - Expense-only invoices no longer incorrectly sent to Inventory system
- [x] **Removed "Mapped Items" Page** - Redundant page showing invoice items (not vendor items catalog)
- [x] **Sidebar Reorganization** - Logical workflow order: Invoices → Vendors → Vendor Items → Unmapped Items
- [x] **Vendors Icon Update** - Changed from building to truck icon for consistency

## Completed (Dec 25, 2025)

- [x] **Invoice Batch Operations API** - Bulk approve, auto-map, status update, mark sent, reset sync, delete
- [x] **Reporting Dashboard API** - Summary, vendor spend, mapping stats, sync status, daily volume, category breakdown
- [x] **Vendor Normalization** - Hub as source of truth with VendorAlias model
- [x] **Duplicate Detection** - Detection service and UI page at `/hub/duplicates`

---

## Known Bugs

- [ ] Some invoices may still have stale error messages after data corrections (need to clear and retry)

---

## Technical Debt

- [ ] Clean up orphaned invoice items from deleted invoices
- [ ] Review webhook endpoint (stub only, not functional)
- [ ] Consider moving to Celery for background processing (currently APScheduler)

---

## Data Quality Tasks

- [ ] Process 67 exact/near-exact OCR matches (auto-correctable)
- [ ] Review 26 medium-confidence OCR matches (manual review)
- [ ] Add vendor items for Gold Coast Beverage, Southern Glazier's if needed
- [ ] Continue cleaning up duplicate invoices

---

## UI/UX Enhancements

- [ ] Dashboard charts for invoice volume trends
- [ ] Better invoice PDF preview
- [ ] Bulk item mapping improvements
- [ ] Mobile-responsive invoice detail view

---

## Integration Improvements

- [ ] Better error feedback on sync failures
- [ ] Retry queue visualization
- [ ] Webhook system for external integrations

---

## Documentation Needed

- [ ] Invoice workflow documentation
- [ ] GL mapping best practices
- [ ] Category mapping setup guide
- [ ] Location-aware costing architecture docs

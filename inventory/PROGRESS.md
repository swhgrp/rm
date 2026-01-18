# Inventory System - Progress

**Last Updated:** January 18, 2026
**Status:** 100%+ Complete - Production Ready

---

## System Overview

The Inventory System is a comprehensive multi-location inventory management platform with POS integration, recipe management, and advanced analytics. With 104 Python files, 28 database tables, and 150+ API routes, it's one of the most feature-rich systems in the platform.

**Note (Dec 25, 2025):** Invoice processing and vendor items have been migrated to the Integration Hub (source of truth). The Inventory system now focuses on inventory counts, transfers, waste, recipes, and POS integration.

---

## Completion Status

| Module | Status | Completion |
|--------|--------|------------|
| Authentication & SSO | Complete | 100% |
| Master Items | Complete | 100% |
| Vendor Management | Complete | 100% |
| Multi-Location | Complete | 100% |
| Inventory Counting | Complete | 100% |
| Count Templates | Complete | 100% |
| Transfers | Complete | 100% |
| Waste Tracking | Complete | 100% |
| Invoice Processing | Moved to Hub | N/A |
| Vendor Items | Moved to Hub | N/A |
| Recipe Management | Complete | 100% |
| POS Integration | Complete | 100% |
| Reporting & Analytics | Complete | 100% |
| Dashboards | Complete | 100% |

**Overall: 100%+ (exceeds original scope)**

### Migrated to Integration Hub (Dec 25, 2025)
- Invoice processing (upload, parsing, approval)
- Vendor items (pricing, mapping)
- Vendor aliases
- COGS calculations
- Vendor spend reports

---

## What's Working

### Master Item Management
- Central item catalog with categories
- Units of measure with conversions
- Par level settings
- Key item flagging (Nov 28)
- Additional count units (count_unit_2, count_unit_3)
- Item unit conversions model
- Links to Hub for vendor item pricing

### Multi-Location Inventory
- 6 restaurant locations
- Location-specific storage areas
- Real-time inventory counts
- Low stock alerts
- Inventory value by location
- User-location restrictions

### Inventory Counting
- Live count sessions with auto-save
- Mobile-responsive interface
- Count by storage area or full location
- Variance detection
- Count templates (reusable)
- Count history and audit trail
- Multiple counting units per item

### Transfers
- Inter-location transfers
- Multi-item transfers
- Status workflow (PENDING → IN_TRANSIT → RECEIVED)
- Approval workflow
- Automatic inventory adjustments

### Waste Tracking
- Waste logging with reasons
- Category/location/reason reports
- Cost impact analysis
- Automatic inventory deduction

### Invoice Processing (Now in Integration Hub)
- **Migrated Dec 25, 2025** - All invoice functionality moved to Integration Hub
- Access via Hub dashboard: `/hub/invoices`
- Inventory dashboard links to Hub for COGS and invoice data

### Recipe Management
- Recipe CRUD with ingredients
- Automatic cost calculations
- Cost per portion
- Food cost percentage
- PDF recipe generation

### POS Integration
- Clover, Square, Toast support
- POS item mapping
- Recipe-based deductions
- Automated sales sync (10-min intervals)
- Inventory deduction from sales

### Reporting & Analytics
- Usage Report (comprehensive)
- Variance Report
- Inventory Valuation
- Waste Report
- Visual dashboards with charts

### Vendor Management
- Vendor database with contacts
- Links to Hub for vendor items and pricing
- Vendor aliases managed in Hub (Dec 25, 2025)
- Duplicate vendor detection

---

## Recent Milestones

### January 18, 2026
- **UOM Architecture Consolidation** ✅ **COMPLETE**:
  - Merged `item_unit_conversions` into `master_item_count_units` model
  - Added fields: `individual_weight_oz`, `individual_volume_oz`, `notes`, `is_active`
  - Data migration script migrated existing conversions to count units
  - New unified "Units of Measure" UI section on item detail page
  - Add Unit modal with auto-calculation from Hub UOM data
  - Edit Item modal now filters dropdown by dimension (weight/volume/count)
  - Promoted secondary-to-primary unit conversion with proper constraint handling
  - `item_unit_conversions` table deprecated (kept for rollback)

### January 17, 2026
- **Recipe Management Improvements**:
  - Searchable ingredient dropdown using Tom Select (all master items, sorted A-Z)
  - Dynamic unit dropdown based on selected item's count units
  - Recipe costing now fetches pricing from Hub's hub_vendor_items table
- **UOM Architecture Research**: Analyzed industry systems (see below)

### December 27, 2025
- **Location Sync Architecture**: Inventory is now the source of truth for locations
  - Added `code`, `legal_name`, `ein` fields to Location model
  - Created `/_sync` API endpoint for Accounting to fetch locations
  - Updated Locations settings page with full Accounting-style UI
  - Accounting syncs locations from Inventory via "Sync from Inventory" button

### December 25, 2025
- **Major Architecture Change**: Migrated invoices and vendor items to Integration Hub
- Removed invoice/vendor_item tables from Inventory DB (Hub is now source of truth)
- Updated UI to link to Hub for invoices, vendor items, and COGS
- Deprecated local invoice and vendor item endpoints

### December 23, 2025
- Massive GFS item import (93.4% → 99.5% mapping)
- Duplicate master item cleanup
- Category cleanup (50+ items recategorized)

### November 28-29, 2025
- Key item flag
- Additional count units (2 and 3)
- Item unit conversions model
- Count session fixes (unit display, variance overflow, delete cascade)

### October 2025
- Initial production deployment
- AI invoice processing
- POS integration framework

---

## Database Statistics

- **28 database tables** (4 removed: invoices, invoice_items, vendor_items, vendor_aliases)
- **104 Python files**
- **28 HTML templates** (2 deprecated)
- **150+ API routes** (invoice/vendor_item endpoints deprecated)

---

## Integration Points

| System | Direction | Status |
|--------|-----------|--------|
| Integration Hub | Hub → Inventory | Working |
| Accounting | Inventory → Accounting (locations) | Working |
| Portal | SSO Auth | Working |
| POS Systems | Bidirectional | Working |

**Source of Truth:**
- **Locations**: Inventory owns location data (code, legal_name, ein, address)
- **Accounting** syncs from Inventory via `/api/locations/_sync` endpoint

---

## Data Quality Status

| Metric | Status |
|--------|--------|
| Mapping Rate | 99.5% (2,592/2,604) |
| Unmapped Items | 12 (intentional or non-products) |
| Uncategorized Items | 96 (mostly bulk store items) |

---

## Goals for Next Phase

1. ~~**UOM Architecture Consolidation**~~ ✅ **DONE** - Merged into single `MasterItemCountUnit` model
2. Export functionality (CSV/Excel/PDF)
3. Continue data quality improvements

---

## UOM Architecture Research (January 2026)

### Industry Standard: Three Unit Types
Most restaurant inventory systems use:
| Unit Type | Purpose | Example |
|-----------|---------|---------|
| Purchase/Vendor Unit | How bought from suppliers | Case, Bag, Wheel |
| Inventory/Count Unit | How physically counted | Each, Pound, Bottle |
| Recipe Unit | How used in recipes | Ounce, Cup, Each |

### Systems Analyzed

| System | Architecture | Key Feature |
|--------|--------------|-------------|
| **Restaurant365** | 3 Measure Types (Weight/Volume/Each) | Primary measure type per item, UoM Equivalence for cross-type |
| **COGS-Well** | Multi-class per item | Most flexible - allows Weight + Volume + Count units on same item |
| **meez** | UoM Equivalency system | Explicit equivalency required (e.g., "10 lemons = 1/2 cup juice") |
| **MarketMan** | Inventory UOM + Purchase UOM | Custom "on hand" UOM for display |
| **Compeat** | Inventory + Purchase + Base Unit | Container-to-inventory mapping |
| **xtraCHEF** | Invoice-driven catalog | Conversions saved per product, reused across recipes |
| **MarginEdge** | Central conversions | One conversion applies to all uses of a product |

### Recommended Consolidation

Merge `MasterItemCountUnit` + `ItemUnitConversion` into single `MasterItemCountUnit`:

| Field | Purpose | Example (Alfredo) | Example (Bottle) |
|-------|---------|-------------------|------------------|
| Primary Count Unit | Base cost unit (smallest) | oz | fl oz |
| Conversion Factor | Always 1.0 for primary | 1.0 | 1.0 |
| Secondary Unit 1 | Common count/purchase | lb (16 oz) | bottle (25.36 fl oz) |
| Secondary Unit 2 | Case/bulk | case (12 lb) | case (12 btl) |

**Key Principles:**
- Primary unit = recipe costing unit (oz or fl oz)
- Secondary units for counting and purchasing
- Cost stored at primary unit → all calculations flow from there
- Vendor pricing converts to primary unit on import

### Sources
- [Restaurant365 Docs](https://docs.restaurant365.com/docs/unit-of-measure-conversions)
- [meez Help Center](https://intercom.help/getmeez/en/articles/5344988-costing-your-recipes)
- [COGS-Well FAQs](https://cogs-well-inc.helpscoutdocs.com/article/739-what-is-a-measure-class-faq)
- [MarginEdge Blog](https://www.marginedge.com/blog/restaurant-plate-and-menu-costing-101)
- [Toast xtraCHEF](https://central.toasttab.com/s/article/xtraCHEF-Recipe-Costing)

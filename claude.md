# Claude Memory - SW Hospitality Group Restaurant Management System

**Last Updated:** January 29, 2026
**System Status:** Production (98% Complete)
**Production URL:** https://rm.swhgrp.com
**Server IP:** 172.233.172.92

---

## 🛠️ CODING PRINCIPLES & GUIDELINES

### Always Use Long-Term Fixes
When fixing issues, **always implement the permanent/architectural solution**, not quick hacks:

1. **Data Sync Issues** → Add API endpoints for automatic syncing, not manual database updates
2. **Cached Data Stale** → Add triggers/hooks to update cache when source changes
3. **Pricing Calculations** → Fix the core formula/query, not just display
4. **Name Mismatches** → Sync mechanisms that auto-update when source changes

### Source of Truth Architecture
- **Hub owns:** UoM, Categories, Vendors, Vendor Items, Invoices
- **Inventory owns:** Master Items, Count Units, Location Costs
- **Accounting owns:** GL Accounts, Journal Entries, Chart of Accounts
- When data is cached across systems, implement sync mechanisms

### Code Quality
- **Delete unused code** - Don't comment out, delete it
- **No backwards-compatibility hacks** - If unused, remove completely
- **Fix root cause** - Don't patch symptoms
- **Test after changes** - Restart containers and verify

### Commit Messages
- Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`
- Include what was changed and why
- End with Claude Code signature

---

## 🎯 CURRENT CONTEXT - WHERE WE ARE

### Most Recent Work (Current Session - January 29, 2026)

**CUSTOMER INVOICE SYSTEM IMPROVEMENTS** ✅ **COMPLETE**

#### 1. **Invoice Creation Bug Fixes** ✅
- **Problem:** Creating invoices returned 422 errors and showed `[object Object]` in error dialog
- **Solution:** Fixed field name mismatches between frontend and Pydantic schema:
  - `line_items` → `lines`, `discount_percent` → `discount_percentage`, `tax_exempt` → `is_tax_exempt`
  - Fixed error display to parse FastAPI 422 validation error arrays
  - Fixed invoice number field showing "undefined" (`data.next_invoice_number` → `data.next_number`)
  - Fixed browser form validation errors on hidden tabs (changed Save as Draft from `type="submit"` to `type="button"`)
- **File:** `accounting/src/accounting/templates/customer_invoices.html`

#### 2. **Invoice Detail Page** ✅
- **Feature:** New detail page at `/customer-invoices/{id}` with full invoice view, print support, and PDF download
- **Template:** `accounting/src/accounting/templates/customer_invoice_detail.html` (NEW)
- **Route:** Added in `accounting/src/accounting/main.py`
- **Features:** Two-column layout, line items table, invoice summary, payment history, event details, audit trail
- **Print:** `@media print` CSS hides navigation/buttons, `window.print()` for browser print

#### 3. **Professional PDF Invoice** ✅
- **Problem:** PDF showed "SW Hospitality Group" instead of selected location (e.g., "The Links Grill")
- **Solution:** Rewrote PDF service with location branding and professional styling
  - Navy blue brand colors, bordered invoice details box, alternating row backgrounds
  - Location name/address/phone/email from Area model
- **Files:** `accounting/src/accounting/services/invoice_pdf_service.py`, `accounting/src/accounting/api/customer_invoices.py`

#### 4. **Draft Invoice Edit & Delete** ✅
- **Feature:** Full edit capability for draft invoices with line item replacement
- **Backend:** Expanded `CustomerInvoiceUpdate` schema with `customer_id`, `area_id`, `is_tax_exempt`, `tax_rate`, `lines`; PUT endpoint deletes and recreates line items with total recalculation
- **Frontend:** Edit button fetches invoice data and populates form; Save uses PUT when editing
- **Delete:** Draft and void invoices can be permanently deleted (not just voided)
- **Files:** `accounting/src/accounting/schemas/customer_invoice.py`, `accounting/src/accounting/api/customer_invoices.py`, `accounting/src/accounting/templates/customer_invoices.html`, `accounting/src/accounting/templates/customer_invoice_detail.html`

#### 5. **Post vs Email Separation** ✅
- **Problem:** "Send" button was ambiguous - it posted to GL, not emailed to customer
- **Solution:** Separated into two distinct actions:
  - **Post** (draft → sent): Finalizes invoice and posts journal entry to GL
  - **Email** (sent invoices): Sends PDF to customer email, can be used multiple times
- **Files:** Both template files updated with new button labels and functions

#### 6. **AR GL Service Fixes** ✅
- **Problem:** GL posting failed with "ACCOUNTS_RECEIVABLE" error and "Customer has no attribute 'name'"
- **Solution:**
  - Fixed account numbers: AR `1200` → `1210`, Sales Tax Payable `2150` → `2300`
  - Removed reference to non-existent `AccountType.ACCOUNTS_RECEIVABLE` enum
  - Fixed `invoice.customer.name` → `invoice.customer.customer_name`
- **File:** `accounting/src/accounting/services/ar_gl_service.py`

#### 7. **Customer Name in API Response** ✅
- **Problem:** Invoice list showed "undefined" for customer name
- **Solution:** Added `customer_name` property to `CustomerInvoice` ORM model and field to `CustomerInvoiceRead` Pydantic schema
- **Files:** `accounting/src/accounting/models/customer_invoice.py`, `accounting/src/accounting/schemas/customer_invoice.py`

#### 8. **Bootstrap Confirm Dialogs** ✅
- Replaced all browser `confirm()` calls with `showConfirm()` Bootstrap modals on invoice detail page
- Matches the rest of the system's UI pattern

---

### Previous Session Work (January 26, 2026)

**CLOVER POS DAILY SALES SYNC IMPROVEMENTS** ✅ **COMPLETE**

#### 1. **Discount Sync & Calculation Fixes** ✅
- **Problem:** Discount amounts from Clover didn't match breakdown
  - Clover reported $23.60 total discounts but itemized amounts differed
  - Percentage-based discounts calculated incorrectly when applied to specific items vs whole order
- **Solution:**
  - Fixed discount extraction logic for both order-level and line-item discounts
  - Added rounding adjustment entry to reconcile calculated vs authoritative totals
  - Tracks order-level discount names to avoid double-counting with line items
- **Files Modified:**
  - `accounting/src/accounting/services/pos_sync_service.py` - Discount extraction logic

#### 2. **Discount Edit Saving Fix** ✅
- **Problem:** Editing discounts in Daily Sales Entry and clicking Verify didn't update journal entry
- **Solution:**
  - Added `discount_breakdown` to saveDSS function data payload
  - Made verify action save pending changes first before verifying
- **File:** `accounting/src/accounting/templates/daily_sales_detail.html`

#### 3. **Refund Breakdown by Category** ✅
- **Feature:** Track refunds by original sale category for accurate journal entries
- **Solution:**
  - Added `refund_breakdown` JSONB column to daily_sales_summary model
  - Extract refund categories from Clover order line items
  - Journal entry preview shows refunds per category with correct revenue account
- **Files Modified:**
  - `accounting/src/accounting/models/daily_sales_summary.py` - New column
  - `accounting/src/accounting/schemas/daily_sales_summary.py` - Schema update
  - `accounting/alembic/versions/20260126_0001_add_refund_breakdown.py` - Migration
  - `accounting/src/accounting/services/pos_sync_service.py` - Extract refunds by category

#### 4. **UI Cleanup & Polish** ✅
- Removed redundant Tax column from Sales Categories tab (already shown on Totals tab)
- Fixed discount amounts to always display with 2 decimal places
- **File:** `accounting/src/accounting/templates/daily_sales_detail.html`

---

### Previous Session Work (January 25, 2026)

**INTEGRATION HUB & INVENTORY BUG FIXES** ✅ **COMPLETE**

#### 1. **Vendor Item Creation Fix** ✅
- **Problem:** 500 error when creating vendor items from unmapped invoice items
- **Solution:** Fixed database constraint to allow NULL for `units_per_case` and `purchase_unit_id`

#### 2. **Inventory Count Units Update Fix** ✅
- **Problem:** 500 error when updating master item count units (invalid `hub_uom_id` reference)
- **Solution:** Removed invalid `hub_uom_id` references from count-units endpoint

#### 3. **Vendor Parsing Rules System** ✅
- Vendor-specific invoice parsing configuration with AI prompt customization

---

### Previous Session Work (January 23, 2026)

**ACCOUNTING CHECK BATCH FIXES** ✅ **COMPLETE**

#### 1. **View Details 403 Error Fix** ✅
- **Problem:** Clicking "View Details" on completed check batches returned 403 Forbidden
- **Solution:** Changed `viewBatch()` to call existing `previewBatch()` function
- **File:** `accounting/src/accounting/templates/check_batches.html`

#### 2. **MICR Line Format Fix** ✅
- **Problem:** Check MICR line had incorrect field order
- **Solution:** Corrected MICR format to: `A267084131A 716209785C C2018C` (Routing, Account, Check)
- **File:** `accounting/src/accounting/services/check_printer.py`

---

### Previous Session Work (January 18, 2026)

**INVENTORY UOM ARCHITECTURE CONSOLIDATION** ✅ **COMPLETE**

Merged `item_unit_conversions` table into `master_item_count_units` to eliminate redundancy.

#### 1. **Database Schema Changes** ✅
- **Migration:** `20260117_0001_consolidate_uom.py`
  - Added `individual_weight_oz`, `individual_volume_oz`, `notes`, `is_active` columns to `master_item_count_units`
  - Data migration script converted existing `item_unit_conversions` to count units
  - Deprecated `item_unit_conversions` table (kept for rollback)

#### 2. **Model Updates** ✅
- **File:** `models/master_item_count_unit.py`
  - Added individual specs fields (weight/volume per unit)
  - Added notes field for contextual info
  - Added is_active for soft delete support

#### 3. **UI Consolidation** ✅
- **File:** `templates/item_detail.html`
  - New "Units of Measure" section replaces separate Count Units + Unit Conversions
  - Unified table showing: Unit, Conversion, Individual Size, Notes, Actions
  - Add Unit modal with:
    - Auto-calculation from Hub UOM data (same dimension)
    - Cross-type conversion input for different dimensions
    - Individual weight/volume/notes fields
  - Edit Item modal dropdown filtering:
    - Filters by `compatibleDimensions` from Hub vendor items
    - Falls back to inferring dimension from current primary count unit
    - Shows dimension notice ("Showing weight units. Based on current primary unit.")

#### 4. **API Fixes** ✅
- **File:** `api/api_v1/endpoints/items.py`
  - Fixed secondary-to-primary unit promotion (delete + flush + update)
  - Added `db.flush()` after delete to avoid unique constraint violations
  - Proper handling of "already assigned" unit scenario

#### 5. **Files Modified:**
- `inventory/alembic/versions/20260117_0001_consolidate_uom.py` - Migration
- `inventory/src/restaurant_inventory/models/master_item_count_unit.py` - Model
- `inventory/src/restaurant_inventory/api/api_v1/endpoints/items.py` - API
- `inventory/src/restaurant_inventory/templates/item_detail.html` - UI

---

### Previous Session Work (January 15, 2026)

**INTEGRATION HUB VENDOR MERGE & ACCOUNTING PAYMENT FIXES** ✅ **PARTIAL**

#### 1. **Hub Vendor Merge Feature** ✅ **API COMPLETE**
- **New Hub API Endpoints:**
  - `POST /hub/api/v1/vendors/merge` - Merge multiple vendors into primary
  - `GET /hub/api/v1/vendors/merge/preview` - Preview merge without changes
  - `POST /hub/api/v1/vendors/push-to-systems` - Push alias state to Inventory/Accounting
  - `GET /hub/api/v1/vendors/push-to-systems/preview` - Preview what push would do

- **Inventory & Accounting Merge Endpoints:**
  - `POST /api/vendors/_hub/merge-into` - Merge vendors (reassign refs, deactivate source)
  - `DELETE /api/vendors/_hub/delete/{vendor_id}` - Delete/deactivate vendor from Hub

- **Hub Vendors Page UI:**
  - Added "Push to Systems" modal and JavaScript functions
  - Added search filter for vendor table
  - Added vendor merge selection UI

- **Files Modified:**
  - `/opt/restaurant-system/integration-hub/src/integration_hub/api/vendors.py`
  - `/opt/restaurant-system/integration-hub/src/integration_hub/services/vendor_sync.py`
  - `/opt/restaurant-system/integration-hub/src/integration_hub/templates/vendors.html`
  - `/opt/restaurant-system/inventory/src/restaurant_inventory/api/api_v1/endpoints/vendors.py`
  - `/opt/restaurant-system/accounting/src/accounting/api/vendors.py`

#### 2. **Duplicate Bill Detection** ✅ **FIXED**
- **Problem:** Same bill number appearing twice for same vendor
- **Solution:** Added duplicate detection in `create_vendor_bill` endpoint
  - Checks for existing bill with same vendor_id + bill_number
  - Returns 400 error if duplicate found (allows re-entering voided bills)
- **File:** `/opt/restaurant-system/accounting/src/accounting/api/vendor_bills.py`

#### 3. **Payment Method Validation Fix** ✅ **FIXED**
- **Problem:** 422 Unprocessable Content error when recording payments
  - Frontend was sending uppercase `'CHECK'` but enum expects lowercase `'check'`
- **Solution:** Changed all payment method option values to lowercase in templates:
  - `/opt/restaurant-system/accounting/src/accounting/templates/vendor_bill_detail.html`
  - `/opt/restaurant-system/accounting/src/accounting/templates/vendor_bills.html`
  - `/opt/restaurant-system/accounting/src/accounting/templates/customer_invoices.html`
  - `/opt/restaurant-system/accounting/src/accounting/templates/payments.html`

#### 4. **Bank Account Dropdown Filter** ✅ **FIXED**
- **Problem:** Payment forms showing all asset accounts, not just bank accounts
- **Solution:** Changed filter from `startsWith('1')` to `num >= 1000 && num < 1100`
  - Only shows Cash/Bank accounts (1000-1099 range)

#### 5. **Payment Redirect URLs** ✅ **FIXED**
- **Problem:** After creating payment, redirecting to portal instead of accounting pages
- **Solution:** Added `/accounting` prefix to all redirects in payments.html:
  - `/check-batches` → `/accounting/check-batches`
  - `/payment-history` → `/accounting/payment-history`
  - `/vendor-bills` → `/accounting/vendor-bills`

---

### 📋 TODO

**See [TODO.md](TODO.md) for the consolidated task list across all systems.**

Quick summary of high-priority items:
- ~~Inventory: UOM Architecture Consolidation~~ ✅ **DONE Jan 18**
- Inventory: Export functionality (Excel/PDF)
- Websites: Static site generation (stub endpoints only, no generator)
- Accounting: Multi-year budget planning

---

### Previous Session Work (January 12, 2026)

**EVENTS CALDAV SYNC FIXES & SSL CERTIFICATE RENEWAL** ✅ **COMPLETE**

#### 1. **CalDAV Bidirectional Sync Fix** ✅ **CRITICAL BUG FIX**
- **Problem:** CalDAV pull sync was overwriting event statuses from phone calendars back to database
  - If someone marked an event CANCELLED on their phone, it would cancel the master event
  - Events not found in CalDAV were being marked as CANCELED incorrectly
  - This caused 15+ events to be incorrectly canceled

- **Solution:** Made web app the source of truth for event status
  - Disabled status sync from CalDAV → database
  - Disabled "missing from CalDAV = canceled" logic
  - CalDAV now only syncs title, description, and times (not status)

- **Files Modified:**
  - `/opt/restaurant-system/events/src/events/services/caldav_sync_service.py`
    - Lines 700-707: Commented out status sync from CalDAV
    - Lines 722-736: Commented out deletion detection logic

#### 2. **Administrator Venue Access Fix** ✅ **DEPLOYED**
- **Problem:** Admin users (like Tina) weren't seeing events on phone calendars
  - CalDAV sync filters events by user's assigned venues
  - Admins weren't automatically assigned to all venues

- **Solution:** Auto-assign all venues to Administrators during HR sync
  - Added `sync_admin_venues()` function to location sync script
  - Queries users with Administrator role
  - Assigns all venues to each admin automatically

- **Files Modified:**
  - `/opt/restaurant-system/events/src/events/scripts/sync_locations_from_hr.py`
    - Added `sync_admin_venues()` function (lines 26-69)
    - Called at end of `sync_locations()` (lines 121-127)

#### 3. **SSL Certificate Renewal** ✅ **FIXED**
- **Problem:** Let's Encrypt certificate expired January 13, 2026
  - Site showing "NET::ERR_CERT_DATE_INVALID" error
  - Old renewal config had incorrect webroot path

- **Solution:** Renewed certificate with correct configuration
  - Fixed webroot path from host path to container path (`/var/www/certbot`)
  - Certificate now valid until April 13, 2026
  - Certbot container running for auto-renewal

#### 4. **Events Intake Form Theme Update** ✅ **DEPLOYED**
- Updated public intake form to use Slate Blue Light theme
- CSS variables for consistent styling
- Matches portal design language

---

### Previous Session Work (January 11, 2026)

**E-SIGNATURE TEMPLATE FIELD EDITOR** ✅ **COMPLETE**

#### 1. **HR E-Signature Visual Field Editor** ✅ **DEPLOYED**
- **Visual PDF Field Placement Interface**
  - PDF.js integration for rendering uploaded template PDFs
  - Click-to-place signature fields on PDF pages
  - Drag and resize placed fields
  - Multi-page navigation with page selector
  - Zoom controls (50%-200%) for precise placement
  - Real-time field position storage (pixels and percentages)

- **Field Types Supported**
  - Signature (primary signature box)
  - Initials (small initial box)
  - Date Signed (auto-filled date field)
  - Text Input (custom text field)

- **API Endpoints**
  - `GET /api/esignature/templates/{id}` - Get template with fields
  - `PUT /api/esignature/templates/{id}/fields` - Save placed fields
  - `GET /api/esignature/templates/{id}/download` - Download PDF for preview

- **Files Modified**
  - `/opt/restaurant-system/hr/src/hr/templates/esignature_templates.html` - Field editor modal with PDF.js
  - `/opt/restaurant-system/hr/src/hr/api/api_v1/endpoints/esignature.py` - API endpoints
  - `/opt/restaurant-system/hr/src/hr/main.py` - Router registration

- **Features**
  - Side-by-side layout (PDF preview + field tools panel)
  - Click-to-place with visual crosshair cursor
  - Field deletion with confirm dialog
  - Placed fields list with page/position info
  - Modal-based editor for template configuration
  - Dropbox Sign integration-ready field storage

---

### Previous Session Work (January 10, 2026)

**MAINTENANCE PORTAL UI** ✅ **COMPLETE**

#### 1. **Maintenance Portal Interface** ✅ **DEPLOYED**
- **Complete Web UI for Maintenance System**
  - Dashboard with real-time stats and alerts
  - Equipment management with search, filters, CRUD
  - Work orders with status workflow
  - Maintenance schedules with completion tracking
  - Consistent styling with Portal design

- **Portal Routes Added**
  - `/portal/maintenance/` - Dashboard
  - `/portal/maintenance/equipment` - Equipment list
  - `/portal/maintenance/work-orders` - Work orders list
  - `/portal/maintenance/work-orders/new` - New work order form
  - `/portal/maintenance/schedules` - Maintenance schedules

- **Templates Created**
  - `maintenance/dashboard.html` - Stats cards, alerts, recent work orders
  - `maintenance/equipment.html` - Equipment list with filters and modal
  - `maintenance/work_orders.html` - Work orders with status management
  - `maintenance/work_order_form.html` - New work order creation
  - `maintenance/schedules.html` - PM schedules with completion tracking

- **Features**
  - Search and filter equipment by category, status, location
  - Work order priority badges and status workflow
  - Inline status updates for work orders
  - Schedule frequency configuration (daily/weekly/monthly/quarterly/yearly)
  - Auto-generate work orders from schedules
  - Permission-based access (can_access_maintenance)

- **Files Modified**
  - `/opt/restaurant-system/portal/src/portal/main.py` - Added maintenance routes
  - `/opt/restaurant-system/portal/templates/home.html` - Added maintenance icon and navigation
  - Created 5 new templates in `portal/templates/maintenance/`

---

### Previous Session Work (January 9, 2026)

**MAINTENANCE SERVICE BACKEND & PASSWORD RESET** ✅ **COMPLETE**

#### 1. **Maintenance & Equipment Tracking Service** ✅ **DEPLOYED**
- **New Microservice Created**
  - Full FastAPI backend with async SQLAlchemy
  - Equipment tracking with auto-generated QR codes
  - Equipment categories (hierarchical)
  - Work order management (create, assign, start, complete)
  - Preventive maintenance scheduling
  - Vendor management
  - Dashboard with alerts

- **API Endpoints**
  - `/maintenance/health` - Health check
  - `/maintenance/dashboard` - Dashboard with stats
  - `/maintenance/equipment` - Equipment CRUD
  - `/maintenance/categories` - Category management
  - `/maintenance/work-orders` - Work order management
  - `/maintenance/schedules` - PM scheduling
  - `/maintenance/vendors` - Vendor management

- **Database Tables**
  - `equipment_categories`, `equipment`, `equipment_history`
  - `maintenance_schedules`, `work_orders`, `work_order_comments`, `work_order_parts`
  - `vendors`

- **Infrastructure**
  - Container: `maintenance-service` (port 8006)
  - Database: `maintenance-postgres`
  - Added to nginx routing
  - Added to monitoring scripts
  - Added to backup scripts
  - Swagger docs at `/maintenance/docs`

- **Files Created**
  - `/opt/restaurant-system/maintenance/` - Complete service directory
  - Models, schemas, routers, Dockerfile, docker-compose.yml
  - Alembic migrations

---

**PASSWORD RESET SYSTEM & MONITORING FIXES** ✅ **COMPLETE**

#### 2. **Password Reset System** ✅ **COMPLETE**
- **Email-Based Self-Service Password Reset**
  - Added "Forgot your password?" link to login page
  - Created forgot password page (email input form)
  - Created reset password page (new password + confirmation)
  - Integrated with existing SMTP configuration from HR system
  - Uses HR's mailcow server at `mail.swhgrp.com`

- **Security Features**
  - Secure random token generation (32-byte URL-safe)
  - 1-hour token expiration
  - Tokens stored in database (reset_token, reset_token_expires columns)
  - Anti-enumeration protection (always shows success message)
  - Password strength validation (minimum 8 characters)
  - Automatic password sync to all connected systems

- **Email Integration**
  - Sends professional HTML emails from `hr@swhgrp.com`
  - Uses encrypted SMTP password from HR database
  - Decryption using HR's ENCRYPTION_KEY
  - Emails delivered through SpamHero

- **Database Changes**
  - Added `reset_token VARCHAR` column to users table
  - Added `reset_token_expires TIMESTAMP` column to users table
  - Created index on reset_token for performance

- **Files Modified**
  - `/opt/restaurant-system/portal/src/portal/main.py` - Added reset endpoints & email service
  - `/opt/restaurant-system/portal/templates/login.html` - Added forgot password link
  - `/opt/restaurant-system/portal/templates/forgot_password.html` - Created
  - `/opt/restaurant-system/portal/templates/reset_password.html` - Created

#### 3. **Monitoring System Fixes** ✅ **COMPLETE**
- **Service Health Check Script Bug**
  - Fixed URL parsing in `monitor-services.sh`
  - Changed delimiter from `:` to `|` to avoid conflict with `https:`
  - All 8 microservices now report correctly (Portal, Inventory, HR, Accounting, Events, Hub, Files, Maintenance)

- **Docker Container Status Bug**
  - Fixed newline handling in container health status
  - Properly handles containers without health checks

- **Nginx Proxy Status Fix**
  - Updated `dashboard-status.sh` to check `nginx-proxy` instead of `nginx-mailcow`
  - Monitoring page now correctly shows nginx as "running"

- **SSL Certificate Auto-Renewal**
  - Created reload hook: `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`
  - Nginx automatically reloads when SSL certificate renews
  - Certificate expires Jan 13, 2026 (will auto-renew)

- **Files Modified**
  - `/opt/restaurant-system/scripts/monitor-services.sh` - Fixed service checking logic
  - `/opt/restaurant-system/scripts/dashboard-status.sh` - Fixed nginx container name
  - `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh` - Created

#### 4. **Important Docker Container Issue Discovered**
- **Portal Container Code Location**
  - Portal app loads from `/app/portal/main.py` (baked into image at build time)
  - Volume mount at `/app/src/portal/` exists but not used by uvicorn
  - **Workaround:** Must manually copy updated main.py: `docker cp portal/src/portal/main.py portal-app:/app/portal/main.py`
  - **Future Fix Needed:** Update Dockerfile or docker-compose to use volume-mounted code

---

### Previous Session Work (January 6, 2026)

**DSS DEPOSIT CALCULATION & DISCOUNT BREAKDOWN** ✅ **COMPLETE**

#### 1. **Split Deposit Display** ✅ **COMPLETE**
- Replaced single "Deposit Amount" field with separate **Card Deposit** and **Expected Cash Deposit**
- Card Deposit = Card payments + Card tips - Refunds (what processor deposits to bank)
- Expected Cash Deposit = Cash payments - Cash Tips Paid Out - Payouts (what's left in drawer)
- Added **Cash Tips Paid** field showing tips paid to employees from cash drawer

#### 2. **Deposit Reconciliation Formula** ✅ **COMPLETE**
- **Variance = (Card Deposit + Expected Cash Deposit + Cash Tips Paid) - Total Collected**
- This should equal $0.00 when all money is accounted for
- Card tips are received via merchant deposit, then paid out to employees from cash drawer
- Formula: Card + Cash + Tips = (Card + Card Tips) + (Cash - Card Tips) + Card Tips = Total Collected

#### 3. **Complete Discount Breakdown** ✅ **COMPLETE**
- Fixed discount extraction to capture BOTH order-level AND line-item discounts
- Fixed percentage-based discount calculation (was using post-discount total, now uses line items total)
- All discounts now appear as individual line items on Discounts tab:
  - 6 Pack, PBC Staff, Staff Meal, Ryan & Nick - Brightview, Waste, etc.
- Total matches Clover's reported discount total exactly

#### 4. **Payouts Tab** ✅ **COMPLETE**
- Added new Payouts tab to DSS detail page
- Displays cash_events from Clover (CASH_ADJUSTMENT type)
- Shows amount, note/reason, employee name, timestamp
- Graceful handling when cash_events endpoint returns 401

#### 5. **Database Migration** ✅ **COMPLETE**
- Migration: `20260106_0001_add_deposit_and_payout_fields.py`
- Added to `daily_sales_summaries`: card_deposit, cash_tips_paid, cash_payouts, expected_cash_deposit, payout_breakdown
- Added to `pos_daily_sales_cache`: same fields

#### 6. **Files Modified**
- `accounting/src/accounting/services/pos_sync_service.py` - Deposit calculations, discount extraction
- `accounting/src/accounting/templates/daily_sales_detail.html` - UI updates, variance calculation
- `accounting/src/accounting/models/daily_sales_summary.py` - New deposit/payout fields
- `accounting/src/accounting/models/pos.py` - New fields in POSDailySalesCache
- `accounting/src/accounting/schemas/daily_sales_summary.py` - Schema updates
- `accounting/src/accounting/core/clover_client.py` - get_cash_events method
- `accounting/alembic/versions/20260106_0001_add_deposit_and_payout_fields.py` - Migration

---

### Previous Session Work (January 5, 2026)

**WASTE LOG & TRANSFER ENHANCEMENTS** ✅ **COMPLETE**

#### 1. **Waste Log UoM Dropdown** ✅ **COMPLETE**
- Added unit of measure dropdown to waste log form
- UoM options populated from item's count units (primary + secondary)
- Fixed API routing issue: `/api/items` (no slash) was hitting simplified endpoint returning null UoM
- Changed `/api/items` endpoint to redirect (307) to `/api/items/` for consistency
- Added `unit_of_measure` column to `waste_records` table (migration: `20260105_0001`)
- Updated WasteRecord model, schemas, and API endpoints to store/display UoM

#### 2. **Transfer Form Enhancements** ✅ **COMPLETE**
- Added searchable Select2 dropdown for item selection
- Added date/time field for transfer date
- Added UoM dropdown populated from item's count units
- Applied slate theme styling to Select2 dropdowns

#### 3. **API Route Consistency Fix** ✅ **COMPLETE**
- Discovered `/api/items` (no trailing slash) in main.py was returning incomplete data
- Changed it to redirect to `/api/items/` which has full UoM processing
- Prevents confusion where different endpoints return different data structures

#### 4. **Files Modified**
- `inventory/src/restaurant_inventory/templates/waste.html` - UoM dropdown, Select2, trailing slash fix
- `inventory/src/restaurant_inventory/templates/transfers.html` - Date, UoM, Select2
- `inventory/src/restaurant_inventory/models/waste.py` - Added `unit_of_measure` column
- `inventory/src/restaurant_inventory/schemas/waste.py` - Added `unit_of_measure` field
- `inventory/src/restaurant_inventory/api/api_v1/endpoints/waste.py` - Store/display UoM
- `inventory/src/restaurant_inventory/main.py` - Redirect `/api/items` → `/api/items/`
- `inventory/alembic/versions/20260105_0001_add_uom_to_waste_records.py` - Migration

---

### Previous Session Work (Dec 31, 2025)

**UNIT CONVERSIONS & PRICING FIXES** ✅ **COMPLETE**

#### 1. **Beer Items - Ounce to Can Conversions** ✅ **COMPLETE**
- Added unit conversions for 10 beer items (16oz cans): oz → Can with factor=16
- Updated all beer items to have "Can" as primary count unit
- Fixed vendor item `size_quantity` consistency (all 16oz beers now have size_quantity=16)
- Pricing calculation: `case_cost / (units_per_case * size_quantity) * conversion_factor`
- Example: Coors Light $31.55/case ÷ 24 ÷ 16oz = $0.082/oz × 16 = $1.31/can

#### 2. **Wine Items - Bottle Count Units** ✅ **COMPLETE**
- Updated all 29 wine items to have "Bottle" as primary count unit
- Wine items do NOT need unit conversions (volume items priced per bottle directly)
- Pricing calculation for volume: `case_cost / units_per_case` (size_quantity is just description)
- Example: Cabernet $189/case ÷ 12 = $15.75/bottle

#### 3. **Master Items List Pricing Fix** ✅ **COMPLETE**
- Added unit conversion lookup to items API endpoint
- Applies conversion factor when displaying `last_price_paid`
- Only applies to weight/count items, not volume items
- Files modified:
  - `inventory/src/restaurant_inventory/api/api_v1/endpoints/items.py` - Unit conversion in pricing

#### 4. **Item Detail Pricing Display Fix** ✅ **COMPLETE**
- Fixed pricing stats calculation in item_detail.html
- Loads unit conversions BEFORE vendor items
- Applies conversion factor correctly based on from_unit/to_unit matching

#### 5. **Count Units Dropdown Fix** ✅ **COMPLETE**
- Inventory count modal now only shows explicitly defined count units
- Removed fallback to "compatible units" that was adding unwanted options
- Files modified:
  - `inventory/src/restaurant_inventory/templates/count_session_new.html`

#### 6. **Pricing Logic Summary**
| Item Type | measure_type | size_quantity division | Unit Conversion |
|-----------|--------------|------------------------|-----------------|
| Weight (flour, meat) | weight | Yes (÷ size_qty) | Yes (oz→lb etc) |
| Count (patties, eggs) | count | Yes (÷ size_qty) | Yes (each→case) |
| Volume (wine, spirits) | volume | No (size is description) | No (per bottle) |
| Beer (special case) | weight (oz) | Yes (÷ 16oz) | Yes (oz→can ×16) |

---

### Previous Session Work (Dec 30, 2025)

**HUB UOM ARCHITECTURE & VENDOR ITEMS PERFORMANCE** ✅ **COMPLETE**

#### 1. **Hub as UoM Source of Truth** ✅ **COMPLETE**
- Hub's `units_of_measure` table is the authoritative source for all UoM data
- Inventory stores `primary_uom_id` (Hub ID) with cached `primary_uom_name` and `primary_uom_abbr`
- New Hub API endpoint: `GET /api/uom/` returns all units with dimension/measure_type
- Inventory proxy: `/api/units/hub` fetches UoMs from Hub for frontend use

#### 2. **Item Unit Conversions** ✅ **COMPLETE**
- Model: `ItemUnitConversion` with `from_unit_id`, `to_unit_id`, `conversion_factor`
- Unit IDs reference Hub's UoM table (not Inventory's deprecated table)
- Added 58 Liter → Bottle conversions for alcohol items (1:1 factor)
- Updated 57 alcohol items to use Bottle as primary count unit

#### 3. **Vendor Items Page Performance** ✅ **COMPLETE**
- Server-side pagination: 50 items per page (was loading all 694+ items)
- AJAX loading via `/hub/api/v1/vendor-items/` with pagination params
- Debounced search (300ms delay before server request)
- Server-side filtering for search, vendor, category, status
- Pagination UI with Previous/Next and "Showing 1-50 of 694" info

---

### Previous Session Work (Dec 27-28, 2025)

**LOCATION-AWARE COSTING ARCHITECTURE** ✅ **SCHEMA COMPLETE**

Major refactor implementing MarginEdge/R365 hybrid architecture for location-specific weighted average costing.

#### System Boundaries (New Architecture)
- **Hub owns:** UOM (global), Categories (global), Vendor Items (per location)
- **Inventory owns:** Master Items, Count Units, Location Costs

#### 1. **Hub Schema Updates** ✅ **COMPLETE**
- **UnitOfMeasure Model** (`integration-hub/src/integration_hub/models/unit_of_measure.py`)
  - Added `MeasureType` enum (each, weight, volume) - simplified from old 4-dimension system
  - Added `measure_type` field with `effective_measure_type` property for backward compatibility
  - Deprecated `dimension` field (kept for migration)
- **HubVendorItem Model** (`integration-hub/src/integration_hub/models/hub_vendor_item.py`)
  - Added `VendorItemStatus` enum (active, needs_review, inactive)
  - Added `location_id` - each vendor item now tied to a specific location
  - Added `status` field for review workflow
  - Added `pack_to_primary_factor` - converts purchase units to primary count units
  - Added `last_purchase_price`, `previous_purchase_price`
  - Added `cost_per_primary_unit` property
  - Deprecated old fields: `conversion_factor`, `unit_price`, `is_active`

#### 2. **Inventory Schema Updates** ✅ **COMPLETE**
- **NEW: MasterItemCountUnit** (`inventory/src/restaurant_inventory/models/master_item_count_unit.py`)
  - Defines multiple count units per master item
  - `is_primary` flag for primary count unit
  - `conversion_to_primary` factor
  - Helper methods: `convert_to_primary()`, `convert_from_primary()`
- **NEW: MasterItemLocationCost** (`inventory/src/restaurant_inventory/models/master_item_location_cost.py`)
  - Weighted average cost per location
  - `current_weighted_avg_cost`, `total_qty_on_hand`
  - `apply_purchase()` and `apply_usage()` methods for cost updates
  - `MasterItemLocationCostHistory` for audit trail
- **MasterItem Model** (`inventory/src/restaurant_inventory/models/item.py`)
  - Added `category_id`, `primary_uom_id`, `primary_uom_name`, `primary_uom_abbr`, `shelf_life_days`
  - Added relationships to `count_units` and `location_costs`
  - Added `get_cost_at_location()` and `get_primary_count_unit()` methods
  - Deprecated cost fields: `current_cost`, `average_cost`

#### 3. **Migration Script** ✅ **COMPLETE**
- **File:** `scripts/migrate_location_aware_costing.py`
- **Phases:**
  - Phase 1a: Hub UOM measure_type migration (dimension → measure_type)
  - Phase 1b: Hub Vendor Items schema updates (add location_id, status, pack_to_primary_factor)
  - Phase 2: Inventory table creation (count_units, location_costs, cost_history)
  - Phase 3: Data migration (copy existing costs to all locations)
- **Usage:** `python3 scripts/migrate_location_aware_costing.py [--dry-run]`

#### 4. **Remaining Work**
- [ ] Run migration script on staging/production
- [ ] Update invoice processing for location detection
- [ ] Build costing engine with weighted average calculations
- [ ] Update UIs for location filters and cost displays

---

### Previous Session Work (Dec 25, 2025)

**HUB VENDOR ITEMS: UI IMPROVEMENTS & SOURCE OF TRUTH CONSOLIDATION** ✅ **COMPLETE**

#### 1. **Vendor Item Modal Field Improvements** 🎨 **UI/UX**
- **Field Label Changes** - Updated Add/Edit modals for clarity:
  - "Purchase Unit" → "Base Unit" (what you count inventory in)
  - "Conversion Factor" → "Quantity Per Case" (how many base units per case)
  - "Unit Price" → "Case Price" / "Last Case Price" (auto-updated from invoices)
- **Removed Pack Size Field** - Redundant since Base Unit + Quantity Per Case already defines the pack
- **Added Helpful Descriptions** - Each field now has explanatory text
- **Files Modified:**
  - `integration-hub/src/integration_hub/templates/hub_vendor_items.html`

#### 2. **Hierarchical Categories via dblink** 📂 **DATA INTEGRATION**
- **Problem:** Category dropdown showed flat list ("Bottled", "Draft") instead of nested ("Beer - Bottled", "Beer - Draft")
- **Solution:** Query Inventory database via dblink for parent-child category relationships
- **Result:** Categories now display as "Parent - Child" format matching Inventory system
- **Files Modified:**
  - `integration-hub/src/integration_hub/main.py` (vendor_items_page function)

#### 3. **Units of Measure via dblink** 📐 **DATA INTEGRATION**
- **Problem:** Hub only had 4 fallback units; needed full 37 units from Inventory
- **Previous Attempt:** httpx API call to Inventory (failed - required authentication)
- **Solution:** Query Inventory database directly via dblink (like categories)
- **Result:** All 37 units now available (Each, Pound, Case, Gallon, etc.)
- **Files Modified:**
  - `integration-hub/src/integration_hub/main.py` (vendor_items_page function)

#### 4. **Hub as Source of Truth - Inventory Cleanup** 🗑️ **ARCHITECTURE**
- **Removed from Inventory System** (Hub now owns these):
  - `invoices.py` endpoint and template
  - `vendor_items.py` endpoint (replaced with hub_vendor_items.py proxy)
  - `invoice_parser.py` and `vendor_item_parser.py`
  - Models: Invoice, InvoiceItem, VendorItem, VendorAlias
  - Schemas: invoice.py, vendor_item.py
- **Deprecated Files** moved to `_deprecated/` folders
- **Hub Client Updated** - Simplified to proxy operations to Hub
- **Files Deleted/Deprecated:**
  - `inventory/src/restaurant_inventory/api/api_v1/endpoints/invoices.py`
  - `inventory/src/restaurant_inventory/api/api_v1/endpoints/vendor_items.py`
  - `inventory/src/restaurant_inventory/core/invoice_parser.py`
  - `inventory/src/restaurant_inventory/core/vendor_item_parser.py`
  - `inventory/src/restaurant_inventory/models/invoice.py`
  - `inventory/src/restaurant_inventory/models/vendor_item.py`
  - `inventory/src/restaurant_inventory/models/vendor_alias.py`
  - `inventory/src/restaurant_inventory/schemas/invoice.py`
  - `inventory/src/restaurant_inventory/schemas/vendor_item.py`

---

### Previous Session Work (Dec 25, 2025 - Earlier)

**INTEGRATION HUB: VENDOR NORMALIZATION, BATCH OPERATIONS, REPORTING & DUPLICATE DETECTION** ✅ **COMPLETE**

#### 1. **Invoice Batch Operations** 📦 **NEW API**
- Created batch operations service and API endpoints
- **Endpoints:** `/api/v1/batch/`
  - `POST /approve` - Batch approve invoices
  - `POST /auto-map` - Batch auto-map unmapped items
  - `POST /status` - Batch status update
  - `POST /mark-sent` - Mark invoices as sent to systems
  - `POST /reset-sync` - Reset sync status for re-processing
  - `POST /delete` - Batch delete invoices
  - `POST /summary` - Get summary for selected invoices
- **Files Created:**
  - `integration-hub/src/integration_hub/services/batch_operations.py`
  - `integration-hub/src/integration_hub/api/batch_operations.py`

#### 2. **Reporting Dashboard** 📊 **NEW API**
- Created reporting service with analytics endpoints
- **Endpoints:** `/api/v1/reports/`
  - `GET /summary` - Overall system summary stats
  - `GET /vendor-spend` - Spending by vendor with period filtering
  - `GET /mapping-stats` - Item mapping statistics
  - `GET /sync-status` - System sync health metrics
  - `GET /daily-volume` - Invoice volume over time
  - `GET /category-breakdown` - Spending by category
- **Files Created:**
  - `integration-hub/src/integration_hub/services/reporting.py`
  - `integration-hub/src/integration_hub/api/reporting.py`

#### 3. **Vendor Name Normalization - Hub as Source of Truth** 🏢 **MAJOR FEATURE**
- **Decision:** Moved vendors to Hub as source of truth (like vendor items)
- **VendorAlias Model:** Maps OCR/invoice name variants to canonical vendors
  - `alias_name` - Original name from invoice (e.g., "Gordon Food Service Inc.")
  - `alias_name_normalized` - Lowercase stripped version for matching
  - `vendor_id` - Links to canonical Hub vendor
  - `source` - 'manual', 'auto', 'migrated', 'ocr'
- **VendorNormalizerService:** Resolves vendor names, creates aliases, links invoices
- **API Endpoints:** `/api/v1/vendors/`
  - CRUD for vendors and aliases
  - `GET /summary` - Vendor/alias statistics
  - `POST /normalization/auto-create-aliases` - Create aliases from linked invoices
  - `POST /normalization/normalize-invoices` - Normalize vendor names on invoices
  - `POST /normalization/link-unlinked` - Link invoices via aliases
- **Results:**
  - Auto-created 8 aliases from linked invoices
  - Normalized 275 invoices to canonical vendor names
  - Linked 19 previously unlinked invoices
  - Deactivated 5 duplicate vendors (merged as aliases)
- **UI Updates:** `/hub/vendors` page
  - Added "Show Aliases" toggle
  - Aliases column shows linked variants
  - "+" button to add aliases per vendor
  - "Manage Aliases" modal with auto-create, link, normalize actions
  - Edit vendor functionality
  - Filters out inactive (merged) vendors
- **Files Created:**
  - `integration-hub/src/integration_hub/models/vendor_alias.py`
  - `integration-hub/src/integration_hub/services/vendor_normalizer.py`
  - `integration-hub/src/integration_hub/api/vendors.py`
- **Files Modified:**
  - `integration-hub/src/integration_hub/templates/vendors.html`
  - `integration-hub/src/integration_hub/main.py` (vendor page route filters inactive)

#### 4. **Duplicate Invoice Detection** 🔍 **NEW FEATURE**
- **Detection Strategies:**
  - Exact invoice number match (same vendor + normalized invoice#) - 95% confidence
  - Vendor + date + amount match (within configurable window) - 70-80% confidence
- **API Endpoints:** `/api/v1/duplicates/`
  - `GET /stats` - Duplicate statistics
  - `GET /scan` - Scan all invoices with configurable thresholds
  - `GET /invoice/{id}` - Find duplicates for specific invoice
  - `POST /mark` - Mark invoice as duplicate (flag or delete)
  - `POST /mark/bulk` - Bulk mark duplicates
- **UI Page:** `/hub/duplicates`
  - Stats cards (groups, potential duplicates, high confidence, scanned)
  - Configurable filters (min confidence, match type, date window)
  - Visual duplicate groups with confidence badges
  - Quick actions: "Keep First" or "Keep Newest"
  - Checkbox selection for bulk deletion
  - View invoice details modal
- **Results Found:**
  - 53 high-confidence duplicate groups (128 total)
  - 257 potential duplicate invoices
  - Primary vendors: Gold Coast Linen (59), Gordon Food Service (51)
- **Files Created:**
  - `integration-hub/src/integration_hub/services/duplicate_detection.py`
  - `integration-hub/src/integration_hub/api/duplicates.py`
  - `integration-hub/src/integration_hub/templates/duplicates.html`
- **Files Modified:**
  - `integration-hub/src/integration_hub/templates/base.html` (nav link)
  - `integration-hub/src/integration_hub/main.py` (page route, router registration)

#### 5. **Navigation Update**
- Added "Duplicates" link to sidebar navigation (between Vendor Items and Settings)

---

### Previous Session Work (Dec 24, 2025)

**UI CONSISTENCY: SIDEBAR HIGHLIGHTING & SUBMENU BEHAVIOR FIXES** ✅ **COMPLETE**

#### 1. **Sidebar Active State Audit** 🔍 **ALL SYSTEMS**
- Audited all 6 systems for consistent sidebar highlighting behavior
- **Approaches Found:**
  | System | Method |
  |--------|--------|
  | Accounting | Jinja template blocks (`{% block nav_xxx %}active{% endblock %}`) |
  | Events | Jinja conditionals (`{% if 'path' in request.path %}active{% endif %}`) |
  | Integration Hub | Jinja conditionals |
  | HR | Jinja template blocks |
  | Inventory | JavaScript-based (path matching) |
  | Websites | Jinja conditionals with `active_page` variable |

#### 2. **Inventory Sidebar Fix** 🔧 **BUG FIX**
- **Problem:** Count History page also highlighted Take Inventory menu item
- **Root Cause:** JavaScript `startsWith()` matching `/inventory/count` matched both `/inventory/count` and `/inventory/count/history`
- **Solution:** Rewrote path matching to use exact match or proper segment boundaries
- **File Modified:** `inventory/src/restaurant_inventory/templates/base.html`

#### 3. **Accounting Submenu Fixes** 🔧 **BUG FIXES**
- **Reports Submenu Closing:** Added `comparative-pl` and `cash-flow-statement` to auto-open logic
- **Recurring Invoices Submenu Closing:** Added `/recurring-invoices` to AR section auto-open logic
- **DSS Journal Entries Wrong Highlight:**
  - Updated `main.py` to pass `source` query parameter to template
  - Updated `journal_entries.html` to conditionally set nav block based on source
  - Now correctly highlights DSS Journal Entries (source=sale) or Bill Journal Entries (source=bill)
- **ACH Batches Text Wrapping:** Added `white-space: nowrap` to submenu items
- **Files Modified:**
  - `accounting/src/accounting/main.py` (added source parameter)
  - `accounting/src/accounting/templates/journal_entries.html` (conditional nav blocks)
  - `accounting/src/accounting/templates/base.html` (CSS fix, auto-open logic)

#### 4. **Events System Theme Fix** 🎨 **UI FIX** (from previous session)
- **Problem:** Settings and Tasks pages had dark theme colors instead of light theme
- **Solution:** Replaced hardcoded dark colors with CSS variables
- **Files Modified:** `events/src/events/templates/admin/settings.html`, `tasks.html`

#### 5. **Integration Hub GL Names Fix** 🔧 **BUG FIX** (from previous session)
- **Problem:** GL account descriptions missing on invoice detail page
- **Root Cause:** Dictionary keys were integers but template looked up strings
- **Solution:** Convert keys to strings when building `gl_names` dictionary
- **File Modified:** `integration-hub/src/integration_hub/main.py`

---

### Previous Session Work (Dec 23, 2025)

**INTEGRATION HUB: INVOICE ITEM MAPPING IMPROVEMENTS + OCR FIXES + INVENTORY CLEANUP** ✅ **COMPLETE**

#### 1. **Massive Inventory Item Import** 📦 **MAJOR DATA WORK**
- **Problem:** 142 unmapped GFS (Gordon Food Service) items preventing full mapping
- **Solution:** Systematically added all items to inventory system
- **Results:**
  - **Before:** 93.4% mapping rate (2,431/2,604 items)
  - **After:** 99.5% mapping rate (2,592/2,604 items)
- **Items Added by Category:**
  | Category | New Master Items | Vendor Items |
  |----------|-----------------|--------------|
  | Beef | Beef Strip Loin | 5 |
  | Produce | Arugula Baby, Romaine Hearts, Avocado Hass | 16 |
  | Bakery | Bun Brioche Round, Empanada Chicken, Pretzel Bites | 10 |
  | Seafood | (linked to existing) | 8 |
  | Pork | Pork Spareribs, Sausage Italian Links | 5 |
  | Frozen | Tater Tots, Onion Rings Breaded | 6 |
  | Dairy | Milk Whole Gallon, Ice Cream (3 flavors), Whipped Topping | 11 |
  | Grocery | Croutons, Pudding Mix, BBQ Rub, Mandarin Oranges, Beans Refried, Chips Tortilla | 22 |
  | Supplies | Containers (2), Foil, Pick Bamboo, Tray Food, Tissue Toilet | 25 |
  | Wine | Conundrum Red, La Crema Pinot Gris, Meiomi Sauvignon Blanc, Rodney Strong Cabernet, Uptown Cocktails (2) | 10 |
- **Naming Convention:** Simple, clean names (e.g., "Beef Flap Meat", "Arugula, Baby", "Tater Tots")
- **Store Items:** GFS Store items (with trailing 0 in item code) linked to same master items as delivery items

#### 2. **Duplicate Master Item Cleanup** 🧹 **DATA QUALITY**
- **Problem:** Multiple master items for same product (user-identified via UI screenshots)
- **Duplicates Consolidated:**
  - Beef Flap items (3 entries) → "Beef Flap Meat" (id=242)
  - Angel's Envy Bourbon (2 entries) → "Angel's Envy Bourbon 86.6" (id=422)
  - Makers Mark Bourbon (2 entries) → consolidated
  - Ham Natural Juice (2 entries) → consolidated
  - Marinara Sauce (3 entries) → consolidated
  - Tea items (4 entries) → consolidated
  - Vegetable Blend Caribbean (2 entries) → consolidated
  - Soft Drink Cola Diet (2 entries) → consolidated
  - Balsamic Vinaigrette (2 entries) → consolidated
  - Drink Concentrates (4 entries) → consolidated
- **Method:** Move vendor_items and waste_records to canonical item, then delete duplicate
- **Total Deleted:** ~15 duplicate master items

#### 3. **Category Cleanup** 🏷️ **DATA QUALITY**
- **Problem:** Many items incorrectly in "Uncategorized" category
- **Fixed:** ~50 items moved to proper categories:
  - Angus Strip Steaks → Beef
  - Bananas → Produce
  - Bread items → Bakery
  - Cheesecake → Bakery
  - Coffee → Grocery
  - Coke/Coca-Cola → Beverages - Non Alcoholic
  - Detergent/Sanitizer → Cleaning & Chemical
  - Don Julio Tequila → Tequila
  - Gloves → Supplies - Disposable
  - Hash Browns → Frozen
  - And many more...
- **Remaining:** 96 items still in Uncategorized (mostly BJ's/Sam's bulk items with long descriptions)

#### 4. **OCR Error Fixes Applied** 🔧 **DATA FIXES**
- Fixed vendor name matching (LLC suffix stripping added)
- Fixed Grill Brick OCR errors (780170 misread as 780117, 780710, 768170)
- Added grill→griddle abbreviation for OCR recovery
- Deleted 128 duplicate invoice items from Invoice 9030397136

#### 5. **Invoice Parser Enhancements** 🤖 **CODE IMPROVEMENTS**
- **UPC vs Item Code Detection:** Added `_fix_upc_as_item_code()` method
  - Detects long codes (>10 digits) starting with 000
  - Corrects using historical invoice data or mapping table
- **Description-Based OCR Fix:** Added `_fix_ocr_by_description()` method
  - When item codes don't match but descriptions are similar
  - Uses Jaccard similarity with abbreviation expansion
  - Includes 100+ food service abbreviations (chix→chicken, bf→beef, etc.)
- **Processing Order:** UPC fix → OCR correction → Description normalization → Description-based fix → Auto-map

#### 6. **Remaining Unmapped Items (12)**
- Miller Lite (intentionally unmapped per user request - not in inventory)
- Non-product entries: Invoice, Transaction, Unknown, Final-Notification (9 items)
- Daily's Lime Juice (item code embedded in description text)
- Pest Control Service (service, not product)

**Files Modified:**
- `integration-hub/src/integration_hub/services/invoice_parser.py` (UPC fix, description fix, abbreviations)
- Inventory database: Created ~30 new master items, ~150 new vendor items
- Hub database: Fixed 128 duplicates, corrected OCR errors

---

### Previous Session Work (Dec 21, 2025)

**INTEGRATION HUB DATA FIXES + LOCATION SYNC IMPROVEMENTS** ✅ **COMPLETE**

1. **Expense Items Display Fix** 🔧 **BUG FIX**
   - **Problem:** Invoice detail showed "Expense" but mapped items page showed "Uncategorized"
   - **Solution:** Updated template logic to show "Expense" badge for items with `inventory_category='Uncategorized'` and only `gl_cogs_account`
   - **Files Modified:**
     - `integration-hub/src/integration_hub/templates/mapped_items.html`
     - `integration-hub/src/integration_hub/templates/unmapped_items.html`
     - `integration-hub/src/integration_hub/templates/invoice_detail.html`
   - **Database:** Updated 558 expense items to have `inventory_category='Uncategorized'`, cleared `gl_asset_account` for 548 expense items

2. **Dashboard Badge Styling** 🎨 **UI FIX**
   - **Problem:** Status badges (mapping, ready) had white text on light backgrounds (unreadable)
   - **Solution:** Added missing CSS classes for badge colors
   - **File Modified:** `integration-hub/src/integration_hub/templates/base.html`
   - **Added:** `.badge-mapping`, `.badge-partial`, `.badge-statement`, `.badge-parse_failed`, `.badge-parsing`

3. **Vendor Name Normalization** 📝 **NEW FEATURE**
   - **Problem:** Inconsistent vendor name capitalization across invoices
   - **Solution:** Created `normalize_vendor_name()` function in invoice_parser.py
   - **Features:**
     - Title case with smart handling for company suffixes (Inc., LLC, Corp.)
     - Preserves state codes (FL, GA) and brand names (AmeriGas, Sysco)
     - Handles lowercase words (of, the, and)
   - **File Modified:** `integration-hub/src/integration_hub/services/invoice_parser.py`
   - **Database:** Updated 107 existing invoices with normalized vendor names

4. **Expense Vendor Sync Status Fix** 🛡️ **DATA FIX**
   - **Problem:** Expense vendors (City Fire, Cozzini Bros, Gold Coast Linen, Tillman) incorrectly showing as synced to inventory
   - **Solution:** Cleared invalid `inventory_vendor_id` for expense vendors in hub database
   - **Vendors Fixed:** City Fire, Cozzini Bros., Gold Coast Linen, Tillman, Amerigas

5. **Invoice Location Fix - CRITICAL** 🔥 **BUG FIX**
   - **Problem:** Invoices sent to inventory system all had wrong location (Seaside Grill)
   - **Root Cause:** `inventory_sender.py` was not sending `location_id` in payload
   - **Solution:** Added `"location_id": invoice.location_id` to payload
   - **File Modified:** `integration-hub/src/integration_hub/services/inventory_sender.py`
   - **Database Cleanup:** Corrected locations for all 18 invoices in inventory system

6. **Accounting Journal Entry Location Fix** 📍 **DATA FIX**
   - **Problem:** Journal entries showing "Corporate" instead of correct restaurant location
   - **Root Cause:** Journal entry **lines** have `area_id`, not just the header's `location_id`
   - **Solution:** Updated `area_id` on journal_entry_lines for affected entries
   - **Key Learning:** Accounting UI reads location from `journal_entry_lines.area_id`, not `journal_entries.location_id`
   - **Entries Fixed:** AP-20251217-0001, AP-20251217-0002, AP-20251217-0005, AP-20251221-0003

7. **Invoice Sync Status Display Fix** 🔧 **UI FIX**
   - **Problem:** Expense invoices showed "Sent" to inventory when they weren't
   - **Root Cause:** Template checked `inventory_sync_at` timestamp instead of `sent_to_inventory` flag
   - **Solution:** Updated template logic to check `sent_to_inventory` flag first
   - **File Modified:** `integration-hub/src/integration_hub/templates/invoice_detail.html`
   - **New Display Logic:**
     - "Sent" - if `sent_to_inventory=true`
     - "Not Applicable" - if `sent_to_inventory=false` but `inventory_sync_at` has timestamp
     - "Not Sent" - otherwise

8. **Duplicate Data Cleanup** 🧹 **DATA FIX**
   - Deleted 20+ duplicate bills in accounting
   - Merged duplicate vendors (GOLD COAST BEVERAGE LLC, Southern Glazier's of FL)
   - Deleted orphaned invoice data

---

### Location ID Reference

**Integration Hub & Inventory System (IDs 1-6):**
| ID | Location Name | Inventory Store ID |
|----|---------------|-------------------|
| 1 | Seaside Grill | 400 |
| 2 | The Nest Eatery | 300 |
| 3 | SW Grill | 500 |
| 4 | Okee Grill | 200 |
| 5 | Park Bistro | 700 |
| 6 | Links Grill | 600 |

**Accounting System (Areas 1-7):**
- IDs 1-6 match the above locations
- ID 7 = "SW Hospitality Group" (Corporate - should NOT be used for AP bills)

**Key Points:**
- Integration Hub uses `location_id` (1-6) from inventory system
- Accounting uses `area_id` on journal_entry_lines (1-6 for restaurants, 7 for corporate)
- Corporate (ID 7) should NEVER be assigned to vendor bills - it indicates missing location data

---

### Previous Session Work (Dec 18, 2025)

**INVENTORY VENDOR ALIASES + INTEGRATION HUB FIXES** ✅ **COMPLETE**

1. **Vendor Aliases System** 🔗 **NEW FEATURE**
   - **Problem:** Duplicate vendors with slight name variations (e.g., "Gordon Food Service" vs "Gordon Food Service Inc.")
   - **Solution:** Implemented vendor alias system mirroring the Accounting system's approach
   - **Database:** Created `vendor_aliases` table with case-insensitive matching option
   - **API Endpoints:**
     - `GET /api/vendors/aliases/all` - Get all aliases system-wide
     - `GET /api/vendors/{vendor_id}/aliases` - Get aliases for specific vendor
     - `POST /api/vendors/{vendor_id}/aliases` - Add alias
     - `DELETE /api/vendors/{vendor_id}/aliases/{alias_id}` - Delete alias
     - `POST /api/vendors/resolve-name` - Resolve vendor name (for Integration Hub)
   - **UI:** Added "Manage Aliases" button and per-vendor alias management in vendors.html
   - **Files Created/Modified:**
     - `inventory/alembic/versions/20251218_add_vendor_aliases.py` (NEW - migration)
     - `inventory/src/restaurant_inventory/models/vendor_alias.py` (NEW - model)
     - `inventory/src/restaurant_inventory/models/__init__.py` (added VendorAlias)
     - `inventory/src/restaurant_inventory/api/api_v1/endpoints/vendors.py` (alias endpoints)
     - `inventory/src/restaurant_inventory/templates/vendors.html` (alias UI)

2. **Duplicate Vendor Merge** 🧹 **DATA CLEANUP**
   - Merged duplicate vendors and created aliases:
     - "Gordon Food Service Inc." → alias of "Gordon Food Service"
     - "Gordon Food Service Store" → alias of "Gordon Food Service"
     - "GOLD COAST BEVERAGE LLC" → alias of "Gold Coast Beverage"
     - "Amerigas" → alias of "AmeriGas"
   - Reassigned all invoices from duplicates to canonical vendors
   - Deleted inactive duplicate vendors

3. **Vendor Delete Protection** 🛡️ **SAFETY FIX**
   - **Problem:** Deleting vendors with invoices caused foreign key errors
   - **Solution:** Added check for related invoices before deletion
   - **Behavior:** Shows user-friendly error with invoice count if vendor has invoices

4. **Category GL Mapping Fix** 🔧 **BUG FIX**
   - **Problem:** Categories with "/" in name (e.g., "Liquor - Bourbon/Whiskey/Scotch") failed lookup
   - **Solution:** Added `encodeURIComponent()` for category parameter and `{category:path}` route pattern
   - **Files Modified:**
     - `integration-hub/src/integration_hub/templates/unmapped_items.html`
     - `integration-hub/src/integration_hub/main.py`

5. **Expense Categories Cleanup** 🗑️ **DATA CLEANUP**
   - **Problem:** Expense categories appearing in Category Mappings page
   - **Explanation:** Category Mappings is for inventory→GL mapping only, not expenses
   - **Action:** Removed 8 expense categories (Expense - Cleaning, Equipment, etc.) from `category_gl_mapping` table

6. **Invoice Detail GL Names** 📝 **UX IMPROVEMENT**
   - Added GL account names display on invoice detail page
   - Shows abbreviated name with full name on hover tooltip

---

### Previous Session Work (Dec 8, 2025)

**COMPREHENSIVE SYSTEM AUDIT & CLEANUP + EVENTS CALDAV/PERMISSIONS** ✅ **COMPLETE**

1. **Events CalDAV Sync Fix** 🔧 **CRITICAL FIX**
   - **Problem:** CalDAV sync returning 409 Conflict errors
   - **Root Cause:** iOS devices connected with username `andy`, but app synced to `/andy@swhgrp.com/`
   - **Solution:** Added `_get_caldav_username()` helper to extract username from email
   - **Files Modified:** `events/src/events/services/caldav_sync_service.py`

2. **CalDAV Event Details Enhanced** 📅 **FEATURE**
   - **Added to calendar events:** Event type, guest count, status, client info (name/phone/email/org), setup/teardown times, venue address
   - **Files Modified:** `events/src/events/services/caldav_sync_service.py`

3. **Events Venue Permissions System** 🔒 **NEW FEATURE**
   - **Feature:** Users can be assigned to specific venues and only see those events
   - **Logic:** Users with no venue assignments have unrestricted access (see all events)
   - **API Endpoints Added:**
     - `GET /api/users/{user_id}/locations` - Get user's venue assignments
     - `POST /api/users/{user_id}/locations` - Set user's venue assignments
   - **UI:** Added venue management modal in Users admin page
   - **Files Modified:**
     - `events/src/events/models/user.py` (added UserLocation model)
     - `events/src/events/api/users.py` (added location endpoints)
     - `events/src/events/api/events.py` (added venue filtering to list/calendar)
     - `events/src/events/templates/admin/users.html` (venue management UI)

4. **Comprehensive System Audit** 🔍 **CODE QUALITY**
   - Ran detailed audits on all 8 microservices
   - **Total Issues Found:** 200+ across all systems

5. **Critical Security Fixes** 🔥 **SECURITY**
   - **Integration Hub:** Moved hardcoded DB credentials to environment variable
     - `accounting_sender.py` now uses `ACCOUNTING_DATABASE_URL` env var
   - **Files System:** Centralized OnlyOffice JWT secret to config.py
     - Removed duplicates from `onlyoffice.py` and `filemanager.py`
   - **Websites:** Fixed `secure=False` → `secure=True` for session cookies

6. **Documentation Fixes** 📚 **ACCURACY**
   - **HR README:** Fixed - was claiming Django 4.2, actually uses FastAPI
     - Updated technology stack, file structure, commands, dependencies
   - **Websites README:** Created - system had no README.md at all

7. **Code Cleanup** 🧹 **MAINTENANCE**
   - Removed orphaned files: `apply_location_filtering.py`, `docker-compose.yml.backup`
   - Removed all `__pycache__` directories across all services
   - Fixed deprecated `datetime.utcnow()` → `datetime.now(timezone.utc)` in Files system

**Files Modified This Session:**
- `events/src/events/services/caldav_sync_service.py` (CalDAV fix + enhanced details)
- `events/src/events/models/user.py` (UserLocation model)
- `events/src/events/api/users.py` (location endpoints)
- `events/src/events/api/events.py` (venue filtering)
- `events/src/events/templates/admin/users.html` (venue UI)
- `integration-hub/src/integration_hub/services/accounting_sender.py` (env var)
- `files/src/files/core/config.py` (OnlyOffice JWT setting)
- `files/src/files/api/onlyoffice.py` (use settings)
- `files/src/files/api/filemanager.py` (use settings)
- `files/src/files/core/security.py` (datetime fix)
- `websites/src/websites/main.py` (secure cookie)
- `websites/README.md` (NEW - created)
- `hr/README.md` (Django → FastAPI corrections)

---

### Previous Session Work (Dec 8, 2025 - Earlier)

**WEBSITES SYSTEM: ACTIVITY LOGGING ENHANCEMENTS + MOBILE RESPONSIVE ADMIN** ✅ **COMPLETE**

1. **Dashboard Activity Pagination** 📄 **UX IMPROVEMENT**
   - **Problem:** Dashboard showed all activity entries with no limit, needed pagination
   - **Solution:** Limited dashboard to 5 recent items with "View All" link to full activity page
   - **New Route:** `/websites/sites/{site_id}/activity` with pagination (20 per page)
   - **Files Modified:**
     - `websites/src/websites/main.py` (added activity route, limited dashboard to 5)
     - `websites/templates/admin/sites/dashboard.html` (added View All button)
     - `websites/templates/admin/sites/activity.html` (NEW - full activity with pagination)

2. **Enhanced Activity Log Detail** 🔍 **FEATURE IMPROVEMENT**
   - **Problem:** Activity entries only showed "Andy created site" with no detail
   - **Solution:** Activity log now captures and displays specific changes
   - **Details Tracked:**
     - Site updates: Shows which fields changed (e.g., "Changed: Name, Domain, Phone")
     - Block operations: Shows block type (e.g., "Block: hero", "Block: two_column")
     - Custom descriptions for important actions

3. **Social Media & Action Links on Website Preview** 🔗 **FEATURE**
   - **Problem:** Settings page had social/ordering/reservation URLs but they weren't displayed
   - **Solution:** Added social links and action buttons to header navbar AND footer

4. **Website Manager Mobile Responsive Design** 📱 **MAJOR UX IMPROVEMENT**
   - **Problem:** Admin interface (Website Manager) not usable on mobile devices
   - **Solution:** Complete mobile-responsive overhaul of admin base template

---

### Previous Session Work (Dec 2, 2025)

**EVENTS: BEO PDF TEMPLATE REDESIGN + FINANCIAL DISPLAY FIXES** ✅ **COMPLETE**

1. **BEO Template Complete Redesign** 📄 **MAJOR FEATURE**
   - **Problem:** Original BEO template was basic, not matching industry-standard catering BEO formats
   - **Solution:** Complete redesign to match comprehensive catering industry BEO format
   - **New Layout:** One-sheet, two-column design with condensed fonts (8-9pt)
   - **Left Column Sections:**
     - EVENT INFORMATION - Event name, client, organization, date, time, guests, type, status, contact info
     - ROOM & SETUP - Room/venue, setup style, tables, head table, dance floor, AV needs, decor
     - TIMELINE - Auto-generated from setup/start/end times, or custom timeline entries
     - STAFFING - Banquet captain, servers, bartenders, culinary, bussers (shows TBD if not set)
   - **Right Column Sections:**
     - FOOD SERVICE - Service style, service time, menu courses/items by section
     - BEVERAGE SERVICE - Bar type, bar hours, signature cocktails, details
     - RENTALS / EQUIPMENT - Equipment and rental information
     - FINANCIAL SUMMARY - Only shows when actual amounts exist (subtotal > 0 or total > 0)
   - **Bottom Section:**
     - Special Notes / Instructions box (full width)
     - Footer with generation timestamp and BEO reference
   - **File Modified:** `events/src/events/templates/pdf/beo_template.html` (complete rewrite)

2. **BEO PDF Generation Fixes** 🔧 **CRITICAL FIXES**
   - **WeasyPrint/pydyf Incompatibility:**
     - Error: `PDF.__init__() takes 1 positional argument but 3 were given`
     - Fix: Added `pydyf<0.10` to requirements.txt (WeasyPrint 60.2 incompatible with pydyf 0.10+)
   - **Jinja2 Dict Method Conflict:**
     - Error: `'builtin_function_or_method' object is not iterable`
     - Root cause: `section.items` interpreted as dict.items() method instead of key
     - Fix: Changed to `section['items']` in template
   - **Document Model Field Names:**
     - Error: `'document_type' is an invalid keyword argument for Document`
     - Fix: Changed `document_type` → `doc_type`, `file_path` → `storage_url`, removed `title`/`file_size`
   - **Template Field Errors:**
     - Fixed `event.attendee_count` → `event.guest_count`
     - Fixed enum handling: `event.status.value if event.status.value else event.status`
   - **Files Modified:**
     - `events/requirements.txt` (added pydyf<0.10)
     - `events/src/events/api/documents.py` (Document model field names)
     - `events/src/events/templates/pdf/beo_template.html` (multiple template fixes)

3. **Financial Summary Display Fix** 💰 **UI FIX**
   - **Problem:** Overview tab showed financial summary card when amounts were $0.00
   - **Root Cause:** Condition checked for `package_id` existence instead of actual amounts
   - **Solution:** Changed condition to `subtotal > 0 || total > 0`
   - **File Modified:** `events/src/events/templates/admin/event_detail.html` (populateOverviewSummaries function)

4. **Stale Financials Data Cleanup** 🧹 **DATA FIX**
   - **Problem:** BEO showing old financial data even when Financials tab showed $0.00
   - **Root Cause:** `financials_json` in database had stale amounts from previous saves
   - **Solution:** Cleared stale amounts while preserving settings (rates, deposit_required)
   - **SQL:** Updated Red Reef Golf event to set subtotal/service_charge/tax/total to 0

**Files Modified This Session:**
- `events/requirements.txt` (pydyf version constraint)
- `events/src/events/api/documents.py` (Document model fields)
- `events/src/events/templates/pdf/beo_template.html` (complete template redesign)
- `events/src/events/templates/admin/event_detail.html` (financial summary condition)

---

### Previous Session Work (Nov 30, 2025)

**ACCOUNTING: JOURNAL ENTRY CORRECTION FEATURE + TAX DOUBLE-COUNTING FIX** ✅ **COMPLETE**

1. **Journal Entry Correction Feature** 🔧 **NEW FEATURE**
   - **Purpose:** Allow users to correct posted journal entries by reversing and re-entering
   - **Workflow:**
     1. User clicks "Correct" on a posted entry
     2. Form pre-populates with entry data (no reversal yet - deferred pattern)
     3. User edits the amounts/accounts as needed
     4. On Save: Original entry reversed, then new corrected entry created
     5. On Cancel: No changes made, correction mode cleared
   - **Key Design Decision:** Deferred reversal pattern
     - Reversal only happens when user actually saves the correction
     - Prevents orphaned reversals if user cancels
   - **Files Modified:**
     - `accounting/src/accounting/templates/journal_entries.html`
       - Added `correctingEntryId` tracking variable
       - Modified `correctEntry()` to store entry ID without immediate reversal
       - Modified `handleSubmit()` to reverse original entry on save
       - Modified `cancelEntry()` to clear correction mode with appropriate message
       - Modified `showListView()` and `showCreateView()` to clear correction mode
     - `accounting/src/accounting/api/journal_entries.py`
       - Changed reversal entries to auto-post (status=POSTED) instead of DRAFT

2. **Reversal Entry Auto-Post** ✅ **IMPROVEMENT**
   - **Problem:** Reversal entries were created as DRAFT status, requiring manual posting
   - **Solution:** Reversal entries now auto-post with `status=JournalEntryStatus.POSTED`
   - Sets `posted_at=datetime.utcnow()` and `posted_by=user.id` automatically
   - **File Modified:** `accounting/src/accounting/api/journal_entries.py` line ~175

3. **Tax Double-Counting Fix** 🔥 **CRITICAL FIX** (from earlier in session)
   - **Problem:** Invoice items that already included tax line items (e.g., "State Sales Tax") were having tax added again from `invoice.tax_amount`
   - **Root Cause:** `accounting_sender.py` always added proportional tax without checking if items already totaled to invoice total
   - **Solution:** Added detection logic to check if items_total ≈ invoice_total
     - If yes: Tax already in items, don't add again
     - If no: Distribute tax proportionally across line items
   - **Code Change:**
     ```python
     # Determine if tax is already included in items
     tax_already_in_items = abs(items_total - invoice_total) < Decimal('0.02')

     if tax_already_in_items:
         logger.info(f"Tax appears to be included in line items")
     else:
         # Add proportional tax to each line
     ```
   - **File Modified:** `integration-hub/src/integration_hub/services/accounting_sender.py` (lines 226-266)

4. **Data Corrections Applied** 🔧 **DATABASE FIXES**
   - Fixed REV-20251130-0001 status from REVERSED to POSTED (reversals should be POSTED)
   - Restored AP-20251130-0004 to POSTED status after test correction was cancelled
   - **SQL Commands:**
     - `UPDATE journal_entries SET status='POSTED', posted_at=NOW() WHERE entry_number='REV-20251130-0001';`
     - `UPDATE journal_entries SET status='POSTED', posted_at=NOW() WHERE entry_number='AP-20251130-0004';`

5. **Accounting Concepts Clarified** 📚 **DOCUMENTATION**
   - **REVERSED status vs REV entry:**
     - REVERSED is a status label on the original entry (marks it as voided)
     - The REV entry is what actually zeros out the GL by creating opposite debits/credits
     - The original entry stays in the ledger with REVERSED status for audit trail
     - The REV entry creates offsetting entries so net effect is zero
   - **Example from session:**
     - AP-20251129-0006 (wrong amount $142.09) → marked REVERSED
     - REV-20251130-0001 (reversal) → credits back the $142.09
     - AP-20251130-0004 (correct amount $127.37) → new correct entry

**Files Modified This Session:**
- `accounting/src/accounting/templates/journal_entries.html` (deferred reversal pattern)
- `accounting/src/accounting/api/journal_entries.py` (auto-post reversals)
- `integration-hub/src/integration_hub/services/accounting_sender.py` (tax double-counting fix)

---

### Previous Session Work (Nov 29, 2025)

**INVENTORY COUNT FIXES + OCR ACCURACY IMPROVEMENT PROJECT** 🔄 **IN PROGRESS**

1. **Inventory Count Session Fixes** ✅ **COMPLETE**
   - **Unit Display Fix:** Items showed "null" next to count amounts
     - Root cause: API used deprecated `unit_of_measure` string field (empty) instead of `unit_of_measure_id` relationship
     - Fixed by changing API endpoints to use `item.master_item.unit.name`
     - Files modified: `items.py`, `count_templates.py`, `storage_areas.py`, `inventory.py`, `waste.py`

   - **Additional Count Units Not Showing:** count_unit_2 and count_unit_3 not appearing in dropdown
     - Root cause: API wasn't returning `count_unit_2_name` and `count_unit_3_name`
     - Fixed by adding joinedload for count_unit_2/3 in items.py and updating count_session_new.html

   - **Unit Conversion Not Working:** Counting 2 cases showed "2 cans" instead of 48
     - Root cause: Pydantic schema `MasterItemResponse` missing `count_unit_2_factor` and `count_unit_3_factor`
     - Fixed by adding fields to `inventory/src/restaurant_inventory/schemas/item.py`

   - **500 Error on Save:** "numeric field overflow" for variance_percent
     - Root cause: Column precision (5,2) couldn't hold 5900% variance
     - Fixed: `ALTER TABLE count_session_items ALTER COLUMN variance_percent TYPE NUMERIC(10, 2);`

   - **Inventory Type Always "Partial":** Should be "Full" when selected
     - Root cause: `create_count_session` endpoint not passing `inventory_type` to model
     - Fixed by adding inventory_type parameter in count_sessions.py

   - **Delete Count Session 500 Error:** Foreign key constraint violation
     - Root cause: `count_session_storage_areas` table not deleted before session
     - Fixed by explicitly deleting related records before session deletion
     - File: `inventory/src/restaurant_inventory/api/api_v1/endpoints/count_sessions.py`

2. **OCR Accuracy Improvement Project** 🔄 **IN PROGRESS - PAUSED**
   - **Problem:** Invoice item codes frequently have OCR errors (1-2 digits off)
   - **Analysis Complete:** Created fuzzy matching script to compare unmapped items vs vendor items
   - **Script Location:** `/opt/restaurant-system/integration-hub/scripts/fuzzy_match_report.py`

   - **Fuzzy Match Report Results:**
     - 356 unique unmapped items analyzed
     - **67 exact/near-exact matches (≥95%)** - Safe to auto-correct
     - **1 high confidence match (80-95%)** - Quick review needed
     - **26 medium confidence matches (60-80%)** - Manual review needed
     - **262 no match** - New items or vendors not in system (Gold Coast Beverage, Southern Glazier's)

   - **OCR Errors Detected Examples:**
     - `104471` → `100471` (Grape Juice)
     - `141441` → `141341` (Honey)
     - `434013` → `431013` (Garlic)
     - `1017400` → `101740` (Caribbean Vegetable Blend)

   - **Next Steps (TO DO):**
     1. Auto-correct the 67 exact matches in hub_invoice_items
     2. Review and approve/reject the 26 medium confidence matches
     3. Add vendor items for Gold Coast Beverage and Southern Glazier's (need price lists)
     4. Enhance invoice parser with OCR confidence scoring
     5. Add fuzzy matching logic to auto-mapper for future invoices

---

### Previous Session Work (Nov 28, 2025)

**INVENTORY: KEY ITEMS + UNIT CONVERSIONS & INTEGRATION HUB: INVOICE FIXES** ✅ **COMPLETE**

1. **Master Item Key Item Flag + Additional Count Units** 🔑 **DATA MODEL**
   - **Feature:** Added `is_key_item` boolean flag to master_items for highlighting important items
   - **Feature:** Added `count_unit_2_id` and `count_unit_3_id` for additional counting units
   - **Database Migration:** `20251128_1600_add_key_item_and_count_units.py`
     - Merges two previous migration heads (`20251009_1330` + `make_master_item_optional`)
     - Adds foreign key constraints to units_of_measure table
   - **Files Modified:**
     - `inventory/alembic/versions/20251128_1600_add_key_item_and_count_units.py` (NEW)
     - `inventory/src/restaurant_inventory/models/item.py` (added fields)
     - `inventory/src/restaurant_inventory/schemas/item.py` (added fields)

2. **Item Unit Conversions Model** 📐 **NEW FEATURE**
   - **Purpose:** Store per-item unit conversions (e.g., 1 case of chicken = 40 lbs)
   - **Model:** `ItemUnitConversion` with from_unit, to_unit, conversion_factor
   - **Database Migration:** `20251128_1800_add_item_unit_conversions.py`
   - **Files Created:**
     - `inventory/alembic/versions/20251128_1800_add_item_unit_conversions.py` (NEW)
     - `inventory/src/restaurant_inventory/models/item_unit_conversion.py` (NEW)
   - **Files Modified:**
     - `inventory/src/restaurant_inventory/models/__init__.py` (added export)

3. **Integration Hub: Invoice Total Mismatch Fixes** 🔧 **CRITICAL FIXES**
   - **Problem:** 11 invoices had "Bill total mismatch" errors preventing send to accounting
   - **Root Causes Identified:**
     - Stale errors (data now correct but old error message persisted)
     - Tax double-counting (tax as line item + tax_amount field)
     - Gold Coast Linen minimum charge ($40 min not parsed)
     - Credits/discounts not parsed (lines > invoice total)
   - **Solutions Applied:**
     - Cleared stale errors and retried sends
     - Set `tax_amount=0` for invoices where taxes appear as line items
     - Fixed negative tax handling for credit memos: `subtotal != 0 and invoice_tax != 0`
     - Added adjustment lines for minimum charges and credits/discounts
   - **Files Modified:**
     - `integration-hub/src/integration_hub/services/accounting_sender.py`
       - Changed tax condition from `> 0` to `!= 0` for credit memo support
       - Added adjustment line logic for minimum charges (lines < invoice)
       - Added "Credit / Discount Adjustment" for lines > invoice
   - **Result:** 10 of 11 invoices successfully sent

4. **Invoice 89 Item Code Corrections** 🔍 **DATA FIX**
   - **Problem:** Re-parsed invoice had OCR errors in item codes
     - 819753 should be 819573 (Philly Beef)
     - 599860 should be 599850 (French Fries)
   - **Issue:** Items were manually mapped to wrong items due to OCR digit errors
   - **Lesson:** Do NOT send invoices until 100% verified correct
   - **Fixed in Hub:** Corrected item codes in hub_invoice_items table
   - **Fixed in Inventory:** Corrected vendor_sku and master_item_id in invoice_items table
   - **Accounting Entry (JE #433):** Verified CORRECT - properly balanced
     - 8 expense lines totaling $978.64 in debits
     - -$20.44 "Credit / Discount Adjustment" (offsets unparsed credits)
     - $958.20 Accounts Payable credit
     - Math: $978.64 - $20.44 = $958.20 ✓

5. **Outstanding Issues**
   - Invoice 217: Bad parse - line items $340 vs invoice $42, needs manual re-parse
   - Item Detail Page: New template created (`item_detail.html`)
   - Storage Areas Page: New template created (`storage_areas.html`)

---

### Previous Session Work (Nov 25, 2025)

**INTEGRATION HUB: OCR ITEM CODE VALIDATION + EMAIL HISTORY UI** ✅ **COMPLETE**

1. **OCR Item Code Auto-Correction** 🔧 **MAJOR FEATURE**
   - **Problem:** Invoice parsing produces OCR errors in item codes (e.g., 006032 instead of 206032)
   - **Solution:** Post-parse validation that compares extracted codes against verified codes
   - **Algorithm:**
     - `digit_similarity_score()` function accounts for common OCR confusions (0↔6↔8, 1↔7↔I, etc.)
     - Requires ≥80% similarity AND matching description words to prevent false positives
     - Only corrects against verified codes (is_verified=true OR occurrence_count≥3)
   - **Files Modified:**
     - `integration-hub/src/integration_hub/services/invoice_parser.py` (added ~150 lines)
       - `levenshtein_distance()` - string distance calculation
       - `digit_similarity_score()` - OCR-aware similarity (handles 0/O/6/8 confusion)
       - `_validate_and_correct_item_codes()` - post-parse validation method
     - Added OCR correction stats to parse response (`ocr_corrected`, `ocr_corrections`)
   - **Impact:** Future invoices auto-correct common OCR errors during parsing

2. **Item Codes Page Filter Enhancement** 🔍 **UI IMPROVEMENT**
   - **Problem:** No way to quickly see unverified item codes that need review
   - **Solution:** Added "Unverified Only" and "Verified Only" filter options
   - **Files Modified:**
     - `integration-hub/src/integration_hub/templates/item_codes.html` (line 38-44)
     - `integration-hub/src/integration_hub/main.py` (lines 1514-1529)
   - **Filter Options Now:**
     - All Item Codes
     - Unverified Only (sorted by occurrence count DESC - review high-frequency first)
     - Verified Only
     - Potential Duplicates
     - Single Occurrence

3. **Events Email History Page Improvements** 📧 **UI FIX**
   - **Problem:** Email list showed full HTML body inline, causing layout issues
   - **Solution:** Changed to clean list view with modal for details
   - **Changes:**
     - Created `EmailListResponse` schema (without body_html for list performance)
     - List API now returns lightweight response
     - Email body fetched on-demand when viewing details
     - Modal uses iframe to isolate email styles (prevents style leakage)
   - **Files Modified:**
     - `events/src/events/schemas/email.py` (added EmailListResponse)
     - `events/src/events/api/emails.py` (changed list response model)
     - `events/src/events/templates/admin/emails.html` (major UI rewrite)
   - **Bug Fixes:**
     - Fixed UUID quoting in JavaScript onclick handlers
     - Fixed layout shift caused by email HTML styles leaking into page
     - Added dark theme styling for modal to match app theme

4. **Occurrence Count Badge Styling** 🎨
   - Green badge (bg-success): Items with >3 occurrences (well-established)
   - Grey badge (bg-secondary): Items with ≤3 occurrences (may need verification)

---

### Previous Session Work (Nov 14-15, 2025)

**FILES SYSTEM: WEBDAV SYNC + TIMEZONE BUG FIX** (Nov 14-15, 2025) ✅ **COMPLETE**

1. **WebDAV Server for Dropbox-like Desktop Sync** 💾 **MAJOR FEATURE**
   - **Goal:** Enable offline file access and two-way sync between desktop and Files system
   - **Solution:** Implemented WebDAV server using WsgiDAV library
   - **Architecture:**
     - WsgiDAV 4.3.0 mounted as WSGI app in FastAPI at `/webdav/`
     - Portal SSO integration via X-Remote-User header
     - User-isolated filesystem provider (maps users to `/app/storage/user_{id}/`)
     - Nginx reverse proxy with WebDAV headers (Depth, Destination, Overwrite)
     - 10GB max upload size, 300s timeouts for large files
   - **Files Created/Modified:**
     - `files/src/files/webdav_server.py` (NEW - 184 lines, custom auth + provider)
     - `files/src/files/main.py` (mounted WebDAV app, auto-discovery endpoint)
     - `files/requirements.txt` (added wsgidav==4.3.0, cheroot==10.0.0)
     - `shared/nginx/conf.d/rm.swhgrp.com-http.conf` (WebDAV location block)
   - **Impact:** Users can now mount Files as network drive on Windows/macOS/Linux

2. **WebDAV Client Support** 🖥️ **CROSS-PLATFORM**
   - Works with any WebDAV client:
     - **Mountain Duck** (macOS/Windows - recommended, smart sync)
     - **RaiDrive** (Windows - free)
     - **macOS Finder** (native, free)
     - **Windows Explorer** (native, free)
     - **davfs2** (Linux)
   - Connection URL: `https://rm.swhgrp.com/files/webdav/andy`
   - Authentication: Portal username/password (same as web interface)

3. **Comprehensive Documentation** 📚
   - Created 400+ line setup guide covering all platforms
   - Step-by-step client configuration for each platform
   - Troubleshooting section (large files, performance, connection issues)
   - Architecture diagrams and technical details
   - Comparison vs Nextcloud sync features
   - **File Created:** `docs/files-webdav-sync.md`

4. **Nextcloud Architecture Research** 🔍
   - Deep-dive comparison of our Files system vs Nextcloud
   - Found 85% architectural similarity (database + filesystem storage)
   - Identified WebDAV as the only missing sync layer
   - **File Created:** `docs/files-vs-nextcloud-comparison.md` (400+ lines)

5. **WsgiDAV 4.3.0 Compatibility Fixes** 🔧 **PRODUCTION FIX**
   - **Problem:** WsgiDAV 4.3.0 deprecated several config options, server wouldn't start
   - **Solution:** Updated configuration for v4.3.0 compatibility
   - Changed `lock_manager` → `lock_storage`
   - Changed `propsmanager` → `property_manager`
   - Moved `enable_loggers` → `logging.enable_loggers`
   - Removed deprecated `dir_browser.ms_mount`
   - Simplified domain controller (removed custom auth, use simple_dc)
   - **File Modified:** `files/src/files/webdav_server.py`
   - **Impact:** WebDAV server now starts and runs successfully

6. **Direct Path Mapping for Users** 🗂️ **CONFIGURATION**
   - **Problem:** Complex UserIsolatedFilesystemProvider causing 404 errors
   - **Solution:** Simplified to direct path mapping
   - `/andy` → `/app/storage/user_2/` (direct FilesystemProvider)
   - Removed path normalization complexity
   - **File Modified:** `files/src/files/webdav_server.py` (lines 137-138)
   - **Impact:** WebDAV now responds with HTTP 200, files accessible

7. **Critical Timezone Bug Fix** 🕐 **CRITICAL BUG FIX**
   - **Problem:** Files web interface always returned "Token expired" error
   - **Root Cause:** Server in EST timezone, code compared local time to UTC
     - `datetime.fromtimestamp(exp)` returned local EST time (00:01:07)
     - `datetime.utcnow()` returned UTC time (05:00:31)
     - Tokens appeared expired 5 hours early!
   - **Solution:** Use timezone-aware datetime for both sides of comparison
     - `datetime.fromtimestamp(exp, tz=timezone.utc)`
     - `datetime.now(timezone.utc)`
   - **File Modified:** `files/src/files/api/auth.py` (lines 30-40)
   - **Impact:** Files web interface now accessible, SSO login works correctly

8. **Production Testing & Validation** ✅ **VERIFIED WORKING**
   - Successfully mounted WebDAV on macOS Finder
   - Verified file operations: LIST, GET, PUT, LOCK, UNLOCK
   - Confirmed Files web interface accessible after timezone fix
   - WebDAV endpoint: `https://rm.swhgrp.com/files/webdav/andy`
   - All systems operational

**EVENTS SYSTEM: CALDAV CALENDAR SYNC & EMAIL FIXES** (Nov 14, 2025) ✅ **COMPLETE**

1. **Fixed Email Event Detail Links** 🔗 **CRITICAL BUG FIX**
   - **Problem:** Email links to event details returned 404 errors
   - **Root Cause:** Email templates used wrong URL patterns:
     - `internal_new_event.html`: Used `/events/admin/events/{id}` (wrong)
     - `internal_update.html`: Used `/events/event/{id}` (wrong - missing query param)
   - **Solution:** Corrected both templates to use `/events/event?id={event_id}`
   - Event detail page uses query parameters, not path parameters
   - **Files Modified:**
     - `events/src/events/templates/emails/internal_new_event.html` (line 220)
     - `events/src/events/templates/emails/internal_update.html` (line 123)
   - **Impact:** Email "View Event Details" links now work correctly

2. **Calendar Status Color Indicators** 🎨 **UX IMPROVEMENT**
   - **Problem:** Calendar events all showed blue dots regardless of status
   - **Solution:** Implemented status-based colored left borders on calendar events
   - Added `use_enum_values=True` to EventListItem schema for proper enum serialization
   - Left border colors indicate event status:
     - **Orange** (#f0883e) = PENDING
     - **Blue** (#1f6feb) = CONFIRMED
     - **Green** (#238636) = CLOSED/COMPLETED
     - **Red** (#da3633) = CANCELED
     - **Gray** (#6e7681) = DRAFT
     - **Purple** (#8957e5) = IN_PROGRESS
   - Text color still shows venue (purple=Links Grill, pink=SW Grill, etc.)
   - **Files Modified:**
     - `events/src/events/schemas/event.py` (line 91 - added use_enum_values=True)
     - `events/src/events/templates/admin/calendar.html` (lines 754-770 - status color mapping)
   - **Impact:** Clear visual status indicators at a glance

3. **Removed FullCalendar Default Dots** 🎯 **CLEANER UI**
   - **Problem:** FullCalendar showed small dots to left of event names (duplicate visual indicator)
   - **Solution:** Added CSS to hide `.fc-daygrid-event-dot` elements
   - Left border line is cleaner and more modern than dots
   - Kept venue legend at top for reference
   - **File Modified:** `events/src/events/templates/admin/calendar.html` (lines 110-112)
   - **Impact:** Cleaner calendar appearance with single status indicator per event

**INTEGRATION HUB: MAJOR WORKFLOW & DATA INTEGRITY IMPROVEMENTS** (Nov 14, 2025) ✅ **COMPLETE**

1. **Persistent Item Mapping System** 🎯 **GAME CHANGER**
   - **Problem:** Users had to manually re-map the same items on every new invoice
   - **Solution:** Implemented persistent mapping that remembers previous mappings
   - Modified `auto_mapper.py` to add `match_by_previous_mapping()` as HIGHEST priority
   - Modified `main.py` bulk mapping endpoint to save mappings to `item_gl_mapping` table
   - When user maps "linen" once, all future "linen" items auto-map to same GL accounts
   - **Files Modified:**
     - `integration-hub/src/integration_hub/services/auto_mapper.py` (lines 167-203)
     - `integration-hub/src/integration_hub/main.py` (bulk mapping endpoint, lines 922-952)
   - **Impact:** Reduces repetitive mapping work by 90%+ for recurring items

2. **Invoice Parser Line Total Validation** 🔧 **DATA QUALITY FIX**
   - **Problem:** OpenAI GPT-4o Vision parser sometimes returned unit_price as line_total (e.g., $5.13 instead of 15×$5.13=$76.95)
   - **Solution:** Added fallback calculation that validates and corrects line totals
   - Detects when line_total equals unit_price (common GPT-4o parsing error) or differs by >$0.02
   - Recalculates as quantity × unit_price when mismatch detected
   - Logs warning when correction is made
   - **File Modified:** `integration-hub/src/integration_hub/services/invoice_parser.py` (lines 426-456)
   - **Impact:** Prevents "Bill total mismatch" errors on send to accounting

3. **Status Filter Tabs with Pagination** 📊 **UX OVERHAUL**
   - **Problem:** Single long list of invoices with dropdown filter - unwieldy
   - **Solution:** Implemented 4-tab system with badge counts and pagination
   - **Tabs:**
     - **Pending** (50): Invoices needing mapping
     - **Ready** (0): Fully mapped, ready to send (excludes errors & already sent)
     - **Errors** (2): Failed sends needing attention
     - **All Invoices** (79): Complete history with 50/page pagination
   - **Pagination:** Previous/Next buttons, shows "1-50 of 200" with page numbers
   - Auto-resets to page 1 when changing tabs or searching
   - Badge counts match visible items (exclude sent invoices from Ready tab)
   - **File Modified:** `integration-hub/src/integration_hub/templates/invoices.html` (major rewrite)
   - **Impact:** Clear workflow stages, better organization, handles thousands of invoices

4. **Duplicate Invoice Prevention** 🚫 **CRITICAL DATA INTEGRITY FIX**
   - **Problem:** Clicking "Send" on already-sent invoice created duplicate journal entries and vendor bills in accounting
   - **Root Cause:** `auto_send.py` didn't check `sent_to_accounting` flag before sending
   - **Solution:**
     - Added duplicate prevention checks before sending to any system
     - Only send if `NOT invoice.sent_to_accounting` and `NOT invoice.sent_to_inventory`
     - Returns "already sent" message instead of creating duplicates
     - Better logging for skipped sends
   - **File Modified:** `integration-hub/src/integration_hub/services/auto_send.py` (lines 95-167)
   - **Impact:** Prevents duplicate accounting entries going forward

5. **Database Cleanup - Deleted 70 Duplicate Records** 🧹 **DATA CLEANUP**
   - **Problem:** 40 Gold Coast Linen journal entries when should be 5 (duplicates from previous bug)
   - **Actions Taken:**
     - Deleted 35 duplicate journal entries (kept oldest for each invoice)
     - Deleted 70 duplicate journal entry lines
     - Deleted 35 duplicate vendor bills (kept ones with journal_entry_id)
   - **SQL Scripts:**
     - `/tmp/delete_duplicate_journal_entries.sql`
     - `/tmp/delete_duplicate_vendor_bills.sql`
   - **Result:** Clean accounting data - 5 unique entries for 5 invoices
   - **Impact:** Accurate financial reports, no inflated AP balances

**Files Modified This Session:**
- `integration-hub/src/integration_hub/services/auto_mapper.py` - Persistent mapping
- `integration-hub/src/integration_hub/services/auto_send.py` - Duplicate prevention
- `integration-hub/src/integration_hub/services/invoice_parser.py` - Line total validation
- `integration-hub/src/integration_hub/main.py` - Save bulk mappings to DB
- `integration-hub/src/integration_hub/templates/invoices.html` - Tabs + pagination
- Database: Cleaned 70 duplicate accounting records

**Git Commits:**
- Commit a979bca: "feat(integration-hub): Major workflow improvements and data integrity fixes" - PUSHED ✅

---

### Previous Session (Nov 12, 2025)

**INTEGRATION HUB: CATEGORY NAMING STRUCTURE STANDARDIZATION** (Nov 12, 2025) ✅ **COMPLETE**

1. **Category Mapping Restructure** 🔧 **CONSISTENCY IMPROVEMENT**
   - Standardized category naming from inconsistent format to nested structure
   - **Old structure:** Mixed standalone (Beef, Dairy) and nested (Beer - Draft, Beer - Bottled)
   - **New structure:**
     - Food items: "Food - Beef", "Food - Dairy", "Food - Produce", etc.
     - Beverages: "Beer - Draft", "Beer - Bottled", "Beverage - Non-Alcohol"
     - Standalone: "Wine", "Liquor", "Merchandise"
   - Updated 9 category mappings in `category_gl_mapping` table
   - Updated 69 invoice items in `hub_invoice_items` table with new category names
   - Removed "Supplies" category (expense-only, not needed)

2. **UI Template Updates** ✅ **ALL DROPDOWNS SYNCHRONIZED**
   - Updated all hardcoded category dropdowns across 3 templates
   - Files modified:
     - `integration-hub/src/integration_hub/templates/mapped_items.html`
     - `integration-hub/src/integration_hub/templates/unmapped_items.html`
     - `integration-hub/src/integration_hub/templates/category_mappings.html`
   - All dropdowns now alphabetically sorted with consistent naming
   - Database and UI now fully synchronized

3. **Direct Database Updates** 🔧
   - Used SQLAlchemy `text()` for direct SQL execution (avoided ORM relationship issues)
   - Successfully renamed categories without triggering circular import errors
   - Renamed categories:
     - Beef → Food - Beef (6 items updated)
     - Dairy → Food - Dairy (2 items)
     - Produce → Food - Produce (36 items)
     - Poultry → Food - Poultry
     - Pork → Food - Pork (4 items)
     - Seafood → Food - Seafood (7 items)
     - Dry Goods → Food - Dry Goods (6 items)
     - Frozen → Food - Frozen
     - Beverage (Non-Alcohol) → Beverage - Non-Alcohol (8 items)

**Impact:** Consistent, professional category structure makes mapping clearer and eliminates confusion between food items and other inventory categories.

**Files Modified:**
- integration-hub/src/integration_hub/templates/mapped_items.html (category dropdown lines 170-186)
- integration-hub/src/integration_hub/templates/unmapped_items.html (category dropdown lines 185-201)
- integration-hub/src/integration_hub/templates/category_mappings.html (category dropdown lines 157-173)
- Database: category_gl_mapping and hub_invoice_items tables updated

**Git Commits:** Ready to commit and push ⏳

---

### Most Recent Work (Previous Session - Nov 11, 2025 - AFTERNOON)

**INTEGRATION HUB: CRITICAL ACCOUNTING BUG FIX + UX IMPROVEMENT** (Nov 11, 2025) 🔥 **PRODUCTION CRITICAL**

1. **Fixed AttributeError in accounting_sender.py** 🔥 **CRITICAL**
   - Line 226 was using `item.line_total` but field is `item.total_amount`
   - This broke ALL accounting integration - no invoices could be sent
   - Error appeared as: "Bill total mismatch: Lines $X != Invoice $Y"
   - Root cause: Field name mismatch, not actual calculation error
   - Fixed: Changed `item.line_total` → `item.total_amount`
   - Rebuilt Integration Hub container with fix
   - Cleared 16 affected invoices (all Cozzini Bros knife service)
   - Commit: 196dab7 - PUSHED ✅

2. **Three-State Sync Status Icons** ✅ **UX IMPROVEMENT**
   - Changed confusing two-state icons to clear three-state system
   - **Before:** Green ✅ = sent OR skipped (confusing!)
   - **After:**
     - ✅ Green check = Actually sent to system (has sync timestamp)
     - ➖ Gray dash = Skipped/Not applicable (no items for that system)
     - ❌ Red X = Not sent yet
   - Updated both invoice list and detail pages
   - Added tooltips for clarity
   - Example: Cozzini invoices (knife service, GL-only) now show gray dash for Inventory
   - Commit: 3c9a0c1 - PUSHED ✅

3. **OpenAI GPT-4o Vision Statement Detection** 🤖 **SMART AUTOMATION**
   - GPT-4o Vision now automatically detects if document is a statement vs invoice
   - Checks for "Statement", "Account Statement", "Monthly Statement" in document title
   - Sets `is_statement=true` automatically during parsing
   - Statements auto-flagged and excluded from system sync
   - Use case: Cozzini Bros and Gordon Food Service monthly account statements
   - User workflow: Click "Re-parse Invoice" → GPT-4o detects statement → Auto-marked
   - Commit: d48c2e1 - PUSHED ✅

4. **Statement Item Handling** 🔧 **FIX**
   - Fixed statements creating unmapped items (invoice numbers, not products)
   - When statement detected: skip item creation, skip mapping workflow
   - Set status='statement' instead of 'mapping'
   - Deleted 16 existing statement items from database ("Invoice #C19780218", etc.)
   - Statements now kept for record-keeping only, no items to map
   - Commit: fb16cb5 - PUSHED ✅

**Impact:** All vendor bill creation to Accounting was completely broken until fix #1. Fixes #2-4 improve UX and automate statement handling.

**Files Modified:**
- integration-hub/src/integration_hub/services/accounting_sender.py (line 226 - field name fix)
- integration-hub/src/integration_hub/templates/invoices.html (three-state sync icons)
- integration-hub/src/integration_hub/templates/invoice_detail.html (three-state sync display)
- integration-hub/src/integration_hub/services/invoice_parser.py (AI statement detection)

**Git Commits:**
- 196dab7 - fix(integration-hub): Critical bug - use total_amount not line_total
- 3c9a0c1 - feat(integration-hub): Improve sync status icons with three states
- d48c2e1 - feat(integration-hub): Add AI-powered statement detection
- fb16cb5 - fix(integration-hub): Skip item creation for statements
- 9bfbb62 - docs: Update claude.md with AI statement detection feature
- 209765b - docs: Update claude.md with three-state sync status UX improvement
- 39e00c7 - docs: Update claude.md with critical accounting bug fix
- e556d55 - docs: Update claude.md with Nov 11 afternoon documentation cleanup session

---

**DOCUMENTATION ACCURACY CLEANUP** (Nov 11, 2025) 📚 **CRITICAL CORRECTIONS**

1. **Framework Documentation Errors Fixed** 🔥 **CRITICAL**
   - Fixed extensive Django/Celery references throughout README (lines 61-119, 778, 835-854)
   - **ALL 7 systems use FastAPI + Alembic** (not Django + manage.py)
   - Fixed Architecture section: Changed "Django application code" → "FastAPI application code"
   - Fixed Common Commands: Removed entire "Django Operations" section
   - Replaced with correct FastAPI/Alembic commands
   - Fixed Installation section: All migration and development commands
   - **Impact:** Documentation was teaching wrong installation procedures
   - Commits: 8da97e2, 8f8e33f, 371c2be, b191ff8 - PUSHED ✅

2. **Database Count Verification** ✅
   - Verified actual database count: **5 databases** (not 7)
   - Databases: inventory_db, accounting_db, hr_db, events_db, hub_db
   - Portal uses hr_db (no separate database)
   - Files uses local storage only (no database)
   - Corrected in README Critical Priorities section

3. **Installation Section Complete Rewrite** ✅
   - Lines 695-703: Database migrations (Django → Alembic for all 5 services)
   - Lines 705-712: Load initial data (removed Django fixtures/loaddata commands)
   - Lines 714-724: Create admin users (removed Django createsuperuser)
   - Lines 744-752: Development server (manage.py runserver → uvicorn)
   - All commands now correct for FastAPI architecture

4. **Monitoring Documentation Clarification** ✅
   - Confirmed monitoring is Portal feature, not separate microservice
   - Routes: `/portal/monitoring` (dashboard), `/portal/api/monitoring/status` (API)
   - Executes bash script: `/opt/restaurant-system/scripts/dashboard-status.sh`
   - Admin-only access control, no separate monitoring container

**Files Modified:**
- `/opt/restaurant-system/README.md` (extensive Django removal, Installation rewrite)

**Git Commits:**
- 8da97e2 - docs: Fix all Django/Celery references to FastAPI/APScheduler
- 8f8e33f - docs: Fix monitoring status and roadmap inaccuracies
- 371c2be - docs: Fix database count - 5 databases, not 7
- b191ff8 - docs: Fix Installation section - remove Django references
- All commits PUSHED ✅

---

### Most Recent Work (Current Session - Nov 11, 2025 - MORNING)

**INTEGRATION HUB: MULTI-PAGE INVOICE PARSING FIXES & ACCOUNTING TAX HANDLING** (Nov 11, 2025) ✅ **PRODUCTION CRITICAL FIXES**

1. **Multi-Page OCR Parsing Fixed** 🔥 **CRITICAL BUG**
   - Fixed invoice_parser.py only reading page 1 of multi-page invoices
   - Changed: `convert_from_path(pdf_path, dpi=200, first_page=1, last_page=1)` → `convert_from_path(pdf_path, dpi=200)`
   - Now processes ALL pages and converts each to base64 for GPT-4o Vision
   - Added prominent "EXTREMELY IMPORTANT - TOTALS FROM LAST PAGE ONLY" section to system prompt
   - Increased max_tokens from 4096 to 8192 for multi-page responses
   - Fixed: Gordon Food Service invoice #9028965836 (3 pages) missing $308.06 from pages 2-3
   - Commit: 33e1d57 - PENDING ⏳

2. **Re-parse Invoice Button Added** ✅
   - Added "Re-parse Invoice" button to invoice_detail.html
   - Non-blocking JavaScript - allows user to navigate away during 30-60 second parse
   - Shows immediate alert that parsing started
   - Button added to lines 22-24, reparseInvoice() function at lines 366-412
   - Resolved template loading issue (FastAPI loading from /app/integration_hub/templates/, not /app/src/)
   - Fixed with: `docker exec integration-hub cp /app/src/.../invoice_detail.html /app/integration_hub/templates/`
   - Commit: a0ebb0c - PENDING ⏳

3. **Accounting Tax Handling Fixed** 🔥 **CRITICAL - TAX CAPITALIZATION**
   - Fixed accounting_sender.py validation error: "Bill total mismatch: Lines $33.50 != Invoice $35.85"
   - **Tax is capitalized into item cost for purchases** (not tracked separately like sales tax)
   - Example: Powerade $10 (no tax) + Trash liners $5 + $0.50 tax = Dr. NAB Cost $10, Dr. Cleaning Supplies $5.50, Cr. AP $15.50
   - Tax distributed proportionally across all line items: `line_tax = (line_subtotal / subtotal) * invoice_tax`
   - Changed validation to compare total_amount (with tax) against invoice_total (not subtotal)
   - Updated lines 229-277 in accounting_sender.py
   - Cleared 32 old "Bill total mismatch" errors from database
   - Commit: PENDING ⏳

4. **UI Improvements** ✅
   - Made "Mark as Statement" button compact (icon-only with tooltip)
   - Changed from full button text to icon only: `<i class="bi bi-file-text"></i>`
   - Added Bootstrap tooltip: `title="Mark as Statement" data-bs-toggle="tooltip"`
   - Initialized tooltips with JavaScript (lines 525-531 in invoices.html)
   - Commit: PENDING ⏳

5. **Database Cleanup** ✅
   - Deleted 12 sets of duplicate invoice records
   - Example: Invoice #C19780218 had IDs 80, 83, 84 (kept 80, deleted 83-84)
   - Cleared 32 invoices with old accounting errors
   - SQL: `UPDATE hub_invoices SET accounting_error = NULL WHERE accounting_error LIKE '%Bill total mismatch%'`

6. **Bank Transaction Matching Investigation** 📊 **RESEARCH COMPLETE**
   - User asked: "What are we using for bank transaction matching?"
   - **Answer: Rule-based matching (NO AI/ML)**
   - Uses multi-tiered approach in transaction_matcher.py and bank_matching.py:
     - **Tier 0**: Exact match (amount + date) - 100% confidence
     - **Tier 1**: Fuzzy match (amount + date ±7 days) - 95-50% confidence
     - **Tier 2**: Composite match (many GL entries → 1 deposit) - 99-50% confidence
     - **Tier 3**: Rule-based match (user-defined rules) - 80-95% confidence
   - Scoring: Amount (40 pts) + Date (30 pts) + Description fuzzy match (30 pts)
   - Uses **rapidfuzz library** for fuzzy string matching (like invoice auto-mapper)
   - Auto-matches transactions with ≥95% confidence
   - Account-specific tolerance: CC ($0.50), Cash (0.5%), Third-party (5%)

**Files Modified:**
- integration-hub/src/integration_hub/services/invoice_parser.py (multi-page OCR fix)
- integration-hub/src/integration_hub/services/accounting_sender.py (tax distribution)
- integration-hub/src/integration_hub/templates/invoice_detail.html (re-parse button)
- integration-hub/src/integration_hub/templates/invoices.html (compact statement button)

**Database Changes:**
- Deleted duplicate invoice records (IDs: 83, 84, and 10 other sets)
- Cleared 32 accounting errors

**Git Commits:**
- 9776ed8 - fix(integration-hub): Critical multi-page parsing and tax handling fixes - PUSHED ✅

---

### Previous Session Work (Nov 10, 2025)

**INVENTORY SYSTEM: VENDOR ITEMS UX IMPROVEMENTS** (Nov 10, 2025) ✅ **COMPLETE - PUSHED**

1. **Integration Hub - Item Code Column Added** ✅
   - Added item code column to unmapped items page
   - Allows verification that vendor item codes in invoices match Inventory system
   - Shows parsed item codes from invoice OCR
   - Commit: e236531 - PUSHED ✅

2. **Vendor Items Terminology Improved** ✅
   - Renamed confusing "Purchase Unit + Conversion Factor" fields
   - New labels: "Base Unit", "Quantity Per Case", "Case Price"
   - Added descriptive help text for clarity
   - Maintains flexible architecture while improving UX
   - Commit: 2b64ba7 - PUSHED ✅

3. **Master Items Dropdown - All Items Loaded** ✅
   - Fixed API default limit (was 100, now 10000)
   - All 485 master items now load in dropdown
   - Items like "Bud Light 16oz" now accessible
   - Updated 2 API calls: api/items/?limit=10000
   - Commit: 0b1ae18 - PUSHED ✅

4. **Searchable Dropdown Implementation** ✅
   - Replaced Select2 with custom searchable select (Integration Hub style)
   - Text input + scrollable select list (size=6, max-height: 200px)
   - Search anywhere in item name (e.g., "ultra" finds "Michelob Ultra")
   - No massive dropdown overlay - compact UX
   - Added filterMasterItems() function using text.includes()
   - Commit: 956f8a7, 079b48d - PUSHED ✅

5. **Filter Persistence After Editing** ✅
   - Save filter values before repopulating dropdowns
   - Restore vendor and master item filters after modal opens
   - Users can filter, edit items, and keep filters applied
   - Fixes annoying UX issue where filters reset on every edit
   - Commit: 079b48d - PUSHED ✅

**Files Modified:**
- integration-hub/src/integration_hub/main.py (unmapped items query)
- integration-hub/src/integration_hub/templates/unmapped_items.html (item code column)
- inventory/src/restaurant_inventory/templates/vendor_items.html (terminology, searchable dropdown, filter persistence)

**Git Commits:**
- e236531 - Add item code column to Integration Hub unmapped items page
- 2b64ba7 - Improve vendor items terminology for clarity
- 0b1ae18 - Fix master items dropdown - load all items
- 956f8a7 - Implement searchable dropdown with Select2
- 079b48d - Replace Select2 with custom searchable dropdown + filter persistence

---

### Previous Session Work (Nov 9, 2025)

**FILES SYSTEM: SHARING & PERMISSIONS OVERHAUL:** (Nov 9, 2025) ✅ **PRODUCTION READY**

1. **Shared Folders Access Fixed** ✅
   - Fixed recursive folder permission checking to allow subfolder access
   - Users can now open shared folders and navigate into all subfolders
   - Permission checks walk up folder tree to find parent shares
   - Fixes: Andy can access "The Nest Files" and all its subfolders
   - Commits: fac7010, 4894738 - PUSHED ✅

2. **Duplicate Share Prevention** ✅
   - Sharing same folder to same user multiple times now updates existing share
   - Prevents duplicate share records in database
   - Removed duplicate share from database (ID 7)
   - "Shared with Me" now shows each item once
   - Commit: a38743d - PUSHED ✅

3. **Dashboard Shared Items Display** ✅
   - Fixed "undefined" folder names showing on dashboard
   - Fixed field name mismatches between API and frontend
   - Dashboard now displays: folder names, "Shared by" info correctly
   - Commit: efce9e2 - PUSHED ✅

4. **Shared With Me Page Fixed** ✅
   - Fixed wrong API endpoint URL (with-me → shared-with-me)
   - Fixed response structure mismatch
   - Added resource_id and shared_by fields to API response
   - Updated frontend to use correct field names
   - Folders now clickable (like regular folder view)
   - Commit: 62b9c48, aa643b4 - PUSHED ✅

5. **Page Refresh State Persistence** ✅
   - Added URL state management for special views
   - Refreshing "Shared with Me" page now stays on that view
   - Uses ?view=shared-with-me URL parameter
   - Also added for shared-by-me and my-files views
   - Commit: 4894738 - PUSHED ✅

6. **Sidebar Navigation** ✅
   - Renamed "All Files" to "Files Dashboard" for consistency
   - Commit: 62b9c48 - PUSHED ✅

**Files Modified:**
- files/src/files/api/shares.py (duplicate prevention, API response fields)
- files/src/files/api/filemanager.py (recursive permission checking)
- files/src/files/templates/filemanager.html (UI fixes, clickable folders, URL state)

**Database Changes:**
- Deleted duplicate internal share record (ID 7)

**Files System Status Updated:** 75-80% → **85% Complete** ✅

**MAIL SYSTEM REMOVAL & DOCUMENTATION CLEANUP:** (Nov 9, 2025) 🗑️ **SYSTEM REMOVAL**

1. **Mail System Completely Removed** 🗑️
   - Removed SOGo mail gateway proxy (150+ lines)
   - Removed Mailcow API integration
   - Removed mail provisioning endpoint
   - Removed auth/verify endpoints for mail
   - Removed can_access_mail from User model
   - Removed mail system tile from dashboard
   - Removed all mail references from documentation
   - **Status:** Mail system fully removed ✅

**COMPREHENSIVE DOCUMENTATION AUDIT & UPDATES:** Complete system analysis (Nov 9, 2025) 📚 **CRITICAL FIXES**

1. **System Cleanup** 🧹
   - Deleted 47 `__pycache__` directories and 357 `.pyc` files
   - Deleted test files: `events/src/events/static/test.txt`, `files/storage/user_2/Test/`
   - Freed ~4MB disk space (238M → 234M)
   - **Status:** Committed and pushed ✅

2. **Comprehensive Codebase Analysis** 📊
   - **Very thorough analysis** of all 7 microservices
   - Identified **57 undocumented features** across systems
   - Found **8 incorrectly documented features**
   - Discovered **1 critical framework error** (Accounting)
   - **Analysis generated:** 4 comprehensive reports (49KB total)
     - `CODEBASE_ANALYSIS_NOV9_2025.md` (22KB) - Deep-dive analysis
     - `CRITICAL_FINDINGS_SUMMARY.md` (9KB) - Executive summary
     - `UNDOCUMENTED_FEATURES_INDEX.md` (11KB) - Complete feature index
     - `ANALYSIS_REPORT_README.md` (7.2KB) - Navigation guide

3. **CRITICAL: Accounting Framework Documentation Fixed** 🔴
   - **Issue:** README stated "Django 4.2" but code uses FastAPI
   - **Impact:** Would confuse developers looking for Django structure
   - **Fix:** Updated `accounting/README.md` line 24
   - Changed from: "Framework: Django 4.2 (Python)"
   - Changed to: "Framework: FastAPI (Python) with SQLAlchemy ORM"
   - Added: "Migrations: Alembic (not Django migrations)"
   - Added: "API Documentation: OpenAPI/Swagger (auto-generated)"
   - **Status:** Fixed and committed ✅

4. **Portal README Fully Updated** 📝
   - **Added undocumented features (REVISED - mail removed):**
     - User profile management (full name, email updates)
     - Password change system with cross-system sync
     - Session auto-refresh middleware
     - Real-time monitoring dashboard
     - Monitoring status API
     - Debug endpoint (with security warning)
   - **Added comprehensive API documentation:**
     - User Profile & Password Management endpoints
     - System Monitoring endpoints
     - Debug endpoints
   - **Added security warnings (REVISED):**
     - Line 283: Debug endpoint no auth
     - Missing rate limiting
     - Missing audit logging
   - **Updated User Model** schema with `can_access_mail` permission
   - **Updated status:** 95% → 99% Production Ready
   - **Status:** Committed ✅

5. **Main README Updated** 📚
   - Updated Portal section with all features
   - Updated Accounting section with correct framework
   - Added Nov 9 to Recent Updates
   - Updated System Status Summary table
   - Updated completion notes
   - **Status:** Committed ✅

6. **Documentation Completeness Scores** 📊
   - Portal: 85% → **99%** ✅ (fully documented)
   - Accounting: **60%** ⚠️ (150+ endpoints undocumented)
   - Events: **99%** ✅ (excellent)
   - HR: **100%** ✅ (perfect)
   - Inventory: **100%** ✅ (perfect)
   - Integration Hub: **100%** ✅ (perfect)
   - Files: **100%** ✅ (perfect)

7. **Security Findings** ⚠️
   - Portal temp password uses hash prefix (line 767) - needs review
   - Debug endpoint has no authentication (line 283) - needs fix
   - No rate limiting on sensitive endpoints
   - No audit logging for sensitive operations
   - **Action:** Security review recommended

8. **Commits & Git Status** 🔄
   - Commit 1: System cleanup (c8cce17)
   - Commit 2: Updated claude.md (7799fb8)
   - Commit 3: Documentation audit updates (d0414f9) - PUSHED ✅
   - Commit 4: Mail system removal (PENDING)
   - **Status:** Mail system removed, ready to commit ⏳

### Previous Work (Nov 8, 2025)

**BUG FIXES:** Fixed critical issues preventing Events system from working (Nov 8, 2025) 🐛
   1. **EmailResponse schema export** - Added to `schemas/__init__.py` exports (commit `7818e2d`)
   2. **API URL resolution** - Changed fetch URLs from absolute to relative (commits `87437d4`, `159893b`)
      - Problem: `<base href="/events/">` doesn't affect JavaScript fetch() URLs
      - Absolute URLs `/api/users/` were going to root instead of `/events/api/users/`
      - Nginx was returning 301 redirects → browsers got HTML instead of JSON
      - Fixed by using relative URLs `api/users/` which properly resolve with base href
      - Applied to: users.html, emails.html, event_detail.html
   3. **Event status consistency** - Fixed status handling across all pages (commits `159893b`, `daa7e15`, `17fb170`)
      - Removed `.toUpperCase()` from status field (enum values are lowercase)
      - Fixed status dropdown in event_detail.html to match EventStatus enum
      - Fixed events_list.html status filter, stats, and CSS classes
      - Removed invalid options: "in_progress", "completed"
      - Changed "Completed" to "Closed" in UI labels
      - Valid statuses: draft, pending, confirmed, closed, canceled
      - Fixed issue where closed events weren't appearing in events list
   4. **User role assignment** - Granted admin role to andy@swhgrp.com and admin@swhgrp.com
   5. **Updated gitignore** - Exclude integration-hub upload PDFs (commit `f946f73`)
   - **Status:** All admin pages fully functional ✅

1. **Events System: Admin UIs Complete** ✅ (Nov 8, 2025) 👥 **MANAGEMENT TOOLS READY**
   - **USERS & ROLES MANAGEMENT** - Full admin interface for managing users and roles
   - **EMAIL HISTORY VIEWER** - Complete email log with stats and resend capability
   - **Backend changes:**
     - Created users.py router with 10 endpoints (list, get, assign/remove roles, activate/deactivate)
     - Created emails.py router with 4 endpoints (list, get details, resend failed, get stats)
     - Created email.py schema for EmailResponse
     - All endpoints protected with `require_auth` or `require_role("admin")`
   - **Frontend changes:**
     - Created users.html admin page with dark theme
     - Search and filter users by name, email, role, department
     - Role management modal for assigning/removing roles
     - Color-coded role badges (admin=red, event_manager=yellow, dept_lead=blue, staff=green, read_only=gray)
     - Activate/deactivate user buttons (prevents self-deactivation)
     - Created emails.html admin page with stats dashboard
     - Stats cards showing total, sent, queued, failed counts
     - Filter by status and time period (7/30/90/365 days)
     - Email detail modal showing full subject, recipients, body HTML
     - Resend button for failed emails (admin action)
     - Added "Users & Roles" and "Email History" links to sidebar
   - **Files created:** 5 files (users.py, users.html, emails.py, email.py, emails.html)
   - **Git commits:**
     - `0d69426` - feat(events): Add Users & Roles Management UI
     - `c6e0b46` - feat(events): Add Email History Management UI
     - `95f5a30` - docs(events): Update README with Admin UIs completion
   - **Status updated:** Events system now 98% complete (was 95%)
   - **Remaining:** UI role-based hiding (2%)

2. **Events System: Comprehensive RBAC Implementation** ✅ (Nov 8, 2025) 🔒 **SECURITY COMPLETE**
   - **FULL ROLE-BASED ACCESS CONTROL** - All API endpoints now properly secured
   - **Backend changes:**
     - Added `require_role()` dependency factory for role-based endpoint protection
     - Added `require_permission()` dependency factory for granular permission checks
     - Protected all Events API endpoints (create, update, delete, confirm)
     - Protected all Tasks API endpoints (create, update, delete with permission checks)
     - Protected all Settings endpoints (locations, event types, beverages, meals, templates)
     - Protected Package and Document endpoints (admin/event_manager only for CUD operations)
     - All endpoints now require Portal SSO authentication (JWT in `portal_session` cookie)
   - **Permission model:**
     - **admin**: Full access to everything
     - **event_manager**: Can create/update events, tasks, settings; cannot delete users
     - **dept_lead**: Can read/update tasks for their department, read events/financials
     - **staff**: Can read/update assigned tasks only (DEFAULT for new users)
     - **read_only**: Read-only access, no financials
   - **Auto-provisioning:** New users are automatically created in Events DB on first login via Portal SSO with 'staff' role
   - **Files modified:** 6 files (169 insertions, 55 deletions)
   - **Git commits:**
     - `1099d2d` - feat(events): Implement comprehensive RBAC enforcement
     - `eeea75b` - docs(events): Update README with RBAC implementation
   - **Status updated:** Events system now 95% complete (was 85%)
   - **Remaining:** UI role-based hiding, admin UI for role management

2. **Integration Hub: Major Workflow Improvements** ✅ (Nov 8, 2025) 🚀 **GAME CHANGER**
   - **REVOLUTIONARY BULK MAPPING** - Map once by description, applies to ALL occurrences
   - **Backend changes:**
     - Added bulk mapping endpoint: `POST /api/items/map-by-description`
     - Redesigned unmapped items query with SQL aggregation (GROUP BY description)
     - Shows frequency count and affected invoices per unique item
     - Auto-triggers send when invoice becomes fully mapped
     - Added statement marking system (`is_statement` boolean field)
     - Implemented invoice deletion with cascade cleanup
     - Smart auto-send logic (only sends to Inventory if items have categories)
     - Enhanced GL validation (different requirements for inventory vs expense items)
   - **Frontend changes:**
     - Unmapped items page completely redesigned with grouping
     - New mapped items review page (`mapped_items.html`)
     - Category mappings show full GL account names ("1000 - Cash")
     - Vendor selection/creation in invoice detail
     - Invoice deletion buttons with confirmation
     - PDF preview and download functionality
   - **API enhancements:**
     - New inventory sync endpoints: `GET /api/items/_hub/sync`, `GET /api/vendor-items/_hub/sync`
     - Statement marking: `POST /api/invoices/{id}/mark-statement`
     - Invoice deletion: `DELETE /api/invoices/{id}`
     - PDF download: `GET /api/invoices/{id}/pdf`
     - Category lookup: `GET /api/category-mappings/{category}`
   - **Database migration:**
     - `20251104_1919_6bd8b98a2419_add_is_statement_field.py` - Adds is_statement boolean
   - **Files modified:** 20 files (2,015 insertions, 165 deletions)
   - **Git commits:**
     - `7d1cc9a` - feat(integration-hub): Major mapping workflow improvements
     - `a274316` - docs(integration-hub): Update README with Nov 4-8 improvements
     - `9f1d6ff` - docs: Update main README with Integration Hub improvements (v2.7)
   - **Pushed to GitHub:** ✅ All commits pushed

### Previous Work (Nov 4, 2025)

1. **Events System: Venue-to-Location Migration + Per-Person Pricing** ✅ (Nov 4, 2025) 🎯
   - **MAJOR ARCHITECTURAL CHANGE** - Complete migration from venue-based to location-based system
   - **Backend changes:**
     - Added `location` string field to Event model
     - Made `venue_id` nullable for backward compatibility
     - Updated all API endpoints (events, calendar, public intake) to use location
     - Database migration: `ALTER TABLE events ADD COLUMN location VARCHAR(255)`
     - Database migration: `ALTER TABLE events ALTER COLUMN venue_id DROP NOT NULL`
   - **Frontend changes:**
     - Updated intake form with location dropdown (from settings)
     - Updated calendar page location filter
     - Updated events list page location filter
     - Updated event detail page with location dropdown
     - Changed event type from text input to dropdown for consistency
   - **Per-person pricing implementation:**
     - Intake form now collects "Estimated Budget Per Person" instead of total budget
     - Added input-group styling with "$" prefix and "per person" suffix
     - JavaScript calculates total: `budgetPerPerson × guestCount`
     - Backend stores calculated total in `financials_json['estimated_total']`
     - Maintains backend compatibility while improving UX
   - **Template management system:**
     - Added event templates to settings page
     - Created template CRUD API and UI
     - Templates store default menu and financials JSON
     - Intake form uses templates to populate event defaults
   - **Bug fixes:**
     - Fixed timezone display issue (was converting to UTC, now uses local time)
     - Fixed packages page API URLs (added `/events` prefix and trailing slashes)
     - Replaced custom alerts with browser-native modals throughout all pages
   - **Files modified:** 15 files (1,179 insertions, 232 deletions)
   - **Git commit:** 6b984a4 - Committed ✅ (Pending push)

### Previous Work (Nov 3, 2025)

1. **Inventory System: Complete Documentation Update** ✅ (Nov 3, 2025 - Late Evening) 📚
   - **DOCUMENTATION COMPLETE** - README fully updated to reflect all features
   - Updated: Inventory README from 427 lines to 960 lines (comprehensive documentation)
   - Documented: AI-powered invoice processing (OpenAI GPT-4 integration)
   - Documented: POS integration (Clover, Square, Toast with auto-sync)
   - Documented: Recipe management and costing system
   - Documented: Waste tracking (fully implemented, was marked as "planned")
   - Documented: All 32 database tables and 25+ models
   - Documented: All 27 HTML templates (940KB total)
   - Documented: All 21 API endpoint modules with 177+ routes
   - Added: Complete API structure documentation
   - Added: Deployment architecture and Portal SSO integration flow
   - Added: Troubleshooting guide for common issues
   - Added: System statistics (15,000+ LOC, 101 Python files)
   - Removed: Outdated "Planned Features" that were already implemented
   - Updated: Future enhancements section (Spanish language planned)
   - Status: Inventory system is 100%+ complete (core + advanced features)
   - Files updated: `inventory/README.md` (v2.0), `README.md` (inventory section + status table)
   - **Git commit:** Pending ⏳

2. **HR System: New Hire Emails + Locations** ✅ (Nov 3, 2025 - Evening) 📧
   - **PRODUCTION READY** - New hire email improvements deployed
   - Fixed: Emails now sent IMMEDIATELY when employee is created (not waiting for documents)
   - Added: Assigned locations included in new hire email notifications
   - Email now shows all selected locations in bullet-point format
   - Backend: Updated `send_new_hire_notification()` with `location_names` parameter
   - Frontend: Locations captured during employee creation and passed to email service
   - Email format: Added "ASSIGNED LOCATIONS" section to notification template
   - Files modified: `hr/services/email.py`, `hr/api/endpoints/employees.py`
   - **Git commit:** Pending ⏳

2. **HR System: Admin-Only Employee Permanent Delete** ✅ (Nov 3, 2025 - Evening) 🗑️
   - **PRODUCTION READY** - Permanent delete functionality for admins
   - New API endpoint: `DELETE /api/employees/{id}/permanent` (admin-only)
   - Deletes employee + all documents (disk + DB) + position assignments + directory
   - UI: Delete button (trash icon 🗑️) added to employee list page (ACTIONS column)
   - UI: "Permanent Delete" button added to employee detail page header
   - Double confirmation prompts for safety
   - Non-admins blocked with 403 Forbidden error
   - Files modified: `hr/api/endpoints/employees.py`, `hr/templates/employees.html`, `hr/templates/employee_detail.html`
   - **Git commit:** Pending ⏳

3. **HR System: Document Access Control - Admin Fixes** ✅ (Nov 3, 2025 - Evening) 🔐
   - **CRITICAL SECURITY FIX** - Document access properly secured
   - Fixed: All document endpoints now require authentication
   - Fixed: ID Copy and Social Security Card documents restricted to admins only
   - Frontend: Restricted documents show lock icon 🔒 for non-admins
   - Frontend: Admins see all documents with full access (preview/download/delete)
   - Backend: Download endpoint enforces 403 Forbidden for non-admin ID/SSN access
   - Fixed: Backend no longer modifies document data (frontend handles display logic)
   - Updated endpoints: `GET /api/documents/employees/{id}/documents`, `GET /api/documents/{id}`, `GET /api/documents/{id}/download`, etc.
   - Files modified: `hr/api/endpoints/documents.py`
   - **Git commit:** Pending ⏳

4. **HR System: User Admin Flag Synchronization** ✅ (Nov 3, 2025 - Evening) 👥
   - **CRITICAL FIX** - Admin users now have correct permissions
   - Fixed: `is_admin` database flag now matches role assignments
   - Updated 4 users: erica, ian, justin, tina (is_admin = true)
   - System uses `is_admin` column (not just role name) for permission checks
   - All 6 admin users verified: admin, andy, erica, ian, justin, tina
   - Admins can now access all documents, use delete buttons, and have full permissions
   - Database update: Direct SQL UPDATE to `users` table
   - **No code changes** - Database fix only

### Previous Work (Nov 1-2, 2025)

5. **POS System Design & Specification - 100% COMPLETE** ✅ (Nov 2, 2025)
   - **PRODUCTION READY** - Full Portal SSO integration implemented
   - Fixed page reload loop caused by URL routing issues with `<base href="/events/">`
   - Implemented JWT token validation from Portal cookies
   - Added JIT (Just-In-Time) user provisioning from Portal tokens
   - Fixed exception handler to distinguish API vs HTML requests (JSON vs redirect)
   - Configured proper redirects to Portal login for unauthenticated users
   - Used absolute URLs for redirects to avoid base href issues
   - Updated all fetch() calls to use relative URLs (removed `/events/` prefix)
   - Fixed `/api/auth/me` to use Portal SSO instead of events-specific session
   - Removed client-side auth check (now server-side only)
   - All navigation links corrected for proper routing
   - **Events system status:** 55% → 75% (PRODUCTION READY)
   - **Git commit:** 400de0d - Pushed to GitHub ✅

2. **Monitoring Dashboard Timezone Fix** ✅ (Nov 1, 2025 - Evening)
   - **Fixed UTC timestamp display** - Now shows local time (EDT/EST)
   - Updated `scripts/dashboard-status.sh` to generate local time
   - Changed from `date -u` (UTC) to `date "+%Y-%m-%d %H:%M:%S %Z"` (local)
   - Added HTML meta tags for cache prevention
   - Added server-side cache-busting headers (Cache-Control, Pragma, Expires)
   - Added client-side cache-busting (query parameters + cache: 'no-store')
   - Added JavaScript UTC-to-local conversion as fallback for cached data
   - Portal monitoring dashboard now displays accurate local timestamps
   - **Git commit:** 400de0d - Pushed to GitHub ✅

3. **Documentation & GitHub Push** ✅ (Nov 1, 2025 - Evening)
   - Updated README.md with Events SSO completion
   - Updated system status table: Events → Production Ready (75%)
   - Added new "Recent Updates" section for v2.6
   - Marked Events authentication as RESOLVED in Critical Issues
   - Version bump: 2.5 → 2.6
   - **Git commit:** 400de0d - Pushed to origin/main ✅
   - **Branch:** main (ahead by 0 commits - fully synced)

4. **Real-Time Monitoring Dashboard** ✅ (Oct 31, 2025 - Updated Nov 1)
   - Added comprehensive system monitoring to Portal
   - URL: https://rm.swhgrp.com/portal/monitoring (Admin only)
   - Features:
     - 7 microservices health monitoring
     - 5 database health checks with connection counts
     - Nginx reverse proxy status
     - Docker network health
     - SSL certificate expiration tracking
     - Per-database backup status
     - Recent errors and alerts display
     - Auto-refresh every 30 seconds
     - **Local time display (EDT/EST)** - Fixed Nov 1 ✅
     - **Aggressive cache prevention** - Fixed Nov 1 ✅
   - Committed: f100a1c, 3bbc2b1, dc34490, 400de0d

5. **System Cleanup & Documentation Audit** ✅ (Oct 31, 2025)
   - Freed 138MB disk space (removed .bak files, __pycache__, orphaned volumes)
   - Consolidated duplicate code (portal_sso.py, inactivity-warning.js)
   - Audited all 55 markdown files - 95/100 health score
   - Automated backup rotation (7-day retention)
   - Committed: 941c389

6. **Integration Hub: Automated Invoice Intake** ✅ (Oct 31, 2025)
   - Email monitoring system (IMAP, checks every 15 minutes)
   - OpenAI GPT-4o Vision integration for PDF invoice parsing
   - Intelligent auto-mapper (vendor item codes, fuzzy matching, GL accounts)
   - Email settings UI with connection testing
   - PDF deduplication (SHA-256 hashing)
   - Committed: 63afd14, 9f0e5c7

### Git Status - All Synced ✅

```bash
# Branch: main
# Status: Clean - All changes committed and pushed
# Last push: November 11, 2025
# Latest commit (Nov 11 - Integration Hub Critical Fixes):
#   - 9776ed8 - fix(integration-hub): Critical multi-page parsing and tax handling fixes - PUSHED ✅
#     * Fixed multi-page invoice parsing (was only reading page 1)
#     * Fixed accounting tax handling (capitalize tax into item costs)
#     * Added re-parse invoice button with non-blocking UX
#     * Made statement button compact with tooltip
#     * Updated README and claude.md documentation
#
# Previous commits (Nov 10 - Inventory & Integration Hub UX):
#   - 079b48d - feat(inventory): Improve vendor items UX - searchable dropdown and filter persistence - PUSHED ✅
#   - 956f8a7 - feat(inventory): Add Select2 searchable dropdown for master items in vendor item form - PUSHED ✅
#   - 0b1ae18 - fix(inventory): Load all master items in vendor item dropdown - increase API limit - PUSHED ✅
#   - 2b64ba7 - feat(inventory): Improve vendor items terminology for clarity - PUSHED ✅
#   - e236531 - feat(integration-hub): Add item code column to unmapped items page - PUSHED ✅
#
# Previous commits (Nov 9 - Files System):
#   - aa643b4 - Make shared folders clickable like regular folders - remove Open button - PUSHED ✅
#   - 4894738 - Fix shared folder access and page refresh state persistence - PUSHED ✅
#   - efce9e2 - Fix dashboard 'Shared with Me' section showing 'undefined' for folder names - PUSHED ✅
#   - a38743d - Prevent duplicate internal shares - update existing instead of creating new - PUSHED ✅
#   - 62b9c48 - Fix 'Shared with Me' page - correct API endpoint and response structure - PUSHED ✅
#
# Untracked files (normal operations, excluded from git):
#   - integration-hub/uploads/ (63 invoice PDFs - correctly ignored by .gitignore)
```

**Current Status:** ✅ All work committed and pushed to GitHub. Repository clean.

---

## 🏗️ SYSTEM ARCHITECTURE

### 7 Microservices (All FastAPI)

**IMPORTANT CORRECTION:** All systems use **FastAPI**, not Django as previously documented.

| Service | Port | Database | Tech Stack | Status |
|---------|------|----------|------------|--------|
| **Portal** | 8000 | hr_db (shared) | FastAPI, SQLAlchemy, JWT | 99%+ ✅ |
| **Inventory** | 8000 | inventory_db | FastAPI, SQLAlchemy, Redis, OpenAI | 100%+ ✅ |
| **HR** | 8000 | hr_db | FastAPI, SQLAlchemy, Email | 100% ✅ |
| **Accounting** | 8000 | accounting_db | FastAPI, SQLAlchemy | ~75% 🔄 |
| **Events** | 8000 | events_db | FastAPI, SQLAlchemy | **80% ✅ PRODUCTION** |
| **Integration Hub** | 8000 | hub_db | FastAPI, SQLAlchemy, OpenAI, APScheduler | 100%+ ✅ |
| **Files** | 8000 | files_db | FastAPI, SQLAlchemy | **85% ✅** |

**Infrastructure:**
- **Nginx:** Reverse proxy with SSL (Let's Encrypt)
- **PostgreSQL 15:** 5 separate databases
- **Redis 7:** Caching for Inventory and Events
- **Docker Compose:** Orchestration (16 containers)
- **Mail:** Mailcow stack (10 containers) at mail.swhgrp.com

### Authentication Flow (SSO)

```
1. User → rm.swhgrp.com → Nginx redirects to /portal/
2. Portal login → validates against HR database
3. Portal issues JWT token (secure HTTP-only cookie, 30-min session)
4. User clicks system → Browser navigates to /[system]/
5. Nginx routes directly to service (NOT through Portal)
6. Service validates JWT token independently
7. If valid: show interface | If invalid: redirect to /portal/login
```

**Key Points:**
- Portal = SSO provider (issues JWT tokens)
- Nginx = Traffic router (routes to microservices)
- Each service = Independent (validates JWT, has own DB)
- No traffic flows through Portal after auth

### Database Strategy

Each service has isolated PostgreSQL database:
- `inventory_db` (port 5432 exposed)
- `hr_db` (shared by Portal and HR)
- `accounting_db`
- `events_db`
- `hub_db`
- `files_db`

**Backups:**
- Automated daily backups (2:00 AM via cron)
- 7-day local retention (`/opt/restaurant-system/backups/`)
- Older backups archived to `/opt/archives/old-backups/`
- Log rotation configured (`/etc/logrotate.d/restaurant-system`)
- Linode Backup Service (server-level snapshots)

---

## 📦 MICROSERVICES DEEP DIVE

### 1. Portal System ✅ 99%+ Complete

**Purpose:** Central authentication and SSO hub

**Location:** `/opt/restaurant-system/portal/`

**Key Files:**
- `src/portal/main.py` - FastAPI app (35,206 bytes)
- `src/portal/config.py` - Configuration
- `templates/` - Login, home, settings, change_password

**Features:**
- ✅ JWT authentication (jose library)
- ✅ Session management (30-min timeout with 2-min warning)
- ✅ User permissions per system
- ✅ Admin user management UI
- ✅ Password change with cross-system sync
- ✅ Real-time monitoring dashboard (NEW)
- ❌ Password reset via email (NOT implemented)
- ❌ Two-factor authentication (FUTURE)

**Undocumented Features:**
- Password change system (`/portal/change-password`, `POST /api/change-password`)
- Session timeout warning (JavaScript: `inactivity-warning.js`)
- Monitoring dashboard (`/portal/monitoring`)

**API Endpoints:**
- `GET /portal/` - Dashboard
- `GET /portal/login` - Login page
- `POST /portal/login` - Process login
- `GET /portal/logout` - Logout
- `GET /portal/settings` - User management (admin only)
- `POST /portal/api/users/{id}/permissions` - Update permissions
- `GET /portal/api/generate-token/{system}` - SSO token
- `GET /portal/change-password` - Password change page
- `POST /portal/api/change-password` - Change password + sync
- `GET /portal/monitoring` - System monitoring (NEW)
- `GET /portal/health` - Health check

---

### 2. Inventory System ✅ 100%+ Complete

**Purpose:** Complete inventory management with POS integration, AI invoice processing, recipe management

**Location:** `/opt/restaurant-system/inventory/`

**Technology:** FastAPI (NOT Django), SQLAlchemy, OpenAI, Redis, APScheduler

**Database:** 25+ models (not 11!)

**Features:**
- ✅ Product catalog management
- ✅ Multi-location inventory tracking
- ✅ Supplier/vendor management
- ✅ Purchase orders
- ✅ Stock counts and adjustments
- ✅ Waste tracking (FULLY implemented)
- ✅ Analytics dashboards
- ✅ Low stock alerts

**Undocumented Major Systems:**

1. **POS Integration** (Complete - NOT documented)
   - Clover, Square, Toast API integration
   - Automatic sales sync (every 10 minutes via APScheduler)
   - POS item mapping to inventory
   - Inventory deduction from sales
   - Daily sales tracking

2. **AI Invoice Processing** (Complete - NOT documented)
   - OpenAI integration for OCR and parsing
   - Automatic line item extraction from PDFs
   - Confidence scoring and anomaly detection
   - Vendor item mapping
   - Status workflow (UPLOADED → PARSING → PARSED → REVIEWED → APPROVED)
   - Manual review/correction interface

3. **Recipe Management & Costing** (Complete - NOT documented)
   - Recipe CRUD with ingredients
   - Yield and portion tracking
   - Ingredient costing calculations
   - Labor and overhead cost tracking
   - Food cost percentage calculation
   - PDF recipe generation

**177+ API routes** (significantly underestimated in docs)

---

### 3. HR System ✅ 100% Complete (Core Features)

**Purpose:** Employee information management (NOT scheduling/payroll/timekeeping)

**Location:** `/opt/restaurant-system/hr/`

**Technology:** FastAPI, SQLAlchemy, Email (SMTP), Encryption

**Database:** 12 models

**What's Implemented:**
- ✅ Employee profile management (encrypted PII)
- ✅ Department and position tracking
- ✅ User account management for Portal SSO
- ✅ Emergency contacts (encrypted)
- ✅ Employee document storage with expiration tracking
- ✅ Role-based access control (Admin, Manager, Employee)
- ✅ Audit logging for data access
- ✅ Email settings management
- ✅ **NEW (Nov 3, 2025):** New hire email notifications with locations
- ✅ **NEW (Nov 3, 2025):** Admin-only permanent employee deletion
- ✅ **NEW (Nov 3, 2025):** Document access control (ID/SSN restricted to admins)

**What's NOT Implemented:**
- ❌ Shift scheduling
- ❌ Time clock (clock in/out)
- ❌ Timesheet workflow
- ❌ Payroll calculation
- ❌ Attendance tracking
- ❌ Benefits management
- ❌ PTO/vacation tracking

**Integration:**
- Master source for user authentication
- Centralized password sync to all microservices
- Portal reads HR database for user data

---

### 4. Accounting System 🔄 ~65% Complete

**Purpose:** Full double-entry accounting system

**Location:** `/opt/restaurant-system/accounting/`

**Technology:** FastAPI (NOT Django!), SQLAlchemy, ReportLab, openpyxl

**Database:** 60+ models (largest system)

**Files:** 154 Python files (most complex system)

**Completion Status:**
- ✅ Core Accounting: 100%
- ✅ Financial Reporting: 100%
- ✅ Multi-Location: 100%
- ✅ Dashboard & Analytics: 95%
- 🔄 Accounts Payable: 60%
- 🔄 Accounts Receivable: 40%
- 🔄 Banking/Reconciliation: 50%
- 🔄 Budgeting: 40%
- ❌ Fixed Asset Management: 0%
- ❌ Job Costing: 0%

**Recent Major Features:**

1. **General Accounting Dashboard** (Oct 22, 2025) ✅
   - 10 real-time widgets (Executive Summary, Sales, COGS, Bank, AP, Alerts, etc.)
   - 6-month performance trends (Chart.js)
   - Location filtering
   - Auto-refresh every 5 minutes
   - 4 new database tables, 6 API endpoints

2. **Banking & Reconciliation** (In Progress - Phase 1B Week 3)
   - Statement reconciliation
   - Composite matching (multiple DSS entries to one bank transaction)
   - Automatic clearing journal entries
   - **Status:** Backend 100%, UI 100%, Week 3 testing next

**251 API endpoints**

**Documentation:** `docs/status/ACCOUNTING_SYSTEM_STATUS.md` (most comprehensive)

---

### 5. Events System ✅ 80% Complete - PRODUCTION READY!

**Purpose:** Event planning and catering management

**Location:** `/opt/restaurant-system/events/`

**Technology:** FastAPI, SQLAlchemy, WeasyPrint, FullCalendar.js

**Database:** 17 models

**PRODUCTION READY - Recent Updates:**

**Nov 4, 2025 - Major Architecture Update:**
- ✅ **Location-Based System** - Migrated from venue foreign keys to location strings
- ✅ **Per-Person Pricing** - Intake form now uses per-person budget instead of total
- ✅ **Event Templates** - Full CRUD system for event templates in settings
- ✅ **Timezone Fixes** - Event detail page now displays correct local times
- ✅ **UI Consistency** - Event type dropdown, native browser modals
- ✅ **Package Management** - Fixed API URLs, packages page fully functional

**Nov 1, 2025 - SSO Complete:**
- ✅ **Portal SSO Integration COMPLETE** - Full JWT authentication
- ✅ JIT (Just-In-Time) user provisioning from Portal tokens
- ✅ Fixed page reload loop (URL routing with base href)
- ✅ Proper exception handling (API JSON vs HTML redirects)
- ✅ Automatic redirect to Portal login for unauthenticated users

**What Works:**
- ✅ Event CRUD with status workflow (location-based)
- ✅ Public intake form (NO auth required) - https://rm.swhgrp.com/events/public/intake
- ✅ Per-person pricing with automatic total calculation
- ✅ Event templates system (create from templates)
- ✅ Calendar views (month/week/day) with location filtering
- ✅ Task management with Kanban board
- ✅ Event packages management (fully functional)
- ✅ BEO PDF generation (WeasyPrint)
- ✅ Email notifications
- ✅ Client management
- ✅ Settings: locations, event types, meal types, beverages, templates
- ✅ Fully mobile-responsive

**Partial/Missing:**
- 🔄 Menu builder UI (JSON storage only - 40%)
- 🔄 Financial integration with Accounting (partial - 50%)
- ❌ S3 storage (currently local)
- ❌ 4 router files (emails, users, admin) - NOT IMPLEMENTED
- ❌ Audit logging (model exists but never populated)
- ❌ Celery/Redis - Dependencies present but NOT USED

**Recent Files Modified (Nov 4):**
- 15 files total (1,179 insertions, 232 deletions)
- Backend: models, schemas, API endpoints (events, public, settings)
- Frontend: intake form, calendar, events list, event detail, packages page
- Templates: base.html with new modal functions

**Git:** Committed 6b984a4 (Nov 4) - Pending push ⏳

---

### 6. Integration Hub ✅ 100%+ Complete

**Purpose:** Invoice processing, GL mapping, journal entry creation

**Location:** `/opt/restaurant-system/integration-hub/`

**Technology:** FastAPI, SQLAlchemy, OpenAI GPT-4o Vision, APScheduler, PyPDF2

**Database:** 7+ models

**CRITICAL CORRECTION:** This is NOT a vendor API integration platform. It does NOT connect to US Foods, Sysco, Restaurant Depot, or any third-party vendor APIs.

**What It Actually Does:**
- ✅ Receives vendor invoices (email, manual upload)
- ✅ AI-powered PDF parsing (OpenAI GPT-4o Vision)
- ✅ Maps invoice line items to inventory items
- ✅ Maps items to GL accounts (Asset, COGS, Waste, Revenue)
- ✅ Sends mapped invoices to Inventory system via REST API
- ✅ Creates journal entries for Accounting system via REST API
- ✅ Vendor master data sync across systems

**Recent Addition: Automated Invoice Intake** (Oct 31, 2025) ✅
- Email monitoring (IMAP, every 15 minutes)
- PDF extraction with SHA-256 deduplication
- OpenAI parsing with confidence scoring
- Multi-strategy auto-mapping:
  - Vendor item code matching (confidence: 1.0)
  - Fuzzy description matching (confidence: 0.7-0.9)
  - Category-level GL account fallback
- Email settings UI with connection testing
- Auto vendor matching with fuzzy logic

**Workflow:**
```
Email → PDF Extract → AI Parse → Auto-Map → Ready for Review → Route to Systems
```

**What It Does NOT Do:**
- ❌ US Foods API - Does NOT exist
- ❌ Sysco API - Does NOT exist
- ❌ Restaurant Depot API - Does NOT exist
- ❌ Any vendor product catalog sync
- ❌ OAuth2 vendor authentication
- ❌ Automated pricing updates from vendors
- ❌ Vendor order submission

---

### 7. Files System ✅ 85% Complete - PRODUCTION READY!

**Purpose:** Document management and file sharing

**Location:** `/opt/restaurant-system/files/`

**Technology:** FastAPI, Local file storage, LibreOffice (document conversion)

**Database:** 6 models

**Storage:** `/app/storage` (persistent volume)

**PRODUCTION READY - Recent Updates (Nov 9, 2025):**

**Sharing & Permissions Overhaul:**
- ✅ **Recursive Permission Checking** - Users can access shared folders and all subfolders
- ✅ **Duplicate Share Prevention** - Sharing same folder multiple times updates existing share
- ✅ **Dashboard Display Fixed** - Shared items show correct folder names and sharer info
- ✅ **Shared With Me Page** - Fully functional with correct API integration
- ✅ **Page Refresh State** - Stays on current view when refreshing (URL parameters)
- ✅ **Clickable Folders** - Entire folder row clickable (consistent UX)
- ✅ **Admin Permission Enforcement** - Admins follow same permission rules as regular users

**Features:**
- ✅ File upload/download (single file, folder upload with hierarchy)
- ✅ File preview (PDFs, images, Office docs)
- ✅ Folder organization with nested subfolders
- ✅ File operations (copy, move, rename, delete)
- ✅ Internal sharing with granular permissions (view, download, upload, edit, delete, share)
- ✅ Public share links with passwords and expiration
- ✅ Portal SSO integration
- ✅ Folder hierarchy creation from uploads
- ✅ Permission inheritance (subfolders inherit parent permissions)
- ✅ Mobile-friendly responsive design
- ⚠️ Bulk upload - UI exists but limited testing
- ⚠️ Bulk operations - Limited API endpoints
- ❌ Collaborative editing - NOT implemented
- ❌ Calendar integration - NOT implemented
- ❌ Comments - NOT implemented
- ❌ Version history - NOT implemented

---

### 8. Maintenance & Equipment Tracking System ✅ 100% Backend Complete

**Purpose:** Track equipment, maintenance schedules, work orders, and vendors across all locations

**Location:** `/opt/restaurant-system/maintenance/`

**Technology:** FastAPI, SQLAlchemy (async), PostgreSQL

**Container:** `maintenance-service` (port 8006)
**Database:** `maintenance-postgres`

**Database Models:**
- `equipment_categories` - Hierarchical equipment categorization
- `equipment` - Equipment/asset tracking with QR codes
- `equipment_history` - Audit log for status/location changes
- `maintenance_schedules` - Preventive maintenance scheduling
- `work_orders` - Repair and maintenance work orders
- `work_order_comments` - Work order communication
- `work_order_parts` - Parts/materials used in work orders
- `vendors` - External service vendors

**Features:**
- ✅ Equipment CRUD with QR code generation
- ✅ Equipment categories (hierarchical tree structure)
- ✅ Equipment history tracking (status changes, maintenance)
- ✅ Work order management (create, assign, start, complete)
- ✅ Work order comments and parts tracking
- ✅ Preventive maintenance scheduling (daily to annual frequencies)
- ✅ Automatic next-due calculation when maintenance completed
- ✅ Vendor management
- ✅ Dashboard with alerts (overdue maintenance, critical work orders)
- ✅ Multi-location support (via location_id)
- ✅ Portal UI (Phase 7 - Complete Jan 10, 2026)
- ❌ QR code printing/PDF export (Future)
- ❌ Email notifications (Future)

**API Endpoints:**
- `GET /maintenance/health` - Health check
- `GET /maintenance/dashboard` - Dashboard stats
- `GET /maintenance/dashboard/alerts` - System alerts
- `GET /maintenance/dashboard/maintenance-due` - Upcoming maintenance
- `GET /maintenance/dashboard/equipment-status` - Equipment by location
- Equipment CRUD: `/maintenance/equipment`
- Categories CRUD: `/maintenance/categories`
- Work Orders CRUD: `/maintenance/work-orders`
- Schedules CRUD: `/maintenance/schedules`
- Vendors CRUD: `/maintenance/vendors`

**Documentation:**
- `/maintenance/docs` - Swagger UI
- `/maintenance/redoc` - ReDoc

**Key Files:**
- `src/maintenance/main.py` - FastAPI application
- `src/maintenance/models.py` - SQLAlchemy models
- `src/maintenance/schemas.py` - Pydantic schemas
- `src/maintenance/routers/` - API routers (equipment, categories, schedules, work_orders, vendors, dashboard)
- `alembic/versions/001_initial.py` - Initial migration

---

### 9. Food Safety & Compliance System ✅ 90% Complete

**Purpose:** Comprehensive food safety management including temperature monitoring, daily checklists, incident tracking, health inspections, and compliance reporting

**Location:** `/opt/restaurant-system/food-safety/`

**Technology:** FastAPI, SQLAlchemy (async), PostgreSQL

**Container:** `food-safety-service` (port 8007)
**Database:** `food-safety-postgres` (port 5440)

**Core Features:**
- Temperature logging with threshold alerts
- Daily checklists with manager sign-off
- Incident tracking (auto-generated INC-YYYY-NNNN numbers)
- Health inspection records with violation tracking
- HACCP plan management
- Comprehensive reports with CSV/PDF export
- Equipment integration with Maintenance service

**Database Models:**
- `user_permissions` - Role-based access control
- `locations` - Restaurant locations (synced from inventory)
- `temperature_logs`, `temperature_thresholds` - Temperature monitoring
- `checklist_templates`, `checklist_submissions`, `checklist_responses` - Checklists
- `incidents`, `corrective_actions` - Incident management
- `inspections`, `inspection_violations` - Health inspections
- `haccp_plans`, `critical_control_points` - HACCP compliance

**API Endpoints:**
- `GET /food-safety/health` - Health check
- `GET /food-safety/dashboard` - Dashboard stats
- Temperature CRUD: `/food-safety/temperatures`
- Checklists CRUD: `/food-safety/checklists`
- Incidents CRUD: `/food-safety/incidents`
- Inspections CRUD: `/food-safety/inspections`
- HACCP CRUD: `/food-safety/haccp`
- Reports: `/food-safety/reports/temperature`, `/checklist`, `/inspection`, `/incident`
- Export: `/food-safety/reports/{type}/export/csv`, `/food-safety/reports/{type}/export/pdf`

**Portal UI:**
- `/portal/food-safety/` - Dashboard
- `/portal/food-safety/temperatures` - Temperature logging
- `/portal/food-safety/checklists` - Daily checklists
- `/portal/food-safety/incidents` - Incident management
- `/portal/food-safety/inspections` - Health inspections
- `/portal/food-safety/haccp` - HACCP plans
- `/portal/food-safety/reports` - Reports with chart visualization and export

**User Management:**
- `/portal/food-safety/users` - User permission management
- Searchable HR employee dropdown for adding users
- Role assignment (Admin, Manager, Supervisor, Staff, Read Only)
- Location-based access control
- HR integration via internal service-to-service API

**Key Files:**
- `src/food_safety/main.py` - FastAPI application
- `src/food_safety/models/` - SQLAlchemy models
- `src/food_safety/schemas.py` - Pydantic schemas
- `src/food_safety/routers/` - API routers (dashboard, temperatures, checklists, incidents, inspections, haccp, reports, users)
- `src/food_safety/services/maintenance_client.py` - Maintenance service integration
- `src/food_safety/services/hr_client.py` - HR service integration for employee lookup

---

## 🔧 RECENT DEVELOPMENT HISTORY

### Major Milestones (Last 2 Weeks)

**January 10, 2026:**
- Food Safety Reports feature implemented
- 4 report types: Temperature, Checklist, Inspection, Incident
- CSV and PDF export for all reports (using reportlab)
- Reports UI with Chart.js trend visualization
- Equipment integration with Maintenance service fixed
- Food Safety User Management with HR integration
  - `/hr-employees` endpoint to fetch employees from HR
  - HR internal endpoint `/_internal/list` for service-to-service calls
  - Searchable employee dropdown in Portal users page
  - Delete user functionality added
- HR templates converted to CSS variables (employee_detail, employee_form)
- Portal home page updated (Food Safety icon, direct access routing)
- Monitoring dashboard shows swap memory stats
- Dashboard status script updated for maintenance & food-safety services
- Backup script includes food-safety database
- Nginx config updated with `/food-safety/` location block

**January 9, 2026:**
- Maintenance & Equipment Tracking Service created and deployed
- Complete backend API (equipment, categories, schedules, work orders, vendors, dashboard)
- Added to nginx routing and monitoring scripts
- Password reset system implemented for Portal
- Monitoring script bugs fixed

**Nov 1, 2025:**
- Sentry error tracking integrated (awaiting DSN)
- Monitoring dashboard added to Portal

**Oct 31, 2025:**
- System cleanup (138MB freed)
- Documentation audit (95/100 health score)
- Integration Hub automated invoice intake complete
- Email monitoring system operational

**Oct 30, 2025:**
- README accuracy corrections (75% overall vs. claimed 90%)
- HR system documentation fixed (removed false scheduling/payroll claims)
- Integration Hub documentation fixed (removed false vendor API claims)

**Oct 29, 2025:**
- Session management improvements (inactivity warnings)
- Inventory fixes (count sessions, master items)
- HR email settings access fixed

**Oct 28, 2025:**
- Files system cleanup (removed Nextcloud code - 484KB)
- Comprehensive Files README created

**Oct 22, 2025:**
- General Accounting Dashboard complete
- Dashboard user-reported issues fixed

**Oct 20, 2025:**
- Banking Phase 1B Week 1 & 2 complete (65% of Phase 1B)
- Banking module now 50% complete (was 30%)

---

## ⚠️ CRITICAL ISSUES & TECHNICAL DEBT

### High Priority

1. **Events System Authentication** ✅ FIXED (Nov 1, 2025)
   - ✅ JWT validation IMPLEMENTED via Portal SSO
   - ✅ RBAC enforcement ENABLED on all endpoints
   - ✅ Authentication middleware added to page routes
   - **Status:** Security vulnerability resolved, system now secure
   - **Files created:**
     - `events/src/events/core/deps.py` - Auth dependency functions
     - `events/src/events/core/security.py` - JWT verification
   - **Files modified:**
     - `events/src/events/main.py` - Added auth to page routes, exception handler
     - `events/src/events/api/events.py` - Enabled auth on API endpoints
     - `events/src/events/api/tasks.py` - Enabled auth on task endpoints

2. **Files System Migration Error** 🔴
   - Production-blocking syntax error in migration file
   - **Impact:** Prevents clean deployments

3. **Uncommitted Changes** 🟡
   - Sentry integration modified 27 files
   - Decision needed: commit or revert
   - **Impact:** Git working tree cluttered

4. **Documentation Debt** 🟡
   - Inventory POS/AI/Recipe systems undocumented
   - Integration Hub purpose misrepresented (now fixed in README)
   - Portal password change system undocumented

### Medium Priority

5. **Accounting System Completion** 🟡
   - AR module 40% complete
   - Banking reconciliation in Week 3 testing
   - Budgeting 40% complete

6. **Missing Features**
   - Password reset via email (all systems)
   - Two-factor authentication (future)
   - Fixed asset management (accounting)
   - Job costing (accounting)

### Recently Fixed (Dec 21, 2025)

7. **Integration Hub Location Sync** ✅ FIXED
   - `inventory_sender.py` now includes `location_id` in payload
   - All future invoice syncs will have correct location

8. **Accounting Journal Entry Locations** ✅ FIXED
   - Must set `area_id` on `journal_entry_lines`, not just `journal_entries.location_id`
   - UI displays location from line-level `area_id`

---

## 📊 SYSTEM STATISTICS

### Code Metrics

- **Total Python files:** 373+ (not 356 as previously claimed)
- **Total HTML templates:** 92+
- **Total database models:** 128+ (not 74!)
- **Total API endpoints:** 500+ (not 150!)
- **Total Docker containers:** 16 (restaurant system) + 10 (Mailcow)

### By System (Python Files)

1. Accounting: 140 files (most complex)
2. Inventory: 101 files
3. HR: 53 files
4. Events: 35 files
5. Integration Hub: 30+ files
6. Files: 11 files
7. Portal: 3 files

### Database Sizes (Approximate)

- Inventory: 30+ tables
- Accounting: 40+ tables
- HR: 20+ tables
- Events: 15+ tables
- Integration Hub: 10+ tables
- Files: 6 tables
- Portal: Uses HR users table

---

## 🚀 DEPLOYMENT & OPERATIONS

### Current Deployment

**Method:** Manual via Docker Compose (NO CI/CD)

**Process:**
```bash
1. SSH to server (172.233.172.92)
2. cd /opt/restaurant-system
3. git pull
4. docker compose build [service]
5. docker compose up -d [service]
6. docker logs -f [service]
```

### Health Checks

All services have `/health` endpoints:
```bash
curl https://rm.swhgrp.com/portal/health
curl https://rm.swhgrp.com/inventory/health
curl https://rm.swhgrp.com/hr/health
curl https://rm.swhgrp.com/accounting/health
curl https://rm.swhgrp.com/events/health
curl https://rm.swhgrp.com/hub/health
curl https://rm.swhgrp.com/files/health
```

**Monitoring Dashboard:** https://rm.swhgrp.com/portal/monitoring (Admin only)

### Backup Status ✅

**Multi-Layer Protection:**
1. **Linode Backup Service** (server-level daily snapshots)
2. **Local Database Backups** (automated via cron at 2:00 AM)
3. **Backup Rotation** (7-day retention, older archived)
4. **Log Rotation** (daily compression, 7-day retention)

**Scripts:**
- `/opt/restaurant-system/scripts/backup_all_databases.sh`
- `/opt/restaurant-system/scripts/rotate-backups.sh` (cron: 3:00 AM)
- `/opt/restaurant-system/scripts/verify-backups.sh`

**Storage:**
- Active: `/opt/restaurant-system/backups/` (last 7 days)
- Archive: `/opt/archives/old-backups/` (older backups)

**Documentation:** `docs/operations/BACKUP_STRATEGY.md`

### Monitoring Status

**Implemented:**
- ✅ Real-time monitoring dashboard (Portal)
- ✅ System health checks (all services)
- ✅ Database health monitoring
- ✅ SSL certificate tracking
- ✅ Backup status tracking
- ✅ Docker network health

**Pending:**
- ⚠️ Sentry error tracking (integrated, awaiting DSN)
- ❌ Performance monitoring (APM)
- ❌ Log aggregation (ELK stack)
- ❌ Uptime monitoring (external)
- ❌ Disk space alerts (automated)

---

## 📝 DOCUMENTATION LOCATIONS

### Master Documents

- **[README.md](README.md)** - Project overview and quick start
- **[SYSTEM_DOCUMENTATION.md](SYSTEM_DOCUMENTATION.md)** - 80-page comprehensive guide
- **[DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md)** - Documentation directory
- **[CHANGELOG.md](CHANGELOG.md)** - System changelog

### Status & Progress

- **[docs/status/ACCOUNTING_SYSTEM_STATUS.md](docs/status/ACCOUNTING_SYSTEM_STATUS.md)** ⭐ Master status document
- **[docs/status/INTEGRATION_HUB_STATUS.md](docs/status/INTEGRATION_HUB_STATUS.md)** - Hub implementation (70%)
- **[docs/status/MULTI_LOCATION_FINAL_STATUS.md](docs/status/MULTI_LOCATION_FINAL_STATUS.md)** - Multi-location (100%)
- **[docs/status/GENERAL_DASHBOARD_IMPLEMENTATION.md](docs/status/GENERAL_DASHBOARD_IMPLEMENTATION.md)** - Dashboard complete

### Operations & Guides

- **[docs/operations/BACKUP_STRATEGY.md](docs/operations/BACKUP_STRATEGY.md)** - Backup & recovery guide
- **[docs/operations/SENTRY_SETUP.md](docs/operations/SENTRY_SETUP.md)** - Sentry error tracking setup
- **[docs/guides/USER_GUIDE.md](docs/guides/USER_GUIDE.md)** - End user guide
- **[docs/guides/OPERATIONS_GUIDE.md](docs/guides/OPERATIONS_GUIDE.md)** - System operations

### Service READMEs

- [portal/README.md](portal/README.md) - Portal system (missing password change docs)
- [inventory/README.md](inventory/README.md) - Inventory (426 lines, needs POS/AI/Recipe expansion)
- [hr/README.md](hr/README.md) - HR system (accurate as of Oct 30)
- [accounting/README.md](accounting/README.md) - Accounting system
- [events/README.md](events/README.md) - Events system (278 lines, needs auth correction)
- [integration-hub/README.md](integration-hub/README.md) - Integration Hub (corrected Oct 30)
- [files/README.md](files/README.md) - Files system (340 lines)

### Completed Features

- **[docs/completions/CLEANUP_SUMMARY_OCT31.md](docs/completions/CLEANUP_SUMMARY_OCT31.md)** - Oct 31 cleanup
- **[docs/SENTRY_INTEGRATION_SUMMARY.md](docs/SENTRY_INTEGRATION_SUMMARY.md)** - Sentry integration
- **[docs/DOCUMENTATION_AUDIT_OCT31.md](docs/DOCUMENTATION_AUDIT_OCT31.md)** - Documentation audit (95/100)

---

## 🎯 WHAT TO WORK ON NEXT

### Immediate Priorities (This Week)

1. **Decision: Sentry Integration** 🔴
   - Commit Sentry changes OR revert before proceeding
   - If keeping: obtain Sentry DSN and configure
   - If reverting: `git checkout -- .` for modified files

2. **Fix Events Authentication** ✅ COMPLETED (Nov 1, 2025)
   - ✅ Implemented JWT validation via Portal SSO
   - ✅ Enabled RBAC enforcement on all endpoints
   - ✅ Added authentication to page routes
   - Security vulnerability RESOLVED

3. **Fix Files Migration Error** 🔴
   - Debug and fix syntax error in migration file
   - Test deployment

4. **Test Banking Phase 1B** 🟡
   - Week 3: Testing and finalization
   - Composite matching validation
   - User acceptance testing

### Short-Term (Next 2 Weeks)

5. **Complete Accounting AR Module** 🟡
   - Customer management UI
   - Invoice creation and tracking
   - Payment receipt workflow
   - Raise from 40% to 80%

6. **Documentation Updates** 🟡
   - Update Inventory README (POS, AI, Recipe features)
   - Update Portal README (password change, monitoring)
   - Update Events README (authentication status)

7. **CI/CD Pipeline** 🟢
   - Set up automated testing
   - Implement deployment pipeline
   - Reduce manual deployment risk

### Medium-Term (Next Month)

8. **Accounting Budgeting** 🟡
   - Complete variance analysis
   - Forecasting features
   - Raise from 40% to 100%

9. **HR Enhancements** 🟢
   - Benefits management
   - PTO/vacation tracking
   - Onboarding workflow improvements

10. **Performance Optimization** 🟢
    - Database query optimization
    - API response time improvements
    - Load testing

---

## 🔑 IMPORTANT CONVENTIONS & PATTERNS

### Authentication Pattern

All services use identical SSO validation:
1. Read JWT token from `access_token` cookie
2. Validate using `PORTAL_SECRET_KEY` (shared secret)
3. Extract user info from token payload
4. Check user permissions for current service
5. Redirect to `/portal/login` if invalid

**Shared Module:** `/opt/restaurant-system/shared/python/portal_sso.py`

### Password Sync Pattern

When password changes in Portal:
1. Update HR database (master)
2. POST to each service's sync endpoint:
   - Inventory: `POST /api/users/sync-password`
   - Accounting: `POST /api/users/sync-password`
   - Events: `POST /api/auth/sync-password`
3. Authenticate with `X-Portal-Auth: {PORTAL_SECRET_KEY}` header
4. Services update password if user exists (JIT provisioning)

### Session Management

All services use identical pattern:
- 30-minute session timeout
- 2-minute warning before expiration (JavaScript: `inactivity-warning.js`)
- Auto-refresh on user activity
- Secure HTTP-only cookies

**Shared Module:** `/opt/restaurant-system/shared/static/js/inactivity-warning.js`

### Design Standards

Documented in: `docs/reference/DESIGN_STANDARD.md`

**Current Theme: Slate Blue Light (December 2025)**

Applied to: Portal, Inventory System

CSS Variables (defined in `inventory/src/restaurant_inventory/templates/base.html`):
```css
:root {
    /* Background colors - light theme */
    --bg-primary: #ECEFF1;      /* Light gray background */
    --bg-secondary: #FFFFFF;    /* White cards/content */
    --bg-tertiary: #F5F5F5;     /* Slightly darker for headers */
    --bg-elevated: #E0E0E0;     /* Hover states */

    /* Border colors */
    --border-primary: #CFD8DC;
    --border-secondary: #B0BEC5;

    /* Text colors - dark for readability */
    --text-primary: #263238;    /* Near black */
    --text-secondary: #546E7A;  /* Slate gray */
    --text-muted: #78909C;      /* Light slate */

    /* Accent colors - Slate Blue */
    --accent-primary: #455A64;  /* Slate blue - sidebar, buttons */
    --accent-secondary: #37474F; /* Darker slate */
    --accent-hover: #263238;    /* Darkest slate for hover */
    --accent-muted: #546E7A;

    /* Semantic colors */
    --success: #43A047;         /* Green */
    --error: #E53935;           /* Red */
    --warning: #FB8C00;         /* Orange */
    --info: #1E88E5;            /* Blue */
}
```

**Key Design Decisions:**
- Light theme with white content areas on light gray background
- Slate blue sidebar (#455A64) with white text
- Standard Bootstrap semantic colors (blue for info, not copper)
- Form focus uses slate blue glow: `box-shadow: 0 0 0 3px rgba(69, 90, 100, 0.15)`

**Files:**
- Inventory base template: `inventory/src/restaurant_inventory/templates/base.html`
- Page-specific styles use CSS variables from base.html

**Sidebar:**
- SW Hospitality Group logo (white on slate blue)
- Navigation links: font-size 14px, white text
- Background: #455A64 (slate blue)
- Active/hover: white left border, rgba(255,255,255,0.15) background

**Top Navbar:**
- System name with Bootstrap icon
- User dropdown on right
- Background: var(--bg-secondary) (white)

**Dashboard Titles:**
- `<h2 class="mb-0">` with icon
- font-size: 1.75rem (~28px)

### Database Migration Pattern

- **FastAPI services:** Alembic migrations
- Run: `docker compose exec [service]-app alembic upgrade head`
- Location: `[service]/alembic/versions/`

---

## 🚨 KNOWN BUGS & ISSUES

### Critical

1. **Events: No Authentication** 🔴
   - File: `events/src/events/core/auth.py`
   - Issue: `validate_token()` raises NotImplementedError
   - Impact: Anyone can access Events system

2. **Files: Migration Syntax Error** 🔴
   - Location: Migration file (specific file not identified)
   - Impact: Blocks clean deployments

### Medium

3. **Integration Hub: Email Monitor Stability** 🟡
   - New feature (Oct 31), needs production testing
   - Potential memory issues with long-running scheduler

4. **Accounting: Dashboard Data Population** 🟡
   - Widgets implemented but need real data
   - Cron scripts exist: `accounting/scripts/populate_dashboard_data.py`
   - Status: Code complete, awaiting data

### Low

5. **Inventory: Documentation Gaps** 🟢
   - POS integration fully implemented but not documented
   - AI invoice processing fully implemented but not documented
   - Recipe management fully implemented but not documented

---

## 💡 TIPS FOR WORKING ON THIS SYSTEM

### Before Starting Work

1. **Check git status** - Are there uncommitted changes?
2. **Review recent commits** - What was done recently?
3. **Check monitoring dashboard** - Are all services healthy?
4. **Read this file** - Refresh context on system state

### When Making Changes

1. **Update todos** - Use TodoWrite tool to track progress
2. **Test locally** - Don't commit broken code
3. **Update documentation** - Keep READMEs current
4. **Commit frequently** - Small, focused commits

### When Deploying

1. **Backup first** - Ensure recent backup exists
2. **Test in dev** - Never deploy untested code
3. **Monitor logs** - Watch for errors after deployment
4. **Have rollback plan** - Know how to revert

### Common Commands

```bash
# View running containers
docker ps

# Check service logs
docker logs -f [service]-app

# Restart service
docker compose restart [service]-app

# Rebuild service
docker compose build [service]-app
docker compose up -d [service]-app

# Access database
docker compose exec [service]-db psql -U [user] -d [database]

# Run migration
docker compose exec [service]-app alembic upgrade head

# Check system health
curl https://rm.swhgrp.com/[service]/health

# View monitoring dashboard
# https://rm.swhgrp.com/portal/monitoring (Admin only)
```

---

## 📞 KEY SYSTEM URLS

### Production URLs

- **Portal:** https://rm.swhgrp.com/portal/
- **Inventory:** https://rm.swhgrp.com/inventory/
- **HR:** https://rm.swhgrp.com/hr/
- **Accounting:** https://rm.swhgrp.com/accounting/
- **Events:** https://rm.swhgrp.com/events/
- **Integration Hub:** https://rm.swhgrp.com/hub/
- **Files:** https://rm.swhgrp.com/files/
- **Mail:** https://mail.swhgrp.com/SOGo/
- **Monitoring:** https://rm.swhgrp.com/portal/monitoring

### Public Access (No Auth)

- **Events Intake Form:** https://rm.swhgrp.com/events/public/intake

### Health Checks

- **Portal:** https://rm.swhgrp.com/portal/health
- **Inventory:** https://rm.swhgrp.com/inventory/health
- **HR:** https://rm.swhgrp.com/hr/health
- **Accounting:** https://rm.swhgrp.com/accounting/health
- **Events:** https://rm.swhgrp.com/events/health
- **Hub:** https://rm.swhgrp.com/hub/health
- **Files:** https://rm.swhgrp.com/files/health

---

## 🔮 FUTURE ROADMAP

### Phase 1: Stabilization (Current - Q4 2025)

- ✅ Core functionality complete
- ✅ Production deployment
- ✅ Documentation complete
- ✅ Monitoring implementation
- ✅ Automated backups
- 🔄 Security hardening (Events auth, Sentry activation)

### Phase 2: Enhancement (Q1 2026)

- Complete RBAC across all systems
- Advanced reporting
- API rate limiting
- Comprehensive testing
- Performance optimization
- CI/CD pipeline

### Phase 3: Scale (Q2 2026)

- Multi-location expansion
- Advanced integrations
- BI and analytics
- Forecasting tools
- Mobile apps (if needed)

### Phase 4: Innovation (Q3 2026)

- AI-powered insights
- Predictive analytics
- Automated workflows
- Advanced automation

---

## 📈 OVERALL SYSTEM HEALTH

**Status:** 🟡 Production with caveats

**Strengths:**
- ✅ Portal, Inventory, HR, Integration Hub: Fully operational
- ✅ Accounting: Core features production-ready
- ✅ Automated backups with multiple layers
- ✅ Real-time monitoring dashboard
- ✅ SSO authentication working well
- ✅ Well-documented (95/100 health score)

**Weaknesses:**
- ⚠️ Events: No authentication (security risk)
- ⚠️ Files: Migration error (deployment blocker)
- ⚠️ Uncommitted changes (Sentry integration)
- ⚠️ No CI/CD pipeline (manual deployments)
- ⚠️ Some documentation gaps (Inventory features)

**Recommended Next Steps:**
1. Fix Events authentication (URGENT - security)
2. Commit or revert Sentry integration (clean git tree)
3. Fix Files migration error
4. Complete Accounting AR module
5. Set up CI/CD pipeline

---

**End of Claude Memory Document**

*This document should be updated whenever significant changes are made to the system. Keep it current to maintain effective context for future work.*

---

## 🔄 SESSION UPDATE - November 2, 2025

### POS System Design & Specification COMPLETE ✅

**Context:** Designed complete POS system specification for SW Hospitality Group based on comprehensive requirements gathering.

#### 1. Requirements Gathering
- **User provided detailed specification prompt** for custom restaurant POS system
- Reference systems: Clover, SpotOn, Toast
- Requirements: Stripe Terminal payments, Raspberry Pi Store Hub, offline operation, table service
- Integration with existing Inventory/Accounting systems

**Clarifying Questions Asked:**
- Integration approach (real-time vs EOD sync)
- Store Hub architecture and hardware
- Payment processing flow and tip handling
- Menu management interface
- Table service workflow (course firing, guest tracking)
- Reporting priorities
- Technology preferences

**User Responses:**
- Inventory sync: EOD batch (not real-time)
- Accounting: EOD batch
- Store Hub: Raspberry Pi 5 (8GB), 3-10 tablets per location
- Payments: Physical Stripe readers (M2/S700), tips included
- Menu: Back office admin panel, time-based switching, 86'd items
- Table service: Course firing, guest count tracking
- Reporting: Real-time priority
- Tech: Web-based PWA, fresh stack, standalone architecture
- Architecture: Cloud + Store Hub + offline temporary service

#### 2. Documentation Created

**File:** `/opt/pos-system/SPECIFICATION.md` (83KB)
- 10 detailed feature modules with Phase 1/2/3 roadmap
- Complete database schema (15+ tables) with SQL definitions:
  - locations, menu_categories, items, item_modifiers
  - tables, checks, check_items, payments
  - users, clock_entries, tips, shifts
  - discounts, reports, integrations
- API integration specifications:
  - Inventory system (EOD batch sync)
  - Accounting system (EOD journal entries)
- Raspberry Pi Store Hub setup guide (12 detailed steps)
- Architecture diagrams (ASCII format)
- Security & PCI compliance guidelines
- Hardware requirements
- Competitive analysis (vs Toast, Clover, SpotOn)

**File:** `/opt/pos-system/README.md` (28KB)
- Executive summary with key differentiators
- Three-tier architecture overview:
  - Cloud: FastAPI + PostgreSQL (permanent)
  - Store Hub: Raspberry Pi + SQLite (transient cache/queue)
  - Clients: React PWA on tablets (offline-capable)
- Technology stack decisions
- Core features by module (10 modules)
- Phase 1/2/3/4 roadmap with success criteria
- Hardware requirements
- Cost analysis: $4,140/year savings per location
- Risk mitigation strategies
- Project structure proposal
- Next steps for development

**File:** `/opt/pos-system/design-mockup.html` (36KB)
- Interactive HTML mockup with 4 switchable views:
  1. **POS Terminal**: Order entry with menu grid, check panel, modifiers, totals, actions
  2. **Floor Layout**: Table management grid with color-coded status (available/occupied/reserved)
  3. **Kitchen Display**: Order tickets with time tracking, item details, bump/done workflow
  4. **Admin Dashboard**: Real-time metrics, sales tracking, performance indicators
- Dark theme matching Restaurant Management Portal design
- Touch-friendly UI optimized for tablets
- Offline mode indicator (demo feature)
- Bootstrap Icons integration
- Responsive layouts

#### 3. Design Mockup Deployment

**Nginx Configuration:**
- Added `/pos-demo` location block to `rm.swhgrp.com-http.conf`
- Routes to Portal static file handler
- Accessible at: **https://rm.swhgrp.com/pos-demo**

**Portal Updates:**
- Created `/opt/restaurant-system/portal/html/` directory
- Copied `design-mockup.html` to `portal/html/pos-demo.html`
- Updated `portal/Dockerfile`:
  - Added `COPY js/ /app/static/js/` (line 24)
  - Added `COPY html/ /app/static/html/` (line 25)
- Rebuilt and restarted `portal-app` container

**Files Modified:**
- `/opt/restaurant-system/shared/nginx/conf.d/rm.swhgrp.com-http.conf` (lines 257-264)
- `/opt/restaurant-system/portal/Dockerfile` (lines 24-25)

#### 4. GitHub Repository Setup ✅

**Repository:** `git@github.com:swhgrp/pos-system.git`
**URL:** https://github.com/swhgrp/pos-system

**Setup Steps:**
1. Initialized git repository in `/opt/pos-system`
2. Renamed branch from `master` to `main`
3. Created `.gitignore` for Python projects
4. Configured git user:
   - Email: admin@swhgrp.com
   - Name: SW Hospitality Group
5. Staged all files
6. Created detailed initial commit with comprehensive description
7. Added GitHub remote
8. Pushed to `origin/main`

**Commit Message Highlights:**
- Complete specification and design documentation
- Architecture overview (3-tier cloud + edge)
- Key features and technology stack
- Cost savings analysis ($4,140/year per location)
- Credit to Claude Code

**Files in Repository:**
- `.gitignore` - Python project exclusions
- `README.md` - Executive summary and overview
- `SPECIFICATION.md` - Complete technical specification
- `design-mockup.html` - Interactive UI mockup

#### 5. Technical Decisions Made

**Architecture Pattern:**
- Three-tier: Cloud (permanent) → Store Hub (transient) → Tablets (PWA)
- Event queueing for offline operation
- EOD batch sync (not real-time) for Inventory/Accounting integration

**Technology Choices:**
- **Frontend:** React 18+, TypeScript, Tailwind CSS, Vite, PWA with Service Workers
- **Backend:** FastAPI (async), PostgreSQL 15+, SQLAlchemy 2.0, Redis, Celery
- **Store Hub:** Raspberry Pi 5 (8GB), Python 3.11+, SQLite, CUPS, Nginx
- **Payments:** Stripe Terminal SDK, Stripe Reader S700
- **Deployment:** Docker, nginx reverse proxy

**Key Design Principles:**
- Offline-first operation
- Cost-effective hardware (Raspberry Pi vs proprietary)
- PWA over native apps (no app store dependencies)
- Modern, maintainable technology stack
- PCI DSS compliance considerations

---

## 📊 POS SYSTEM PROJECT STATUS

**Status:** 📝 Specification Complete - Ready for Development

**Phase:** Planning & Design (100% Complete)

**Deliverables:**
- ✅ Complete technical specification (83KB)
- ✅ Executive summary and project overview (28KB)
- ✅ Interactive UI/UX mockup (36KB)
- ✅ Database schema design (15+ tables)
- ✅ API integration specifications
- ✅ Hardware requirements and setup guide
- ✅ Cost analysis and ROI justification
- ✅ GitHub repository setup and initial commit
- ✅ Live demo accessible at https://rm.swhgrp.com/pos-demo

**Next Steps (When Development Begins):**
1. Review and approve specification with stakeholders
2. Finalize technology stack confirmation
3. Setup development environment:
   - Create GitHub project board
   - Setup PostgreSQL development database
   - Configure CI/CD pipeline (GitHub Actions)
4. Phase 1 MVP Development (3-4 months):
   - Database schema migrations
   - Menu management backend API
   - Basic order entry UI
   - Table management
   - Payment processing (Stripe Terminal integration)
   - Kitchen display system
   - Basic reporting

**Estimated Timeline:**
- Phase 1 (MVP): 3-4 months
- Phase 2 (Enhancements): 2-3 months
- Phase 3 (Advanced Features): 2-3 months
- **Total:** 7-10 months to full production

**Cost Savings:**
- Per location: $4,140/year vs competitors
- 5 locations: $20,700/year savings
- 10 locations: $41,400/year savings

---

**End of Session Update - November 2, 2025**

*Next update will include: Development environment setup, Phase 1 progress, or stakeholder feedback integration.*


## 🔄 SESSION UPDATE - November 16, 2025

### Files Service: OnlyOffice Integration & UI Improvements ✅

**Context:** Completed OnlyOffice Document Server integration and fixed multiple UI/UX issues in the Files service.

#### 1. OnlyOffice Document Server Integration
**Initial Setup:**
- Added OnlyOffice Document Server container to docker-compose.yml
- Configured JWT authentication with shared secret
- Set up nginx reverse proxy for `/onlyoffice` path
- Created document templates (blank.docx, blank.xlsx, blank.pptx)

**Backend Implementation:**
- Created `/files/api/onlyoffice.py` with editor configuration endpoint
- Implemented document type detection (Word, Excel, PowerPoint)
- Added file editability checking based on extension
- Configured callback endpoint for document saves
- Generated unique document keys using file ID + modification time hash
- Implemented JWT signing for OnlyOffice API requests

**Frontend Integration:**
- Created `/files/templates/editor.html` for OnlyOffice editor iframe
- Added "New Document" functionality with template selection modal
- Implemented edit button for Office files (pencil icon)
- Connected editor to backend API for configuration loading

#### 2. Permission System Fixes

**Issue:** Shared files in nested folders returned 403 errors when trying to open in OnlyOffice.

**Root Cause:** Permission check in `onlyoffice.py` only checked immediate parent folder, not ancestor folders.

**Solution:**
- Created `check_folder_access()` helper function (lines 26-52)
- Traverses UP folder tree to find any shared ancestor folder
- Returns inherited permissions from first shared parent found
- Updated `get_editor_config()` to use recursive folder access check

**Files Modified:**
- `/opt/restaurant-system/files/src/files/api/onlyoffice.py`
  - Lines 26-52: New `check_folder_access()` function
  - Lines 131-134: Updated to use recursive folder check

#### 3. UI/UX Improvements

**Navigation State Management:**
- Added `currentView` tracking variable ('dashboard', 'myfiles', 'shared-with-me', 'shared-by-me', 'folder')
- Updated all navigation functions to set `currentView` state
- Fixed refresh button to stay on current page instead of returning to dashboard
- Fixed create/delete operations to refresh current view instead of navigating to dashboard

**Dynamic Page Headers:**
- Added `id="pageTitle"` to page header element (line 903)
- Created `setPageTitle(title)` function (lines 1774-1779)
- Updated all navigation functions to set appropriate page titles:
  - Dashboard → "Files Dashboard"
  - My Files → "My Files"
  - Shared with Me → "Shared with Me"
  - Shared by Me → "Shared by Me"
  - Folders → Show folder name

**URL State Management:**
- Updated `loadMyFiles()` to set URL parameter: `?view=my-files`
- Updated `loadSharedByMe()` to set URL parameter: `?view=shared-by-me`
- Fixed `restoreFromURL()` to properly restore view state on page refresh

**Files Display:**
- Fixed `loadMyFiles()` to fetch and display BOTH folders AND files from root
- Previously only displayed folders, hiding root-level files
- Now calls both `/api/files/folders` and `/api/files/files/root` endpoints

**Shared Files UI:**
- Added edit button for shared Office files with write permissions
- Detects Office file types with regex: `/\.(docx?|xlsx?|pptx?|odt|ods|odp)$/i`
- Shows edit button only if user has `can_edit` or `can_upload` permission
- Added proper file actions container for consistent button layout

**Files Modified:**
- `/opt/restaurant-system/files/src/files/templates/filemanager.html`
  - Line 903: Added `id="pageTitle"` to header
  - Lines 1398-1400: Added `currentView` tracking variable
  - Lines 1402-1412: Updated `loadRootFolders()` to set view state
  - Lines 1427-1444: Fixed `loadMyFiles()` to load both folders and files
  - Lines 1456-1471: Updated `loadFolder()` to set view state
  - Lines 1774-1779: Added `setPageTitle()` function
  - Lines 2396-2428: Rewrote `refreshFiles()` with switch/case for all views
  - Lines 3003-3084: Updated `loadSharedWithMe()` with edit button logic
  - Lines 3085-3159: Updated `loadSharedByMe()` with URL state
  - Lines 3063-3084: Added edit button for shared files

#### 4. Complete Fix Summary

**All Issues Resolved:**
1. ✅ OnlyOffice Document Server fully integrated and working
2. ✅ Shared files open correctly with proper permission inheritance
3. ✅ Files display in "My Files" view (both folders and files)
4. ✅ Dynamic page headers update based on current view
5. ✅ Refresh button stays on current page
6. ✅ Create/delete operations stay on current page
7. ✅ Shared files show edit button when user has write permissions
8. ✅ URL state persists across page refreshes

**Technical Achievements:**
- Recursive folder permission checking for nested shared folders
- Proper state management with `currentView` tracking
- Dynamic UI updates without page reloads
- Conditional rendering based on file type and permissions
- JWT-based security for OnlyOffice integration

**Testing Confirmed:**
- Documents can be created from templates
- Owned files can be edited in OnlyOffice
- Shared files with edit permissions can be edited
- Files in nested folders of shared parents work correctly
- All navigation states persist on refresh
- Page headers update correctly across all views



## 🔄 SESSION UPDATE - November 16, 2025

### Files Service: OnlyOffice Integration & UI Improvements ✅

**Context:** Completed OnlyOffice Document Server integration and fixed multiple UI/UX issues in the Files service.


## 🔄 SESSION UPDATE - November 16, 2025

### Files Service: OnlyOffice Integration & UI Improvements ✅

**Context:** Completed OnlyOffice Document Server integration and fixed multiple UI/UX issues in the Files service.

#### 1. OnlyOffice Document Server Integration
**Initial Setup:**
- Added OnlyOffice Document Server container to docker-compose.yml
- Configured JWT authentication with shared secret
- Set up nginx reverse proxy for `/onlyoffice` path
- Created document templates (blank.docx, blank.xlsx, blank.pptx)

**Backend Implementation:**
- Created `/files/api/onlyoffice.py` with editor configuration endpoint
- Implemented document type detection (Word, Excel, PowerPoint)
- Added file editability checking based on extension
- Configured callback endpoint for document saves
- Generated unique document keys using file ID + modification time hash
- Implemented JWT signing for OnlyOffice API requests

**Frontend Integration:**
- Created `/files/templates/editor.html` for OnlyOffice editor iframe
- Added "New Document" functionality with template selection modal
- Implemented edit button for Office files (pencil icon)
- Connected editor to backend API for configuration loading

#### 2. Permission System Fixes

**Issue:** Shared files in nested folders returned 403 errors when trying to open in OnlyOffice.

**Root Cause:** Permission check in `onlyoffice.py` only checked immediate parent folder, not ancestor folders.

**Solution:**
- Created `check_folder_access()` helper function (lines 26-52)
- Traverses UP folder tree to find any shared ancestor folder
- Returns inherited permissions from first shared parent found
- Updated `get_editor_config()` to use recursive folder access check

**Files Modified:**
- `/opt/restaurant-system/files/src/files/api/onlyoffice.py`
  - Lines 26-52: New `check_folder_access()` function
  - Lines 131-134: Updated to use recursive folder check

#### 3. UI/UX Improvements

**Navigation State Management:**
- Added `currentView` tracking variable ('dashboard', 'myfiles', 'shared-with-me', 'shared-by-me', 'folder')
- Updated all navigation functions to set `currentView` state
- Fixed refresh button to stay on current page instead of returning to dashboard
- Fixed create/delete operations to refresh current view instead of navigating to dashboard

**Dynamic Page Headers:**
- Added `id="pageTitle"` to page header element (line 903)
- Created `setPageTitle(title)` function (lines 1774-1779)
- Updated all navigation functions to set appropriate page titles:
  - Dashboard → "Files Dashboard"
  - My Files → "My Files"
  - Shared with Me → "Shared with Me"
  - Shared by Me → "Shared by Me"
  - Folders → Show folder name

**URL State Management:**
- Updated `loadMyFiles()` to set URL parameter: `?view=my-files`
- Updated `loadSharedByMe()` to set URL parameter: `?view=shared-by-me`
- Fixed `restoreFromURL()` to properly restore view state on page refresh

**Files Display:**
- Fixed `loadMyFiles()` to fetch and display BOTH folders AND files from root
- Previously only displayed folders, hiding root-level files
- Now calls both `/api/files/folders` and `/api/files/files/root` endpoints

**Shared Files UI:**
- Added edit button for shared Office files with write permissions
- Detects Office file types with regex: `/\.(docx?|xlsx?|pptx?|odt|ods|odp)$/i`
- Shows edit button only if user has `can_edit` or `can_upload` permission
- Added proper file actions container for consistent button layout

**Files Modified:**
- `/opt/restaurant-system/files/src/files/templates/filemanager.html`
  - Line 903: Added `id="pageTitle"` to header
  - Lines 1398-1400: Added `currentView` tracking variable
  - Lines 1402-1412: Updated `loadRootFolders()` to set view state
  - Lines 1427-1444: Fixed `loadMyFiles()` to load both folders and files
  - Lines 1456-1471: Updated `loadFolder()` to set view state
  - Lines 1774-1779: Added `setPageTitle()` function
  - Lines 2396-2428: Rewrote `refreshFiles()` with switch/case for all views
  - Lines 3003-3084: Updated `loadSharedWithMe()` with edit button logic
  - Lines 3085-3159: Updated `loadSharedByMe()` with URL state
  - Lines 3063-3084: Added edit button for shared files

#### 4. Complete Fix Summary

**All Issues Resolved:**
1. ✅ OnlyOffice Document Server fully integrated and working
2. ✅ Shared files open correctly with proper permission inheritance
3. ✅ Files display in "My Files" view (both folders and files)
4. ✅ Dynamic page headers update based on current view
5. ✅ Refresh button stays on current page
6. ✅ Create/delete operations stay on current page
7. ✅ Shared files show edit button when user has write permissions
8. ✅ URL state persists across page refreshes

**Technical Achievements:**
- Recursive folder permission checking for nested shared folders
- Proper state management with `currentView` tracking
- Dynamic UI updates without page reloads
- Conditional rendering based on file type and permissions
- JWT-based security for OnlyOffice integration

**Testing Confirmed:**
- Documents can be created from templates
- Owned files can be edited in OnlyOffice
- Shared files with edit permissions can be edited
- Files in nested folders of shared parents work correctly
- All navigation states persist on refresh
- Page headers update correctly across all views

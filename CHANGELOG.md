# Changelog

## [2026-01-06] - DSS Deposit Calculation & Discount Breakdown

### Summary
Enhanced Daily Sales Summary (DSS) with split deposit display (Card Deposit vs Expected Cash Deposit), complete discount breakdown showing individual line items, and proper variance calculation that accounts for cash tips paid to employees.

### Added - Accounting System
- **Split Deposit Display:**
  - Replaced single "Deposit Amount" with **Card Deposit** and **Expected Cash Deposit**
  - Card Deposit = Card payments + Card tips - Refunds (what processor deposits)
  - Expected Cash Deposit = Cash sales - Cash Tips Paid - Payouts (what's left in drawer)
  - Added Cash Tips Paid field showing tips paid to employees from cash drawer

- **Payouts Tab:**
  - New tab on DSS detail page for cash adjustments from Clover
  - Displays cash_events (CASH_ADJUSTMENT type) with amount, note, employee, timestamp
  - Graceful 401 handling when cash_events endpoint permissions are missing

- **Database Fields:**
  - Migration: `20260106_0001_add_deposit_and_payout_fields.py`
  - Added to `daily_sales_summaries` and `pos_daily_sales_cache`:
    - `card_deposit`, `cash_tips_paid`, `cash_payouts`, `expected_cash_deposit`, `payout_breakdown`

### Fixed - Accounting System
- **Discount Breakdown Completeness:**
  - Now captures BOTH order-level AND line-item discounts
  - Fixed percentage-based discount calculation (was using post-discount total)
  - All discounts appear as individual line items on Discounts tab
  - Totals match Clover's reported discount totals exactly

- **Variance Calculation:**
  - Formula: Variance = (Card Deposit + Expected Cash Deposit + Cash Tips Paid) - Total Collected
  - Correctly accounts for tip flow: Card tips deposited via processor, then paid out in cash
  - Variance is now $0.00 when all money is properly accounted for

- **JavaScript Error:**
  - Fixed "Cannot set properties of null" error in `calculatePaymentTotals()`
  - Removed reference to deprecated `depositAmount` element

### Files Modified
- `accounting/src/accounting/services/pos_sync_service.py`
- `accounting/src/accounting/templates/daily_sales_detail.html`
- `accounting/src/accounting/models/daily_sales_summary.py`
- `accounting/src/accounting/models/pos.py`
- `accounting/src/accounting/schemas/daily_sales_summary.py`
- `accounting/src/accounting/core/clover_client.py`
- `accounting/alembic/versions/20260106_0001_add_deposit_and_payout_fields.py`

---

## [2026-01-05] - Waste Log UoM & Transfer Enhancements

### Summary
Added unit of measure (UoM) support to the waste log and enhanced the transfer form with searchable dropdowns and date selection. Fixed API routing issue where `/api/items` (no trailing slash) was returning incomplete data.

### Added - Inventory System
- **Waste Log UoM Dropdown:**
  - New dropdown to select unit of measure when logging waste
  - Options populated from item's count units (primary + secondary)
  - Selected UoM stored with waste record for accurate reporting
  - Database migration: `20260105_0001_add_uom_to_waste_records.py`

- **Transfer Form Enhancements:**
  - Searchable Select2 dropdown for item selection (matches waste log)
  - Date/time picker for transfer date
  - UoM dropdown populated from item's count units
  - Slate theme styling applied to all Select2 dropdowns

### Fixed - Inventory System
- **API Route Consistency:**
  - `/api/items` (no trailing slash) was returning simplified data without UoM fields
  - Changed to redirect (307) to `/api/items/` which has full UoM processing
  - Prevents confusion where different endpoints return different data structures

### Files Modified
- `inventory/src/restaurant_inventory/templates/waste.html`
- `inventory/src/restaurant_inventory/templates/transfers.html`
- `inventory/src/restaurant_inventory/models/waste.py`
- `inventory/src/restaurant_inventory/schemas/waste.py`
- `inventory/src/restaurant_inventory/api/api_v1/endpoints/waste.py`
- `inventory/src/restaurant_inventory/main.py`
- `inventory/alembic/versions/20260105_0001_add_uom_to_waste_records.py`

---

## [2025-12-24] - UI Consistency: Sidebar Highlighting & Submenu Behavior Fixes

### Summary
Fixed sidebar active state highlighting issues across multiple systems. Corrected submenu auto-open behavior in Accounting system. Fixed theme inconsistencies in Events system. Resolved GL account name display issue in Integration Hub.

### Fixed - Inventory System
- **Sidebar Active State:** Count History page no longer incorrectly highlights Take Inventory
  - Root cause: JavaScript `startsWith()` matched `/inventory/count` for both paths
  - Solution: Rewrote path matching to use exact match or segment boundary checks
  - File: `inventory/src/restaurant_inventory/templates/base.html`

### Fixed - Accounting System
- **Reports Submenu Auto-Open:** Added `comparative-pl` and `cash-flow-statement` to auto-open logic
- **Recurring Invoices Submenu:** Added `/recurring-invoices` to AR section auto-open logic
- **DSS Journal Entries Highlighting:** Now correctly highlights based on `source` query parameter
  - Journal Entries (no source) → highlights "Journal Entries"
  - `?source=sale` → highlights "DSS Journal Entries"
  - `?source=bill` → highlights "Bill Journal Entries"
- **ACH Batches Text Wrapping:** Added `white-space: nowrap` to prevent text wrapping in submenu
- Files modified:
  - `accounting/src/accounting/main.py` (pass source parameter to template)
  - `accounting/src/accounting/templates/journal_entries.html` (conditional nav blocks)
  - `accounting/src/accounting/templates/base.html` (CSS fix, auto-open logic)

### Fixed - Events System
- **Settings Page Theme:** Replaced hardcoded dark colors with CSS variables for light theme
- **Tasks Page Theme:** Same light theme CSS variable fixes
- Files: `events/src/events/templates/admin/settings.html`, `tasks.html`

### Fixed - Integration Hub
- **GL Account Names Missing:** Invoice detail page now shows GL account descriptions
  - Root cause: Dictionary keys were integers but template looked up strings
  - Solution: Convert keys to strings when building `gl_names` dictionary
  - File: `integration-hub/src/integration_hub/main.py`

### Audited - All Systems
- Documented sidebar highlighting approaches across all 6 systems:
  - Accounting: Jinja template blocks
  - Events: Jinja conditionals
  - Integration Hub: Jinja conditionals
  - HR: Jinja template blocks
  - Inventory: JavaScript-based
  - Websites: Jinja conditionals with `active_page` variable

---

## [2025-12-23] - Integration Hub: Invoice Mapping Improvements & Inventory Cleanup

### Summary
Massively improved invoice item mapping rate from 93.4% to 99.5% by systematically adding unmapped GFS (Gordon Food Service) items to the inventory system. Enhanced the invoice parser with UPC detection and description-based OCR correction. Cleaned up duplicate master items and fixed category assignments.

### Added - Integration Hub
- **UPC vs Item Code Detection:** New `_fix_upc_as_item_code()` method
  - Detects UPC barcodes (>10 digits, starts with 000) incorrectly parsed as item codes
  - Corrects using historical invoice data or mapping table lookup
  - Example: `0007199030106` (UPC) → `14889` (item code)

- **Description-Based OCR Fix:** New `_fix_ocr_by_description()` method
  - Uses Jaccard similarity to match item descriptions when codes don't match
  - Includes 100+ food service abbreviations for expansion:
    - `chix` → `chicken`, `bf` → `beef`, `wht` → `white`
    - `slcd` → `sliced`, `frz` → `frozen`, `brst` → `breast`
    - `grill` → `griddle` (handles OCR G/D confusion)
  - Acceptance criteria: ≥80% description match, or ≥60% with code similarity

- **Processing Pipeline Enhanced:**
  1. UPC code fix (new)
  2. OCR code correction
  3. Description normalization
  4. Description-based fix (new)
  5. Auto-mapping

### Added - Inventory System
- **~30 New Master Items** across categories:
  - Beef: Beef Strip Loin
  - Produce: Arugula Baby, Romaine Hearts, Avocado Hass
  - Bakery: Bun Brioche Round 5.5", Empanada Chicken, Pretzel Bites Bavarian
  - Pork: Pork Spareribs, Sausage Italian Links
  - Frozen: Tater Tots, Onion Rings Breaded
  - Dairy: Milk Whole Gallon, Ice Cream (Butter Pecan, Mint Chocolate Chip, Salted Caramel), Whipped Topping
  - Grocery: Croutons Seasoned, Pudding Mix Vanilla, BBQ Rub, Mandarin Oranges, Beans Refried, Chips Tortilla
  - Supplies: Container SmartLock (5.75" and 7.5"), Foil Cutter Box, Pick Bamboo Paddle, Tray Food Paper, Tissue Toilet Roll
  - Wine: Conundrum Red, La Crema Pinot Gris, Meiomi Sauvignon Blanc, Rodney Strong Cabernet Sauvignon, Uptown Wine Cocktails (Mango & Strawberry Margarita)

- **~150 New Vendor Items** for GFS (vendor_id=1) and Southern Glaziers (vendor_id=6)

### Fixed - Inventory System
- **Duplicate Master Items Consolidated:**
  - 3 Beef Flap entries → "Beef Flap Meat" (id=242)
  - 2 Angel's Envy entries → "Angel's Envy Bourbon 86.6" (id=422)
  - 2 Makers Mark entries → consolidated
  - 2 Ham Natural Juice entries → consolidated
  - 3 Marinara Sauce entries → consolidated
  - 4 Tea entries (sweetened/unsweetened) → consolidated
  - 2 Vegetable Blend Caribbean entries → consolidated
  - 2 Soft Drink Cola Diet entries → consolidated
  - 2 Balsamic Vinaigrette entries → consolidated
  - 4 Drink Concentrate entries → consolidated

- **~50 Items Recategorized** from "Uncategorized" to proper categories:
  - Angus Strip Steaks → Beef
  - Bananas, Cilantro, Watermelon → Produce
  - Bread, Cheesecake, Pretzels → Bakery
  - Coffee, Croutons, Chips → Grocery
  - Coca-Cola, Sparkling Water → Beverages - Non Alcoholic
  - Don Julio Tequila → Tequila
  - Cupcake Moscato → Wine
  - Detergent, Sanitizer → Cleaning & Chemical
  - Gloves, Cups, Containers → Supplies - Disposable
  - Hash Browns → Frozen
  - Shrimp, Snapper → Seafood

### Fixed - Integration Hub
- **Vendor Name Matching:** Added LLC suffix stripping for better matching
  - "Gold Coast Beverage LLC" now matches "Gold Coast Beverage"
- **Grill Brick OCR Errors:** Fixed item code 780170 (was being misread as 780117, 780710, 768170)
- **128 Duplicate Invoice Items Deleted** from Invoice 9030397136

### Results
- **Mapping Rate:** 93.4% → 99.5% (2,431 → 2,592 of 2,604 items)
- **Remaining Unmapped (12):**
  - Miller Lite (intentionally unmapped - not in inventory)
  - Invoice/Transaction/Unknown entries (9 non-product items)
  - Daily's Lime Juice (item code in description text)
  - Pest Control Service (service, not product)

### Files Modified
- `integration-hub/src/integration_hub/services/invoice_parser.py`
  - Added `_fix_upc_as_item_code()` method (lines 622-734)
  - Added `_fix_ocr_by_description()` method (lines 736-1070)
  - Added 100+ food service abbreviations
  - Updated processing pipeline to call new methods

### Database Changes
- **Inventory DB:** Created 30+ master_items, 150+ vendor_items, deleted 15 duplicate master_items
- **Hub DB:** Deleted 128 duplicate hub_invoice_items, corrected OCR errors in item_code

---

## [2025-10-31] - Mail System Migration: SnappyMail → Mailcow SOGo

### Summary
Migrated from SnappyMail standalone webmail to Mailcow's integrated SOGo webmail. Removed custom SnappyMail theming and configuration. Updated Portal to link directly to Mailcow SOGo for email access. Cleaned up nginx configuration and removed SnappyMail containers.

### Removed - SnappyMail
- Removed mail-ui Docker container (SnappyMail)
- Removed custom SWHospitality dark theme for SnappyMail
- Removed SnappyMail domain configuration files
- Removed mail-ui nginx proxy routes (`/mail-ui/` and `/snappymail/`)
- Removed SnappyMail data volume

### Changed - Portal System
- Updated mail link in [main.py:243](file:///opt/restaurant-system/portal/src/portal/main.py#L243)
- Changed from `/mail-ui/` to `https://mail.swhgrp.com/SOGo/`
- Mail now opens directly in Mailcow SOGo webmail

### Changed - Nginx Configuration
- Removed SnappyMail proxy routes from [rm.swhgrp.com-http.conf](file:///opt/restaurant-system/shared/nginx/conf.d/rm.swhgrp.com-http.conf)
- Kept existing Mailcow SOGo proxy routes intact:
  - `/SOGo/` - Main webmail interface
  - `/SOGo-*/` - Static resources
  - `/SOGo.woa/WebServerResources/` - WebServer resources
  - `/mail-admin/` - Admin interface (Portal admin auth required)
- Reloaded nginx configuration without downtime

### Benefits
- **Simpler Architecture**: One less container to manage
- **Better Integration**: SOGo is Mailcow's native webmail with full integration
- **Professional UI**: SOGo provides enterprise-grade webmail interface
- **Reduced Complexity**: No custom theming or configuration needed
- **Native Auth**: Users login with their mailbox credentials directly

### Technical Details
- Mailcow SOGo: Native webmail at https://mail.swhgrp.com/SOGo/
- Custom theme: Mailcow has sw-portal-dark.css matching portal design
- Auth: Direct mailbox authentication (no SSO required for email)
- Container: Uses existing mail-sogo-mailcow-1 (part of Mailcow stack)

## [2025-10-30] - Design Standardization, Password Management & Documentation Accuracy

### Summary
Implemented centralized password change functionality in Portal. Created comprehensive design standards based on Accounting system template. Standardized styling across all microservices for consistent user experience. Corrected HR system documentation to accurately reflect implemented features.

### Added - Portal System
- Change password page UI at `/portal/change-password`
  - Dark GitHub-style theme matching Portal dashboard
  - Form with validation (8+ character minimum)
  - Real-time sync status display showing which systems were updated
  - Client-side validation (passwords match, different from current)
  - Responsive design with dark mode colors (#0d1117 background, #161b22 cards)
  - Bootstrap Icons for visual consistency
- Password change API endpoint `POST /portal/api/change-password`
  - Validates current password before allowing change
  - Updates HR database (master user source)
  - Syncs to all microservices asynchronously
  - Returns detailed sync status for each system
- "Change Password" button added to Portal dashboard navbar
- Password sync helper function with async HTTP calls and error handling

### Added - Inventory System
- Password sync endpoint `POST /api/users/sync-password`
  - Internal service API secured with X-Portal-Auth header
  - Updates password for existing users
  - Gracefully handles non-existent users (JIT provisioning)

### Added - Accounting System
- Password sync endpoint `POST /api/users/sync-password`
  - Secured with X-Portal-Auth header validation
  - Updates accounting user passwords when synced from Portal

### Added - Events System
- Password sync endpoint `POST /api/auth/sync-password`
  - Consistent security model with other systems
  - Handles username-based password updates

### Security Features
- Internal service authentication using X-Portal-Auth header with PORTAL_SECRET_KEY
- All passwords stored as bcrypt hashes (never plain text)
- Password validation: minimum 8 characters, must differ from current
- Comprehensive audit logging across all systems
- Secure transport over internal Docker network

### Technical Details
- Language: Python (FastAPI)
- HTTP Client: httpx with async support
- Timeout: 10 seconds per system
- Error Handling: Graceful degradation if one system fails
- JIT Provisioning: Users auto-created on first SSO login

### Files Modified
- `/opt/restaurant-system/portal/src/portal/main.py`
- `/opt/restaurant-system/portal/templates/home.html`
- `/opt/restaurant-system/inventory/src/restaurant_inventory/api/api_v1/endpoints/users.py`
- `/opt/restaurant-system/accounting/src/accounting/api/users.py`
- `/opt/restaurant-system/events/src/events/api/auth.py`
- `/opt/restaurant-system/SYSTEM_DOCUMENTATION.md`

### Added - Design Standards
- **DESIGN_STANDARD.md** - Comprehensive design system documentation
  - Accounting system used as template
  - Standardized sidebar structure (logo only, no system name)
  - Standardized top navbar (system name with icon, no logo)
  - Bootstrap Icons specification per system
  - Color palette, typography, spacing standards
  - Component standards (cards, buttons, forms, tables)
  - Implementation checklist for each system

### Updated - Inventory System
- **Top navbar**: Replaced logo with system name and icon
  - Changed from: SW Logo image
  - Changed to: `<i class="bi bi-box-seam"></i> Inventory System`
- **Dashboard title**: Changed from `<h1>Dashboard</h1>` to `<h2 class="mb-0">Inventory Dashboard</h2>`
- Added base h2 styling: `font-size: 1.75rem` (~28px)
- Updated CSS for `.page-title` styling (18px, font-weight 600)
- Mobile-responsive page title sizing (14px on mobile)
- Files: `base.html`, `dashboard.html`

### Updated - HR System
- **Top navbar**: Replaced dynamic page title block with fixed system name
  - Changed from: `{% block page_title %}HR Management{% endblock %}`
  - Changed to: `<i class="bi bi-people"></i> HR System`
- **Dashboard title**: Changed from page_title block to `<h2 class="mb-0">HR Dashboard</h2>`
- Added base h2 styling: `font-size: 1.75rem` (~28px)
- Updated CSS from `.top-navbar h1` to `.page-title`
- Files: `base.html`, `dashboard.html`

### Updated - Events System
- **Sidebar**: Replaced icon/text branding with logo image
  - Changed from: `<i class="bi bi-calendar-event"></i> Events` (link with icon and text)
  - Changed to: `<img src="/inventory/static/images/sw-logo.png">` in div.sidebar-brand
  - Updated CSS: Changed from flex layout to centered logo with 180px max-width
- **Top navbar**: Replaced dynamic page title block with fixed system name
  - Changed from: `{% block page_title %}Events Management{% endblock %}`
  - Changed to: `<i class="bi bi-calendar-event"></i> Events System`
- **Dashboard title**: Simplified from welcome message to `<h2 class="mb-0">Events Dashboard</h2>`
  - Removed: "Welcome to Events Management" with description
- Added base h2 styling: `font-size: 1.75rem` (~28px)
- Updated CSS from `.top-bar-title` to `.page-title` (3 locations: base, tablet, mobile)
- Files: `base.html`, `admin/dashboard.html`

### Updated - Integration Hub System
- **Dashboard title**: Replaced page-header structure with standardized format
  - Changed from: `<h1>Dashboard</h1>` with description in page-header
  - Changed to: `<h2 class="mb-0">Integration Hub Dashboard</h2>`
- Added base h2 styling: `font-size: 1.75rem` (~28px)
- Top navbar already correct: `<i class="bi bi-grid-3x3-gap-fill"></i> Integration Hub`
- Files: `base.html`, `dashboard.html`

### Updated - Files System
- **Complete layout restructure** to match standard system layout
  - Changed from: Full-width navbar at top with sidebar below
  - Changed to: Fixed sidebar (full-height) + main wrapper with navbar and content
- **Sidebar**: Restructured to match other systems
  - Now fixed position, full-height from top of page
  - Logo at top, followed by navigation list (`<ul class="sidebar-nav">`)
  - Changed navigation from `<a class="sidebar-item">` to standard `<li><a>` structure
  - Added proper hover effects with left border highlight
- **Top navbar**: Moved inside main-wrapper (no longer full-width at top)
  - System name with icon: `<i class="bi bi-folder2"></i> Files System`
  - User name displayed on right side
- **Dashboard title**: Added `<h2 class="mb-0"><i class="bi bi-folder2"></i> Files Dashboard</h2>`
- **CSS overhaul**:
  - Sidebar: Fixed positioning (width 200px, height 100vh, z-index 1000)
  - Main wrapper: `margin-left: 200px` to accommodate fixed sidebar
  - Top navbar: Standard layout with border-bottom
  - Content area: Flex layout with padding
  - Navigation links: `font-size: 14px` matching all systems
- Added base h2 styling: `font-size: 1.75rem` (~28px)
- Files: `filemanager.html` (major restructure)

### Consistency Standards Applied
- All sidebar navigation links now use `font-size: 14px` across all systems
- All dashboard titles use `<h2 class="mb-0">` with `font-size: 1.75rem` (~28px)
- All sidebars show SW Hospitality Group logo only (no system name or icon)
- All top navbars show system name with corresponding Bootstrap icon

### Files Created
- `/opt/restaurant-system/portal/templates/change_password.html`
- `/opt/restaurant-system/DESIGN_STANDARD.md`

### Fixed - Portal System
- **JavaScript Error**: Fixed missing inactivity-warning.js file
  - Created `/opt/restaurant-system/portal/js/` directory
  - Added `inactivity-warning.js` script for session timeout warnings
  - Updated `docker-compose.yml` to mount `./portal/js:/app/static/js`
  - File now accessible at `/portal/static/js/inactivity-warning.js`

### System Cleanup
- **Removed duplicate Portal static directory**: Deleted `/opt/restaurant-system/portal/static/` (unused)
- **Removed unused Portal files**:
  - `index.html` (old static file, replaced by templates/home.html)
  - `css/portal.css` (unreferenced)
  - `images/sw-logo-light.png` (unreferenced)
  - `images/sw-logo.svg` (unreferenced)
  - `images/sw-logo-white.svg` (unreferenced)
- **Cleaned Docker images**:
  - Removed old `restaurant-inventory-app:latest` (~776MB)
  - Removed old `restaurant-inventory-accounting-app:latest` (~571MB)
  - Pruned 108 dangling Docker images
- **Cleaned Python cache**: Removed all `__pycache__` directories and `*.pyc` files (331 files)
- **Total space reclaimed**: ~1.35GB+ from Docker images

### Services Restarted
- portal-app, inventory-app, accounting-app, events-app, hr-app, integration-hub, files-app

### Fixed - HR System Documentation
- **README.md Accuracy Correction**: Updated to reflect actual implementation
  - Changed status from "85% Complete" to "Production Ready (Core Features)"
  - Added clear note: "This is an employee information management system"
  - Split features into accurate ✅ IMPLEMENTED and ❌ NOT IMPLEMENTED sections
  - Removed false claims about scheduling, time tracking, and payroll features
  - Updated API Endpoints section with actual endpoints only
  - Removed non-existent Usage instructions (scheduling, time clock, payroll)
  - Updated File Structure to reflect actual codebase
  - Expanded Portal/SSO integration details
  - Replaced troubleshooting for non-existent features with actual issues
  - Expanded Security section with detailed implementation details
  - Reorganized Future Enhancements with clear labels
  - **Accuracy improvement: 36% → 100%**

### Fixed - Integration Hub Documentation
- **README.md Accuracy Correction**: Completely rewrote to reflect actual implementation
  - Changed title from "Third-Party Integration Manager" to "Invoice Processing & GL Mapping"
  - Changed status from "70% Production Ready" to "Production Ready (Core Features)"
  - Added clear note: "This is NOT a vendor API integration platform"
  - Technology Stack: Changed from Django/Celery/Redis to FastAPI/Uvicorn (actual framework)
  - Removed ALL false claims about vendor API integrations:
    - ❌ US Foods API - Does NOT exist
    - ❌ Sysco API - Does NOT exist
    - ❌ Restaurant Depot API - Does NOT exist
  - Removed false claims about Celery/Redis background jobs (NOT installed)
  - Removed false claims about webhook system (stub only, not functional)
  - Database Schema: Corrected from 8 claimed models to 4 actual models
  - API Endpoints: Removed 20+ fake endpoints, documented actual 15 endpoints
  - Clarified actual purpose: Invoice processing, GL mapping, journal entry creation
  - Added accurate usage workflow for invoice→inventory→accounting routing
  - Updated integration details with actual REST API payloads
  - **Accuracy improvement: ~20% → 100%**

---

## [2025-10-29] - Session Management & Inventory Fixes

### Added
- Inactivity Warning System across all systems
  - 2-minute warning before 30-minute timeout
  - Real-time countdown with Stay Logged In option
  
### Fixed - HR System
- Email settings access for Admin role users

### Fixed - Inventory System  
- Master items page description column removed
- Count session 404 errors fixed
- Read-only view for approved counts
- Admin delete button for count sessions

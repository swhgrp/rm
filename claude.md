# Claude Memory - SW Hospitality Group Restaurant Management System

**Last Updated:** November 8, 2025 (Evening)
**System Status:** Production (85% Complete - Core systems operational)
**Production URL:** https://rm.swhgrp.com
**Server IP:** 172.233.172.92

---

## 🎯 CURRENT CONTEXT - WHERE WE ARE

### Most Recent Work (Last Session - Nov 8, 2025)

1. **Integration Hub: Major Workflow Improvements** ✅ (Nov 8, 2025) 🚀 **GAME CHANGER**
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
   - OpenAI GPT-4o-mini integration for PDF invoice parsing
   - Intelligent auto-mapper (vendor item codes, fuzzy matching, GL accounts)
   - Email settings UI with connection testing
   - PDF deduplication (SHA-256 hashing)
   - Committed: 63afd14, 9f0e5c7

### Git Status - All Synced ✅

```bash
# Branch: main
# Status: Clean - All changes committed and pushed
# Last push: November 8, 2025
# Latest commits (Nov 8):
#   - 9f1d6ff - docs: Update main README with Integration Hub improvements (v2.7) - PUSHED ✅
#   - a274316 - docs(integration-hub): Update README with Nov 4-8 improvements - PUSHED ✅
#   - 7d1cc9a - feat(integration-hub): Major mapping workflow improvements - PUSHED ✅
# Previous commits (Nov 4-8):
#   - 7d94ccf - fix(events): correct tasks API endpoint - PUSHED ✅
#   - ddc197c - docs: update claude.md with Nov 4 Events changes - PUSHED ✅
#   - 6b984a4 - feat(events): venue-to-location migration - PUSHED ✅
#   - abd4a3a - feat: vendor bill creation from Integration Hub - PUSHED ✅
#   - 36767b3 - Integration Hub: PDF preview/download - PUSHED ✅
#
# Untracked files:
#   - integration-hub/uploads/ (58 invoice PDFs - correctly ignored by .gitignore)
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
| **Files** | 8000 | files_db | FastAPI, SQLAlchemy | 75-80% ⚠️ |

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

**Files:** 140 Python files (most complex system)

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

**Technology:** FastAPI, SQLAlchemy, OpenAI GPT-4o-mini, APScheduler, PyPDF2

**Database:** 7+ models

**CRITICAL CORRECTION:** This is NOT a vendor API integration platform. It does NOT connect to US Foods, Sysco, Restaurant Depot, or any third-party vendor APIs.

**What It Actually Does:**
- ✅ Receives vendor invoices (email, manual upload)
- ✅ AI-powered PDF parsing (OpenAI GPT-4o-mini)
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

### 7. Files System ⚠️ 75-80% Complete

**Purpose:** Document management and file sharing

**Location:** `/opt/restaurant-system/files/`

**Technology:** FastAPI, Local file storage, LibreOffice (document conversion)

**Database:** 6 models

**Storage:** `/app/storage` (persistent volume)

**Critical Issue:** Migration file has syntax error (production blocker)

**Features:**
- ✅ File upload/download (single file, no bulk)
- ✅ File preview (PDFs, images, Office docs)
- ✅ Folder organization
- ✅ File operations (copy, move, rename, delete)
- ✅ Internal sharing with permissions
- ✅ Public share links with passwords
- ✅ Portal SSO integration
- ⚠️ Bulk upload - CLAIMED but NOT implemented
- ⚠️ Bulk operations - NO API endpoints
- ❌ Collaborative editing - NOT implemented
- ❌ Calendar integration - NOT implemented
- ❌ Comments - NOT implemented

---

## 🔧 RECENT DEVELOPMENT HISTORY

### Major Milestones (Last 2 Weeks)

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

**Sidebar:**
- SW Hospitality Group logo only (no system name)
- Navigation links: font-size 14px
- Dark theme (#161b22 background)

**Top Navbar:**
- System name with Bootstrap icon
- User name on right
- Dark theme (#0d1117 background)

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


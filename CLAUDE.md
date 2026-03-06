# CLAUDE.md - SW Hospitality Group Restaurant Management System

## Project Overview
Microservices-based restaurant management platform for SW Hospitality Group.
- **Production URL:** https://rm.swhgrp.com
- **Architecture:** 10 FastAPI microservices behind Nginx reverse proxy, each with its own PostgreSQL database
- **Portal:** Central auth + UI at `/portal/`, serves templates from each service's template directory
- **Last Updated:** March 5, 2026

## Repository Structure
```
restaurant-system/
├── portal/          # Central auth portal + UI templates (FastAPI, Jinja2)
├── inventory/       # Inventory management (source of truth for locations)
├── accounting/      # Accounting, GL, invoices, Clover POS sync
├── hr/              # HR management, employee records
├── events/          # Event planning, BEOs, CalDAV sync
├── integration-hub/ # Vendor invoices, email monitoring, CSV parsing
├── maintenance/     # Equipment tracking, work orders, PM scheduling
├── food-safety/     # Food safety compliance
├── files/           # File management service
├── websites/        # Website management
├── docs/            # Documentation and archived development history
```

## Tech Stack
- **Backend:** FastAPI (Python 3.11), async SQLAlchemy with asyncpg (maintenance, food-safety), sync SQLAlchemy (most others)
- **Database:** PostgreSQL 15, one DB per service, Alembic migrations
- **Frontend:** Jinja2 templates, Bootstrap Icons, vanilla JS (no frameworks)
- **Infrastructure:** Docker Compose (root compose for most services, separate compose for maintenance and food-safety), Nginx reverse proxy
- **Auth:** JWT tokens in HTTP-only cookies, portal-based SSO

## Key Patterns

### Source of Truth Architecture
- **Hub owns:** UoM, Categories, Vendors, Vendor Items, Invoices
- **Inventory owns:** Master Items, Count Units, Location Costs, Order Sheets
- **Accounting owns:** GL Accounts, Journal Entries, Chart of Accounts
- **Inventory service** is source of truth for locations — other services fetch via `/inventory/api/locations/_sync`
- Services communicate via internal HTTP calls on Docker network

### Invoice Cost Update Flow (Single Purchase UOM)
- Hub's `LocationCostUpdaterService` writes directly to Inventory's PostgreSQL DB (not via API)
- **Single purchase UOM per vendor item:** defined by `pack_to_primary_factor` on `hub_vendor_items`
- Cost calculation: `cost_per_primary = unit_price / pack_to_primary_factor` (single deterministic path)
- `pack_to_primary_factor` auto-calculated on vendor item save: `units_per_case × size_quantity` (weight/count) or `units_per_case` (volume)
- **DEPRECATED:** `vendor_item_uoms` table retained for history but no longer used; `matched_uom_id` column kept but all values nulled, FK dropped
- `price_is_per_unit` flag still set for display but NOT used in cost calculation
- Inventory service vendor items page is **read-only** (Hub is source of truth)

### Database Connections
- Most services: sync SQLAlchemy (`Session`, `get_db`)
- Maintenance and Food Safety: **async** SQLAlchemy (`AsyncSession`, `get_db`, `asyncpg`)
  - Maintenance uses `pool_pre_ping=True`, `pool_recycle=300`
  - Maintenance has startup DB warmup with retry (5 attempts, 2s delay) to handle Postgres race conditions

### Portal Templates
- Located in `portal/templates/{service}/` (e.g., `portal/templates/maintenance/`)
- Extend `{service}/base.html`
- Dark theme with CSS variables (`--bg-primary`, `--accent-primary`, etc.)
- Table action buttons use `.actions-wrap` div with `inline-flex` for alignment

### Docker
- **Root `docker-compose.yml`** manages 20 containers: Portal, Inventory, HR, Accounting, Events, Hub, Files, Websites, CalDAV, OnlyOffice, Nginx, Certbot, and their databases/Redis
- **Separate compose files**: `maintenance/docker-compose.yml` (2 containers) and `food-safety/docker-compose.yml` (2 containers)
- Source mounts: only maintenance uses `:ro`; most services have read-write mounts
- Rebuild root services: `docker compose up -d --build {service}` (from repo root)
- Rebuild maintenance: `cd maintenance && docker compose up -d --build`
- Rebuild food-safety: `cd food-safety && docker compose up -d --build`

### Authentication Flow (SSO)
1. User → rm.swhgrp.com → Nginx routes to `/portal/`
2. Portal login → validates against HR database → issues JWT (HTTP-only cookie, 30-min session)
3. User clicks system → Nginx routes directly to service (NOT through Portal)
4. Service validates JWT independently using shared `PORTAL_SECRET_KEY`
5. If invalid: redirect to `/portal/login`
- Keepalive endpoints (`/api/auth/keepalive`) in Events, Accounting, HR, Files ping every 5 min
- Password changes sync from Portal to all services via `POST /api/users/sync-password`

## Common Commands
```bash
# Rebuild a root service (inventory, accounting, hr, events, hub, portal, files, websites)
docker compose up -d --build inventory-app

# Rebuild maintenance or food-safety (separate compose files)
cd maintenance && docker compose up -d --build
cd food-safety && docker compose up -d --build

# Check service logs
docker compose logs --tail=50 inventory-app
cd maintenance && docker compose logs --tail=50 maintenance-service

# Run Alembic migration
docker compose exec inventory-app alembic upgrade head
cd maintenance && docker compose exec maintenance-service alembic upgrade head

# Test an API endpoint
curl -s http://localhost:{port}/endpoint | python3 -m json.tool

# Git commands (repo owned by root, use docker)
docker run --rm -v /opt/restaurant-system:/repo -w /repo alpine/git status
docker run --rm -v /opt/restaurant-system:/repo -v /root/.ssh:/root/.ssh:ro -w /repo alpine/git push origin main
```

## Service Ports (internal → external)
| Service | Internal | External |
|---------|----------|----------|
| Portal | 8000 | 8000 |
| Inventory | 8000 | 8001 |
| HR | 8000 | 8002 |
| Accounting | 8000 | 8003 |
| Events | 8000 | 8004 |
| Integration Hub | 8000 | 8005 |
| Maintenance | 8000 | 8006 |
| Food Safety | 8000 | 8007 |
| Files | 8000 | via nginx |
| Websites | 8000 | via nginx |

## Location ID Reference
| ID | Location Name | Inventory Store ID |
|----|---------------|-------------------|
| 1 | Seaside Grill | 400 |
| 2 | The Nest Eatery | 300 |
| 3 | SW Grill | 500 |
| 4 | Okee Grill | 200 |
| 5 | Park Bistro | 700 |
| 6 | Links Grill | 600 |

- Accounting `area_id` 1–6 matches above; ID 7 = "SW Hospitality Group" (Corporate — should NOT be used for AP bills)
- Integration Hub uses `location_id` (1-6) from inventory system
- `JournalEntryLine.area_id` FK → `areas.id` is how location is tracked on all journal entries

---

## Feature Documentation

### Mobile App Bearer Auth (Mar 2026)
- **Portal endpoints**: `POST /api/mobile/login` (returns JWT as bearer token), `POST /api/mobile/refresh` (refreshes token)
- **Bearer token support** added to: Events (`deps.py`), Food Safety (`auth.py`), HR (`auth.py`), Accounting (`auth.py`)
- Inventory already had Bearer support via `HTTPBearer`
- Pattern: `_try_bearer_auth()` decodes Portal JWT with `PORTAL_SECRET_KEY`, looks up user by username
- iOS app at `/opt/SWHospitality/` (separate repo), SwiftUI, iOS 17+

### Catering Contract PDF (Mar 2026)
- **Template**: `events/src/events/templates/pdf/catering_contract_template.html` — standalone WeasyPrint template
- **Endpoint**: `GET /api/documents/events/{event_id}/contract-pdf`
- **Service**: `pdf_service.py` → `generate_catering_contract_pdf()` calculates financials from `menu_json`/`financials_json`
- **Venue logos**: Embedded as base64 data URIs from `events/src/events/static/logos/`
- **Financial defaults**: tax_rate=6.5%, service_rate=21%, 50% deposit clause
- **Beverage guard**: Only shows beverage section when `bar_type` is set and not empty/none/no_bar
- **Menu rendering**: Item names only (no descriptions), total food cost line, per-section display
- **Legal clauses**: 16 sections including Force Majeure, Cancellation (30%), FL/Palm Beach law

### Calendar Item CalDAV Sync (Mar 2026)
- `sync_calendar_item_to_caldav()` / `remove_calendar_item_from_caldav()` in `caldav_sync_service.py`
- Items with `location_id` sync to all active users at that venue; items without location sync to creator only
- Items use UID format `item-{id}@swhgrp.com` (vs `{id}@swhgrp.com` for events)
- Notes/reminders set `TRANSP: TRANSPARENT` so they don't block time on phone calendars
- Sync triggered on create, update, and delete in `calendar_items.py` API
- Location change handling: removes from old venue calendar before syncing to new one

### Accounting GL Learning & Bank Reconciliation (Mar 2026)
- **GL learning improvements**: Stop-word filtering, reordered pattern priority, competing pattern deactivation
- **Batch GL suggestions**: `POST /batch-gl-suggestions` — loads suggestions for multiple transactions in one call
- **Reconciliation UI**: Default filter = "Unreconciled Only", added search bar, inline GL suggestion badges, `quickAssignGL()` function
- **Dashboard GL Variance**: Changed from bank vs GL balance to sum of unreconciled transactions
- **Custom date range**: Banking dashboard now supports custom date range picker

### Inventory Count Session Reports (Mar 2026)
- **Report view**: `GET /count/{session_id}/report` — printable HTML report grouped by storage area and category
- **CSV export**: `GET /api/v1/count-sessions/{session_id}/export` — CSV download with cost data
- **Cost lookup chain**: location cost → hub pricing → inventory unit_cost → master item cost
- **Template**: `count_session_report.html` with summary totals by area and category

### Vendor Item Code Management & Alias Learning (Feb 2026)
- **Mapped codes endpoint**: `GET /api/vendor-items/{id}/mapped-codes` — shows all distinct item codes from invoices mapped to a vendor item, with invoice count, first/last seen, and `is_canonical` flag
- **Unmap code endpoint**: `POST /api/vendor-items/{id}/unmap-code` — removes incorrect code mappings; sets `inventory_item_id=NULL` and `is_mapped=false`; recalculates affected invoice statuses; prevents unmapping canonical SKU
- **Vendor alias learning**: When users manually map invoice items (`POST /api/items/{id}/map`), the system auto-saves to `learned_sku_mappings` table (vendor_id, item_code, item_description, vendor_item_id)
- **Auto-mapper priority**: (1) exact SKU match → (2) learned mapping match → (3) fuzzy description match
- **Vendor item detail page** (`vendor_item_detail.html`): Shows mapped codes tab, invoice history, and unmap actions
- **UOM container matching**: `_find_specific_container_uom()` uses unit-symbol-aware patterns (e.g., "Bottle 1L%" won't match "Bottle 187ml")

### Invoice Post-Parse Validation (Feb 2026)
- **Post-parse validator** (`post_parse_validator.py`): runs after AI/CSV parsing, before auto-mapping
- **Per-item checks**: price_anomaly (>$500), qty_anomaly (>999), possible_sku_as_price, possible_field_swap, possible_fee
- **Invoice-level**: reconciles `sum(line_totals)` vs `(total_amount - tax_amount)`, flags if >5% AND >$5 mismatch
- **`needs_review` status**: sits between 'mapping' and 'ready', blocks auto-send
- **Low-confidence hold**: fuzzy_name mappings with confidence < 0.8 trigger `needs_review`
- **Auto-reparse**: `email_monitor.py` triggers `reparse_with_vendor_rules()` after first parse if vendor has rules
- **Approve endpoint**: `POST /api/invoices/{id}/approve-review` clears flags, re-evaluates status

### Vendor Item Name Normalization (Feb 2026)
- `to_title_case()` in `utils/text_utils.py` — shared utility for smart food/restaurant title casing
- `HubVendorItem` has `@validates('vendor_product_name')` — auto-normalizes on any create/update
- Handles: abbreviations (IPA, IQF, PET, AA), number+unit combos (16oz, 750ml), ordinals (25th), apostrophes (D'Asti), hyphens (Bag-in-Box), slashes (Mozzarella/Provolone)

### Inventory Order Sheets (Feb 2026)
- **Order sheet templates**: Reusable per-location lists of hub vendor items with par levels; model in `models/order_sheet_template.py`
- **Order sheets**: Filled instances from templates; snapshot vendor data at creation for historical accuracy; status: DRAFT → COMPLETED → SENT
- **Key fields**: `hub_vendor_item_id` (cross-DB reference, no FK), `par_level`, `on_hand`, `to_order`, plus denormalized snapshot (`item_name`, `vendor_sku`, `vendor_name`, `category`, `unit_abbr`)
- **Templates**: `order_sheet_templates.html` (manage), `order_sheets.html` (list), `order_sheet_fill.html` (fill), `order_sheet_print.html` (print)
- **API**: `/api/order-sheet-templates/` CRUD + `/api/order-sheets/` CRUD with complete/send workflow
- **Migrations**: `20260218_0001`, `20260218_0002`, `20260218_0003`

### Inventory Count Sessions
- **Dual count types**: Full Inventory (uncounted items set to 0) vs Partial Inventory (uncounted items retain values)
- **Storage area tracking**: Count by storage area with "Mark as Finished" per area
- **Real-time progress**: Items counted counter during active session
- **Template**: `count_session_new.html` with location, date, notes, and type selection

### Inventory Settings — UOM Management (Feb 2026)
- **Units of Measure tab** in settings page: Full CRUD for units organized by category (Weight, Volume, Count, etc.)
- **Unit relationships**: Hierarchical units with reference unit and contains quantity (e.g., Case contains 6 Each)
- **Unit converter**: Built-in from/to conversion calculator
- **API endpoints**: `/api/units/`, `/api/units/categories`, `/api/units/convert`

### Accounting Reports — Multi-Location & Multi-Period (Feb 2026)
- **GL Account Detail** (`account_detail.html`): Location column, location filter dropdown
- **Balance Sheet by Location**: `GET /api/reports/balance-sheet-by-location` — side-by-side columns per location, `area_ids` filter
- **P&L by Location**: `GET /api/reports/profit-loss-by-location` — same pattern
- **Multi-Period P&L**: `GET /api/reports/multi-period-profit-loss` — month-by-month comparison
- **Location picker UI**: Styled chip/pill selector (`.loc-chip` CSS class) shown when "All Locations (By Location)" selected
- **Compare dropdown**: P&L tab has "Compare" for Last 2/3/6/12 Months

### Food Safety Incident System (Feb 2026)
- **Incident CRUD**: Create, view, edit incidents with category-specific `extra_data` JSONB fields
- **Categories**: `food_safety`, `workplace_safety`, `security`, `general` — 24 incident types
- **Edit mode**: `incident_form.html` handles both create and edit via `{{ incident_id }}` template variable
- **Document uploads**: `incident_documents` table, upload/download/delete API at `/incidents/{id}/documents`
- **View modal uploads**: Can upload photos/docs directly from incidents list modal
- **Reporter names**: `reported_by` stores **portal user ID** (not HR employee ID); names fetched from `/portal/api/users/names`
- **Print view**: Standalone HTML at `/portal/food-safety/incidents/{id}/print`

### HR Required Documents (Feb 2026)
- **Required doc types**: ID Copy, Social Security Card, Food Handler/Manager Certificate
- **Upload on create**: `employee_form.html` Required Documents section with `required` file inputs
- **Bug fix**: `uploadRequiredDocuments()` now skips optional TIPS cert instead of throwing
- **Missing docs banner**: `employee_detail.html` shows red warning banner listing missing required docs
- **Employees list badge**: `employees.html` "Docs & Certs" column shows red "X Missing" badge
- **Priority order**: Missing docs > Expired certs > Expiring certs > All Current

### HR Document Upload & Employee Form (Feb 2026)
- **Bootstrap modal fix**: Upload modal uses Bootstrap 5 Modal API (`new bootstrap.Modal()`)
- **Upload form**: Uses `new FormData(e.target)` with `name` attributes on inputs
- **File size validation**: 10MB max, client-side + server-side
- **Hire date protection**: `hire_date` added to `EmployeeUpdate` schema; readonly for non-admins
- **Null field rendering**: All nullable fields use `employee.field if employee and employee.field else ''`

### HR Location-Based Access Control (Feb 2026)
- **Employee filtering**: Uses `employee_locations` many-to-many table (NOT `employee_positions` which is empty)
- **`get_user_location_ids(user)`** in `authorization.py`: returns `None` (admin = all access), `list` (non-admin), `[]` (no assignments)
- **Corrective action form**: Uses `isAdmin` template variable to call correct endpoint
- **Toggle switch UI**: Location assignment modals use toggle switches (`.loc-toggle`, `.loc-toggle-inv`, `.loc-toggle-evt`)

### Security Audit Remediation (Feb 2026)
- **OpenAI API key rotation**: Rotated exposed key in `integration-hub/.env` and `inventory/.env`
- **Hardcoded credentials removed**: All DB connection strings now require env vars across `integration-hub/db/database.py`, `accounting_sender.py`, `invoice_parser.py`, `location_cost_updater.py`, `inventory/core/config.py`, `portal/config.py`
- **Hub invoice line items**: Add (`POST /api/invoices/{id}/items`), delete, recalculate totals/status endpoints

### Maintenance System (Jan 2026)
- **Separate docker-compose** at `maintenance/docker-compose.yml` (port 8006)
- **Async SQLAlchemy** with `asyncpg`, pool_pre_ping, pool_recycle
- **Features**: Equipment CRUD with QR codes, work orders, PM schedules, vendor management, dashboard with alerts
- **Portal UI**: Dashboard, equipment list, work orders, schedules at `/portal/maintenance/`

### Food Safety System (Jan 2026)
- **Separate docker-compose** at `food-safety/docker-compose.yml` (port 8007)
- **Async SQLAlchemy** with `asyncpg`
- **Features**: Temperature logging, daily checklists, incidents, health inspections, HACCP plans, reports with CSV/PDF export
- **Portal UI**: All pages at `/portal/food-safety/`
- **User management**: Role-based (Admin, Manager, Supervisor, Staff, Read Only) with HR employee lookup

### Events System
- **CalDAV sync**: Bidirectional with external calendar server; web app is source of truth for status
- **CalDAV multi-user sync**: Events push to ALL users assigned to the event's venue (via `UserLocation` table), not just the current user
- **Calendar item CalDAV sync** (Mar 2026): Notes/reminders/meetings sync to CalDAV for all users at the item's location; notes/reminders marked as transparent (don't block time)
- **BEO PDF**: WeasyPrint generation with timezone conversion (`_to_et()` filter), pydyf<0.10 required
- **Catering Contract PDF** (Mar 2026): `GET /api/documents/events/{event_id}/contract-pdf` — formal legal contract with venue logo, menu, financials, legal clauses, signature blocks
- **Calendar search**: Search input on calendar page with 300ms debounce, server-side `ilike` filter + client-side filtering
- **Public intake form**: No auth required at `/events/public/intake`
- **RBAC**: 5 roles (admin, event_manager, dept_lead, staff, read_only) enforced on all endpoints
- **Calendar**: FullCalendar.js with status-colored left borders and venue-colored text

### Files System
- **OnlyOffice integration**: Document editing with JWT auth, callback for saves
- **WebDAV**: WsgiDAV server at `/files/webdav/` for desktop sync
- **Sharing**: Recursive folder permission checking, duplicate share prevention
- **Features**: Upload, preview, folder organization, internal/public sharing

### Design Standards — Slate Blue Light Theme
- Light theme: `--bg-primary: #ECEFF1`, `--bg-secondary: #FFFFFF`
- Slate blue sidebar: `--accent-primary: #455A64`
- CSS variables defined in each service's `base.html`
- Mobile responsive: 991.98px breakpoint, mobile header bar, hamburger menu

---

## Important Notes
- Never modify `.env` files (contain production secrets)
- Location data comes from inventory service — don't duplicate
- Maintenance and Food Safety use **async** SQLAlchemy (different from other services)
- CalDAV sync service pushes events to external calendar server
- Customer invoice PDFs can include area/location logos for branding
- **Git permissions**: `.git/` is owned by root; use `docker run --rm -v /opt/restaurant-system:/repo -w /repo alpine/git <command>` for git operations
- **Development history**: Archived session log at `docs/development-history.md`
- **Databases**: 7 PostgreSQL DBs — inventory_db, accounting_db, hr_db (shared by Portal), events_db, hub_db, maintenance_db, food_safety_db
- **Backups**: Automated daily at 2:00 AM, 7-day retention in `/opt/restaurant-system/backups/`

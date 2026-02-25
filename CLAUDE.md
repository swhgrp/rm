# CLAUDE.md - SW Hospitality Group Restaurant Management System

## Project Overview
Microservices-based restaurant management platform for SW Hospitality Group.
- **Production URL:** https://rm.swhgrp.com
- **Architecture:** 10 FastAPI microservices behind Nginx reverse proxy, each with its own PostgreSQL database
- **Portal:** Central auth + UI at `/portal/`, serves templates from each service's template directory

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
```

## Tech Stack
- **Backend:** FastAPI (Python 3.11), async SQLAlchemy with asyncpg (maintenance, food-safety), sync SQLAlchemy (most others)
- **Database:** PostgreSQL 15, one DB per service, Alembic migrations
- **Frontend:** Jinja2 templates, Bootstrap Icons, vanilla JS (no frameworks)
- **Infrastructure:** Docker Compose (root compose for most services, separate compose for maintenance and food-safety), Nginx reverse proxy
- **Auth:** JWT tokens in HTTP-only cookies, portal-based SSO

## Key Patterns

### Service Communication
- Inventory service is **source of truth** for locations - other services fetch via `/inventory/api/locations/_sync`
- Hub is source of truth for vendors, invoices, UOM, and vendor items
- Services communicate via internal HTTP calls on Docker network

### Invoice Cost Update Flow (Multi-UOM System — Feb 2026)
- Hub's `LocationCostUpdaterService` writes directly to Inventory's PostgreSQL DB (not via API)
- **Multi-UOM architecture:** `vendor_item_uoms` table stores multiple purchase UOMs per vendor item with `conversion_factor`
- `hub_invoice_items.matched_uom_id` FK → `vendor_item_uoms` — set at mapping time by matching invoice UOM to vendor item's defined UOMs
- Cost calculation: `cost_per_primary = unit_price / conversion_factor` (deterministic, no guessing)
- `uom_normalizer.py` normalizes invoice UOM strings → standard abbreviations (CS→cs, BTL→btl, LB→lb, etc.)
- Auto-mapper: `match_invoice_uom_to_vendor_uom()` → exact UOM match → normalized → default fallback
- **Legacy fallback:** `price_is_per_unit` flag still set during transition period; cost updater uses `matched_uom_id` when available, falls back to flag
- Manual mapping endpoint also sets `matched_uom_id`
- `vendor_item_uoms.last_cost` / `last_cost_date` auto-populated from invoice prices
- UOM CRUD API: GET/POST/PUT/DELETE at `/api/v1/vendor-items/{id}/uoms`
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

### Accounting Reports — Multi-Location & Multi-Period (Feb 2026)
- **GL Account Detail** (`account_detail.html`): Location column, location filter dropdown, area_id/area_name in `GeneralLedgerLineResponse`
- **GL report on Reports page** (`reports.html` → `renderGeneralLedger`): Also has Location column
- **Balance Sheet by Location**: `GET /api/reports/balance-sheet-by-location` — side-by-side columns per location, `area_ids` comma-separated filter
- **P&L by Location**: `GET /api/reports/profit-loss-by-location` — same pattern, `area_ids` filter
- **Multi-Period P&L**: `GET /api/reports/multi-period-profit-loss` — month-by-month comparison (existing endpoint)
- **Location picker UI**: Styled chip/pill selector (`.loc-chip` CSS class) shown when "All Locations (By Location)" selected
- **Compare dropdown**: P&L tab has "Compare" dropdown for Last 2/3/6/12 Months using multi-period endpoint
- `JournalEntryLine.area_id` FK → `areas.id` is how location is tracked on all journal entries

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
- Backfill script: `scripts/backfill_vendor_item_names.py` (--dry-run supported)

### Food Safety Incident System (Feb 2026)
- **Incident CRUD**: Create, view, edit incidents with category-specific `extra_data` JSONB fields
- **Categories**: `food_safety`, `workplace_safety`, `security`, `general` — 24 incident types
- **Edit mode**: `incident_form.html` handles both create and edit via `{{ incident_id }}` template variable
- **Document uploads**: `incident_documents` table, upload/download/delete API at `/incidents/{id}/documents`
- **View modal uploads**: Can upload photos/docs directly from the incidents list modal (no need to go to edit page)
- **Reporter names**: `reported_by` stores **portal user ID** (not HR employee ID); names fetched from `/portal/api/users/names`
- **Double-submit prevention**: Submit button disabled + text changed on click, re-enabled on error
- **Print view**: Standalone HTML at `/portal/food-safety/incidents/{id}/print`

### HR Required Documents (Feb 2026)
- **Required doc types**: ID Copy, Social Security Card, Food Handler/Manager Certificate
- **Upload on create**: `employee_form.html` Required Documents section with `required` file inputs
- **Bug fix**: `uploadRequiredDocuments()` now skips optional TIPS cert instead of throwing (was causing all uploads to fail)
- **Missing docs banner**: `employee_detail.html` shows red warning banner listing missing required docs
- **Employees list badge**: `employees.html` "Docs & Certs" column shows red "X Missing" badge for employees missing required docs
- **Priority order**: Missing docs > Expired certs > Expiring certs > All Current

### HR Document Upload & Employee Form (Feb 2026)
- **Bootstrap modal fix**: Upload modal uses Bootstrap 5 Modal API (`new bootstrap.Modal()`) — custom `.modal.active` class conflicted with Bootstrap CSS
- **Upload form**: Uses `new FormData(e.target)` with `name` attributes on inputs — more reliable than manual `formData.append()`
- **File size validation**: 10MB max, client-side `alert()` popup before request is sent (server also validates)
- **Hire date protection**: `hire_date` added to `EmployeeUpdate` schema (was previously dropped on every save); readonly for non-admins in edit form
- **Null field rendering**: All nullable fields in `employee_form.html` use `employee.field if employee and employee.field else ''` to prevent rendering Python `None` as string "None"

### HR Location-Based Access Control (Feb 2026)
- **Employee filtering**: Uses `employee_locations` many-to-many table (NOT `employee_positions` which is empty)
- **employees.py**: `list_employees` and `get_employee` filter via subquery on `employee_locations.c.employee_id`
- **`get_user_location_ids(user)`** in `authorization.py`: returns `None` (admin = all access), `list` (non-admin), `[]` (no assignments)
- **Corrective action form**: Uses `isAdmin` template variable to call correct endpoint (`/hr/api/locations/all` vs `/hr/api/locations/`)
- **Auto-select**: When user has only one location, it's auto-selected in dropdowns
- **Toggle switch UI**: Location assignment modals in HR, Inventory, Events use toggle switches (`.loc-toggle`, `.loc-toggle-inv`, `.loc-toggle-evt`)

## Important Notes
- Never modify `.env` files (contain production secrets)
- Location data comes from inventory service - don't duplicate
- Maintenance and Food Safety services use **async** SQLAlchemy (different from other services)
- CalDAV sync service pushes events to external calendar server
- Customer invoice PDFs can include area/location logos for branding

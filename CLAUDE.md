# CLAUDE.md - SW Hospitality Group Restaurant Management System

## Project Overview
Microservices-based restaurant management platform for SW Hospitality Group.
- **Production URL:** https://rm.swhgrp.com
- **Architecture:** 11 FastAPI microservices behind Nginx reverse proxy, each with its own PostgreSQL database
- **Portal:** Central auth + UI at `/portal/`, serves templates from each service's template directory
- **Last Updated:** March 27, 2026

## Infrastructure & Development Environment
- **Production Server:** Linode Ubuntu instance at `/opt/restaurant-system/`
- **Development Machine:** Separate Ubuntu workstation (connects to Linode via SSH)
- **Mac (secondary):** Used for Xcode / iOS builds when needed
- **iOS App Repo:** `/opt/SWHospitality/` on the Linode server (code written here, built on Mac)
- **Android App (planned):** Kotlin Multiplatform — shared module + Jetpack Compose UI
- **Git:** `.git/` owned by root; use `docker run alpine/git` for git operations on the server

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
├── cookbook/         # AI-powered cookbook reference and recipe creation (RAG)
├── websites/        # Website management
├── docs/            # Documentation and archived development history
```

## Tech Stack
- **Backend:** FastAPI (Python 3.11), async SQLAlchemy with asyncpg (maintenance, food-safety), sync SQLAlchemy (most others)
- **Database:** PostgreSQL 15, one DB per service, Alembic migrations
- **Frontend:** Jinja2 templates, Bootstrap Icons, vanilla JS (no frameworks)
- **AI/ML:** Anthropic Claude API (cookbook, GL review), sentence-transformers embeddings, ChromaDB vector store
- **Infrastructure:** Docker Compose (root compose for all services), Nginx reverse proxy
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
- **Root `docker-compose.yml`** manages all 26 containers: Portal, Inventory, HR, Accounting, Events, Hub, Files, Websites, Maintenance, Food Safety, Cookbook, CalDAV, OnlyOffice, Nginx, Certbot, and their databases/Redis
- Source mounts: only maintenance uses `:ro`; most services have read-write mounts
- Rebuild any service: `docker compose up -d --build {service}` (from repo root)

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
# Rebuild any service
docker compose up -d --build inventory-app
docker compose up -d --build maintenance-service
docker compose up -d --build food-safety-service

# Check service logs
docker compose logs --tail=50 inventory-app
docker compose logs --tail=50 maintenance-service

# Run Alembic migration
docker compose exec inventory-app alembic upgrade head
docker compose exec maintenance-service alembic upgrade head

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
| Cookbook AI | 8000 | 8008 |
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

### Mobile App (Mar 2026)
- **iOS app**: `/opt/SWHospitality/` on Linode server (separate repo), SwiftUI, iOS 17+, built on Mac via Xcode
- **Android app (planned)**: Kotlin Multiplatform (KMP) — shared business logic module + Jetpack Compose UI
- **KMP strategy**: Shared Kotlin module for models, API client, auth logic; platform-specific UI (SwiftUI iOS, Compose Android)
- **Portal endpoints**: `POST /api/mobile/login` (returns JWT as bearer token), `POST /api/mobile/refresh` (refreshes token)
- **Bearer token support** added to: Events (`deps.py`), Food Safety (`auth.py`), HR (`auth.py`), Accounting (`auth.py`)
- Inventory already had Bearer support via `HTTPBearer`
- Pattern: `_try_bearer_auth()` decodes Portal JWT with `PORTAL_SECRET_KEY`, looks up user by username
- **iOS status**: Auth complete, Inventory module complete (counts, items, waste, transfers, orders), other modules stubbed
- **Bundle ID**: `com.swhgrp.manager`

### Cookbook AI System (Mar 2026)
- **RAG-based cookbook reference**: Upload PDF cookbooks → extract text → chunk → embed → query with Claude AI
- **Port 8008**, managed in root `docker-compose.yml` (cookbook-app + cookbook-db containers)
- **Stack**: FastAPI, PostgreSQL (metadata), ChromaDB (vector store), transformers/PyTorch (local embeddings), Anthropic Claude API
- **PDF processing pipeline**: pdfplumber text extraction → OCR fallback (pytesseract) → NUL character stripping → word-level chunking (500 words, 50 overlap) → embedding → ChromaDB storage
- **Embedding model**: `sentence-transformers/all-MiniLM-L6-v2` via HuggingFace `transformers` + CPU-only PyTorch (mean pooling) — runs locally, ~2GB RAM
- **Recipe format**: Structured output matching inventory recipe system — category, yield, prep/cook time, ingredients table (qty/unit/item/preparation), numbered instructions
- **Portal UI**: Templates at `portal/templates/cookbook/` — dashboard, lookup, creator, library, books management
- **Pages**: Dashboard (`/portal/cookbook/`), Recipe Lookup, Recipe Creator, Recipe Library, Book Management
- **SSO**: `GET /cookbook/api/auth/sso-login?token=...` validates Portal JWT, sets `portal_session` cookie, redirects to portal cookbook page
- **Auth**: Cookie-based (reads `portal_session`), Bearer token, JIT user provisioning from Portal JWT
- **Access control**: `can_access_cookbook` column on portal users table (default false), manageable from User Management page
- **API endpoints**: `/api/books/upload` (POST), `/api/books` (GET), `/api/query` (POST, recipe lookup), `/api/create` (POST, recipe creator), `/api/recipes` (GET/POST), `/api/queries` (GET)
- **Data persistence**: 3 Docker volumes — `cookbook_data` (DB), `cookbook_uploads` (PDFs), `cookbook_chroma` (vectors)
- **Upload limit**: 200MB (nginx 250m, client-side + server-side validation)
- **Background processing**: PDF upload triggers threaded processing; UI polls `/api/books/{id}/status` every 3s

### Catering Contract PDF (Mar 2026)
- **Template**: `events/src/events/templates/pdf/catering_contract_template.html` — standalone WeasyPrint template
- **Endpoint**: `GET /api/documents/events/{event_id}/contract-pdf`
- **Service**: `pdf_service.py` → `generate_catering_contract_pdf()` calculates financials from `menu_json`/`financials_json`
- **Venue logos**: Embedded as base64 data URIs from `events/src/events/static/logos/`
- **Financial defaults**: tax_rate=6.5%, service_rate=21%, 50% deposit clause
- **Beverage guard**: Only shows beverage section when `bar_type` is set and not empty/none/no_bar
- **Menu rendering**: Item names only (no descriptions), total food cost line, per-section display
- **Legal clauses**: 16 sections including Force Majeure, Cancellation (30%), FL/Palm Beach law

### Price Quote PDF (Mar 2026)
- **Template**: `events/src/events/templates/pdf/price_quote_template.html` — standalone WeasyPrint template
- **Endpoint**: `GET /api/documents/events/{event_id}/quote-pdf`
- **Service**: `pdf_service.py` → `generate_price_quote_pdf()` — simpler than contract, focused on pricing
- **Button**: Added to event detail page admin actions

### Equipment & Rentals Line Items (Mar 2026)
- **Structured equipment items**: Equipment & Rentals section on event menu tab converted from free-text to structured line items (name, quantity, price)
- **Data storage**: `menu_json.equipment_items` array + `menu_json.equipment_notes` for additional notes
- **Financial integration**: Equipment prices included in subtotal calculation alongside food items; service charge and tax apply to full total
- **PDF output**: Quote PDF shows itemized equipment table (qty/price/total); Contract PDF lists equipment items under menu section
- **Backward compat**: Old `menu_json.equipment` text field auto-migrates to `equipment_notes` on page load

### Daily Automated Accounting Review (Mar 2026)
- **Automated daily audit**: 5 AM scheduled job scans Accounting, Hub, and Inventory databases for anomalies
- **Script**: `services/daily_review.py` — all check logic, cross-DB connections, email report generation
- **Cross-DB access**: Accounting service connects to Hub DB and Inventory DB via `HUB_DATABASE_URL` and `INVENTORY_DATABASE_URL` env vars
- **Scheduler**: APScheduler `CronTrigger(hour=5)` in `scheduler.py`, runs in thread pool (`asyncio.to_thread`) to avoid blocking web server
- **Checks implemented (Sections 1-5E from REVIEW_SPEC.md)**:
  - Section 1: Invoice accuracy (total mismatch, price outliers >40% from 90-day avg, implausible quantities)
  - Section 2: GL integrity (unbalanced JEs for all types, corporate area on AP bills, inactive accounts, large manual entries)
  - Section 3: Inventory cost consistency (stale costs after invoice processing)
  - Section 4: Duplicate vendor bill detection
  - Section 5A: Hub ↔ Accounting sync reconciliation (bill lines vs total, missing bills, total mismatches)
  - Section 5B: Invoice pipeline health (stale ready, missing location, statement misclassification, stuck needs_review, credit memos without lines)
  - Section 5C: Beverage distributor pricing validation (discount not captured)
  - Section 5D: Linen service parse quality (Gold Coast Linen price/total swap detection)
  - Section 5E: Delivery fee/fuel surcharge completeness
  - Section 5F: PDF verification & auto-fix — calls Hub verify API (Claude Vision) to auto-correct parsing errors
- **Email report**: HTML report emailed to admin@swhgrp.com with severity breakdown, per-section summary, and detailed findings
- **Persistence**: `daily_review_runs` and `daily_review_findings` tables in accounting DB
- **Migration**: `20260326_0001_add_daily_review_tables.py`
- **Spec**: `REVIEW_SPEC.md` — full specification for all checks, auto-correction rules, duplicate resolution, and report format
- **Phase 1**: Read-only audit + flagging only. No auto-corrections yet (spec defines correction types for future phases)

### Weekly Forensic Accounting Review (Mar 2026)
- **Deep-dive audit**: Sunday 6 AM scheduled job — forensic-level review across Accounting, Hub, and Inventory databases
- **Script**: `services/weekly_review.py` — 7 sections, reuses daily review Finding model and persistence tables
- **Scheduler**: APScheduler `CronTrigger(day_of_week='sun', hour=6)` in `scheduler.py`, runs in thread pool
- **Section 1**: End-to-end transaction flow — traces Hub invoice → Accounting bill → JE, checks amounts match at each hop
- **Section 2**: Vendor forensics — price creep (90-day trends), invoice number gaps, round-number analysis, activity spikes/drops
- **Section 3**: GL forensic analysis — Benford's Law (chi-squared test on first-digit distribution), manual JE review (>$1,000), weekend entries, dormant account activation, reversed entries
- **Section 4**: Inventory cost integrity — cost divergence (>25%), cross-location price consistency
- **Section 5**: Cross-system data integrity — inactive accounts in posted JEs, invalid area references, orphaned master item references in Hub
- **Section 6**: AP/cash flow reconciliation — undeposited funds balance, cash over/short trending, overdue AP bills
- **Section 7**: Tax optimization — capital vs expense (>$2,500 IRS de minimis), repair vs capital improvement (keyword detection), employee meals GL tracking, entertainment/marketing categorization, large non-inventory expenses
- **Email report**: HTML report emailed to admin@swhgrp.com with severity breakdown, per-section summary, and detailed findings
- **Persistence**: Stored in `daily_review_runs` and `daily_review_findings` tables (shared with daily review, prefixed `weekly-` run IDs)
- **Cross-DB access**: Same `HUB_DATABASE_URL` and `INVENTORY_DATABASE_URL` env vars as daily review

### Invoice PDF Verification System (Mar 2026)
- **Claude Vision verification**: Re-reads original PDF via Claude Sonnet Vision (Anthropic API), compares against DB data, auto-corrects discrepancies
- **Triple-check flow**: (1) Extract items from PDF with Claude, (2) Compare & auto-fix, (3) Re-extract to confirm corrections match
- **Service**: `integration-hub/src/integration_hub/services/invoice_verifier.py`
- **API endpoints**: `POST /api/invoices/{id}/verify` (single), `POST /api/invoices/verify-batch` (batch)
- **UI**: "Verify vs PDF" button on invoice detail page for unsent invoices with PDFs
- **Auto-correction**: Fixes item codes (transpositions), quantities, unit prices, line totals; adds missing items
- **Matching strategies**: exact code → near code (1-digit diff) → description+total → total match
- **Daily review integration**: Section 5F auto-verifies and fixes candidates at 5 AM (calls Hub verify API which uses Claude)
- **Post-correction**: Runs post-parse validation and status recalculation; auto-sends if invoice becomes ready
- **Model**: Configurable via `INVOICE_VERIFY_MODEL` env var (default: `claude-sonnet-4-20250514`)
- **Why Claude over GPT-4o**: Claude is more accurate at reading exact item codes, doesn't transpose digits or combine similar line items

### GL Anomaly Review System (Mar 2026)
- **Automated GL sweep**: Nightly job (3 AM) scans journal entries for anomalies using rules engine + Claude AI analysis
- **Rules engine**: `gl_review/rules_engine.py` — pattern-based detection (amount thresholds, duplicate entries, unusual accounts, etc.)
- **AI analyzer**: `gl_review/ai_analyzer.py` — Claude Sonnet analyzes flagged entries for reasoning/severity
- **Models**: `GLAnomalyFlag` (flags with lifecycle: open → reviewed → dismissed → superseded) + `GLAccountBaseline` (statistical baselines)
- **Monthly baseline rebuild**: 4 AM on 1st of month, recomputes statistical baselines per GL account
- **API**: `gl_review/router.py` — flag CRUD, review/dismiss actions, 90-day retention cleanup
- **UI**: `/portal/accounting/gl-review` page, nav link in accounting sidebar
- **Migration**: `20260312_0001_add_gl_anomaly_tables.py`
- **Config**: `GL_REVIEW_AI_MODEL` env var (default: `claude-sonnet-4-6`), requires `ANTHROPIC_API_KEY`

### CSV Expected Vendors & PDF Reference Status (Mar 2026)
- **CSV expected vendors**: `csv_expected_vendors` table tracks vendor+location combos where CSV invoices are the primary format
- **8 vendors configured**: Southern Glazer's (all 6), Breakthru (all 6), GFS (all 6), Gold Coast (5), Southern Eagle (4), Double Eagle (2), Republic National (2), J.J. Taylor (1), Western Beverage (2)
- **`pdf_reference` status**: When a PDF invoice arrives for a CSV-expected vendor, it's stored as reference only (not parsed/mapped)
- **PDF-to-CSV replacement**: When CSV arrives and a matching PDF invoice exists (same number+location), CSV data replaces the PDF data — regardless of current status (including `sent`)
- **Sent invoice reset**: When CSV replaces a previously-sent invoice, `inventory_sent`/`accounting_sent` and sync timestamps are cleared for re-sync
- **Leading-zero matching**: Invoice number comparison strips leading zeros (e.g., `0903123` matches `903123`) — used in both duplicate detection and CSV-over-PDF replacement
- **Duplicate detection**: `invoice_parser.py` uses two-strategy dedup: (1) vendor_id + stripped invoice number, (2) vendor name + stripped invoice number; respects location boundaries
- **CSV file tracking**: `raw_data.csv_file_path` stores path to source CSV file on CSV-replaced invoices for the CSV viewer
- **CSV viewer filtering**: `/api/invoices/{id}/csv-data` endpoint filters multi-vendor/multi-location CSV files to show only rows matching the specific invoice number
- **GFS CSV start date**: GFS added to csv_expected_vendors on 3/25/2026; pre-3/13 GFS invoices are PDF-only (no CSV available)
- **Model**: `CsvExpectedVendor` with `vendor_id`, `location_id`, `is_active`
- **Service**: `csv_preference.py` — `is_csv_expected()` with in-memory caching (refreshes on container restart)
- **UI**: `pdf_reference` status shown as "PDF Reference" badge; grouped under "Statements" tab in invoice list; CSV-source invoices show both PDF and CSV viewer buttons
- **Migration**: `20260318_0001_add_csv_expected_vendors.py`

### GFS CSV Invoice Parsing (Mar 2026)
- **Format detection**: `_detect_csv_format()` identifies GFS, Fintech, or statement CSV formats from column headers
- **GFS column mapping**: `_normalize_gfs_row()` maps GFS columns (`Item Number`, `Item Description`, `Quantity Shipped`, `Case Price`, `Extended Price`) to standard format
- **Catch-weight handling**: When `Catch Weight == 'Y'`, uses `CW Weight` as quantity instead of `Quantity Shipped`
- **Location name fallback**: `get_location_by_store_number()` accepts optional `location_name` for substring/fuzzy matching when store code lookup fails
- **Row deduplication**: Skips duplicate CSV rows based on `(product_number, quantity, unit_price, total)` key
- **CSV-aware auto-mapping**: `map_item(csv_source=True)` skips near-SKU and fuzzy description matching for CSV data (exact SKUs only)
- **Near-SKU preserves original**: `apply_mapping()` no longer overwrites parsed `item_code`/`item_description` on near-SKU matches

### Invoice Parser Improvements (Mar 2026)
- **AI math expression fix**: Post-processes AI responses to evaluate math expressions (e.g., `8.33 / 45`) in JSON values
- **Line item deduplication**: Deduplicates items based on `(item_code, quantity, unit_price, line_total)` — handles GFS PDFs that render items twice
- **Minimum charge adjustment**: If invoice subtotal exceeds sum of line items by >$0.05, adds a "Minimum Charge Adjustment" line item (`MIN-ADJ`)
- **Background parse with vendor rules**: `_parse_invoice_background()` now directly calls `reparse_with_vendor_rules()` if vendor has rules, instead of waiting for email monitor auto-reparse
- **Review flag reset on re-parse**: `reparse_with_vendor_rules()` clears `needs_review` and `review_reason` before re-parsing

### Post-Parse Validator Improvements (Mar 2026)
- **Expanded fee patterns**: Added `EMPTY KEG`, `KEG DEPOSIT`, `KEG RETURN`, `POS EMPTY` to fee detection
- **Fee items exempt from catalog check**: Items matching fee patterns no longer flagged as `unknown_item_code`
- **Mapped items exempt from review**: Already-mapped items with `unknown_item_code` flag no longer trigger invoice-level `needs_review`
- **Better review reason format**: Changed from `item_anomaly:<description>` to `item_anomaly:<flag_name>:<description>` for specific UI display
- **Fresh review reasons on re-validation**: No longer carries over old `review_reason` values

### Vendor Item Duplicate Prevention (Mar 2026)
- **Cross-location dedup**: `VendorItemReviewService` now checks `(vendor_id, vendor_sku)` across ALL locations and statuses (including inactive)
- **Prevents re-creating deactivated items**: Previously only checked within same location

### Daily Sales Summary System (Mar 2026)
- **Clover POS sync**: `POSSyncService` pulls orders, payments, discounts, refunds, and payouts from Clover API daily
- **Discount extraction**: Category-aware breakdown (`Category|DiscountName` keys) with 3-tier GL routing (override → category → fallback)
- **Proportional discount scaling**: Percentage-based Clover discounts (amount=None, percentage only) are proportionally scaled so breakdown sums exactly to `effective_discounts` (authoritative from payments) — eliminates rounding adjustments
- **Automated review & post**: `scripts/dss_review_and_post.py` — validates math, GL mappings, duplicates, payouts; auto-posts clean entries, flags issues
- **Cash deposit logic**: Negative cash deposit (tips exceed cash) credits the location's Safe GL account; positive cash deposits debit the deposit account
- **Third-party payment handling**: DoorDash, UberEats, and other non-cash payments treated like credit cards — included in `card_deposit` calculation, deposited to Undeposited Funds for later reconciliation
- **Deposit formula**: `card_deposit = card_amount + card_tips + third_party_amount - refunds`; `expected_cash = cash_amount - tips_paid_out - payouts`
- **Seaside Grill rolling safe**: CASH payment type maps to `1014 - Safe - Seaside Grill` (not 1091); all cash flows through safe as rolling balance
- **Payout accounting**: Cash payouts from Clover `cash_events` API create DEBIT lines to assigned GL accounts; payouts reduce expected cash deposit
- **Payment GL enforcement**: No fallback to default accounts for unmapped payment types — sync leaves `deposit_account_id=NULL`, caught during posting validation
- **Server-side validation**: `post_daily_sales_summary()` validates all category, payment, and discount GL mappings before creating journal entry
- **Client-side validation**: `postDSS()` JS function checks GL accounts before submitting, displays notification listing missing accounts
- **Deposit reconciliation**: Managers record actual cash deposit, variance creates Cash Over/Short JE
- **Area safe accounts**: Each area has `safe_account_id` FK linking to its Safe GL account (1011-1016)
- **Post-success redirect**: After successful DSS post, redirects to `/accounting/daily-sales` list page

### Accounting Vendor Reactivation (Mar 2026)
- **Inactive vendor reuse**: `VendorService` checks for inactive vendors with matching name before creating duplicates; reactivates if found

### Integration Hub Connection Pooling (Mar 2026)
- **Centralized engine management**: `get_inventory_engine()` in `db/database.py` — shared, pooled connection to Inventory DB
- **Connection pooling**: Main hub engine: pool_size=10, max_overflow=20; Accounting engine: pool_size=3, max_overflow=5
- **Refactored**: Eliminated 20+ inline `create_engine()` calls across `vendor_items.py`, `invoice_parser.py`, `location_cost_updater.py`, `main.py`
- **All engines**: `pool_pre_ping=True`, `pool_recycle=300` for reliability

### Files System Improvements (Mar 2026)
- **Owner-only folder filter**: `GET /api/folders?owner_only=true` — filters folders by current user
- **Search improvements**: Empty query returns all files, better file type and date range filtering
- **UI enhancements**: Improved filemanager template with better search and folder navigation

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
- **Split GL assignment**: `POST /transactions/{id}/assign-gl-split` — split a bank transaction across multiple GL accounts (e.g., tax payments to 3 different tax GLs)
- **Split UI**: Toggle between "Single Account" and "Split Across Accounts" modes in GL assignment modal; dynamic line add/remove with running total and remaining balance
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
- **Approve endpoint**: `POST /api/invoices/{id}/approve-review` clears flags, re-evaluates status; 0-item invoices auto-set to `statement`
- **Mark as Statement**: Invoice detail page shows "Mark as Statement" button for 0-item invoices; `POST /api/invoices/{id}/mark-statement`
- **EFT Notification handling**: GFS EFT Notification PDFs parsed with 0 items should be marked as statements (not invoices)

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
- **Port 8006**, managed in root `docker-compose.yml`
- **Async SQLAlchemy** with `asyncpg`, pool_pre_ping, pool_recycle
- **Features**: Equipment CRUD with QR codes, work orders, PM schedules, vendor management, dashboard with alerts
- **Portal UI**: Dashboard, equipment list, work orders, schedules at `/portal/maintenance/`

### Food Safety System (Jan 2026)
- **Port 8007**, managed in root `docker-compose.yml`
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
- **Databases**: 8 PostgreSQL DBs — inventory_db, accounting_db, hr_db (shared by Portal), events_db, hub_db, maintenance_db, food_safety_db, cookbook_db
- **Backups**: Automated daily at 2:00 AM, 7-day retention in `/opt/restaurant-system/backups/`

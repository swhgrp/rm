# SW HOSPITALITY GROUP - RESTAURANT MANAGEMENT SYSTEM
## Complete System Documentation
**Last Updated:** 2026-02-14
**Status:** Production Ready (~98% Complete)

---

## TABLE OF CONTENTS
1. [System Overview](#system-overview)
2. [Portal System](#portal-system)
3. [Inventory System](#inventory-system)
4. [HR System](#hr-system)
5. [Accounting System](#accounting-system)
6. [Events System](#events-system)
7. [Integration Hub](#integration-hub)
8. [Files System](#files-system)
9. [Websites System](#websites-system)
10. [Maintenance System](#maintenance-system)
11. [Food Safety System](#food-safety-system)
12. [Infrastructure](#infrastructure)
13. [Deployment](#deployment)

---

## SYSTEM OVERVIEW

### Architecture
**Type:** Microservices Architecture
**Deployment:** Docker Compose on dedicated server (172.233.172.92)
**Domain:** rm.swhgrp.com
**Authentication:** Centralized JWT-based SSO via Portal
**Database:** PostgreSQL 15 (separate instance per service)
**Cache/Queue:** Redis 7 (Inventory, Events)
**Web Server:** Nginx with SSL/TLS (Let's Encrypt)

### Technology Stack (ALL Systems)
- **Framework:** FastAPI (Python 3.11)
- **ORM:** SQLAlchemy (sync for most services, async with asyncpg for Maintenance and Food Safety)
- **Migrations:** Alembic
- **Templates:** Jinja2
- **Background Jobs:** APScheduler (NOT Celery)
- **PDF Generation:** WeasyPrint (Events), ReportLab (Accounting, Inventory)
- **AI:** OpenAI GPT-4o Vision (Hub invoice parsing), OpenAI Embeddings (Hub semantic search)

### System URLs
- **Portal:** https://rm.swhgrp.com/portal/
- **Inventory:** https://rm.swhgrp.com/inventory/
- **HR:** https://rm.swhgrp.com/hr/
- **Accounting:** https://rm.swhgrp.com/accounting/
- **Events:** https://rm.swhgrp.com/events/
- **Integration Hub:** https://rm.swhgrp.com/hub/
- **Files:** https://rm.swhgrp.com/files/
- **Websites:** https://rm.swhgrp.com/websites/
- **Maintenance:** https://rm.swhgrp.com/portal/maintenance/
- **Food Safety:** https://rm.swhgrp.com/portal/food-safety/
- **Calendar:** https://rm.swhgrp.com/caldav/
- **Document Editing:** https://rm.swhgrp.com/onlyoffice/

### Infrastructure Status
```
DOCKER COMPOSE: Root (docker-compose.yml) — 20 containers
✅ nginx-proxy          - Nginx reverse proxy (ports 80, 443)
✅ certbot              - Let's Encrypt SSL renewal
✅ portal-app           - Authentication & navigation
✅ inventory-app        - Inventory management
✅ inventory-db         - PostgreSQL 15
✅ inventory-redis      - Redis cache
✅ hr-app               - HR management
✅ hr-db                - PostgreSQL 15
✅ accounting-app       - Accounting system
✅ accounting-db        - PostgreSQL 15
✅ events-app           - Events & catering
✅ events-db            - PostgreSQL 15
✅ events-redis         - Redis cache
✅ integration-hub      - Invoice processing
✅ hub-db               - PostgreSQL 15 + pgvector
✅ files-app            - File management + WebDAV
✅ websites-app         - Website CMS
✅ websites-db          - PostgreSQL 15
✅ caldav               - Radicale calendar server
✅ onlyoffice           - OnlyOffice Document Server

DOCKER COMPOSE: maintenance/docker-compose.yml — 2 containers
✅ maintenance-service  - Equipment & work orders (port 8006)
✅ maintenance-postgres - PostgreSQL 15

DOCKER COMPOSE: food-safety/docker-compose.yml — 2 containers
✅ food-safety-service  - Incident tracking (port 8007)
✅ food-safety-postgres - PostgreSQL 15 (port 5440)

TOTAL: 24 containers across 3 compose files
```

---

## PORTAL SYSTEM

### Purpose
Central authentication and single sign-on portal, system monitoring hub, and UI host for Maintenance and Food Safety.

### Implementation Status: ~95% Complete

**Technology Stack:**
- FastAPI (Python 3.11)
- SQLAlchemy ORM (uses HR database — no own database)
- JWT tokens (jose library)
- Bcrypt password hashing
- Jinja2 templates

**Core Authentication:**
- ✅ JWT token authentication with secure HTTP-only cookies
- ✅ Session management (30-min idle timeout with keepalive)
- ✅ Permission-based system access control (10 systems)
- ✅ Admin user management interface
- ✅ SSO token generation (5-min tokens)
- ✅ Cross-system password synchronization
- ✅ Self-service password reset via email (secure random tokens, 1-hour expiry)

**System Monitoring Dashboard:**
- ✅ Real-time infrastructure monitoring (admin-only)
- ✅ 9+ microservices health status
- ✅ Database health with connection counts
- ✅ SSL certificate expiration tracking
- ✅ Per-database backup status
- ✅ Auto-refresh every 30 seconds
- ✅ URL: https://rm.swhgrp.com/portal/monitoring

**Portal-Hosted UIs:**
- ✅ Maintenance equipment/work orders/schedules/vendors
- ✅ Food Safety incidents/users

**Missing (~5%):**
- ⚠️ `/debug` endpoint has no authentication
- ❌ Two-factor authentication (future)

**Database:**
Portal has NO database of its own — uses HR database (`hr_db`), table: `users`

**Key Endpoints:**
- `GET/POST /portal/login` - Login
- `GET /portal/logout` - Logout
- `GET /portal/settings` - User management (admin only)
- `POST /portal/api/users/{id}/permissions` - Update user permissions
- `GET /portal/api/generate-token/{system}` - Generate SSO token
- `GET/POST /portal/change-password` - Change password + sync to all systems
- `GET /portal/monitoring` - Infrastructure monitoring (admin only)
- `GET /portal/health` - Health check

---

## INVENTORY SYSTEM

### Purpose
Enterprise-grade inventory management with location-aware costing, POS integration, recipe costing, and analytics.

### Implementation Status: 100% Complete ✅

**Technology Stack:**
- FastAPI (Python 3.11)
- SQLAlchemy ORM (sync)
- PostgreSQL 15 (inventory_db)
- Redis (caching)
- APScheduler (POS auto-sync)
- ReportLab (PDF generation)
- Alembic migrations (19+ revisions)

**Files:** 104 Python files, 31 templates, 32 tables, 190+ API routes

**Source of Truth:**
- Locations (code, legal_name, ein, address)
- Master items (central item catalog)
- Count units (per-item counting units with conversion factors)
- Location costs (weighted average cost per item per location)

**Core Features:**
- ✅ Master item catalog with SKUs and categorization
- ✅ Multi-location inventory tracking with storage areas
- ✅ Location-aware costing (per-location weighted average)
- ✅ Multiple count units (primary + 2 additional per item)
- ✅ Live count sessions with auto-save (mobile-responsive)
- ✅ Count templates for recurring counts
- ✅ Waste tracking with UoM dropdown
- ✅ Inter-location transfer workflow (request, approve, ship, receive)
- ✅ Recipe management with ingredient costing
- ✅ POS integration (Clover, Square, Toast) with auto-sync every 10 min
- ✅ Advanced analytics dashboard with charts
- ✅ Comprehensive reporting (usage, variance, valuation)
- ✅ Low stock alerts, audit trail

**Integration:**
- Hub writes directly to Inventory's PostgreSQL for location cost updates
- Accounting fetches locations via `/_sync` endpoint
- Master items reference Hub categories and UOMs

---

## HR SYSTEM

### Purpose
Employee information management system. Manages employee records, documents, and user accounts for Portal SSO.

### Implementation Status: ~95% Complete

**Technology Stack:**
- FastAPI (Python 3.11)
- SQLAlchemy ORM (sync)
- PostgreSQL 15 (hr_db)
- Alembic migrations (10+ revisions)

**Files:** 60+ Python files, 17 templates, 20+ tables

**Core Features:**
- ✅ Employee profile management with encrypted PII
- ✅ Department and position tracking
- ✅ User account management for Portal SSO
- ✅ Emergency contacts (encrypted)
- ✅ Employee document storage with expiration tracking
- ✅ Required documents enforcement (ID, SSN, Food Certificate)
- ✅ Missing documents warning banner and list badge
- ✅ Role-based access control (Admin, Manager, Employee)
- ✅ E-Signature templates (PDF.js field editor + Dropbox Sign integration)
- ✅ HR Forms (Corrective Action, First Report of Injury with signature pads)
- ✅ Enhanced audit logging (field-level tracking, document access logging)

**NOT Implemented (by design — this is NOT an HRIS):**
- ❌ Shift scheduling
- ❌ Time clock / clock in-out
- ❌ Payroll calculation
- ❌ Benefits management
- ❌ PTO/vacation tracking

**Integration:**
- Master source for user authentication (Portal reads HR database)
- Centralized password changes sync to all microservices

---

## ACCOUNTING SYSTEM

### Purpose
Full double-entry accounting system with chart of accounts, journal entries, AP/AR, and financial reporting.

### Implementation Status: ~95% Complete

**Technology Stack:**
- FastAPI (Python 3.11)
- SQLAlchemy ORM (sync)
- PostgreSQL 15 (accounting_db)
- Alembic migrations (39+ revisions)
- Plaid API (bank connections)

**Files:** 119 Python files, 38+ templates, 45+ tables, 250+ API endpoints

**Core Features:**
- ✅ Chart of accounts with hierarchy
- ✅ General ledger with drill-down and location column
- ✅ Journal entries with multi-line support
- ✅ Trial balance, account reconciliation
- ✅ Fiscal period management, year-end close
- ✅ Balance Sheet, P&L, Cash Flow reports
- ✅ Multi-location reports (Balance Sheet by Location, P&L by Location)
- ✅ Multi-period P&L comparisons (2/3/6/12 months)
- ✅ PDF and Excel export

**Accounts Payable:**
- ✅ Vendor management, bill entry/approval
- ✅ Payment processing, AP aging (30/60/90)
- ✅ 1099 tracking, check printing

**Accounts Receivable:**
- ✅ Customer management with credit limits
- ✅ Invoice creation, posting, PDF generation
- ✅ Auto GL posting on invoice post
- ✅ Email invoice delivery
- ✅ Recurring invoices, payment reminders
- ✅ AR aging reports, credit memos

**Banking:**
- ✅ Bank account management, reconciliation
- ✅ Plaid bank connection (transaction sync)
- 🔄 Bank feeds (partial)

**Budgeting:**
- ✅ Budget creation by account
- ✅ Budget vs Actual reports
- 🔄 Variance analysis (partial)

**Other:**
- ✅ COGS tracking, sales analysis
- ✅ Multi-entity support
- ✅ Role-based access (Admin, Accountant, AP/AR Clerk, Read-only)
- ✅ Clover POS daily sales sync via APScheduler

---

## EVENTS SYSTEM

### Purpose
Event planning and catering management with BEO generation, CalDAV calendar sync, and public intake form.

### Implementation Status: ~99% Complete

**Technology Stack:**
- FastAPI (Python 3.11)
- SQLAlchemy ORM (sync)
- PostgreSQL 15 (events_db)
- Redis (caching)
- WeasyPrint (PDF generation)
- FullCalendar.js
- CalDAV (Radicale) bidirectional sync every 15 min

**Files:** 55 Python files, 16 templates, 20+ tables, 80+ API endpoints

**Core Features:**
- ✅ Event CRUD with status workflow (Draft → Pending → Confirmed → In Progress → Completed)
- ✅ Quick Holds (block dates without full event details, auto-expire, convert to event)
- ✅ Public intake form (no auth, hCaptcha, auto-creates client records)
- ✅ Calendar view (month/week/day, color-coded, FullCalendar)
- ✅ CalDAV sync with Radicale server (venue-based calendars)
- ✅ Task management with Kanban board and auto-generation from templates
- ✅ BEO and event summary PDF generation
- ✅ Email notifications (client confirmations, team notifications, task assignments)
- ✅ Client and venue management

**Partial/Missing:**
- 🔄 Menu builder UI (JSON storage only)
- 🔄 Financial integration with Accounting (partial)
- ❌ RBAC enforcement (models exist, not enforced)
- ❌ Audit log population (model exists, never populated)

**Note:** Events has NO Alembic migration files (uses `create_all()` instead)

---

## INTEGRATION HUB

### Purpose
Automated invoice processing hub with email monitoring, AI parsing, vendor item management, and smart routing to Accounting.

### Implementation Status: ~98% Complete

**Technology Stack:**
- FastAPI (Python 3.11)
- SQLAlchemy ORM (sync)
- PostgreSQL 15 + pgvector (hub_db)
- OpenAI GPT-4o Vision (invoice parsing)
- OpenAI Embeddings (semantic search)
- APScheduler (email monitoring every 15 min)
- Alembic migrations (23+ revisions)

**Files:** 61 Python files, 14 templates, 16+ tables, 123 API endpoints

**Critical Note:** This is an internal invoice processing hub, NOT a vendor API platform. It does NOT connect to US Foods/Sysco APIs. It processes vendor invoices received via email/upload and routes data to internal systems.

**Source of Truth:**
- Vendors (with alias normalization and merge)
- Vendor items (with location-aware pricing)
- Invoices and line items
- GL mappings (item-to-GL account)
- UOM and categories

**Core Features:**
- ✅ Email monitoring (IMAP, every 15 min via APScheduler)
- ✅ PDF extraction with SHA-256 deduplication
- ✅ AI invoice parsing (GPT-4o Vision, multi-page)
- ✅ CSV invoice parsing (GFS delivery + store formats)
- ✅ Vendor parsing rules (per-vendor AI instructions)
- ✅ Post-parse validation (price/qty anomalies, total reconciliation)
- ✅ Auto-reparse with vendor rules after initial parse
- ✅ Multi-strategy auto-mapping (SKU → near-SKU → learned → fuzzy → expense)
- ✅ Multi-UOM system (vendor_item_uoms with conversion factors)
- ✅ Catch-weight support (variable-weight meat/seafood)
- ✅ Bulk mapping by description (10x faster)
- ✅ AI semantic search (pgvector, OpenAI embeddings)
- ✅ Vendor merge with alias management
- ✅ Push to Systems (sync vendors to Inventory/Accounting)
- ✅ Expense items vs vendor items separation
- ✅ Vendor item name normalization (smart title case)
- ✅ Smart routing to Accounting (creates balanced journal entries)

**Workflow:**
```
Email → PDF Extract → AI Parse → Validate → Auto-Map → Review → Send → Accounting JE
```

**Integration:**
- → Accounting: Creates balanced journal entries (Dr = Cr)
- → Inventory: Updates location costs directly via PostgreSQL
- ← Email (IMAP): Monitors for invoice PDFs

---

## FILES SYSTEM

### Purpose
Document management with file sharing, WebDAV desktop sync, and OnlyOffice collaborative editing.

### Implementation Status: ~85% Complete

**Technology Stack:**
- FastAPI (Python 3.11)
- SQLAlchemy ORM (sync)
- PostgreSQL 15 (uses HR database for users, own DB for file metadata)
- WsgiDAV 4.3.0 (WebDAV server)
- OnlyOffice Document Server
- LibreOffice (document conversion)
- Alembic migrations

**Files:** 18 Python files, 4 templates, 7 tables

**Core Features:**
- ✅ File upload/download
- ✅ File preview (PDFs, images, Office docs)
- ✅ Folder organization with hierarchy
- ✅ File operations (copy, move, rename, delete)
- ✅ Internal sharing with granular permissions
- ✅ Public share links with passwords and expiration
- ✅ Advanced search (filename, type, date, size)
- ✅ WebDAV server for desktop sync (Mountain Duck, RaiDrive, Finder, Explorer)
- ✅ OnlyOffice document editing (Word, Excel, PowerPoint)
- ✅ Portal SSO integration
- ✅ User-based storage isolation
- ✅ Share access audit logging

---

## WEBSITES SYSTEM

### Purpose
Restaurant website CMS with block-based page builder, menu management, and contact form submissions.

### Implementation Status: ~90% Complete

**Technology Stack:**
- FastAPI (Python 3.11)
- SQLAlchemy ORM (sync)
- PostgreSQL 15 (websites_db)
- Jinja2, Bootstrap 5, HTMX, Pillow

**Files:** 7 Python files, 18 templates, 11 tables

**Core Features:**
- ✅ Multi-site support (manage multiple restaurant websites)
- ✅ Block-based page builder (hero, text, menu preview, gallery, etc.)
- ✅ Menu management with categories, items, dietary flags
- ✅ Image upload with auto-thumbnails
- ✅ Contact form submission capture
- ✅ Activity logging with field-level change tracking
- ✅ Mobile-responsive admin with hamburger menu
- ✅ Live preview with edit mode toggle

**Note:** No Alembic migrations — uses `create_all()` instead

---

## MAINTENANCE SYSTEM

### Purpose
Equipment tracking, work order management, and preventive maintenance scheduling.

### Implementation Status: 100% Complete ✅

**Technology Stack:**
- FastAPI (Python 3.11)
- **Async** SQLAlchemy with asyncpg
- PostgreSQL 15 (maintenance DB)
- Alembic migrations (2 revisions)
- Separate `maintenance/docker-compose.yml` (port 8006)

**Files:** 16 Python files, 5 Portal templates, 10 tables, 40+ API endpoints

**Core Features:**
- ✅ Equipment catalog with hierarchical categories
- ✅ QR code generation for asset tracking
- ✅ Work order management (priority, assignment, status workflow)
- ✅ Preventive maintenance scheduling (daily/weekly/monthly/quarterly/yearly)
- ✅ Maintenance completion logging with document attachments
- ✅ Vendor management for maintenance contractors
- ✅ Dashboard with action items, recent activity, open work orders
- ✅ Portal UI integration with consistent styling

---

## FOOD SAFETY SYSTEM

### Purpose
Food safety and compliance incident tracking with document uploads and category-specific data collection.

### Implementation Status: 100% Complete ✅

**Technology Stack:**
- FastAPI (Python 3.11)
- **Async** SQLAlchemy with asyncpg
- PostgreSQL 15 (food_safety DB)
- Alembic migrations (3 revisions)
- Separate `food-safety/docker-compose.yml` (port 8007)

**Files:** 29 Python files, 5 Portal templates, 18 tables, 80+ API endpoints

**Core Features:**
- ✅ Incident management with 4 categories (food safety, workplace safety, security, general)
- ✅ 24 incident types across categories
- ✅ Category-specific detail fields stored as JSONB (`extra_data`)
- ✅ Incident editing with full field population
- ✅ Document and photo uploads (drag-and-drop, upload from view modal)
- ✅ Status workflow (open → investigating → resolved → closed)
- ✅ Severity levels (critical, high, medium, low)
- ✅ Auto-generated incident numbers (INC-YYYY-NNNN)
- ✅ Reporter name display (from portal user system)
- ✅ Print-friendly incident reports
- ✅ User permission management (admin, manager, user, viewer)
- ✅ HR employee integration
- ✅ Double-submit prevention

---

## INFRASTRUCTURE

### Server Details
- **IP:** 172.233.172.92
- **Domain:** rm.swhgrp.com
- **OS:** Ubuntu Linux
- **Docker:** 3 Docker Compose files (root + maintenance + food-safety)
- **SSL:** Let's Encrypt certificates via Certbot with auto-renewal
- **Firewall:** UFW configured

### Network Architecture

**IMPORTANT:** Portal provides SSO authentication (JWT tokens), but does NOT proxy traffic. Each service is accessed directly through Nginx.

```
Internet → Nginx (ports 80/443) → Reverse Proxy → Microservices
                                                    ├─ Portal (8000) [SSO Auth]
                                                    ├─ Inventory (8000)
                                                    ├─ HR (8000)
                                                    ├─ Accounting (8000)
                                                    ├─ Events (8000)
                                                    ├─ Integration Hub (8000)
                                                    ├─ Files (8000) [Web + WebDAV]
                                                    ├─ Websites (8000)
                                                    ├─ Maintenance (8000)
                                                    ├─ Food Safety (8000)
                                                    ├─ CalDAV (5232)
                                                    └─ OnlyOffice (80)
```

### Nginx Routing (14 URL patterns → 11 upstreams)
- `/portal/` → portal-app:8000
- `/inventory/` → inventory-app:8000
- `/hr/` → hr-app:8000
- `/accounting/` → accounting-app:8000
- `/events/` → events-app:8000
- `/hub/` → integration-hub:8000
- `/files/` → files-app:8000
- `/files/webdav/` → files-app:8000
- `/websites/` → websites-app:8000
- `/maintenance/` → maintenance-service:8000
- `/food-safety/` → food-safety-service:8000
- `/caldav/` → caldav:5232
- `/onlyoffice/` → onlyoffice:80

### Database Strategy
Each service has its own PostgreSQL 15 database:
- `inventory_db` — Inventory service
- `hr_db` — HR service (also used by Portal and Files for user auth)
- `accounting_db` — Accounting service
- `events_db` — Events service
- `hub_db` — Integration Hub (with pgvector extension)
- `websites_db` — Websites service
- `maintenance` — Maintenance service (separate compose)
- `food_safety` — Food Safety service (separate compose)

**Cross-service DB access:**
- Portal reads HR database for user authentication (no own DB)
- Hub writes directly to Inventory's PostgreSQL for location cost updates
- Files uses HR database for user data

### Redis Usage
- `inventory-redis` — Caching and sessions
- `events-redis` — Caching

### Backup Strategy
✅ **IMPLEMENTED:** Automated database backups
- ✅ Daily PostgreSQL dumps for all 8 databases (cron at 2:00 AM)
- ✅ 7-day local retention (`scripts/rotate-backups.sh`)
- ✅ Older backups archived to `/opt/archives/old-backups/`
- ✅ Linode server-level backups (daily snapshots)
- ✅ Log rotation configured via `/etc/logrotate.d/restaurant-system`
- ⚠️ TODO: Remote backup to S3

### Monitoring
✅ **IMPLEMENTED:**
- ✅ Health check monitoring dashboard (Portal /monitoring, admin-only)
- ✅ Service health status tracking (all 10 systems)
- ✅ Database connectivity monitoring
- ✅ SSL certificate expiration tracking (30-day warning)
- ✅ Disk space monitoring (90% warning, 95% critical)
- ✅ Per-database backup status
- ✅ Auto-refresh every 30 seconds
- ✅ Health check scripts (`scripts/health_check.sh`, `scripts/monitor-services.sh`)

⚠️ **Not Implemented:**
- Error tracking (Sentry)
- APM (Application Performance Monitoring)
- Log aggregation (ELK stack)

### Security
✅ **Implemented:**
- HTTPS/SSL encryption (Let's Encrypt with auto-renewal)
- HTTP-only secure cookies
- CORS configuration
- Firewall rules (UFW)
- Password hashing (bcrypt)
- JWT tokens with shared secret key
- Encrypted PII in HR service

⚠️ **Needs Improvement:**
- API rate limiting
- Secrets management (env files on server)
- Regular security audits

---

## DEPLOYMENT

### Current Status: Production

**Deployment Method:** Docker Compose (3 compose files)

**Deployment Process:**
1. SSH to server
2. Pull latest code: `git pull`
3. Rebuild affected containers:
   - Root services: `docker compose up -d --build [service]`
   - Maintenance: `cd maintenance && docker compose up -d --build`
   - Food Safety: `cd food-safety && docker compose up -d --build`
4. Check logs: `docker compose logs -f [service]`

⚠️ **No CI/CD pipeline** - All deployments are manual

### Docker Compose Services (24 total)

**Root compose (20 services):**
portal-app, inventory-app, inventory-db, inventory-redis, hr-app, hr-db, accounting-app, accounting-db, events-app, events-db, events-redis, integration-hub, hub-db, files-app, websites-app, websites-db, caldav, onlyoffice, nginx-proxy, certbot

**Maintenance compose (2 services):**
maintenance-service, maintenance-postgres

**Food Safety compose (2 services):**
food-safety-service, food-safety-postgres

### Database Migrations
ALL systems use **Alembic** for database migrations (NOT Django):

```bash
# Run migrations (from appropriate compose context)
docker compose exec inventory-app alembic upgrade head
docker compose exec hr-app alembic upgrade head
docker compose exec accounting-app alembic upgrade head
docker compose exec events-app alembic upgrade head
docker compose exec integration-hub alembic upgrade head

# Maintenance and Food Safety (separate compose files)
cd maintenance && docker compose exec maintenance-service alembic upgrade head
cd food-safety && docker compose exec food-safety-service alembic upgrade head

# Exceptions: Events and Websites use create_all() — no migration files
```

### Health Checks
Each system has `/health` endpoint:
- https://rm.swhgrp.com/portal/health
- https://rm.swhgrp.com/inventory/health
- https://rm.swhgrp.com/hr/health
- https://rm.swhgrp.com/accounting/health
- https://rm.swhgrp.com/events/health
- https://rm.swhgrp.com/hub/health
- https://rm.swhgrp.com/maintenance/health
- https://rm.swhgrp.com/food-safety/health

---

## SYSTEM METRICS

### Code Statistics (Feb 2026)
- **Total Python files:** 490+
- **Total HTML templates:** 170+
- **Total database models:** 160+
- **Total API endpoints:** 850+
- **Total Docker containers:** 24
- **Total databases:** 8

### System Complexity (Python files)
1. Accounting: 119 files (most complex)
2. Inventory: 104 files
3. Integration Hub: 61 files
4. HR: 60+ files
5. Events: 55 files
6. Food Safety: 29 files
7. Files: 18 files
8. Maintenance: 16 files
9. Websites: 7 files
10. Portal: 3 files (+ templates for Maintenance/Food Safety UI)

### Database Tables
- Accounting: 45+ tables
- Inventory: 32 tables
- HR: 20+ tables
- Events: 20+ tables
- Food Safety: 18 tables
- Integration Hub: 16+ tables
- Websites: 11 tables
- Maintenance: 10 tables
- Files: 7 tables
- Portal: Uses HR `users` table

### Overall Completion by System
1. **Inventory:** 100% ✅
2. **Maintenance:** 100% ✅
3. **Food Safety:** 100% ✅
4. **Events:** ~99% ✅
5. **Integration Hub:** ~98% ✅
6. **Portal:** ~95% ✅
7. **Accounting:** ~95% ✅
8. **HR:** ~95% ✅
9. **Websites:** ~90% ✅
10. **Files:** ~85% ✅

**Overall: ~98% Complete**

---

## APPENDIX: QUICK REFERENCE

### Common Commands
```bash
# View all running containers
docker ps

# View logs for a service
docker compose logs -f [service-name]

# Restart a service
docker compose restart [service-name]

# Rebuild and restart (root services)
docker compose up -d --build [service-name]

# Rebuild maintenance/food-safety
cd maintenance && docker compose up -d --build
cd food-safety && docker compose up -d --build

# Access database
docker compose exec inventory-db psql -U inventory_user -d inventory_db

# Run migrations (all systems use Alembic)
docker compose exec inventory-app alembic upgrade head
docker compose exec events-app alembic upgrade head

# View system health
curl https://rm.swhgrp.com/[system]/health
```

### Important File Locations
- Docker Compose (root): `/opt/restaurant-system/docker-compose.yml`
- Docker Compose (maintenance): `/opt/restaurant-system/maintenance/docker-compose.yml`
- Docker Compose (food-safety): `/opt/restaurant-system/food-safety/docker-compose.yml`
- Nginx Config: `/opt/restaurant-system/shared/nginx/conf.d/`
- System Code: `/opt/restaurant-system/[system-name]/`
- Environment Files: `/opt/restaurant-system/[system-name]/.env`
- Backups: `/opt/restaurant-system/backups/`
- Logs: `/opt/restaurant-system/logs/`

---

**Document Version:** 2.0
**Last Updated:** 2026-02-14
**Maintained By:** Development Team

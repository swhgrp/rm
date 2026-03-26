# SW Hospitality Group - Restaurant Management System

[![Status](https://img.shields.io/badge/status-production-green)]()
[![Completion](https://img.shields.io/badge/completion-98%25-brightgreen)]()
[![Documentation](https://img.shields.io/badge/docs-updated-blue)]()

**Complete microservices-based restaurant management platform**

**Production URL:** https://rm.swhgrp.com
**Last Updated:** March 26, 2026
**Status:** ~98% Complete - All 11 Systems Production Ready ✅
**Latest:** Daily automated accounting review with email reports, vendor bill validation defense-in-depth (Mar 26, 2026) ✅

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [System Components](#system-components)
- [Quick Start](#quick-start)
- [Documentation](#documentation)
- [Common Commands](#common-commands)
- [Integration Points](#integration-points)
- [Critical Priorities](#critical-priorities)
- [Support](#support)

---

## 🎯 Overview

The SW Hospitality Group Restaurant Management System is a comprehensive microservices platform handling all aspects of restaurant operations including inventory management, human resources, accounting, event planning, and third-party integrations.

### Infrastructure
- **Production Server:** Linode Ubuntu instance
- **Development:** Separate Ubuntu workstation (SSH to Linode)
- **iOS Builds:** Mac with Xcode (secondary machine)
- **Repository:** `/opt/restaurant-system/` on Linode server
- **Mobile App Repo:** `/opt/SWHospitality/` on Linode server (separate repo, built on Mac)

### Key Statistics (Verified Mar 8, 2026)
- **11 microservices** running in production (including Maintenance, Food Safety & Cookbook AI)
- **490+ Python files** across all systems
- **170+ HTML templates** for user interfaces
- **160+ database models** with full relationships
- **850+ API endpoints** for system integration
- **26 Docker containers** orchestrated via single root Docker Compose file
- **~98% completion** - all 11 systems production ready

### Source of Truth Architecture
| Data Domain | Owner System | Consumer Systems |
|-------------|--------------|------------------|
| **Locations** | Inventory | Accounting, Hub |
| **Master Items** | Inventory | Hub |
| **Count Units** | Inventory | - |
| **Location Costs** | Inventory | - |
| **Vendors** | Hub | Inventory, Accounting |
| **Vendor Items** | Hub | Inventory |
| **Invoices/GL** | Hub | Accounting |
| **Categories** | Hub (global) | Inventory |
| **UOM** | Hub (global) | Inventory |

---

## 🏗️ Architecture

This project uses a **microservices architecture** where each business domain is a separate, independently deployable service:

```
restaurant-system/
├── portal/             # Central Authentication Portal
│   ├── src/            # FastAPI application code
│   ├── templates/      # Portal pages (login, dashboard, settings)
│   ├── static/         # Portal assets (CSS, images)
│   ├── Dockerfile      # Container definition
│   ├── requirements.txt
│   ├── .env            # Service configuration
│   └── README.md       # Portal documentation
│
├── inventory/          # Inventory Management Service
│   ├── src/            # FastAPI application code (104 Python files)
│   ├── alembic/        # Database migrations
│   ├── templates/      # 30 HTML templates
│   ├── static/         # CSS, JS, images
│   ├── uploads/        # File uploads
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env
│   └── README.md       # Complete documentation (426 lines)
│
├── hr/                 # HR Management Service
│   ├── src/            # FastAPI application code (56 Python files)
│   ├── alembic/        # Database migrations
│   ├── templates/      # 14 HTML templates
│   ├── documents/      # Employee document storage
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env
│   └── README.md       # HR system documentation
│
├── accounting/         # Accounting Service (LARGEST SYSTEM)
│   ├── src/            # FastAPI application code (157 Python files)
│   ├── alembic/        # 50+ database migrations
│   ├── templates/      # 38 HTML templates
│   ├── static/         # CSS, JS, charts
│   ├── fixtures/       # Default chart of accounts
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env
│   └── README.md       # Comprehensive accounting docs
│
├── events/             # Event Planning & Catering Service
│   ├── src/            # FastAPI application code (53 Python files)
│   ├── alembic/        # Database migrations
│   ├── templates/      # 16 HTML templates
│   │   ├── admin/      # Dashboard, calendar, tasks
│   │   ├── public/     # Public intake form
│   │   ├── pdf/        # BEO & contract PDF templates
│   │   └── emails/     # Email templates (with event detail links)
│   ├── services/       # CalDAV sync service
│   ├── storage/        # Document storage
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env
│   └── README.md       # Events documentation (278 lines)
│
├── caldav/             # CalDAV Calendar Server (Radicale 3.5.8)
│   ├── Dockerfile      # Radicale container
│   ├── config          # Server configuration
│   ├── rights          # Access control rules
│   └── data/           # Persistent calendar storage (venue-based)
│
├── integration-hub/    # Integration Hub Service
│   ├── src/            # FastAPI application code (39 Python files)
│   ├── alembic/        # Database migrations
│   ├── templates/      # 10 HTML templates
│   ├── services/       # APScheduler background jobs (email monitoring)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env
│   └── README.md       # Integration Hub documentation
│
├── files/              # Files Management Service + WebDAV Sync + OnlyOffice
│   ├── src/            # FastAPI application code (18 Python files)
│   │   └── webdav_server.py  # WebDAV server for desktop sync
│   ├── alembic/        # Database migrations
│   ├── templates/      # 4 HTML templates (file manager interface)
│   ├── storage/        # User file storage (isolated per user)
│   ├── logs/           # Application logs
│   ├── Dockerfile
│   ├── requirements.txt  # Includes WsgiDAV 4.3.0
│   ├── .env
│   └── README.md       # Files system documentation (340 lines)
│
├── websites/           # Website CMS Service (NEW - Dec 2025) 🌟
│   ├── src/            # FastAPI application code (7 Python files)
│   ├── alembic/        # Database migrations
│   ├── templates/      # 18 HTML templates (admin + preview)
│   │   ├── admin/      # Admin interface templates
│   │   └── preview/    # Website preview templates
│   ├── uploads/        # Site image uploads
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env
│
├── maintenance/        # Maintenance & Equipment Tracking (NEW - Jan 2026) 🌟
│   ├── src/            # FastAPI application code (12 Python files)
│   │   └── maintenance/
│   │       ├── models.py     # SQLAlchemy models
│   │       ├── schemas.py    # Pydantic schemas
│   │       ├── routers/      # API routers (6 modules)
│   │       └── services/     # External integrations
│   ├── alembic/        # Database migrations
│   ├── Dockerfile
│   ├── docker-compose.yml  # Standalone deployment
│   ├── requirements.txt
│   └── .env
│
├── food-safety/        # Food Safety & Compliance (NEW - Jan 2026) 🌟
│   ├── src/            # FastAPI application code (20+ Python files)
│   │   └── food_safety/
│   │       ├── models/       # SQLAlchemy models
│   │       ├── schemas.py    # Pydantic schemas
│   │       ├── routers/      # API routers (9 modules)
│   │       └── services/     # External integrations
│   ├── alembic/        # Database migrations
│   ├── Dockerfile
│   ├── docker-compose.yml  # Standalone deployment
│   ├── requirements.txt
│   └── README.md       # Food safety documentation
│
├── shared/             # Shared Infrastructure
│   ├── nginx/          # Reverse proxy configuration
│   │   └── conf.d/     # Site configurations
│   ├── certbot/        # SSL certificates
│   └── python/         # Shared Python libraries
│
├── scripts/            # Utility Scripts
│   ├── backup_databases.sh    # Automated backups
│   ├── health_check.sh        # System monitoring
│   └── tests/                 # Test scripts
│
├── docs/               # Additional Documentation
│   ├── events-caldav-calendar-sync.md  # CalDAV setup guide (324 lines)
│   ├── files-webdav-sync.md            # WebDAV desktop sync guide (500+ lines)
│   ├── archived/       # Historical docs (Oct-Nov 2025)
│   └── status/         # Progress reports
│
├── docker-compose.yml  # Multi-service orchestration
├── CLAUDE.md           # Developer reference & patterns
├── SECURITY.md         # Security audit & remediation tracker
├── TODO.md             # Active task tracking
└── README.md           # This file
```

### Network Architecture

**Important:** This diagram shows the **routing architecture**. All services use the Portal for **SSO authentication** (JWT tokens), but traffic is routed directly from Nginx to each service.

```
┌──────────────────────────────────────────────────────────────┐
│                Nginx Reverse Proxy (SSL/TLS)                  │
│                rm.swhgrp.com (172.233.172.92)                 │
│                                                               │
│  Routes:                                                      │
│  /portal/       → portal-app:8000      (SSO Auth)            │
│  /inventory/    → inventory-app:8000                         │
│  /accounting/   → accounting-app:8000                        │
│  /hr/           → hr-app:8000                                │
│  /events/       → events-app:8000                            │
│  /caldav/       → caldav:5232          (Calendar Sync)       │
│  /hub/          → integration-hub:8000                       │
│  /files/        → files-app:8000       (Web UI)              │
│  /files/webdav/ → files-app:8000       (Desktop Sync)        │
│  /websites/     → websites-app:8000    (Website CMS)         │
│  /maintenance/  → maintenance-service:8000 (Equipment)       │
│  /food-safety/  → food-safety-service:8000 (Food Safety)     │
│  /onlyoffice/   → onlyoffice:80        (Document Editing)    │
└──────────────────────────────────────────────────────────────┘
         │           │           │           │
         ▼           ▼           ▼           ▼
    ┌────────┐  ┌──────────┐  ┌────┐  ┌──────────┐
    │Portal  │  │Inventory │  │ HR │  │Accounting│
    │  SSO   │  │Management│  │Sys │  │  System  │
    │ :8000  │  │  :8000   │  │8000│  │  :8000   │
    └────────┘  └──────────┘  └────┘  └──────────┘
         │           │           │           │
         └───────────┴───────────┴───────────┘
                     │
              ┌──────▼───────┐
              │  PostgreSQL  │
              │  15 Cluster  │
              │ (per-service │
              │  databases)  │
              └──────┬───────┘
                     │
    ┌────────────────┼────────────────┐
    ▼                ▼                ▼
┌────────┐  ┌──────────────┐  ┌──────────────┐
│Events  │  │     Hub      │  │    Files     │
│ :8000  │  │    :8000     │  │   Storage    │
└────┬───┘  └──────────────┘  └──────┬───────┘
     │                               │
     ▼                               ▼
┌────────┐                    ┌──────────────┐
│CalDAV  │                    │  OnlyOffice  │
│Radicale│                    │  Doc Server  │
└────────┘                    └──────────────┘

┌────────────────────────────────────┐
│           Shared Services          │
├────────────────────────────────────┤
│ Redis 7       - Caching            │
│ Websites :8000 - CMS               │
│ Cookbook :8000  - AI/RAG (ChromaDB) │
└────────────────────────────────────┘
```

### Authentication Flow

```
1. User visits https://rm.swhgrp.com/
   ↓
2. Nginx redirects to /portal/
   ↓
3. Portal displays login page
   ↓
4. User enters credentials
   ↓
5. Portal validates against HR database
   ↓
6. Portal issues JWT token (stored in cookie)
   ↓
7. Portal displays dashboard with accessible systems
   ↓
8. User clicks "Inventory Management"
   ↓
9. Browser navigates to /inventory/
   ↓
10. Nginx routes to inventory-app:8000
    ↓
11. Inventory app validates JWT token from cookie
    ↓
12. If valid: Show inventory interface
    If invalid: Redirect to /portal/login
```

**Key Points:**
- **Portal = SSO Provider** (issues JWT tokens)
- **Nginx = Traffic Router** (routes to microservices)
- **Each Service = Independent** (validates JWT, has own database)
- **No Traffic Through Portal** (direct Nginx → Service routing)
- **Mobile App** — Uses `POST /api/mobile/login` for bearer token, then calls service APIs directly with `Authorization: Bearer <token>`

---

## 📦 System Components

### 1. Portal System ✅ **~95% Complete**
**Central authentication, system monitoring hub, and maintenance management**

- **URL:** https://rm.swhgrp.com/portal/
- **Purpose:** JWT-based SSO, infrastructure monitoring, and maintenance UI
- **Technology:** FastAPI (Python), PostgreSQL
- **Files:** 3 Python files, 15 templates

**Core Authentication:**
- ✅ JWT token authentication with secure HTTP-only cookies
- ✅ Session management (30-min idle timeout with keepalive auto-refresh)
- ✅ Permission-based system access control (9 systems)
- ✅ Admin user management interface
- ✅ Single sign-on (SSO) token generation (5-min tokens)
- ✅ Cross-system password synchronization

**User Management:**
- ✅ User profile management (update full name and email)
- ✅ Password change system with cross-system sync
- ✅ Password complexity enforcement (8+ characters minimum)
- ✅ Session auto-refresh (extends when <10 min remaining)
- ✅ **Self-service password reset** via email (NEW Jan 2026) 🌟
  - Secure random token generation (32-byte URL-safe)
  - 1-hour token expiration
  - Anti-enumeration protection
  - Professional HTML email templates

**System Monitoring Dashboard:**
- ✅ Real-time infrastructure monitoring (admin-only)
- ✅ 9 microservices health status
- ✅ Database health with connection counts
- ✅ SSL certificate expiration tracking
- ✅ Per-database backup status
- ✅ Recent alerts and error logs
- ✅ Auto-refresh every 30 seconds
- ✅ Local time display (EDT/EST timezone aware)
- ✅ **URL:** https://rm.swhgrp.com/portal/monitoring

**Maintenance Portal (NEW Jan 2026):** 🌟
- ✅ Equipment management UI
- ✅ Work order management UI
- ✅ Maintenance schedules UI with completion logging
- ✅ Dashboard with action items, recent activity, and open work orders
- ✅ **URL:** https://rm.swhgrp.com/portal/maintenance/

**Mobile App Support (NEW Mar 2026):** 🌟
- ✅ `POST /api/mobile/login` — Returns JWT as bearer token in JSON body
- ✅ `POST /api/mobile/refresh` — Refreshes bearer token using existing token
- ✅ Bearer token auth added across all services (Events, HR, Accounting, Food Safety)
- ✅ **iOS app** (SwiftUI, iOS 17+) — Auth, biometric login, full Inventory module (counts, items, waste, transfers, orders)
- 🔄 **Android app** (planned) — Kotlin Multiplatform (KMP) with shared business logic + Jetpack Compose UI

**Missing (~5%):**
- ⚠️ `/debug` endpoint has no authentication - security risk
- ❌ Two-factor authentication (future)

**[→ View Portal Documentation](./portal/README.md)**

---

### 2. Inventory System ✅ **Production Ready (100%+ Complete)** 🌟
**Enterprise-grade inventory management with location-aware costing, POS integration, recipe costing, and advanced analytics**

- **URL:** https://rm.swhgrp.com/inventory/
- **Database:** inventory_db (PostgreSQL 15) - **32 tables, 26+ models**
- **Technology:** FastAPI, SQLAlchemy, Redis, APScheduler, ReportLab
- **Files:** 104 Python files, **31 templates**, 177+ API routes across 23 modules

**Source of Truth (Jan 5, 2026):**
- ✅ **Locations** - Inventory owns all location data (code, legal_name, ein, address)
- ✅ **Master Items** - Central item catalog with category/UOM references to Hub
- ✅ **Count Units** - Per-item counting units with conversion factors
- ✅ **Location Costs** - Weighted average cost per item per location

**Core Inventory Features:**
- ✅ Master item catalog with SKUs and categorization
- ✅ Multi-location inventory tracking with storage areas
- ✅ **Location-aware costing** - Per-location weighted average costs
- ✅ **Multiple count units** - Primary + 2 additional count units per item
- ✅ Live count sessions with auto-save (mobile-responsive)
- ✅ **Count session reports** — printable HTML reports grouped by storage area/category with cost data (NEW Mar 2026) 🌟
- ✅ **Count session CSV export** — download with cost lookup chain (location → hub → inventory → master item) (NEW Mar 2026) 🌟
- ✅ Count templates for recurring counts
- ✅ **Waste tracking with UoM dropdown** - Select unit of measure when logging waste (NEW Jan 5) 🌟
- ✅ **Transfer form enhancements** - Searchable Select2 dropdown, date picker, UoM selection (NEW Jan 5) 🌟
- ✅ **Dashboard with COGS display** - Cost of goods sold metrics (NEW Jan 5) 🌟
- ✅ Inter-location transfer workflow (request, approve, ship, receive)
- ✅ Advanced analytics dashboard with charts
- ✅ Comprehensive reporting (usage, variance, valuation)
- ✅ Low stock alerts based on par levels
- ✅ Complete audit trail and transaction history
- ✅ Portal SSO integration with JWT
- ✅ Units of measure library with conversion factors

**🌟 Integration Hub Connection:**
- ✅ **Note:** Invoice processing is in Integration Hub (source of truth)
- ✅ Inventory provides `/_sync` endpoint for Accounting to fetch locations
- ✅ Master items reference Hub categories and UOMs
- ✅ Location costs updated by Hub when invoices are processed

**🌟 POS Integration (PRODUCTION READY):**
- ✅ Clover, Square, and Toast POS support
- ✅ Automated sales sync (every 10 minutes via APScheduler)
- ✅ POS item-to-inventory mapping UI (one-to-one or recipe-based)
- ✅ Automatic inventory deduction from sales
- ✅ Daily sales tracking by location
- ✅ POS configuration interface with API credentials
- ✅ Sync history and error logging
- ✅ Manual sync triggers

**🌟 Recipe Management & Costing (PRODUCTION READY):**
- ✅ Recipe CRUD with multi-ingredient support
- ✅ Yield and portion tracking (servings/portions)
- ✅ Automatic ingredient cost calculations from inventory
- ✅ Labor and overhead cost allocation
- ✅ Total recipe cost and cost per portion
- ✅ Food cost percentage calculation
- ✅ PDF recipe generation for printing
- ✅ Recipe categories and organization
- ✅ 44KB recipe management UI

**System Statistics:**
- **32 database tables** with full relationships
- **30 HTML templates**
- **21 API endpoint modules** with 190+ routes
- **15,000+ lines of code**
- **Complete audit logging** for all transactions

**[→ View Inventory Documentation](./inventory/README.md)** ✅ **FULLY DOCUMENTED** (Updated Nov 3, 2025)

---

### 3. HR System ✅ **Production Ready (Core Features)**
**Employee information management system**

- **URL:** https://rm.swhgrp.com/hr/
- **Database:** hr_db (PostgreSQL 15)
- **Technology:** FastAPI, SQLAlchemy, Redis, APScheduler
- **Files:** 60+ Python files, 17 templates

**Note:** This is an employee information management system. It does NOT include scheduling, time tracking, or payroll features.

**Features:**
- ✅ Employee profile management with encrypted PII
- ✅ Department and position tracking
- ✅ User account management for Portal SSO
- ✅ Emergency contacts (encrypted)
- ✅ Employee document storage with expiration tracking
- ✅ Required documents enforcement (ID, SSN, Food Certificate) on new hire creation
- ✅ Missing documents warning banner on employee profile
- ✅ Missing docs badge on employees list ("Docs & Certs" column)
- ✅ Document upload with 10MB file size validation (client-side alert + server-side check)
- ✅ Hire date admin-only editing (readonly for non-admins, preserved across all updates)
- ✅ **Location-based employee filtering** - Non-admin users only see employees at their assigned locations (Feb 25, 2026) 🌟
- ✅ **Toggle switch UI** for location assignments in user management (Feb 25, 2026) 🌟
- ✅ Role-based access control (Admin, Manager, Employee)
- ✅ Email settings management
- ✅ **E-Signature Templates** - Visual field editor for PDF signature placement
  - PDF.js integration for document preview
  - Click-to-place signature, initials, date, and text fields
  - Drag, resize, and delete field boxes
  - Multi-page navigation with zoom controls (50%-200%)
  - Dropbox Sign webhook integration
- ✅ **HR Forms** (NEW Jan 2026) 🌟
  - **Corrective Action Form** - Document disciplinary actions with digital signatures
  - **First Report of Injury** - OSHA-compliant injury reporting with witness signatures
  - Signature pad integration for employee and supervisor signatures
  - Past incident history tracking
  - Form printing and PDF generation
- ✅ **Enhanced Audit Logging** (NEW Jan 2026) 🌟
  - Detailed field-level tracking (e.g., "Viewed: Street Address, Phone Number, Date Of Birth")
  - Document access logging (ID Copy, Social Security Card, Certifications)
  - Human-readable field names (snake_case → Title Case)
  - IP address and user agent tracking
  - Audit log UI with filtering by action, entity type, and user
- ❌ Shift scheduling - NOT IMPLEMENTED
- ❌ Time clock (clock in/out) - NOT IMPLEMENTED
- ❌ Timesheet workflow - NOT IMPLEMENTED
- ❌ Payroll calculation - NOT IMPLEMENTED
- ❌ Attendance tracking - NOT IMPLEMENTED
- ❌ Benefits management - NOT IMPLEMENTED
- ❌ PTO/vacation tracking - NOT IMPLEMENTED

**Integration:**
- Master source for user authentication (Portal reads HR database)
- Centralized password changes sync to all microservices
- Portal SSO integration with JWT tokens
- JIT (Just-In-Time) user provisioning for other systems

**[→ View HR Documentation](./hr/README.md)**

---

### 4. Accounting System ✅ **Production Ready (~95% Complete)** 🌟
**Full double-entry accounting system** *(Most Sophisticated System)*

- **URL:** https://rm.swhgrp.com/accounting/
- **Database:** accounting_db (PostgreSQL 15) - 26+ tables
- **Technology:** **FastAPI with SQLAlchemy ORM**
- **Migrations:** Alembic (23 migrations)
- **Files:** **119 Python files** (largest system!), 38+ templates, 250+ API endpoints
- **API Docs:** OpenAPI/Swagger auto-generated
- **Latest:** DSS GL validation, inactive vendor reactivation (Mar 20, 2026) 🌟

**Features:**

**Core Accounting:**
- ✅ Chart of accounts with hierarchy
- ✅ General ledger with drill-down
- ✅ Journal entries with multi-line support
- ✅ Trial balance
- ✅ Account reconciliation
- ✅ Fiscal period management
- ✅ Year-end close process

**Financial Reporting:**
- ✅ Balance Sheet
- ✅ Profit & Loss Statement (P&L)
- ✅ Cash Flow Statement
- ✅ General Ledger reports
- ✅ Account transaction history
- ✅ Multi-period comparisons
- ✅ Department/location reporting
- ✅ PDF and Excel export

**Accounts Payable (AP):**
- ✅ Vendor management
- ✅ Bill entry and approval
- ✅ Payment processing
- ✅ AP aging reports (30/60/90 days)
- ✅ 1099 tracking
- ✅ Check printing

**Accounts Receivable (AR):** *(97% Complete - Full Invoice Workflow!* ✨🚀*)*
- ✅ Customer management with credit limits
- ✅ Invoice creation with event integration
- ✅ **Invoice detail page** with print support and PDF download 🆕
- ✅ **Draft invoice editing** with full line item replacement 🆕
- ✅ **Draft/void invoice deletion** 🆕
- ✅ **Post vs Email separation** - Post finalizes to GL, Email sends to customer 🆕
- ✅ **Professional PDF invoices** with location branding and logo upload (ReportLab) 🌟
- ✅ **Auto GL posting** - Journal entries created on invoice post (DR: AR, CR: Revenue) 🌟
- ✅ **Credit limit enforcement** (prevents over-limit invoicing) 🌟
- ✅ **Email invoice delivery** with SMTP configuration 🌟
- ✅ **Customer statements** with aging and transaction detail 🌟
- ✅ **Recurring invoices** - Automated billing from templates (weekly, monthly, quarterly, annually) 🔥
- ✅ **Payment reminders** - Automated 3-tier reminder system for overdue invoices 🔥
- ✅ **AR automation script** - Daily cron job for invoice generation and reminder processing
- ✅ Payment receipt and tracking
- ✅ AR aging reports (30/60/90+ days)
- ✅ Collections tracking
- ✅ Credit memos
- ✅ Customer credit status API
- ✅ Email settings UI for AR communications
- ✅ Payment reminder settings UI with configurable schedule

**Banking:**
- ✅ Bank account management
- ✅ Bank reconciliation with inline GL suggestions and search (enhanced Mar 2026) 🌟
- ✅ **Batch GL suggestions** — single API call for multiple transaction suggestions (Mar 2026) 🌟
- ✅ **GL learning improvements** — stop-word filtering, competing pattern deactivation, rejection tracking (Mar 2026) 🌟
- ✅ Transaction import
- ✅ Check register
- ✅ **Custom date range picker** on banking dashboard (Mar 2026) 🌟
- 🔄 Bank feeds (partial)

**Budgeting:**
- ✅ Budget creation by account (single fiscal year only)
- ✅ Budget vs Actual reports
- 🔄 Variance analysis (partial - 40%)
- 🔄 Forecasting (minimal implementation - ~30%)

**Daily Sales & Vendor Improvements (Mar 2026):** 🌟
- ✅ **DSS GL validation** — server-side + client-side validation of all GL account mappings before posting journal entry
- ✅ **Third-party payment deposits** — DoorDash, UberEats, etc. included in card_deposit calculation (not just CARD payments)
- ✅ **Inactive vendor reactivation** — VendorService reuses inactive vendors with matching name instead of creating duplicates

**GL Review & Anomaly Detection (Mar 2026):** 🌟
- ✅ **Automated nightly GL sweep** — rules engine + Claude AI anomaly detection
- ✅ **Statistical baselines** — monthly recompute per GL account
- ✅ **Flag lifecycle** — open → reviewed → dismissed → superseded with 90-day retention
- ✅ **AI reasoning** — Claude Sonnet analyzes flagged entries for severity and explanation
- ✅ **GL Review UI** — dedicated page for reviewing and acting on anomaly flags

**Daily Automated Accounting Review (NEW Mar 2026):** 🔥
- ✅ **Cross-system daily audit** — scans Accounting, Hub, and Inventory DBs at 5 AM daily
- ✅ **10 check categories** — invoice accuracy, GL integrity, sync reconciliation, pipeline health, beverage pricing, linen parse quality, delivery fees, duplicate detection
- ✅ **Email report** — HTML summary with critical/warning/info findings emailed to admin
- ✅ **4-layer vendor bill validation** — post-parse validator → Hub sender reject → Accounting receiver reject → JE balance check
- ✅ **Finding persistence** — all findings stored in `daily_review_runs` / `daily_review_findings` tables
- ✅ **Review spec** — `REVIEW_SPEC.md` defines all checks, correction rules, and report format

**Other:**
- ✅ COGS tracking
- ✅ Sales analysis
- ✅ Multi-entity support
- ✅ Role-based access (Admin, Accountant, AP/AR Clerk, Read-only)
- ❌ Fixed asset management - NOT IMPLEMENTED
- ❌ Job costing - NOT IMPLEMENTED

**[→ View Accounting Documentation](./accounting/README.md)** *(Note: Needs framework correction)*

---

### 5. Events System ✅ **Production Ready (~99% Complete)** 🌟
**Event planning and catering management with public intake, Quick Holds, and Portal SSO**

- **URL:** https://rm.swhgrp.com/events/
- **Public Form:** https://rm.swhgrp.com/events/public/intake (NO AUTH REQUIRED)
- **Database:** events_db (PostgreSQL 15)
- **Technology:** FastAPI, SQLAlchemy, WeasyPrint (PDF), FullCalendar.js
- **Files:** 55 Python files, 18 templates
- **Latest:** Equipment/rental line items with pricing, catering contracts, CalDAV sync (Mar 20, 2026) 🌟

**✅ Portal SSO Integration Complete:**
- ✅ JWT token validation from Portal
- ✅ JIT (Just-In-Time) user provisioning
- ✅ Automatic redirect to Portal login for unauthenticated users
- ✅ Proper exception handling (JSON for API, redirects for HTML)
- ✅ Fixed URL routing with base href compatibility

**🆕 NEW: Quick Holds (Jan 5, 2026):**
- ✅ **Quick hold creation** - Block dates without full event details
- ✅ **Hold expiration** - Auto-expire holds after configurable period
- ✅ **Convert to event** - One-click conversion to full event
- ✅ **Calendar integration** - Holds shown on calendar view
- ✅ **API endpoints** - Full CRUD for quick holds

**Features:**

**Event Management:**
- ✅ Event CRUD with status workflow
  - Draft → Pending → Confirmed → In Progress → Completed
- ✅ Client management
- ✅ Venue management
- ✅ Guest count tracking
- ✅ Event types (Wedding, Corporate, Birthday, etc.)
- ✅ Setup/teardown time tracking
- ✅ Special requirements notes

**Public Intake Form:** ⭐
- ✅ No authentication required - accessible to anyone
- ✅ hCaptcha spam protection
- ✅ Auto-creates client records
- ✅ Creates pending events for review
- ✅ Email confirmation to client
- ✅ **Fully mobile-optimized**
- ✅ URL: https://rm.swhgrp.com/events/public/intake

**Calendar & Scheduling:**
- ✅ Month/week/day calendar views
- ✅ FullCalendar integration
- ✅ Color-coded by event status
- ✅ Event filtering
- ✅ Visual timeline
- ✅ **Calendar search** with 300ms debounce (server + client-side filtering) (NEW Mar 2026) 🌟

**Task Management:**
- ✅ Auto-task generation from templates
- ✅ Department assignment
- ✅ Priority levels (Urgent, High, Medium, Low)
- ✅ Due date tracking
- ✅ Checklist items
- ✅ Task status workflow (Todo, In Progress, Blocked, Done)
- ✅ Kanban board view

**Document Generation:**
- ✅ BEO (Banquet Event Order) PDF generation
- ✅ **Catering Contract PDF** — formal legal contract with venue logos, menu, financials, legal clauses, signature blocks (Mar 2026) 🌟
- ✅ **Price Quote PDF** — itemized quote with equipment/rentals, menu pricing, terms (Mar 2026) 🌟
- ✅ Event summary PDF
- ✅ WeasyPrint rendering with venue logo embedding (base64 data URIs)
- ✅ Download/email delivery
- 🔄 Version control (partial - 40%)

**Email Notifications:**
- ✅ Client confirmation emails
- ✅ Internal team notifications
- ✅ Task assignment emails
- ✅ Event update alerts
- ✅ Template-based system

**UI/UX:**
- ✅ Dark theme matching system design
- ✅ **Fully mobile-responsive** (all pages)
- ✅ Touch-friendly interface
- ✅ Dashboard with stats
- ✅ Filterable events list
- ✅ Tabbed event detail view

**Partial/Missing:**
- ✅ **Menu builder UI** — sectioned menu items with pricing, equipment/rental line items (Mar 2026) 🌟
- 🔄 Financial integration with Accounting (partial - 50%)
- 🔄 Event packages pricing system (CRUD complete, needs UI polish - 80%)
- ❌ S3 storage (currently local)
- ❌ Event templates CRUD UI
- ❌ 4 router files (emails, templates, users, admin) - NOT IMPLEMENTED
- ❌ Audit logging - Model exists but NEVER POPULATED
- ❌ Celery/Redis - Dependencies present but NOT USED

**[→ View Events Documentation](./events/README.md)** *(Note: Authentication status needs correction)*

---

### 6. Integration Hub ✅ **Production Ready with AI Search & Sizing** 🌟
**Automated invoice processing with email monitoring, AI parsing, semantic search, Backbar-style sizing, and smart routing**

- **URL:** https://rm.swhgrp.com/hub/
- **Database:** hub_db (PostgreSQL 15 + pgvector) - **18+ tables, 25+ models**
- **Technology:** **FastAPI**, SQLAlchemy, OpenAI GPT-4o Vision, OpenAI Embeddings, pgvector, APScheduler, PyPDF2, pdf2image
- **Files:** 55+ Python files, 14 templates

**Critical Correction:** This is NOT a vendor API integration platform. It does NOT connect to third-party vendor APIs like US Foods or Sysco. It is an internal hub for processing invoices and creating accounting journal entries.

**Source of Truth Architecture (Dec 27, 2025):**
- **Hub owns:** Invoices, Vendor Items (location-aware), Vendors, GL Mappings, UOM, Categories
- **Inventory owns:** Master Items, Count Units, Location Costs, Locations
- **Location-aware pricing:** Vendor items track prices per location from invoices
- **Weighted average costing:** Hub updates Inventory's `MasterItemLocationCost` on invoice processing
- **Single purchase UOM per vendor item:** `pack_to_primary_factor` auto-calculated from size fields; cost calc: `unit_price / pack_to_primary_factor`
- **DEPRECATED:** `vendor_item_uoms` table and `matched_uom_id` column retained for history but no longer used

**🆕 UOM Simplification (Feb 26, 2026):**
- ✅ **Single purchase UOM** - Each vendor item has one purchase UOM defined by `pack_to_primary_factor`
- ✅ **Auto-calculation** - `pack_to_primary_factor` computed on save: `units_per_case × size_quantity` (weight/count) or `units_per_case` (volume)
- ✅ **Removed multi-UOM system** - `vendor_item_uoms` CRUD endpoints, `match_invoice_uom_to_vendor_uom()`, Purchase UOMs UI section all removed
- ✅ **Simplified cost path** - Single deterministic `cost_per_primary = unit_price / pack_to_primary_factor` (no fallbacks)
- ✅ **Vendor parsing rules** - Per-vendor AI instructions for invoice column disambiguation (e.g., Breakthru Case/Btles/Pieces columns)
- ✅ **Vendor item imports** - Republic National Distributing (32 items from eRNDC), Southern Glaziers (148 items from CSV)

**🤖 AI Semantic Search & Backbar-Style Sizing (Dec 28, 2025):**
- ✅ **AI-powered semantic search** - Find vendor items using natural language
- ✅ **pgvector integration** - HNSW index for fast similarity lookups
- ✅ **Similar item detection** - Find duplicates across vendors
- ✅ **Backbar-style sizing** - [Quantity] [Unit] [Container] format (e.g., "750 ml bottle")
- ✅ **Size units & containers** - Configurable units (L, ml, lb, oz) and containers (bottle, can, bag)
- ✅ **Vendor item detail page** - Comprehensive view with pricing history and AI suggestions
- ✅ **Auto unit cost calculation** - `case_cost / units_per_case`

**🆕 NEW: Vendor Merge & Push to Systems (Jan 15, 2026):**
- ✅ **Vendor merge** - Merge multiple vendors into one primary vendor
- ✅ **Alias management** - Merged vendor names become aliases of primary vendor
- ✅ **Push to Systems** - Push Hub's vendor/alias state to Inventory and Accounting
- ✅ **Bill reassignment** - Automatically reassign bills when merging in Accounting
- ✅ **Preview mode** - Preview what merge/push will do before executing
- ✅ **Search filter** - Filter vendor table by name in Hub vendors page

**🆕 Expense Items vs Vendor Items (Dec 28, 2025):**
- ✅ **Clear separation** - Vendor Items = inventory tracked, Expense Items = expense-only (not counted)
- ✅ **Expense Items page** - View/manage items mapped to expense GL accounts
- ✅ **"Map to Expense" action** - Convert vendor items to expense items (deletes from vendor items)
- ✅ **Searchable GL dropdowns** - Type-to-filter expense account selection
- ✅ **Convert to Inventory** - Move expense items back to vendor items with master item link
- ✅ **Auto-cleanup** - Mapping to expense removes item from Vendor Items table

**🚀 Major Workflow Improvements (Nov 8, 2025):**
- ✅ **Bulk mapping by description** - Map once, apply to ALL occurrences (10x faster)
- ✅ **Unique item grouping** - Unmapped items page shows frequency & affected invoices
- ✅ **Mapped items review page** - View/edit all mapped items with vendor details
- ✅ **Statement handling** - Mark statements to prevent routing to systems
- ✅ **Smart auto-send** - Only sends to Inventory if items have categories
- ✅ **Invoice deletion** - Cascade delete with PDF cleanup
- ✅ **Vendor selection/creation** - Create vendors on-the-fly in invoice detail
- ✅ **Auto-trigger send** - Automatically sends when invoice fully mapped via bulk action
- ✅ **Enhanced GL validation** - Different requirements for inventory vs expense items

**🆕 CSV Expected Vendors & GFS Parsing (Mar 2026):** 🌟
- ✅ **CSV expected vendors** — 8 vendors (34 vendor+location combos) where CSV is the primary invoice format
- ✅ **`pdf_reference` status** — PDF invoices for CSV-expected vendors stored for reference only, replaced when CSV arrives
- ✅ **Leading-zero duplicate detection** — Fintech CSV invoice numbers (e.g., `04827201`) matched against PDFs (`4827201`) using stripped comparison
- ✅ **CSV viewer filtering** — multi-vendor/multi-location CSV files filtered to show only the specific invoice's rows
- ✅ **CSV-over-PDF replacement** — CSV data replaces PDF-parsed data regardless of status; clears sync flags for re-send
- ✅ **GFS CSV format support** — auto-detects GFS column headers, maps to standard format, handles catch-weight items
- ✅ **CSV-aware auto-mapping** — skips fuzzy matching for CSV data (exact SKUs only, prevents wrong product matches)
- ✅ **Line item deduplication** — deduplicates items from GFS PDFs that render items twice (text + table)
- ✅ **AI math expression fix** — evaluates math expressions in AI-parsed JSON values
- ✅ **Minimum charge adjustment** — auto-adds balancing line item when subtotal exceeds line item sum
- ✅ **Vendor item cross-location dedup** — prevents re-creating intentionally deactivated vendor items

**🌟 Automated Invoice Intake Pipeline (Oct 31, 2025):**
- ✅ **Email monitoring** - Automated IMAP email checking every 15 minutes
- ✅ **PDF extraction** - Attachment capture with SHA-256 deduplication
- ✅ **CSV invoice parsing** - Automated parsing for CSV-format vendor invoices
- ✅ **OpenAI parsing** - GPT-4o Vision powered invoice data extraction
- ✅ **Intelligent auto-mapping** - Multi-strategy item-to-GL mapping:
  - Vendor item code matching (confidence: 1.0)
  - Fuzzy description matching (confidence: 0.7-0.9)
  - Category-level GL account fallback
- ✅ **Email settings UI** - IMAP configuration with connection testing
- ✅ **Confidence scoring** - AI-powered data validation
- ✅ **Auto vendor matching** - Fuzzy logic vendor identification

**Core Invoice Processing Features:**
- ✅ Receives vendor invoices (email, manual upload, or API)
- ✅ Maps invoice line items to inventory master items (with bulk mapping)
- ✅ Maps items to GL accounts (Asset, COGS, Waste, Revenue)
- ✅ **Smart routing** - Creates journal entries in Accounting system
- ✅ Creates and sends journal entries to Accounting system via REST API
- ✅ **Vendor items managed in Hub** - Inventory queries Hub for pricing/catalog
- ✅ Invoice status tracking (pending → mapping → ready → sent/statement)
- ✅ **Support for non-inventory items** - Propane, linen, janitorial, etc.

**Technical Stack:**
- OpenAI: 1.12.0 (GPT-4o Vision for multi-page invoice parsing)
- PyPDF2: 3.0.1 (PDF text extraction)
- pdf2image: 1.16.3 (PDF rendering to images)
- APScheduler: 3.10.4 (Background job scheduling)
- Pillow: 10.1.0 (Image processing support)

**Workflow:**
```
Email → PDF Extract → AI Parse → Bulk Map (by description) → Auto-Send → Route to Systems
```

**Integration Points:**
- → **Accounting:** Creates balanced journal entries (Dr = Cr)
- ← **Inventory:** Queries for master items, categories, units (via dblink)
- ← **Email (IMAP):** Monitors for invoice PDFs
- **Note:** Hub is source of truth for invoices, vendor items, and vendors

**Note:** Integration Hub is an **internal invoice processing hub**, not a vendor API integration platform. It processes invoices from any vendor (email/upload) and routes data to internal systems.

**[→ View Integration Hub Documentation](./integration-hub/README.md)** *(Updated 2025-12-25)*

---

### 7. Files System (~85% Complete) ✅ **WebDAV Sync Now Available**
**Document management with file sharing + Desktop sync**

- **URL:** https://rm.swhgrp.com/files/
- **WebDAV:** https://rm.swhgrp.com/files/webdav/ (Desktop sync endpoint)
- **Technology:** FastAPI, WsgiDAV 4.3.0, OnlyOffice Document Server, LibreOffice (document conversion)
- **Files:** 18 Python files, 4 templates
- **Storage:** Persistent volume on server (`/app/storage`)
- **Status:** Core features operational, WebDAV sync production-ready ✅

**Features:**
- ✅ File upload/download (single file, no bulk)
- ✅ File preview (PDFs, images, Office docs with LibreOffice conversion)
- ✅ Folder organization with nested hierarchy
- ✅ File operations (copy, move, rename, delete)
- ✅ Internal sharing with granular permissions
- ✅ Public share links with passwords and expiration
- ✅ Advanced search (filename, type, date, size filters)
- ✅ Portal SSO integration
- ✅ User-based storage isolation
- ✅ Role-based access control
- ✅ Share access audit logging
- ✅ **WebDAV server for desktop sync** (NEW - Nov 14, 2025) 🌟
- ✅ **Desktop client support** (Mountain Duck, RaiDrive, Finder, Explorer) 🌟
- ✅ **Offline file access** with two-way sync 🌟
- ✅ **10GB file upload support** via WebDAV 🌟
- ⚠️ Bulk upload - CLAIMED but NOT IMPLEMENTED
- ⚠️ Bulk operations - CLAIMED but NO API endpoints
- ✅ OnlyOffice document editing integration (Word, Excel, PowerPoint)
- ❌ Calendar integration - NOT IMPLEMENTED
- ❌ Contacts management - NOT IMPLEMENTED
- ❌ Tasks/To-do lists - NOT IMPLEMENTED
- 🔄 Mobile app — iOS app has Inventory module; Files integration not yet added
- ❌ Comments - NOT IMPLEMENTED

**Access:**
- Web: https://rm.swhgrp.com/files/

**Use Cases:**
- Employee document storage
- Shared department files
- File sharing (internal and external)

---

### 8. Websites System ✅ **Production Ready (NEW - Dec 2025)** 🌟
**Restaurant website CMS with block-based page builder and mobile-responsive admin**

- **URL:** https://rm.swhgrp.com/websites/
- **Database:** websites_db (PostgreSQL 15)
- **Technology:** FastAPI, SQLAlchemy, Jinja2, Bootstrap 5, HTMX, Pillow
- **Files:** 7 Python files, 18 templates
- **Status:** Production ready with full feature set ✅

**Features:**

**Site Management:**
- ✅ Multi-site support (manage multiple restaurant websites)
- ✅ Site settings (domain, branding colors, contact info)
- ✅ Social media integration (Instagram, Facebook links)
- ✅ Online ordering and reservation URL integration
- ✅ Business hours management with special hours
- ✅ Site publishing workflow

**Page Builder:**
- ✅ Block-based page editor (drag-and-drop ready)
- ✅ Block types: Hero, Text, Menu Preview, Hours, Contact Form, Map, Gallery, Two-Column, Image
- ✅ Visual block editing with live preview
- ✅ Block visibility toggles
- ✅ Block reordering

**Menu Management:**
- ✅ Menu CRUD with categories
- ✅ Menu items with descriptions, prices, dietary flags
- ✅ Menu preview block on pages
- ✅ Multiple menus per site (Lunch, Dinner, Drinks, etc.)

**Image Management:**
- ✅ Image upload with automatic thumbnails
- ✅ Image library per site
- ✅ Image picker for blocks
- ✅ Alt text and captions

**Contact Form Submissions:**
- ✅ Form submission capture from public websites
- ✅ Submission management (read/unread, spam marking)
- ✅ Email notifications for new submissions
- ✅ Reply via email links

**Activity Logging:**
- ✅ Full activity audit trail
- ✅ Detailed change tracking (which fields changed)
- ✅ Paginated activity history
- ✅ User attribution

**Mobile Responsive Admin:** 🌟
- ✅ Hamburger menu on mobile
- ✅ Slide-out sidebar navigation
- ✅ Touch-friendly interface
- ✅ Responsive stats cards and buttons

**Website Preview:**
- ✅ Live preview with edit mode toggle
- ✅ Social icons in header and footer
- ✅ Action buttons (Order Online, Reservations)
- ✅ Responsive design

**Access:**
- Admin: https://rm.swhgrp.com/websites/
- Preview: https://rm.swhgrp.com/websites/preview/{site-slug}/

**[→ View Websites Documentation](./websites/README.md)**

---

### 9. Maintenance System ✅ **Production Ready (NEW - Jan 2026)** 🌟
**Equipment tracking, work order management, and preventive maintenance scheduling**

- **URL:** https://rm.swhgrp.com/portal/maintenance/
- **API:** https://rm.swhgrp.com/maintenance/
- **Database:** maintenance (PostgreSQL 15)
- **Technology:** FastAPI, async SQLAlchemy, Alembic
- **Files:** 12 Python files, 5 Portal templates
- **Status:** Production ready with full feature set ✅

**Features:**

**Equipment Management:**
- ✅ Equipment catalog with categories (hierarchical)
- ✅ Auto-generated QR codes for asset tracking
- ✅ Equipment status tracking (operational, needs maintenance, under repair, out of service, retired)
- ✅ Location-based organization
- ✅ Serial number and model tracking
- ✅ Purchase date and warranty expiry tracking
- ✅ Equipment history audit trail
- ✅ Search and filter by category, status, location

**Work Order Management:**
- ✅ Work order creation with priority levels (low, medium, high, critical)
- ✅ Work order types (repair, preventive, inspection, installation, other)
- ✅ Assignment to technicians
- ✅ Status workflow (open → in progress → on hold → completed/cancelled)
- ✅ Due date tracking
- ✅ Work order comments
- ✅ Parts tracking per work order
- ✅ Auto-generation from maintenance schedules

**Preventive Maintenance Scheduling:**
- ✅ Recurring maintenance schedules
- ✅ Frequency options (daily, weekly, monthly, quarterly, yearly)
- ✅ Configurable intervals (e.g., every 2 weeks, every 3 months)
- ✅ Next due date calculation
- ✅ Overdue maintenance alerts
- ✅ Schedule completion tracking with custom date selection
- ✅ Maintenance completion logging (MaintenanceLog with date, notes, performed_by)
- ✅ Document attachments on completion (MaintenanceDocument with file uploads)
- ✅ One-click work order creation from schedules
- ✅ Location filter on schedules page
- ✅ Vendor assignment to scheduled maintenance

**Vendor Management:**
- ✅ Vendor contact information with phone formatting
- ✅ Service type categorization
- ✅ Link vendors to equipment and schedules
- ✅ Searchable vendor dropdown in work orders
- ✅ Quick-add vendor from work order/schedule forms

**Dashboard & Alerts:**
- ✅ Real-time statistics (total equipment, open work orders, overdue items)
- ✅ Unified action items (overdue + upcoming maintenance + critical work orders)
- ✅ Recent activity feed with location names and completion dates
- ✅ Open work orders panel
- ✅ DB connection warmup with retry on startup

**Portal Integration:**
- ✅ Full Portal UI with consistent styling
- ✅ Permission-based access (can_access_maintenance)
- ✅ Dashboard, Equipment, Work Orders, Schedules, Vendors pages
- ✅ Mobile-responsive design
- ✅ Styled confirmation dialogs (replaces browser alerts)
- ✅ Searchable dropdown components for equipment and vendors

**API Endpoints:**
- `/maintenance/health` - Health check
- `/maintenance/dashboard` - Dashboard stats, alerts, and recent activity
- `/maintenance/equipment` - Equipment CRUD with history
- `/maintenance/categories` - Category management
- `/maintenance/work-orders` - Work order management
- `/maintenance/schedules` - PM scheduling
- `/maintenance/vendors` - Vendor management

**Access:**
- Portal UI: https://rm.swhgrp.com/portal/maintenance/
- API Docs: https://rm.swhgrp.com/maintenance/docs

---

### 10. Food Safety System ✅ **Production Ready (NEW - Feb 2026)** 🌟
**Food safety & compliance incident tracking with document uploads and category-specific data**

- **URL:** https://rm.swhgrp.com/portal/food-safety/
- **API:** https://rm.swhgrp.com/food-safety/
- **Database:** food_safety (PostgreSQL 15)
- **Technology:** FastAPI, async SQLAlchemy (asyncpg), Alembic
- **Status:** Production ready with full feature set ✅

**Incident Management:**
- ✅ Incident creation with 4 categories (food safety, workplace safety, security, general)
- ✅ 24 incident types across categories
- ✅ Category-specific detail fields stored as JSONB (`extra_data`)
- ✅ Incident editing with full field population including category-specific sections
- ✅ Status workflow (open → investigating → resolved → closed)
- ✅ Severity levels (critical, high, medium, low)
- ✅ Location-based filtering
- ✅ Auto-generated incident numbers (INC-YYYY-NNNN)
- ✅ Double-submit prevention on forms
- ✅ Reporter name display (fetched from portal user system)
- ✅ Print-friendly incident reports

**Document & Photo Uploads:**
- ✅ File upload on incident creation and editing
- ✅ Upload directly from view modal (no need to open edit page)
- ✅ Drag-and-drop support
- ✅ Image, PDF, and Word document support (max 10MB)
- ✅ Download and delete documents
- ✅ Persistent storage via Docker volumes

**User Permissions:**
- ✅ Role-based access (admin, manager, user, viewer)
- ✅ HR employee integration for user management
- ✅ Portal SSO authentication

**API Endpoints:**
- `/food-safety/health` - Health check
- `/food-safety/incidents` - Incident CRUD
- `/food-safety/incidents/{id}/documents` - Document upload/list
- `/food-safety/incidents/documents/{id}/download` - Document download
- `/food-safety/users` - User permission management

**Access:**
- Portal UI: https://rm.swhgrp.com/portal/food-safety/
- API Docs: https://rm.swhgrp.com/food-safety/docs

---

### 11. Cookbook AI System ✅ **Production Ready (NEW - Mar 2026)** 🌟
**RAG-based cookbook reference and AI recipe creation tool powered by Claude**

- **URL:** https://rm.swhgrp.com/portal/cookbook/
- **API:** https://rm.swhgrp.com/cookbook/
- **Database:** cookbook_db (PostgreSQL 15) + ChromaDB (vector store)
- **Technology:** FastAPI, SQLAlchemy, ChromaDB, HuggingFace transformers (CPU PyTorch), Anthropic Claude API
- **Status:** Production ready with full feature set ✅

**PDF Cookbook Management:**
- ✅ Upload PDF cookbooks (up to 200MB)
- ✅ Automatic text extraction via pdfplumber with OCR fallback (pytesseract)
- ✅ Word-level chunking with configurable size/overlap
- ✅ Local embedding generation (sentence-transformers/all-MiniLM-L6-v2)
- ✅ Vector storage in ChromaDB for semantic search
- ✅ Background processing with real-time status polling
- ✅ Book deletion with cascade (DB chunks + ChromaDB vectors + PDF file)

**Recipe Lookup (RAG):**
- ✅ Natural language questions about uploaded cookbooks
- ✅ Semantic search across all books or filtered by specific books
- ✅ Claude AI generates answers with cookbook references and page numbers
- ✅ Query history tracking

**Recipe Creator:**
- ✅ AI-generated recipes based on ingredients, cuisine, cooking method
- ✅ Optional cookbook knowledge base reference for authentic techniques
- ✅ Structured output matching inventory recipe format (category, yield, prep/cook time, ingredients table, numbered instructions)
- ✅ Additional instructions field for dietary notes, scaling, substitutions
- ✅ Auto-saved to recipe library with full metadata

**Recipe Library:**
- ✅ Browse all saved and generated recipes
- ✅ Filter by cuisine, cooking method, book reference
- ✅ Individual recipe detail pages with structured layout
- ✅ Delete recipes from library list and detail view

**Access Control:**
- ✅ `can_access_cookbook` permission on portal users table
- ✅ Manageable from User Management page
- ✅ Portal SSO authentication with JIT user provisioning

**API Endpoints:**
- `/cookbook/health` - Health check with book/chunk counts
- `/cookbook/api/books/upload` - Upload PDF cookbook
- `/cookbook/api/books` - List books
- `/cookbook/api/query` - Recipe lookup (RAG query)
- `/cookbook/api/create` - Recipe creator
- `/cookbook/api/recipes` - Recipe library CRUD

**Access:**
- Portal UI: https://rm.swhgrp.com/portal/cookbook/
- API Docs: https://rm.swhgrp.com/cookbook/docs

---

## 🚀 Quick Start

### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- 4GB+ RAM
- 20GB+ disk space
- Domain with DNS configured

### Installation

1. **Clone the repository:**
```bash
git clone git@github.com:swhgrp/rm.git
cd restaurant-system
```

2. **Configure environment variables:**
```bash
# Copy environment files for each system
for dir in portal inventory hr accounting events integration-hub; do
    cp $dir/.env.example $dir/.env
    # Edit $dir/.env with your configuration
done
```

3. **Start all services:**
```bash
docker compose up -d
```

4. **Run database migrations:**
```bash
# All systems use Alembic for migrations
docker compose exec inventory-app alembic upgrade head
docker compose exec hr-app alembic upgrade head
docker compose exec accounting-app alembic upgrade head
docker compose exec events-app alembic upgrade head
docker compose exec integration-hub alembic upgrade head
```

5. **Load initial data:**
```bash
# Load chart of accounts for accounting (Python script, not Django command)
docker compose exec accounting-app python -c "from accounting.fixtures.load_coa import load_default_coa; load_default_coa()"

# Note: Admin users are created through HR system and Portal interface
# Initial data is typically loaded via SQL scripts or Python scripts, not Django fixtures
```

6. **Create admin users:**
```bash
# Admin users are created in the HR system database
# Use the HR system interface or direct SQL to create users
# Portal reads from hr_db for authentication

# Example: Access HR system to create first admin user
# Visit https://rm.swhgrp.com/hr/ or use SQL:
# INSERT INTO users (username, email, hashed_password, full_name, is_admin, is_active)
# VALUES ('admin', 'admin@example.com', '$2b$...', 'Admin User', true, true);
```

7. **Access the portal:**
```
https://rm.swhgrp.com/portal/
```

### Development Setup

```bash
# Run specific system locally
cd inventory  # or hr, accounting, events, etc.

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run development server
# All systems use FastAPI with Uvicorn
cd src
uvicorn portal.main:app --reload        # Portal
uvicorn inventory.main:app --reload     # Inventory
uvicorn hr.main:app --reload            # HR
uvicorn accounting.main:app --reload    # Accounting
uvicorn events.main:app --reload        # Events
uvicorn integration_hub.main:app --reload  # Integration Hub
uvicorn forms.main:app --reload           # Forms
```

---

## 📚 Documentation

### System Documentation
Each system has comprehensive README documentation:

- **[Portal README](./portal/README.md)** - Authentication, SSO, user management
- **[Inventory README](./inventory/README.md)** - Complete guide (426 lines)
- **[HR README](./hr/README.md)** - Employee management, documents, user accounts
- **[Accounting README](./accounting/README.md)** - Financial management, AP/AR
- **[Events README](./events/README.md)** - Event planning, public intake (278 lines)
- **[Integration Hub README](./integration-hub/README.md)** - API integrations, vendor sync
- **[Files README](./files/README.md)** - Document management, WebDAV sync, OnlyOffice
- **[Websites README](./websites/README.md)** - Restaurant CMS, page builder, menus

### Project Documentation
- **[CLAUDE.md](./CLAUDE.md)** - Developer reference (patterns, commands, features)
- **[SECURITY.md](./SECURITY.md)** - Security audit findings & remediation tracker
- **[TODO.md](./TODO.md)** - Active task tracking
- **[DOCUMENTATION_INDEX.md](./DOCUMENTATION_INDEX.md)** - Full docs directory

### API Documentation
- **Portal:** https://rm.swhgrp.com/portal/docs (FastAPI interactive docs)
- **Events:** https://rm.swhgrp.com/events/docs (FastAPI interactive docs)
- **All Systems:** FastAPI auto-generated OpenAPI docs at `/{system}/docs` endpoints

---

## 🛠️ Common Commands

### Docker Operations
```bash
# View all running containers
docker ps

# View all containers (including stopped)
docker ps -a

# View logs (follow mode)
docker compose logs -f [service-name]

# View last 100 lines of logs
docker compose logs --tail=100 [service-name]

# Restart a service
docker compose restart [service-name]

# Rebuild and restart
docker compose up -d --build [service-name]

# Stop all services
docker compose down

# Stop and remove volumes
docker compose down -v

# View container resource usage
docker stats
```

### Database Operations
```bash
# Access PostgreSQL databases
docker compose exec inventory-db psql -U inventory_user -d inventory_db
docker compose exec hr-db psql -U hr_user -d hr_db
docker compose exec accounting-db psql -U accounting_user -d accounting_db
docker compose exec events-db psql -U events_user -d events_db

# Backup database
docker compose exec inventory-db pg_dump -U inventory_user inventory_db > backup_$(date +%Y%m%d).sql

# Restore database
cat backup_20251028.sql | docker compose exec -T inventory-db psql -U inventory_user inventory_db

# Backup all databases (daily automated backups)
./scripts/backup_databases.sh

# Rotate backups (keep last 7 days, archive older ones)
./scripts/rotate-backups.sh
```

### FastAPI/Alembic Operations
```bash
# Run migrations (all systems use Alembic)
docker compose exec [service]-app alembic upgrade head

# Create new migration
docker compose exec [service]-app alembic revision --autogenerate -m "description"

# Downgrade migration
docker compose exec [service]-app alembic downgrade -1

# View migration history
docker compose exec [service]-app alembic history

# Python shell (interactive Python with service context)
docker compose exec [service]-app python

# View FastAPI OpenAPI docs
# Visit: https://rm.swhgrp.com/[service]/docs
```

### System Health Checks
```bash
# Check all system health endpoints
curl https://rm.swhgrp.com/portal/health
curl https://rm.swhgrp.com/inventory/health
curl https://rm.swhgrp.com/hr/health
curl https://rm.swhgrp.com/accounting/health
curl https://rm.swhgrp.com/events/health
curl https://rm.swhgrp.com/hub/health

# Run all health checks at once
./scripts/health_check.sh
```

### Monitoring

**Web Dashboard (Recommended):**
```
Access: https://rm.swhgrp.com/portal/monitoring (Admin only)
Features: Real-time monitoring of all services, databases, backups, SSL, and infrastructure
Auto-refresh: Every 30 seconds
```

**Manual Monitoring Commands:**
```bash
# View monitoring dashboard status
/opt/restaurant-system/scripts/dashboard-status.sh

# Check service health
/opt/restaurant-system/scripts/monitor-services.sh

# Check disk space
/opt/restaurant-system/scripts/monitor-disk-space.sh

# Check SSL certificate
/opt/restaurant-system/scripts/monitor-ssl-cert.sh

# Verify backups
/opt/restaurant-system/scripts/verify-backups.sh

# View Nginx access logs
docker compose exec nginx-proxy tail -f /var/log/nginx/access.log

# View Nginx error logs
docker compose exec nginx-proxy tail -f /var/log/nginx/error.log

# Check disk space
df -h

# View system memory
free -h

# Check database sizes
docker compose exec inventory-db psql -U inventory_user -d inventory_db -c "\l+"
```

---

## 🔄 Integration Points

### Portal → All Systems
- **Provides:** JWT authentication tokens
- **Manages:** User sessions and permissions
- **Validates:** System access per user
- **Flow:** User logs in → Portal creates JWT → Systems validate token

### Inventory → Accounting
- **Sends:** Product costs for COGS calculation
- **Sends:** Purchase order data for AP
- **Sends:** Inventory valuation for Balance Sheet
- **Frequency:** Real-time on transactions

### Events → Accounting (Future)
- **Sends:** Event revenue data
- **Sends:** Deposits and payments
- **Sends:** Event-related expenses
- **Status:** Planned integration

### HR → Portal
- **Provides:** User account data
- **Shares:** `users` table for authentication
- **Manages:** System permissions
- **Sync:** Real-time via shared database

### Integration Hub ↔ Inventory
- **Hub provides:** Vendor items, pricing, invoices, GL mappings, UOM, Categories (source of truth)
- **Inventory provides:** Master items, count units, location costs, locations
- **Location-aware costing:** Hub updates `MasterItemLocationCost` when invoices are processed
- **Single purchase UOM:** `pack_to_primary_factor` on vendor items defines purchase-to-primary-unit conversion; auto-calculated from size fields
- **Location sync:** Accounting fetches locations from Inventory via `/_sync` endpoint
- **Note:** Hub is authoritative for vendor/pricing data; Inventory owns item costs and locations

### Integration Hub → Accounting
- **Creates:** Journal entries from processed invoices
- **Tracks:** AP bills with GL account mappings
- **Status:** Production (creates balanced Dr/Cr entries)

### POS Systems → Inventory
- **Syncs:** Daily sales data
- **Updates:** Stock levels based on sales
- **Tracks:** Recipe usage
- **Supported:** Clover, Square, Toast

---

## ⚠️ Critical Priorities

### Immediate (This Week) 🔴
- [x] **Set up automated database backups** ✅ COMPLETED
  - [x] Daily backups for all 5 databases (automated via cron)
  - [x] 7-day retention policy implemented (`scripts/rotate-backups.sh`)
  - [x] Older backups archived to `/opt/archives/old-backups/`
  - [x] Log rotation configured via `/etc/logrotate.d/restaurant-system`
  - [x] ✅ Remote backup via **Linode Backup Service** (server-level backups)
  - [ ] TODO: Test restore procedures

- [x] **Implement monitoring and alerting** ✅ COMPLETED (Nov 9, 2025)
  - [x] Health check monitoring dashboard (Portal /monitoring)
  - [x] Disk space alerts (90% warning, 95% critical)
  - [x] SSL certificate expiration monitoring (30-day warning)
  - [x] Service health status tracking (all 7 systems)
  - [x] Database connectivity monitoring
  - [x] Auto-refresh every 30 seconds

- [ ] **Move secrets out of Git repository**
  - Use environment variables or secrets manager
  - Rotate API keys and passwords
  - Remove `.env` files from Git history

- [x] **Document backup/restore procedures** ✅ COMPLETED
  - [x] Backup rotation documented
  - [x] ✅ Complete backup strategy guide: `docs/BACKUP_STRATEGY.md`
  - [x] ✅ Disaster recovery procedures documented
  - [x] ✅ RTO/RPO defined (1-2 hours / 24 hours)

### Short-Term (Next 2 Weeks) 🟡
- [ ] Set up error tracking (Sentry or similar)
- [ ] Implement API rate limiting
- [ ] Configure SSL auto-renewal monitoring
- [ ] Test all backup procedures
- [ ] Complete RBAC enforcement in Events system
- [ ] Set up log aggregation

### Medium-Term (Next Month) 🟢
- [ ] Implement CI/CD pipeline
- [ ] Complete Integration Hub webhook retry logic
- [ ] Finish Accounting budgeting features
- [ ] Implement HR benefits management
- [ ] Add more vendor integrations to Hub
- [ ] Write comprehensive test suites
- [ ] Performance optimization

### Long-Term (Next Quarter) 🔵
- [ ] Advanced analytics dashboard
- [ ] AI/ML features (forecasting, recommendations)
- [x] ✅ Mobile apps — iOS app built (SwiftUI), Android planned (Kotlin Multiplatform)
- [x] ✅ Multi-location support (already implemented in Inventory, Accounting, HR, Events)
- [ ] Advanced workflow automation
- [ ] Blockchain audit trail (if required)

---

## 📞 Support

### System Health Checks
```bash
# Check individual services
curl https://rm.swhgrp.com/portal/health
curl https://rm.swhgrp.com/inventory/health
curl https://rm.swhgrp.com/hr/health
curl https://rm.swhgrp.com/accounting/health
curl https://rm.swhgrp.com/events/health
curl https://rm.swhgrp.com/hub/health

# All checks at once
./scripts/health_check.sh
```

### Log Access
```bash
# View logs for any service
docker compose logs -f [service-name]

# View all logs
docker compose logs -f

# View last 100 lines
docker compose logs --tail=100 [service-name]

# Follow specific service
docker compose logs -f inventory-app
```

### Access Points
- **Portal:** https://rm.swhgrp.com/portal/
- **Inventory:** https://rm.swhgrp.com/inventory/
- **HR:** https://rm.swhgrp.com/hr/
- **Accounting:** https://rm.swhgrp.com/accounting/
- **Events:** https://rm.swhgrp.com/events/
- **Integration Hub:** https://rm.swhgrp.com/hub/
- **Files:** https://rm.swhgrp.com/files/
- **Websites:** https://rm.swhgrp.com/websites/

### Contact Information
- **Development Team:** [Contact Info]
- **System Administrator:** [Contact Info]
- **User Support:** [Contact Info]
- **Emergency Contact:** [Contact Info]

---

## 🤝 Contributing

This is a proprietary internal system. For authorized contributors:

1. Create feature branch from `main`
2. Make changes with clear commit messages
3. Test thoroughly in development environment
4. Submit pull request with detailed description
5. Wait for code review and approval
6. Merge after approval

**Commit Message Format:**
```
type(scope): Brief description

Detailed explanation of changes...

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## 📈 Development Roadmap

### Phase 1: Stabilization (Current - Q4 2025)
- ✅ Core functionality complete
- ✅ Production deployment
- ✅ Documentation complete
- ✅ **Monitoring implementation** (Complete real-time dashboard)
- ✅ **Automated backups** (Daily backups with weekly verification)
- 🔄 Security hardening

### Phase 2: Enhancement (Q1 2026)
- Complete RBAC across all systems
- Advanced reporting
- API rate limiting
- Comprehensive testing
- Performance optimization

### Phase 3: Scale (Q2 2026)
- ✅ Multi-location support (already implemented in Inventory, Accounting, HR, Events)
- 🔄 Mobile apps — iOS (SwiftUI) Inventory module complete, Android (KMP) planned
- Advanced third-party integrations (POS, payment processors)
- Enhanced BI and analytics dashboards
- Demand forecasting tools
- Mobile apps (if needed)

### Phase 4: Innovation (Q3 2026)
- AI-powered insights
- Predictive analytics
- Automated workflows
- Advanced automation
- Blockchain integration (if required)

---

## 📄 License

**Proprietary - SW Hospitality Group Internal Use Only**

This software is proprietary and confidential. Unauthorized copying, distribution, or use is strictly prohibited.

---

## 🎉 Acknowledgments

**Built with:**
- **FastAPI** - Modern async framework for ALL 11 systems (Portal, HR, Inventory, Accounting, Integration Hub, Events, Files, Websites, Maintenance, Food Safety, Cookbook AI)
- PostgreSQL 15 - Reliable database system
- **SQLAlchemy** - ORM for all systems
- Redis 7 - Caching and task queues
- **APScheduler** - Background job scheduling (not Celery)
- Docker & Docker Compose - Containerization
- Nginx - High-performance web server
- Bootstrap 5 - UI framework
- HTMX - Dynamic frontend interactions
- FullCalendar.js - Event calendar
- Chart.js - Data visualization
- WeasyPrint - PDF generation
- **OnlyOffice Document Server** - Collaborative document editing
- **WsgiDAV** - WebDAV server for desktop sync
- **Radicale** - CalDAV server for calendar sync
- Local File Storage - Document management

---

## 📊 System Status Summary

| System | Status | Python Files | Templates | Models | Completion | Notes |
|--------|--------|--------------|-----------|--------|------------|-------|
| Portal | ⚠️ Production | 3 | 15 | 1 | **~95%** | Monitoring dashboard, password reset |
| Inventory | ✅ Production | 104 | 31 | 32+ | **100%** 🌟 | POS sync, recipe costing, location costs |
| HR | ✅ Production | 60+ | 17 | 20+ | **~95%** | Required docs, e-signatures, audit logging |
| Accounting | ✅ Production | 119 | 38+ | 26+ | **~95%** 🌟 | Plaid, multi-location reports, AR automation |
| Events | ✅ Production | 55 | 18 | 17+ | **~99%** 🌟 | Contracts, CalDAV item sync, calendar search |
| Integration Hub | ✅ Production | 61 | 14 | 18+ | **~98%** 🌟 | Single-UOM pricing, post-parse validation, AI search |
| Files | ✅ Production | 18 | 4 | 7 | **~85%** | WebDAV sync + OnlyOffice editing |
| Websites | ✅ Production | 7 | 18 | 11+ | **~90%** | Block-based page builder, menu management |
| Maintenance | ✅ Production | 16 | 5 | 10 | **100%** 🌟 | Equipment, work orders, PM schedules |
| Food Safety | ✅ Production | 29 | 5 | 18 | **100%** 🌟 | Incidents, document uploads, user permissions |
| Cookbook AI | ✅ Production | 12 | 7 | 5 | **100%** 🌟 | RAG cookbook search, AI recipe creation, PDF upload |

**Total:** 510+ Python files, 180+ templates, 165+ database models (verified Mar 20, 2026)

**Overall Status:** ~98% Complete - All 11 Systems Production Ready ✅

**Active Issues (Mar 5, 2026):**
- ⚠️ **Portal:** `/debug` endpoint has no authentication
- ⚠️ **HR:** Uses in-memory dict for sessions (should use Redis)
- ⚠️ **Events/Websites:** Empty alembic/versions directories (use create_all instead)

**Resolved Issues:**
- ✅ ~~Events System: Authentication not implemented~~ - RESOLVED (Nov 1, 2025)
- ✅ ~~Accounting System: Wrong framework documented~~ - RESOLVED (Nov 11, 2025)
- ✅ ~~Integration Hub: Major feature misrepresentation~~ - RESOLVED (Oct 31, 2025)
- ✅ **Websites CMS added** - Full restaurant website management (Dec 8, 2025)
- ✅ **Cookbook AI added** - RAG-based cookbook reference, AI recipe creation, PDF upload & processing (Mar 9, 2026)
- ✅ **Cookbook structured recipes** - Inventory-format recipe output, delete from library, embedding fix (Mar 11, 2026)
- ✅ **Event price quotes** - Price Quote PDF generation from events (Mar 11, 2026)
- ✅ **File manager improvements** - Owner-only folders, search enhancements (Mar 11, 2026)
- ✅ **GFS CSV invoice parsing** — Multi-format CSV support, catch-weight handling, PDF-to-CSV replacement (Mar 20, 2026)
- ✅ **DSS GL validation** — Server+client-side GL account validation before posting daily sales (Mar 20, 2026)
- ✅ **Fintech duplicate detection** — Leading-zero-stripped invoice matching prevents Fintech CSV/PDF duplicates (Mar 25, 2026)
- ✅ **CSV viewer filtering** — Multi-vendor CSV files filtered to show only relevant invoice rows (Mar 25, 2026)
- ✅ **Third-party payment deposits** — DoorDash/UberEats included in DSS card_deposit calculation (Mar 25, 2026)

---

**Version:** 4.6
**Last Updated:** March 25, 2026
**Maintained By:** SW Hospitality Group Development Team

**For developer reference, see [CLAUDE.md](./CLAUDE.md)**

---

## Development History

For detailed development history, see the git log. Key milestones:

- **Mar 2026** — Fintech duplicate detection, CSV viewer filtering, third-party payment deposits, GFS CSV parsing, PDF reference invoices, CSV expected vendors, DSS GL validation, vendor reactivation, mobile app (iOS auth + inventory), catering contracts, CalDAV item sync, GL anomaly detection, count session reports, e-signatures
- **Feb 2026** — UOM simplification (single purchase UOM per vendor item), post-parse invoice validation, food safety incidents, HR required documents, order sheets, vendor item name normalization
- **Jan 2026** — Maintenance system, food safety system, Plaid bank integration, quick holds, CalDAV sync
- **Dec 2025** — Location-aware costing architecture, Hub source of truth, AI semantic search, expense/vendor item separation, vendor items pagination
- **Nov 2025** — Automated invoice intake pipeline (email → AI parse → auto-map), multi-page OCR, bulk mapping, Events SSO integration, documentation audit
- **Oct 2025** — Initial documentation overhaul, system cleanup, Nextcloud removal, Files system refactor

For developer reference and feature documentation, see [CLAUDE.md](./CLAUDE.md).

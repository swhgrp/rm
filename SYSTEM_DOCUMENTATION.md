# SW HOSPITALITY GROUP - RESTAURANT MANAGEMENT SYSTEM
## Complete System Documentation
**Last Updated:** 2025-10-28
**Status:** Production Ready (90% Complete)

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
9. [Infrastructure](#infrastructure)
10. [Deployment](#deployment)

---

## SYSTEM OVERVIEW

### Architecture
**Type:** Microservices Architecture
**Deployment:** Docker Compose on dedicated server (172.233.172.92)
**Domain:** rm.swhgrp.com
**Authentication:** Centralized JWT-based SSO via Portal
**Database:** PostgreSQL 15 (separate instance per system)
**Cache/Queue:** Redis 7
**Web Server:** Nginx with SSL/TLS

### System URLs
- **Portal:** https://rm.swhgrp.com/portal/
- **Inventory:** https://rm.swhgrp.com/inventory/
- **HR:** https://rm.swhgrp.com/hr/
- **Accounting:** https://rm.swhgrp.com/accounting/
- **Events:** https://rm.swhgrp.com/events/
- **Integration Hub:** https://rm.swhgrp.com/hub/
- **Files:** https://rm.swhgrp.com/files/

### Infrastructure Status
```
RUNNING CONTAINERS:
✅ nginx-proxy          - Nginx reverse proxy (ports 80, 443)
✅ portal-app           - Authentication & navigation
✅ inventory-app        - Inventory management
✅ inventory-db         - PostgreSQL 15 (port 5432)
✅ inventory-redis      - Redis cache
✅ hr-app               - HR management
✅ hr-db                - PostgreSQL 15
✅ accounting-app       - Accounting system
✅ accounting-db        - PostgreSQL 15
✅ events-app           - Events & catering
✅ events-db            - PostgreSQL 15
✅ events-redis         - Redis cache
✅ integration-hub      - Integration services
✅ hub-db               - PostgreSQL 15
```

---

## PORTAL SYSTEM

### Purpose
Central authentication and single sign-on portal for all restaurant systems.

### Implementation Status: 95% Complete

**What's Built:**
- ✅ JWT-based authentication
- ✅ Session management with secure cookies
- ✅ User login/logout
- ✅ Permission-based system access control
- ✅ Admin user management interface
- ✅ System navigation dashboard
- ✅ Token generation for cross-system authentication
- ✅ Dark theme UI matching Events system
- ❌ Password reset flow (MISSING)
- ❌ User registration (manual only)
- ❌ Two-factor authentication (FUTURE)

**Technology Stack:**
- FastAPI (Python)
- SQLAlchemy ORM
- JWT tokens (jose library)
- Bcrypt password hashing
- Jinja2 templates
- Shares HR database for user management

**Files:**
- Python: 3 files
- Templates: 4 HTML files
- Models: Inline in main.py (User model)

**Database:**
Uses HR system database, table: `users`

**User Permissions:**
Each user has boolean flags:
- `can_access_portal` - Portal access
- `can_access_inventory` - Inventory system
- `can_access_accounting` - Accounting system
- `can_access_hr` - HR system
- `can_access_events` - Events system
- `can_access_integration_hub` - Integration Hub
- `can_access_files` - Files system
- `accounting_role_id` - Accounting system role assignment

**API Endpoints:**
- `GET /portal/` - Dashboard (requires auth)
- `GET /portal/login` - Login page
- `POST /portal/login` - Process login
- `GET /portal/logout` - Logout
- `GET /portal/settings` - User management (admin only)
- `POST /portal/api/users/{id}/permissions` - Update user permissions
- `GET /portal/api/generate-token/{system}` - Generate SSO token
- `GET /portal/health` - Health check

**Authentication Flow:**
1. User logs in via Portal
2. Portal creates JWT token with user info
3. Token stored in secure HTTP-only cookie
4. User clicks system link (e.g., Inventory)
5. Portal generates short-lived (5 min) system token
6. System validates token and creates own session
7. User accesses system without re-login

---

## INVENTORY SYSTEM

### Purpose
Complete inventory management including products, suppliers, purchase orders, stock counts, and locations.

### Implementation Status: 100% Complete ✅

**Technology Stack:**
- Django 4.2 (Python)
- PostgreSQL 15
- Redis (caching & sessions)
- Bootstrap 5 UI
- Chart.js for analytics

**Files:**
- Python: 101 files
- Templates: 27 HTML files
- Models: 21 model files
- API routes: 23 files
- Services: 5 files
- README: 426 lines (COMPLETE)

**Database:** inventory_db (dedicated PostgreSQL instance)

**Core Features:**
✅ **Product Management**
  - Products with categories, UOM, par levels
  - Product variants and pricing
  - Barcode scanning support
  - Image upload

✅ **Supplier Management**
  - Supplier directory with contacts
  - Product-supplier relationships
  - Pricing history

✅ **Purchase Orders**
  - Create/edit/approve workflow
  - Email PO to suppliers
  - Receive against PO
  - Partial receiving
  - PO status tracking

✅ **Stock Counts**
  - Physical count entry
  - Variance reporting
  - Count sheets by location/category
  - Adjustment history

✅ **Locations & Warehouses**
  - Multi-location support
  - Stock transfers
  - Location-specific inventory

✅ **Analytics & Reporting**
  - Stock level reports
  - Usage analytics
  - Valuation reports
  - Reorder suggestions

✅ **Integration**
  - Vendor API integration (via Integration Hub)
  - Automated stock updates
  - Recipe costing (future)

**Key Models:**
- Product, ProductCategory, ProductVariant
- Supplier, SupplierProduct
- PurchaseOrder, PurchaseOrderItem
- StockCount, StockCountItem
- StockMovement, StockAdjustment
- Location, Warehouse
- RecipeIngredient (future)

**API Endpoints:** 50+ REST endpoints

**Documentation:** Comprehensive README.md exists

---

## HR SYSTEM

### Purpose
Employee management, scheduling, time tracking, and payroll integration.

### Implementation Status: 85% Complete

**Technology Stack:**
- Django 4.2 (Python)
- PostgreSQL 15
- Celery (background jobs)
- Bootstrap UI

**Files:**
- Python: 53 files
- Templates: 13 HTML files
- Models: 13 model files
- API routes: 12 files
- Services: 2 files
- README: MISSING ❌

**Database:** hr_db (dedicated PostgreSQL instance)

**Core Features:**
✅ **Employee Management**
  - Employee profiles
  - Department assignments
  - Job titles and positions
  - Emergency contacts
  - Document storage

✅ **User Accounts**
  - Portal integration
  - Username/password
  - System permissions
  - Active/inactive status

✅ **Scheduling**
  - Shift scheduling
  - Department-based schedules
  - Availability tracking
  - Shift swaps (partial)

✅ **Time Tracking**
  - Clock in/out
  - Time adjustments
  - Overtime calculation
  - Break tracking

🔄 **Payroll** (Partial - 50%)
  - Pay rate management
  - Hour calculations
  - Export for payroll processing
  - ❌ Direct payroll processing
  - ❌ Tax calculations
  - ❌ Direct deposit

❌ **Benefits Management** (Not Started)
  - Health insurance
  - PTO tracking
  - 401k management

**Key Models:**
- Employee, Department, Position
- User (shared with Portal)
- Schedule, Shift, Availability
- TimeEntry, TimeAdjustment
- PayRate, PayPeriod
- EmergencyContact, Document

**Integration:**
- Provides user data to Portal for authentication
- Syncs employee data to other systems
- Integration Hub can sync from external HR systems

**Needs:**
- Comprehensive README documentation
- Complete payroll features
- Benefits management
- PTO/vacation tracking

---

## ACCOUNTING SYSTEM

### Purpose
Full double-entry accounting system with chart of accounts, journal entries, invoices, and financial reporting.

### Implementation Status: 95% Complete

**Technology Stack:**
- Django 4.2 (Python)
- PostgreSQL 15
- Complex financial logic
- Advanced reporting

**Files:**
- Python: 140 files (LARGEST SYSTEM)
- Templates: 37 HTML files
- Models: 26 model files
- API routes: 28 files
- Services: 17 files
- README: MISSING ❌

**Database:** accounting_db (dedicated PostgreSQL instance)

**Core Features:**
✅ **Chart of Accounts**
  - Account hierarchy
  - Account types (Asset, Liability, Equity, Revenue, Expense)
  - Account codes
  - Active/inactive accounts
  - Account balances

✅ **Journal Entries**
  - Manual journal entries
  - Auto-posting from other systems
  - Entry validation (debits = credits)
  - Reversal entries
  - Recurring entries
  - Entry approval workflow

✅ **Accounts Payable**
  - Vendor invoices
  - Bill payment
  - Payment tracking
  - Aging reports
  - 1099 tracking

✅ **Accounts Receivable**
  - Customer invoices
  - Payment receipt
  - Collections
  - Aging reports
  - Credit memos

✅ **Banking**
  - Bank account reconciliation
  - Bank feeds (partial)
  - Check printing
  - Deposit tracking

✅ **Financial Reporting**
  - Balance Sheet
  - Profit & Loss (Income Statement)
  - Cash Flow Statement
  - Trial Balance
  - General Ledger
  - Account transaction history
  - Custom date ranges
  - Comparison reports

✅ **Fiscal Period Management**
  - Period open/close
  - Year-end close
  - Audit trail

🔄 **Budgeting** (Partial - 40%)
  - Budget entry
  - Budget vs Actual
  - ❌ Variance analysis
  - ❌ Forecasting

✅ **Multi-Entity** (If needed)
  - Separate books per location/entity
  - Consolidated reporting

**Key Models:**
- Account, AccountType, AccountSubtype
- JournalEntry, JournalEntryLine
- Invoice, InvoiceItem, Payment
- Bill, BillItem, BillPayment
- BankAccount, BankTransaction, Reconciliation
- Customer, Vendor
- FiscalPeriod, FiscalYear
- Budget, BudgetItem
- TaxRate, TaxJurisdiction

**Reporting Engine:**
- Complex SQL queries
- PDF report generation
- Excel export
- Email delivery

**Integration:**
- Receives transactions from Inventory (product costs)
- Receives transactions from Events (event revenue)
- Integration Hub can sync with QuickBooks/Xero (future)

**Role-Based Access:**
- Admin - Full access
- Accountant - All except period close
- AP Clerk - Bills and payments only
- AR Clerk - Invoices and receipts only
- Read Only - Reports only

**Needs:**
- Complete README documentation
- Finish budgeting features
- Add forecasting
- Complete bank feed integration

---

## EVENTS SYSTEM

### Purpose
Event planning and catering management with BEO generation, task tracking, and client communications.

### Implementation Status: 85% Complete

**Technology Stack:**
- FastAPI (Python async)
- PostgreSQL 15
- Redis
- WeasyPrint (PDF generation)
- FullCalendar.js
- Bootstrap Icons
- Dark theme UI

**Files:**
- Python: 35 files
- Templates: 10 HTML files
- Models: 9 model files
- API routes: 6 files
- Services: 5 files
- README: 278 lines (EXISTS but outdated)

**Database:** events_db (dedicated PostgreSQL instance)

**Core Features:**
✅ **Event Management**
  - Create/edit events
  - Event status workflow (Draft → Pending → Confirmed → In Progress → Completed)
  - Client assignment
  - Venue selection
  - Guest count tracking
  - Start/end times with setup/teardown
  - Event types (Wedding, Corporate, Birthday, etc.)
  - Special requirements/notes

✅ **Public Intake Form**
  - No authentication required
  - hCaptcha spam protection
  - Auto-creates client records
  - Creates pending events for review
  - Email confirmation to client
  - Mobile-optimized
  - URL: https://rm.swhgrp.com/events/public/intake

✅ **Calendar View**
  - Month/week/day views
  - FullCalendar integration
  - Color-coded by status
  - Drag-and-drop (partial)
  - Event filtering

✅ **Task Management**
  - Auto-task generation from templates
  - Department assignment
  - Priority levels
  - Due date tracking
  - Checklist items
  - Task status (Todo, In Progress, Blocked, Done)
  - Kanban board view

✅ **Document Generation**
  - BEO (Banquet Event Order) PDF
  - Event summary PDF
  - WeasyPrint rendering
  - Version control (partial)
  - Download/email delivery

✅ **Email Notifications**
  - Client confirmation emails
  - Internal team notifications
  - Task assignment emails
  - Event update alerts
  - Template-based
  - SMTP sending

✅ **Client Management**
  - Client contact info
  - Organization tracking
  - Event history
  - Auto-create from intake form

✅ **Venue Management**
  - Venue directory
  - Room configurations
  - Capacity tracking
  - Availability (future)

🔄 **Menu & Catering** (Partial - 60%)
  - Menu JSON storage
  - Menu display in BEO
  - ❌ Menu builder UI
  - ❌ Recipe integration with Inventory
  - ❌ Cost calculation

🔄 **Financials** (Partial - 50%)
  - Pricing packages
  - Deposit tracking
  - ❌ Payment processing
  - ❌ Integration with Accounting
  - ❌ Invoicing

🔄 **RBAC** (Partial - 60%)
  - User/role models exist
  - Auth service has logic
  - ❌ Not enforced on endpoints
  - ❌ UI doesn't hide features

❌ **Not Implemented:**
  - HR sync for user management
  - Celery background jobs
  - S3 document storage (uses local)
  - Event templates CRUD UI
  - Audit log population
  - Advanced analytics

**Key Models:**
- Event, EventStatus, EventTemplate
- Client, Venue, EventPackage
- Task, TaskChecklistItem
- Document, DocumentType
- Email, EmailStatus
- User, Role, UserRole (not actively used)
- NotificationRule
- AuditLog (defined but not populated)

**API Endpoints:**
- Events CRUD: GET/POST/PATCH/DELETE
- Calendar: GET /api/events/calendar
- Stats: GET /api/events/stats
- Venues: GET /api/events/venues
- Clients: GET /api/events/clients
- Tasks: Full CRUD
- Documents: PDF generation
- Public: POST /public/beo-intake

**UI Pages:**
- Dashboard - Stats, quick actions, upcoming events
- All Events - Filterable event list
- Event Detail - Tabbed view (Overview, Details, Menu, Financials, Tasks, Docs)
- Calendar - Month/week/day calendar
- Tasks - Kanban board
- Public Intake Form - External submission

**Mobile Responsive:** ✅ All pages fully mobile-optimized

**Documentation:** README exists but states "40% complete" when actually ~85% complete

**Needs:**
- Update README to reflect actual status
- Implement RBAC enforcement
- Complete menu builder
- Financial integration with Accounting
- HR sync for users
- Complete document versioning
- S3 storage migration

---

## INTEGRATION HUB

### Purpose
Central integration point for third-party vendor APIs, data synchronization, and webhook management.

### Implementation Status: 70% Complete

**Technology Stack:**
- Django 4.2 (Python)
- PostgreSQL 15
- Celery (async tasks)
- Redis (task queue)
- OAuth2 for vendor authentication

**Files:**
- Python: 24 files
- Templates: 7 HTML files
- Models: 5 model files
- API routes: 2 files
- Services: 5 files
- README: MISSING ❌

**Database:** hub_db (dedicated PostgreSQL instance)

**Core Features:**
✅ **Vendor Integrations**
  - Vendor connection management
  - OAuth2 authentication
  - API credential storage (encrypted)
  - Connection status monitoring
  - Sync frequency configuration

✅ **Data Synchronization**
  - Product catalog sync
  - Pricing updates
  - Inventory levels
  - Order status
  - Scheduled sync jobs
  - Manual sync triggers

🔄 **Webhook Management** (Partial - 50%)
  - Webhook registration
  - Payload validation
  - Event routing
  - ❌ Retry logic
  - ❌ Dead letter queue

✅ **Sync Logging**
  - Sync attempt tracking
  - Success/failure logs
  - Error details
  - Sync history

🔄 **Supported Vendors** (Partial)
  - ✅ US Foods
  - ✅ Sysco
  - 🔄 Restaurant Depot (partial)
  - ❌ Shamrock Foods (planned)
  - ❌ Performance Food Group (planned)

✅ **API Management**
  - Rate limiting
  - Request logging
  - Error handling
  - Timeout management

**Key Models:**
- VendorConnection, VendorType
- SyncLog, SyncStatus
- WebhookEndpoint, WebhookEvent
- APICredential
- DataMapping

**Integration Points:**
- **Inventory System:** Product catalog, pricing, stock levels
- **Accounting System:** Vendor invoices, payments
- **HR System:** Employee sync from external systems (future)
- **Events System:** Catering supplier integration (future)

**Background Jobs:**
- Scheduled vendor syncs (Celery)
- Webhook processing
- Failed sync retry
- Data cleanup

**Needs:**
- Comprehensive README
- Complete webhook retry logic
- Add more vendor integrations
- Better error handling
- Sync conflict resolution
- Admin UI improvements

---

## FILES SYSTEM

### Purpose
Document management, file storage, and secure file sharing for the restaurant system.

### Implementation Status: 100% Complete ✅

**Technology:** FastAPI with local file storage

**Integration:** SSO via Portal system (✅ Complete)

**Database:** PostgreSQL 15 (HR database for users, local DB for file metadata)

**Storage:** Local filesystem at `/app/storage` with per-user isolation

**Document Conversion:** LibreOffice (headless) for Office document preview

**Python Files:** 11 | **Templates:** 2

**Access:** https://rm.swhgrp.com/files/

### Core Features

**File Management:**
✅ Upload files (single and bulk with drag-and-drop)
✅ Download files (direct and streaming)
✅ File preview (PDFs, images, Office documents)
✅ Delete, rename, copy, and move files
✅ File metadata tracking (size, type, owner, timestamps)
✅ MIME type detection
✅ Bulk selection for batch operations

**Folder Organization:**
✅ Create folders with hierarchical structure
✅ Nested folders with CASCADE delete
✅ Breadcrumb navigation and back button
✅ Dashboard view with recent files and stats
✅ My Files view with traditional folder browser
✅ Shared views ("Shared with Me" and "Shared by Me")

**Security & Permissions:**
✅ User-based storage isolation (`user_{id}/`)
✅ Role-based access control (Admin, Owner, Shared)
✅ JWT authentication via Portal
✅ Granular permission levels (view, edit, upload, download, share, comment)
✅ Permission inheritance from folders

**Sharing:**
✅ Internal sharing with specific users
✅ Public share links with optional passwords
✅ Username autocomplete with full name display
✅ Share badges showing share status
✅ Expiration dates for public links
✅ Granular permission controls
✅ Dedicated share management pages

**Mobile & Responsive:**
✅ Mobile-responsive design (phones, tablets, desktops)
✅ Slide-out hamburger menu for mobile navigation
✅ Touch-optimized UI with 44px minimum touch targets
✅ Full-screen modals on mobile devices
✅ Responsive dashboard with stacked cards
✅ Breakpoints: ≤768px mobile, 768-992px tablet, ≥992px desktop

### Database Schema

**Tables:**
- `file_metadata` - File information and metadata
- `folders` - Hierarchical folder structure
- `internal_shares` - User-to-user sharing with permissions
- `share_links` - Public share links with tokens and passwords
- `users` - From HR database (authentication)

**Key Models:**
- FileMetadata, Folder, InternalShare, ShareLink, User

**Integration Points:**
- **Portal System:** JWT authentication and user permissions
- **HR System:** User data and authentication
- **Future:** Events (BEO attachments), HR (employee documents), Accounting (receipts), Inventory (product images)

### API Structure

**Endpoints:**
- `GET /api/files/folders` - List accessible folders
- `POST /api/files/folders` - Create new folder
- `DELETE /api/files/folders/{id}` - Delete folder
- `GET /api/files/list` - List files in folder
- `POST /api/files/upload` - Upload file(s)
- `GET /api/files/download/{id}` - Download file
- `DELETE /api/files/{id}` - Delete file
- `POST /api/files/share` - Share folder with user

**Frontend:**
- `/` - File manager interface
- `/health` - Health check endpoint

### Future Enhancements
- [ ] File versioning (track history)
- [ ] File preview (images, PDFs in browser)
- [ ] Search functionality
- [ ] Trash/recycle bin
- [ ] Storage quotas per user
- [ ] Bulk download (zip archives)
- [ ] File tagging
- [ ] Activity logs
- [ ] WebDAV support

---

## INFRASTRUCTURE

### Server Details
- **IP:** 172.233.172.92
- **Domain:** rm.swhgrp.com
- **OS:** Ubuntu Linux
- **Docker:** Docker Compose orchestration
- **SSL:** Let's Encrypt certificates via Certbot
- **Firewall:** UFW configured

### Network Architecture

**IMPORTANT:** This shows the **routing architecture**. Portal provides **SSO authentication** (JWT tokens), but does NOT proxy traffic. Each service is accessed directly through Nginx.

```
Internet → Nginx (ports 80/443) → Reverse Proxy → Microservices
                                                    ├─ Portal (8000) [SSO Auth]
                                                    ├─ Inventory (8000)
                                                    ├─ HR (8000)
                                                    ├─ Accounting (8000)
                                                    ├─ Events (8000)
                                                    ├─ Integration Hub (8000)
                                                    └─ Files (8000)
```

### Nginx Routing (Direct to Services)
- `/portal/` → portal-app:8000 **(Authentication/SSO)**
- `/inventory/` → inventory-app:8000
- `/hr/` → hr-app:8000
- `/accounting/` → accounting-app:8000
- `/events/` → events-app:8000
- `/hub/` → integration-hub:8000
- `/files/` → files-app:8000

### Authentication Flow (SSO)

```
1. User visits rm.swhgrp.com
2. Nginx redirects to /portal/ (login page)
3. User enters credentials
4. Portal validates against HR database
5. Portal issues JWT token (stored in secure cookie)
6. User sees dashboard with accessible systems
7. User clicks system (e.g., "Inventory")
8. Browser navigates to /inventory/
9. Nginx routes directly to inventory-app:8000
10. Inventory app validates JWT token from cookie
11. If valid: Show interface | If invalid: Redirect to /portal/login
```

**Key Architecture Points:**
- **Portal Role:** Authentication provider (SSO), NOT traffic proxy
- **Nginx Role:** SSL termination and routing to services
- **Service Independence:** Each service validates JWT independently
- **No Bottleneck:** Traffic does NOT flow through Portal
- **Shared Secret:** All services share Portal's JWT secret key for validation

### Database Strategy
Each system has its own PostgreSQL 15 database for true microservices isolation:
- `inventory_db` (port 5432 exposed)
- `hr_db`
- `accounting_db`
- `events_db`
- `hub_db`
- `music-streamer-db` (port 5433)

### Redis Usage
- inventory-redis: Caching, sessions
- events-redis: Caching, background jobs
- music-streamer-redis: Queue management

### Backup Strategy
⚠️ **CRITICAL NEED:** Automated database backups not fully configured

Recommended:
- Daily PostgreSQL dumps
- Backup to remote storage (S3)
- Retention policy (30 days daily, 12 months weekly)
- Disaster recovery testing

### Monitoring
⚠️ **NEEDS IMPLEMENTATION:**
- Health check monitoring
- Error tracking (Sentry)
- Performance monitoring (APM)
- Log aggregation (ELK stack or similar)
- Uptime monitoring
- Disk space alerts
- SSL expiration alerts

### Security
✅ **Implemented:**
- HTTPS/SSL encryption
- HTTP-only secure cookies
- CORS configuration
- Firewall rules
- Password hashing (bcrypt)
- JWT tokens

⚠️ **Needs Improvement:**
- Rate limiting
- API authentication tokens
- Secrets management (env files in repo)
- Regular security audits
- Dependency vulnerability scanning

---

## DEPLOYMENT

### Current Status: Production

**Deployment Method:** Docker Compose

**Deployment Process:**
1. Code changes pushed to Git (manual)
2. SSH to server
3. Pull latest code
4. Rebuild affected containers: `docker compose build [service]`
5. Restart containers: `docker compose up -d [service]`
6. Check logs: `docker compose logs -f [service]`

⚠️ **No CI/CD pipeline** - All deployments are manual

### Docker Compose Services
- portal-app
- inventory-app, inventory-db, inventory-redis
- hr-app, hr-db
- accounting-app, accounting-db
- events-app, events-db, events-redis
- integration-hub, hub-db
- files-app
- nginx-proxy

### Environment Variables
Each system has `.env` file with:
- Database credentials
- Secret keys
- API keys
- Third-party credentials
- Feature flags

⚠️ **Security Risk:** .env files may be in Git repository

### Database Migrations
- **Inventory:** Django migrations
- **HR:** Django migrations
- **Accounting:** Django migrations
- **Events:** Alembic migrations
- **Integration Hub:** Django migrations

Migration process:
```bash
# Django systems
docker compose exec [service] python manage.py migrate

# Events (FastAPI/Alembic)
docker compose exec events-app alembic upgrade head
```

### Rollback Process
⚠️ **NOT DOCUMENTED** - Need formal rollback procedures

### Health Checks
Each system has `/health` endpoint:
- https://rm.swhgrp.com/portal/health
- https://rm.swhgrp.com/inventory/health
- https://rm.swhgrp.com/hr/health
- https://rm.swhgrp.com/accounting/health
- https://rm.swhgrp.com/events/health
- https://rm.swhgrp.com/hub/health

---

## CRITICAL NEEDS (Priority Order)

### 1. IMMEDIATE (This Week)
- [ ] Set up automated database backups
- [ ] Update Events README to reflect actual status
- [ ] Create README for HR, Accounting, Integration Hub, Portal
- [ ] Document backup/restore procedures
- [ ] Implement RBAC enforcement in Events system
- [ ] Move secrets out of Git repository

### 2. SHORT-TERM (Next 2 Weeks)
- [ ] Implement monitoring and alerting
- [ ] Set up error tracking (Sentry)
- [ ] Configure SSL certificate auto-renewal monitoring
- [ ] Create disaster recovery plan
- [ ] Implement API rate limiting
- [ ] Set up log aggregation
- [ ] Test all backup procedures

### 3. MEDIUM-TERM (Next Month)
- [ ] Implement CI/CD pipeline
- [ ] Complete Events system RBAC
- [ ] Finish Integration Hub webhook retry logic
- [ ] Complete Accounting budgeting features
- [ ] Implement HR benefits management
- [ ] Add more vendor integrations to Hub
- [ ] SSO integration for Files system
- [ ] Write comprehensive test suites

### 4. LONG-TERM (Next Quarter)
- [ ] Performance optimization and load testing
- [ ] Complete mobile apps (if needed)
- [ ] Advanced analytics across all systems
- [ ] AI/ML features (forecasting, recommendations)
- [ ] Complete audit logging across all systems
- [ ] Multi-location support expansion
- [ ] Advanced reporting dashboard

---

## SYSTEM METRICS

### Code Statistics
- **Total Python files:** 356
- **Total HTML templates:** 98
- **Total database models:** 74
- **Total API endpoints:** ~150+
- **Total services/workers:** 34

### System Complexity (Python files)
1. Accounting: 140 files (most complex)
2. Inventory: 101 files
3. HR: 53 files
4. Events: 35 files
5. Integration Hub: 24 files
6. Portal: 3 files

### Database Tables (approximate)
- Inventory: 30+ tables
- Accounting: 40+ tables
- HR: 20+ tables
- Events: 15+ tables
- Integration Hub: 10+ tables
- Portal: Uses HR users table

### Overall Completion by System
1. **Inventory:** 100% ✅
2. **Files:** 100% ✅
3. **Portal:** 95% ✅
4. **Accounting:** 95% ✅
5. **Events:** 85% 🔄
6. **HR:** 85% 🔄
7. **Integration Hub:** 70% 🔄

**Average:** ~90% Complete

---

## CONCLUSION

The SW Hospitality Group Restaurant Management System is a **sophisticated, production-ready platform** with comprehensive functionality across all major business areas. The system demonstrates:

✅ **Strong Architecture:** Microservices with proper isolation
✅ **Comprehensive Features:** Nearly all core functionality implemented
✅ **Professional UI:** Dark theme, mobile-responsive, modern design
✅ **Good Security:** SSL, JWT auth, password hashing
✅ **Scalable Infrastructure:** Docker-based, easy to scale

**Key Strengths:**
- Inventory system is rock-solid
- Accounting system is highly sophisticated
- Events system has great UX
- Central authentication works well
- Mobile-responsive design throughout

**Key Weaknesses:**
- Missing documentation (4 systems have no README)
- No automated backups configured
- No CI/CD pipeline
- Limited monitoring/alerting
- Some features partially implemented
- No comprehensive testing

**Recommendation:** The system is **ready for production use** with daily operations, but **critical infrastructure improvements** (backups, monitoring, documentation) should be prioritized immediately to ensure long-term success and maintainability.

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

# Rebuild and restart
docker compose up -d --build [service-name]

# Access database
docker compose exec inventory-db psql -U inventory_user -d inventory_db

# Run migrations
docker compose exec inventory-app python manage.py migrate
docker compose exec events-app alembic upgrade head

# Create superuser (Django systems)
docker compose exec inventory-app python manage.py createsuperuser

# View system health
curl https://rm.swhgrp.com/[system]/health
```

### Important File Locations
- Docker Compose: `/opt/restaurant-system/docker-compose.yml`
- Nginx Config: `/opt/restaurant-system/shared/nginx/conf.d/`
- System Code: `/opt/restaurant-system/[system-name]/`
- Environment Files: `/opt/restaurant-system/[system-name]/.env`
- Backups: `/opt/restaurant-system/backups/`
- Logs: `/opt/restaurant-system/logs/`

### Support Contacts
- **System Architecture:** [Developer Contact]
- **Server Access:** [DevOps Contact]
- **Database:** [DBA Contact]
- **User Support:** [Support Contact]

---

**Document Version:** 1.0
**Last Updated:** 2025-10-28
**Next Review:** 2025-11-28
**Maintained By:** Development Team

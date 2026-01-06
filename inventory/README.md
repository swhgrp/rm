# Restaurant Inventory Management System

A comprehensive web-based inventory management system built for restaurant operations, featuring multi-location tracking, location-aware costing, POS integration, recipe management, and advanced analytics.

**Last Updated:** January 5, 2026

## Recent Updates

### January 5, 2026 - Waste Log UoM & Transfer Enhancements 🔧

**Waste Log UoM Dropdown:**
- ✅ **UoM selection** - Select unit of measure when logging waste
- ✅ **Dynamic dropdown** - Shows item's available count units
- ✅ **Conversion support** - Records waste in selected unit
- ✅ **Updated template** - `templates/waste.html` with UoM dropdown

**Transfer Form Improvements:**
- ✅ **Select2 item dropdown** - Searchable item selection with AJAX
- ✅ **Date picker** - Calendar-based date selection for transfers
- ✅ **UoM dropdown** - Select unit based on item's count units
- ✅ **Improved UX** - Modern form controls replace basic inputs

**Dashboard COGS Display:**
- ✅ **Cost metrics** - Cost of goods sold shown on dashboard
- ✅ **Location-aware** - COGS calculated per location

**Files Modified:**
- `templates/waste.html` - UoM dropdown for waste logging
- `templates/transfers.html` - Select2, date picker, UoM selection
- `api/api_v1/endpoints/waste.py` - UoM parameter handling
- `schemas/waste.py` - WasteCreate schema with uom_id

---

### December 27, 2025 - Location-Aware Costing Architecture 🏗️

**Major Architecture Refactor - Source of Truth:**
- ✅ **Inventory owns Locations** - All location data (code, legal_name, ein, address) managed here
- ✅ **Accounting syncs from Inventory** - `/_sync` endpoint for Accounting to fetch locations
- ✅ **Location model enhanced** - Added `code`, `legal_name`, `ein` fields

**New Location-Aware Costing Models:**
- ✅ **MasterItemCountUnit** - Multiple count units per item with conversion factors
  - `master_item_id` + `uom_id` + `is_primary` flag
  - `conversion_to_primary` factor for unit conversions
  - `convert_to_primary()` and `convert_from_primary()` methods
- ✅ **MasterItemLocationCost** - Weighted average cost per item per location
  - `master_item_id` + `location_id` (unique together)
  - `current_weighted_avg_cost`, `total_qty_on_hand`
  - `apply_purchase()` and `apply_usage()` methods
- ✅ **MasterItemLocationCostHistory** - Full audit trail for cost changes

**Deprecated Models (moved to _deprecated/):**
- Invoice, InvoiceItem, InvoiceStatus → Use Integration Hub
- VendorItem, VendorAlias → Use Integration Hub

**Migration Stats:**
- 409 count units created
- 372 location cost records (62 items × 6 locations)

---

### November 28-29, 2025 - Key Items, Unit Conversions & Count Fixes 🔧

**New Data Model Features:**
- ✅ **Key Item Flag** (`is_key_item`) - Highlight important inventory items
- ✅ **Additional Count Units** - `count_unit_2_id` and `count_unit_3_id` for flexible counting
- ✅ **Item Unit Conversions** - New `ItemUnitConversion` model for per-item conversions
  - Example: 1 case of chicken = 40 lbs, 1 LB Sausage = 8 Patties (2oz)
  - `from_unit_id`, `to_unit_id`, `conversion_factor` (Numeric 20,6)
  - `individual_weight_oz` and `individual_volume_oz` for reference

**Count Session Fixes:**
- ✅ Fixed unit display showing "null" - now uses proper unit name via relationship
- ✅ Fixed count_unit_2/3 not showing in dropdowns
- ✅ Fixed unit conversion calculations
- ✅ Fixed variance_percent overflow (increased precision to 10,2)
- ✅ Fixed inventory_type not saving ("Full" vs "Partial")
- ✅ Fixed delete count session cascade (count_session_storage_areas)

**Database Migrations:**
- `20251128_1600_add_key_item_and_count_units.py`
- `20251128_1800_add_item_unit_conversions.py`

## System Overview

**Technology Stack:**
- **Backend:** Python 3.11, FastAPI
- **Database:** PostgreSQL 15 (32 tables)
- **Cache/Session:** Redis 7
- **AI/ML:** OpenAI GPT-4 (invoice parsing)
- **Frontend:** HTML5, JavaScript, Bootstrap 5
- **Web Server:** Nginx (reverse proxy with SSL/TLS)
- **Containerization:** Docker & Docker Compose
- **Database Migrations:** Alembic
- **PDF Generation:** ReportLab
- **Background Jobs:** APScheduler

**Deployment:**
- **Production URL:** https://rm.swhgrp.com/inventory/
- **Portal Integration:** JWT-based SSO authentication
- **Status:** Production Ready (100%+ Complete)

**Statistics:**
- **104 Python files** across the codebase
- **30 HTML templates**
- **32 database tables** with full relationships
- **21 API endpoint modules** with 177+ routes
- **25+ database models** with SQLAlchemy ORM

---

## ✅ Core Features

### 1. Authentication & Authorization ✅
- **Portal SSO Integration** - JWT token-based single sign-on
- **Role-based access control** - Admin and User roles
- **Password hashing** - bcrypt encryption
- **Session management** - Redis-backed sessions with 30-minute timeout
- **Password reset system** - Token-based password recovery
- **Audit logging** - Complete activity tracking
- **Admin-only features:**
  - Settings and configuration access
  - User management
  - POS configuration
  - Invoice parsing settings
  - Inventory record editing/deletion

### 2. Master Item Management ✅
- **Master Items** - Central item catalog with:
  - Item name, description, and SKU
  - Category assignment
  - Primary vendor tracking
  - Unit of measure (UOM) configuration
  - Par level settings (min/max thresholds)
  - Cost tracking and history
  - Active/inactive status
- **Vendor Items** - Multi-vendor support:
  - Track same item across multiple vendors
  - Vendor-specific item codes
  - Vendor-specific pricing
  - Vendor-specific UOMs
  - Preferred vendor designation
- **Categories** - Hierarchical categorization system
- **Storage Areas** - Location-specific storage zones
- **Units of Measure** - Comprehensive UOM library with:
  - Standard units (lb, oz, kg, g, gal, qt, pt, etc.)
  - Unit categories (Weight, Volume, Count)
  - Conversion factors between units

### 3. Multi-Location Inventory ✅
- **Location Management** - Track inventory across multiple restaurant locations
- **Location-specific storage areas** - Organize by prep areas, walk-ins, dry storage, etc.
- **Real-time inventory counts** - Live quantity tracking
- **Low stock alerts** - Automatic alerts based on par levels
- **Inventory value calculation** - Total inventory value by location
- **Advanced filtering:**
  - Filter by location, storage area, category
  - Filter by stock status (in stock, low stock, out of stock)
  - Search by item name or SKU
- **User-location assignment** - Restrict users to specific locations

### 4. Inventory Counting ✅
- **Live Count Sessions** - Real-time inventory counting with:
  - Auto-save functionality (no data loss)
  - Mobile-responsive interface for tablets/phones
  - Count by storage area or full location
  - Variance detection (expected vs actual)
  - Notes and adjustment reasons
  - Multi-user support (each user has own sessions)
- **Count Templates** - Pre-configured item lists:
  - Create reusable templates for common counts
  - Template-based session creation (one-click start)
  - Location-specific templates
  - Storage area filtering within templates
- **Count History** - Complete audit trail:
  - Review all previous count sessions
  - Reopen incomplete sessions
  - View count details and variances
  - Export count data
- **Automatic inventory updates** - Inventory adjusted upon count completion

### 5. Transfer System ✅
- **Inter-location transfers** - Move inventory between locations
- **Multi-item transfers** - Transfer multiple items in one request
- **Transfer workflow:**
  - **PENDING** - Awaiting approval
  - **IN_TRANSIT** - Approved and shipped
  - **RECEIVED** - Completed at destination
  - **REJECTED** - Denied by approver
- **Transfer actions:**
  - Request transfer (any user)
  - Approve/reject (managers/admins)
  - Ship items (sender location)
  - Receive items (recipient location)
- **Automatic inventory adjustments:**
  - Deduct from sending location on ship
  - Add to receiving location on receive
- **Transfer history and audit trail**
- **Transfer notes and documentation**

### 6. Waste Tracking ✅ **PRODUCTION READY**
- **Waste logging** - Record wasted inventory with:
  - Item, quantity, and UOM
  - Waste reason (spoilage, damage, expiration, etc.)
  - Location tracking
  - Date/time stamps
  - User who recorded waste
- **Waste reports** - Analyze waste patterns:
  - Waste by category
  - Waste by location
  - Waste by reason
  - Cost impact analysis
  - Date range filtering
- **Automatic inventory deduction** - Waste reduces inventory count
- **Waste UI** - Dedicated waste log page (26KB template)

### 7. AI-Powered Invoice Processing ✅ **PRODUCTION READY**
- **Automated invoice intake** - Upload PDF/image invoices
- **OpenAI GPT-4 integration** - AI-powered data extraction:
  - Vendor identification
  - Invoice number and date
  - Line item extraction (description, quantity, unit price, total)
  - Tax and subtotal calculation
  - Due date extraction
- **Confidence scoring** - AI confidence ratings for extracted data
- **Anomaly detection** - Flag unusual prices or quantities
- **Invoice workflow:**
  - **UPLOADED** - File uploaded, awaiting processing
  - **PARSING** - AI actively extracting data
  - **PARSED** - Data extracted, awaiting review
  - **REVIEWED** - Human-verified and corrected
  - **APPROVED** - Final approval for payment
- **Manual review interface:**
  - Review AI-extracted data
  - Correct errors and misreads
  - Map invoice items to master items
  - Approve or reject invoice
- **Invoice UI** - Full-featured invoice management (69KB template)
- **Invoice item mapping** - Link invoice items to inventory items

### 8. Recipe Management & Costing ✅ **PRODUCTION READY**
- **Recipe CRUD** - Create and manage recipes with:
  - Recipe name, description, and category
  - Yield (servings/portions)
  - Prep time and cook time
  - Chef notes and instructions
- **Recipe ingredients** - Multi-ingredient recipes:
  - Link to master items
  - Quantity and UOM per ingredient
  - Ingredient cost lookup
  - Substitution notes
- **Recipe costing** - Automatic cost calculations:
  - Ingredient costs (from current inventory costs)
  - Labor cost allocation
  - Overhead cost allocation
  - Total recipe cost
  - Cost per portion
  - Food cost percentage
- **PDF recipe generation** - Print-ready recipe cards
- **Recipe categories** - Organize by meal type, course, etc.
- **Recipe UI** - Full recipe management interface (44KB template)

### 9. POS Integration ✅ **PRODUCTION READY**
- **Supported POS systems:**
  - Clover POS
  - Square POS
  - Toast POS
- **POS configuration** - Admin settings for:
  - API credentials (API key, secret)
  - Store/location mapping
  - Sync frequency settings
  - Active/inactive status
- **POS item mapping** - Map POS items to inventory items:
  - One-to-one mapping (1 POS item = 1 inventory item)
  - Recipe-based mapping (1 POS item = multiple inventory items via recipe)
  - Custom quantity deductions
  - Mapping UI with search and filtering (29KB template)
- **Automated sales sync** - Background job scheduler:
  - Sync sales data every 10 minutes (configurable)
  - Automatic inventory deduction based on sales
  - Sales tracking by location
  - Sync history and logs
- **POS sales tracking** - Record and analyze:
  - Daily sales by location
  - Sales by POS item
  - Inventory impact from sales
  - Sync status and error logs
- **Manual sync triggers** - Force sync on demand
- **POS settings UI** - Configuration interface (13KB template)

### 10. Reporting & Analytics ✅
- **Usage Report** - Comprehensive usage analysis:
  - Starting inventory (beginning of period)
  - Purchases and additions
  - Adjustments (transfers in/out, waste, sales)
  - Ending inventory (end of period)
  - Total usage calculation
  - Cost analysis by category
  - Inventory value tracking
  - Collapsible category drill-down
  - Location-specific reports
  - Date range selection
- **Variance Report** - Compare expected vs actual:
  - Theoretical inventory (based on transactions)
  - Actual inventory (from count sessions)
  - Variance amounts and percentages
  - Cost impact of variances
  - Variance reasons and notes
- **Inventory Valuation Report** - Current inventory value:
  - Total value by location
  - Value by category
  - Value by storage area
  - Historical value trends
- **Waste Report** - Waste analysis and tracking
- **Sales Report** - POS sales analysis (when POS integrated)
- **Reports UI** - Comprehensive reporting interface (53KB template)
- **Export functionality** - Currently browser-based (future: CSV/Excel/PDF)

### 11. Analytics Dashboard ✅
- **Key Metrics Display:**
  - Total inventory value (all locations)
  - Low stock items count
  - Pending transfers count
  - Recent waste amounts
  - Sales trends (when POS integrated)
- **Visual Charts:**
  - Inventory value by category (pie chart)
  - Inventory levels over time (line chart)
  - Waste trends (bar chart)
  - Usage patterns (area chart)
- **Recent Activity Feed:**
  - Latest count sessions
  - Recent transfers
  - Waste entries
  - Invoice uploads
- **Location Selector** - Filter dashboard by location
- **Analytics UI** - Advanced analytics page (28KB template)

### 12. Vendor Management ✅
- **Vendor database** - Comprehensive vendor tracking:
  - Vendor name and contact information
  - Email and phone numbers
  - Address and delivery information
  - Payment terms and credit limits
  - Active/inactive status
  - Vendor notes
- **Vendor items** - Track vendor-specific items:
  - Vendor SKU/item codes
  - Vendor-specific pricing
  - Vendor-specific UOMs
  - Lead times and minimum orders
  - Preferred vendor flagging
- **Multi-vendor support** - Same item from multiple vendors
- **Vendor UI** - Vendor management interface (26KB template)
- **Vendor Items UI** - Vendor item catalog (41KB template)

### 13. User Management (Admin) ✅
- **User CRUD** - Create, edit, and delete users
- **Role assignment** - Admin or User roles
- **Location assignment** - Restrict users to specific locations
- **Password management:**
  - Admin password reset for users
  - User self-service password change
  - Password complexity enforcement
- **User activity tracking** - Audit log of user actions
- **User status** - Active/inactive users
- **Users UI** - User management page (11KB template)

### 14. Settings & Configuration (Admin) ✅
- **Settings dashboard** - Centralized admin configuration (163KB template)
- **Location management** - Add/edit restaurant locations
- **Storage area management** - Define storage zones per location
- **Category management** - Organize inventory categories
- **Vendor management** - Vendor database maintenance
- **Master item management** - Central item catalog
- **Unit of measure management** - UOM library
- **Count template management** - Create reusable count templates
- **POS integration settings** - Configure POS connections
- **Email settings** - SMTP configuration for notifications
- **Audit trail viewer** - System activity logs
- **User management** - User administration

### 15. Inventory Movements ✅
- **Transaction history** - Complete audit trail:
  - All inventory additions (purchases, transfers in)
  - All inventory deductions (sales, waste, transfers out)
  - Adjustments from count sessions
  - User who made each transaction
  - Date/time stamps
  - Transaction reasons and notes
- **Movement filtering:**
  - Filter by location
  - Filter by item
  - Filter by transaction type
  - Date range selection
- **Running balance** - Track inventory levels over time
- **Movements UI** - Transaction history page (10KB template)

---

## 🗄️ Database Schema

### 37 Database Tables

**Core Tables:**
- `users` - User accounts and authentication
- `roles` - User roles (Admin, User)
- `locations` - Restaurant locations (SOURCE OF TRUTH - synced to Accounting)
- `storage_areas` - Storage zones within locations
- `categories` - Item categories (references Hub)
- `vendors` - Vendor/supplier database
- `master_items` - Central item catalog

**Location-Aware Costing Tables (NEW Dec 27, 2025):**
- `master_item_count_units` - Multiple count units per item with conversion factors
- `master_item_location_costs` - Weighted average cost per item per location
- `master_item_location_cost_history` - Audit trail for cost changes
- `item_unit_conversions` - Per-item unit conversions (e.g., 1 case = 40 lbs)

**Inventory Tables:**
- `inventory` - Current inventory quantities
- `inventory_transactions` - Transaction history
- `storage_area_items` - Item-storage area relationships

**Counting Tables:**
- `count_sessions` - Count session records
- `count_session_items` - Items counted in each session
- `count_session_storage_areas` - Storage areas in count sessions
- `count_templates` - Reusable count templates
- `count_template_items` - Items in count templates

**Transfer Tables:**
- `transfers` - Transfer requests and status

**Waste Tables:**
- `waste_records` - Waste logging and tracking

**Recipe Tables:**
- `recipes` - Recipe headers
- `recipe_ingredients` - Recipe ingredient lists

**POS Tables:**
- `pos_configurations` - POS system settings
- `pos_sales` - POS sales transactions
- `pos_sale_items` - POS sale line items
- `pos_item_mappings` - POS item to inventory item mappings

**System Tables:**
- `units_of_measure` - UOM library (local cache, Hub is source of truth)
- `unit_categories` - UOM category groupings
- `user_locations` - User-location assignments
- `audit_log` - System activity audit trail
- `password_reset_tokens` - Password reset functionality
- `alembic_version` - Database migration tracking

**Deprecated Tables (moved to _deprecated/ models):**
- `invoices`, `invoice_items` - Use Integration Hub
- `vendor_items`, `vendor_aliases` - Use Integration Hub

---

## 🔌 API Structure

All API endpoints are prefixed with `/inventory/api/`:

### Authentication & Users
- **/auth** - Login, logout, token management, password reset
- **/users** - User CRUD, role assignment, location assignment

### Master Data
- **/locations** - Location management
- **/storage-areas** - Storage area management
- **/categories** - Category management
- **/vendors** - Vendor management
- **/vendor-items** - Vendor item catalog
- **/items** - Master item management (primary endpoint)
- **/units** - Units of measure management

### Inventory Operations
- **/inventory** - Inventory CRUD and queries
- **/inventory-movements** - Transaction history
- **/count-sessions** - Count session management
- **/count-templates** - Template CRUD
- **/transfers** - Transfer creation and management
- **/waste** - Waste logging and reporting

### Advanced Features
- **/invoices** - AI-powered invoice processing
- **/recipes** - Recipe management and costing
- **/pos** - POS integration and sales sync
- **/pos-item-mapping** - POS item mapping management

### Reporting
- **/reports** - Usage, variance, valuation reports
- **/analytics** - Advanced analytics and charts
- **/dashboard** - Dashboard metrics and KPIs

### System
- **/audit-log** - Activity audit trail
- **/cache-management** - Redis cache management (admin)
- **/roles** - Role management (admin)

**Total API Endpoints:** 177+ routes across 21 modules

---

## 🖥️ Frontend Pages

### Public Pages
- **Login** (`/login`) - User authentication (Portal SSO)

### Main Pages
- **Dashboard** (`/dashboard`) - Overview with metrics and recent activity
- **Inventory** (`/inventory`) - Not implemented (redirects to master items)
- **Master Items** (`/master-items`) - Central item catalog management
- **Vendor Items** (`/vendor-items`) - Vendor-specific item catalog

### Inventory Operations
- **Take Inventory** (`/count`) - Live counting interface with auto-save
- **Count History** (`/count/history`) - Previous count sessions
- **Templates** (`/templates-management`) - Count template management
- **Transfers** (`/transfers`) - Transfer request and approval
- **Waste Log** (`/waste`) - Waste tracking and reporting
- **Inventory Movements** (`/inventory-movements`) - Transaction history

### Purchasing & Invoicing
- **Invoices** (`/invoices`) - AI-powered invoice processing
- **Vendors** (`/vendors`) - Vendor management

### Menu & Recipes
- **Recipes** (`/recipes`) - Recipe management and costing

### POS Integration
- **POS Item Mapping** (`/pos-item-mapping`) - Map POS items to inventory
- **POS Configuration** (`/pos-config`) - POS settings (admin, via settings)

### Reporting & Analytics
- **Reports** (`/reports`) - Usage, variance, and valuation reports
- **Analytics** (`/analytics`) - Advanced analytics dashboard

### Configuration (Admin Only)
- **Settings** (`/settings`) - Comprehensive admin configuration:
  - Locations and storage areas
  - Categories and vendors
  - Units of measure
  - Count templates
  - User management
  - POS integration settings
  - Audit trail viewer
- **Users** (`/users`) - User administration
- **Categories** (`/categories`) - Category management
- **Locations** (`/locations`) - Location management
- **Storage Areas** (`/storage-areas`) - Storage area management
- **Units of Measure** (`/units-of-measure`) - UOM library

### User Pages
- **Profile** (`/profile`) - User profile management
- **Setup Password** (`/setup-password`) - Password setup for new users

**Total Templates:** 30 HTML files

---

## 🚀 Deployment Architecture

### Production Environment
- **URL:** https://rm.swhgrp.com/inventory/
- **Server:** Linode VPS (172.233.172.92)
- **SSL:** Let's Encrypt via Certbot
- **Reverse Proxy:** Nginx
- **Container Orchestration:** Docker Compose

### Docker Services
1. **inventory-app** - FastAPI application (Python 3.11)
2. **inventory-db** - PostgreSQL 15 database
3. **redis** - Redis 7 cache/session store
4. **nginx-proxy** - Shared Nginx reverse proxy (system-wide)

### Network Flow
```
Internet → rm.swhgrp.com
  → Nginx Proxy (SSL termination)
    → /inventory/ route
      → inventory-app:8000 (FastAPI)
        → inventory-db:5432 (PostgreSQL)
        → redis:6379 (Redis cache)
```

### Portal SSO Integration
```
1. User accesses /inventory/
2. FastAPI checks for JWT token in cookies
3. If no token → Redirect to /portal/login
4. Portal authenticates user → Issues JWT token
5. User redirected back to /inventory/
6. FastAPI validates JWT → Grants access
7. User permissions checked against hr_db.users table
```

---

## 📦 Installation & Setup

### Prerequisites
- Docker and Docker Compose installed
- Access to shared PostgreSQL and Redis services
- Portal system running (for SSO authentication)

### Environment Variables
Key variables in `/opt/restaurant-system/inventory/.env`:
```bash
# Database
DATABASE_URL=postgresql://inventory_user:inventory_pass@inventory-db:5432/inventory_db

# Redis
REDIS_URL=redis://redis:6379/0

# Portal SSO
PORTAL_SECRET_KEY=<shared-secret-for-jwt-validation>

# OpenAI (for invoice parsing)
OPENAI_API_KEY=<your-openai-api-key>

# Application
SECRET_KEY=<your-secret-key>
ENVIRONMENT=production
```

### Quick Start
```bash
# Navigate to project root
cd /opt/restaurant-system

# Start inventory service
docker compose up -d inventory-app inventory-db

# View logs
docker compose logs -f inventory-app

# Check health
curl https://rm.swhgrp.com/inventory/health
```

### Database Migrations
```bash
# Run pending migrations
docker compose exec inventory-app alembic upgrade head

# Create new migration
docker compose exec inventory-app alembic revision --autogenerate -m "description"

# View migration history
docker compose exec inventory-app alembic history
```

### Initial Data Setup
```bash
# Access database
PGPASSWORD=inventory_pass psql -h localhost -U inventory_user -d inventory_db

# Create first admin user (if needed)
# Admin users are provisioned via Portal SSO
```

---

## 🔐 Security Features

- **JWT token-based authentication** - Portal SSO integration
- **Password hashing** - bcrypt with salt
- **HTTPS/TLS** - All traffic encrypted
- **Role-based access control (RBAC)** - Admin and User roles
- **Audit logging** - Complete activity tracking
- **CORS protection** - Configured for rm.swhgrp.com domain
- **SQL injection prevention** - SQLAlchemy ORM with parameterized queries
- **XSS protection** - Content Security Policy headers
- **Session management** - Redis-backed with 30-minute timeout
- **Location-based access control** - Users restricted to assigned locations
- **Password reset tokens** - Time-limited, one-time use tokens
- **API key protection** - POS API keys encrypted at rest

---

## 🎯 Future Enhancements

### Planned Features (Not Yet Implemented)
- ❌ **Purchase Order Management** - Not implemented (invoices exist, but no formal PO workflow)
- ❌ **Barcode/QR Code Scanning** - Future feature for faster counting and receiving
- ❌ **Automated Reorder Suggestions** - AI-based reordering based on par levels and usage patterns
- ❌ **Mobile Apps** - Native iOS/Android apps (web UI is mobile-responsive)
- ❌ **Multi-language Support** - Currently English-only (Spanish planned)
- ❌ **Report Export (CSV/Excel/PDF)** - Reports are browser-based only (export planned)
- ❌ **Advanced Forecasting** - Predictive analytics for demand forecasting
- ❌ **Vendor Portal** - Allow vendors to view POs and submit invoices directly
- ❌ **Integration with Accounting** - Auto-create journal entries for inventory transactions

### On Hold
- Purchase order workflow (company not using POs currently)
- Barcode scanning integration
- Automated reorder suggestions

### In Progress
- Spanish language support (coming soon)
- Report export functionality (CSV/Excel/PDF)

---

## 🛠️ Development

### Project Structure
```
/opt/restaurant-system/inventory/
├── src/restaurant_inventory/
│   ├── api/api_v1/endpoints/    # 21 API endpoint modules
│   │   ├── analytics.py
│   │   ├── audit_log.py
│   │   ├── auth.py
│   │   ├── cache_management.py
│   │   ├── categories.py
│   │   ├── count_sessions.py
│   │   ├── count_templates.py
│   │   ├── dashboard.py
│   │   ├── inventory.py
│   │   ├── invoices.py          # AI invoice processing
│   │   ├── items.py              # Master items
│   │   ├── locations.py
│   │   ├── pos.py                # POS integration
│   │   ├── recipes.py            # Recipe management
│   │   ├── reports.py
│   │   ├── roles.py
│   │   ├── storage_areas.py
│   │   ├── transfers.py
│   │   ├── units.py
│   │   ├── users.py
│   │   ├── vendor_items.py
│   │   ├── vendors.py
│   │   └── waste.py
│   ├── core/                     # Config, security, dependencies
│   │   ├── audit.py              # Audit logging
│   │   ├── config.py             # App configuration
│   │   ├── deps.py               # FastAPI dependencies
│   │   ├── invoice_parser.py    # OpenAI invoice parsing
│   │   ├── recipe_parser.py     # Recipe parsing
│   │   ├── recipe_pdf.py        # Recipe PDF generation
│   │   ├── security.py          # JWT, password hashing
│   │   └── portal_sso.py        # Portal SSO integration
│   ├── db/                       # Database setup
│   │   └── session.py
│   ├── models/                   # 25+ SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── audit_log.py
│   │   ├── category.py
│   │   ├── count.py
│   │   ├── inventory.py
│   │   ├── invoice.py
│   │   ├── location.py
│   │   ├── pos_sale.py
│   │   ├── recipe.py
│   │   ├── role.py
│   │   ├── storage_area.py
│   │   ├── transfer.py
│   │   ├── unit.py
│   │   ├── user.py
│   │   ├── vendor.py
│   │   └── waste.py
│   ├── schemas/                  # Pydantic schemas
│   │   ├── auth.py
│   │   ├── category.py
│   │   ├── count.py
│   │   ├── inventory.py
│   │   ├── invoice.py
│   │   ├── location.py
│   │   ├── pos.py
│   │   ├── recipe.py
│   │   ├── storage_area.py
│   │   ├── transfer.py
│   │   ├── unit.py
│   │   ├── user.py
│   │   ├── vendor.py
│   │   └── waste.py
│   ├── services/                 # Business logic services
│   │   └── pos_sync.py          # POS background sync
│   ├── static/                   # CSS, JS, images
│   │   ├── css/style.css
│   │   ├── js/auth.js
│   │   ├── js/main.js
│   │   └── images/sw-logo.png
│   ├── templates/                # 30 HTML templates
│   │   ├── analytics.html       # 28KB - Analytics dashboard
│   │   ├── base.html            # 29KB - Base template
│   │   ├── categories.html      # 12KB
│   │   ├── count_history.html   # 10KB
│   │   ├── count_session.html   # 35KB
│   │   ├── count_session_new.html # 58KB - New count UI
│   │   ├── dashboard.html       # 15KB
│   │   ├── inventory.html       # 28KB
│   │   ├── inventory_movements.html # 10KB
│   │   ├── invoices.html        # 69KB - AI invoice processing
│   │   ├── items.html           # 32KB - Deprecated (use master_items)
│   │   ├── locations.html       # 9KB
│   │   ├── login.html           # 4KB
│   │   ├── master_items.html    # 41KB - Master item catalog
│   │   ├── pos_config.html      # 13KB - POS settings
│   │   ├── pos_item_mapping.html # 29KB - POS mapping
│   │   ├── profile.html         # 8KB
│   │   ├── recipes.html         # 44KB - Recipe management
│   │   ├── reports.html         # 53KB - Comprehensive reporting
│   │   ├── settings.html        # 163KB - Admin settings hub
│   │   ├── setup_password.html  # 16KB
│   │   ├── templates_management.html # 18KB
│   │   ├── transfers.html       # 17KB
│   │   ├── units_of_measure.html # 40KB
│   │   ├── users.html           # 11KB
│   │   ├── vendor_items.html    # 41KB
│   │   ├── vendors.html         # 26KB
│   │   └── waste.html           # 26KB - Waste tracking
│   └── main.py                   # FastAPI application entry
├── alembic/                      # Database migrations
│   └── versions/                 # 20+ migration files
├── uploads/                      # File uploads
│   └── invoices/                 # Invoice PDFs
├── docker-compose.yml            # Docker service definition
├── Dockerfile                    # Application container
├── requirements.txt              # Python dependencies
├── .env                          # Environment variables
└── README.md                     # This file
```

### Key Dependencies
```
fastapi==0.104.1         # Web framework
uvicorn==0.24.0          # ASGI server
sqlalchemy==2.0.23       # ORM
alembic==1.12.1          # Database migrations
psycopg2-binary==2.9.9   # PostgreSQL driver
redis==5.0.1             # Redis client
pydantic==2.5.0          # Data validation
python-jose==3.3.0       # JWT handling
passlib==1.7.4           # Password hashing
bcrypt==4.1.1            # Bcrypt hashing
openai==1.3.5            # OpenAI API (invoice parsing)
reportlab==4.0.7         # PDF generation
apscheduler==3.10.4      # Background job scheduling
python-multipart==0.0.6  # File uploads
jinja2==3.1.2            # Template engine
```

### Adding New Features

1. **Create database model** in `src/restaurant_inventory/models/`
2. **Create Pydantic schema** in `src/restaurant_inventory/schemas/`
3. **Create API endpoint** in `src/restaurant_inventory/api/api_v1/endpoints/`
4. **Create/update HTML template** in `src/restaurant_inventory/templates/`
5. **Generate migration:**
   ```bash
   docker compose exec inventory-app alembic revision --autogenerate -m "description"
   ```
6. **Run migration:**
   ```bash
   docker compose exec inventory-app alembic upgrade head
   ```
7. **Restart application:**
   ```bash
   docker compose restart inventory-app
   ```

---

## 🧪 Testing

### Health Check
```bash
curl https://rm.swhgrp.com/inventory/health
```

Expected response:
```json
{
  "status": "healthy",
  "app": "Restaurant Inventory Management",
  "version": "1.0.0",
  "database": "connected"
}
```

### Manual Testing Checklist
- [ ] Login via Portal SSO
- [ ] Create master item
- [ ] Create vendor and vendor item
- [ ] Take inventory count
- [ ] Create transfer between locations
- [ ] Upload invoice for AI parsing
- [ ] Create recipe and view costing
- [ ] Configure POS integration
- [ ] Run usage report
- [ ] Log waste record
- [ ] Check analytics dashboard

---

## 🔧 Troubleshooting

### Application won't start
```bash
# Check logs
docker compose logs -f inventory-app

# Check database connection
docker compose ps

# Restart service
docker compose restart inventory-app
```

### Database connection issues
```bash
# Test database connectivity
PGPASSWORD=inventory_pass psql -h localhost -U inventory_user -d inventory_db -c "SELECT 1"

# Check database logs
docker compose logs inventory-db

# Restart database
docker compose restart inventory-db
```

### Portal SSO not working
```bash
# Verify PORTAL_SECRET_KEY matches Portal's secret
grep PORTAL_SECRET_KEY /opt/restaurant-system/inventory/.env
grep PORTAL_SECRET_KEY /opt/restaurant-system/portal/.env

# Check JWT token in browser cookies (access_token)
# Verify token is being sent to /inventory/ routes
```

### AI invoice parsing not working
```bash
# Check OpenAI API key
grep OPENAI_API_KEY /opt/restaurant-system/inventory/.env

# Test OpenAI connectivity
docker compose exec inventory-app python3 -c "import openai; print(openai.__version__)"

# Check invoice upload directory permissions
ls -la /opt/restaurant-system/inventory/uploads/invoices/
```

### POS sync not running
```bash
# Check POS configuration in database
PGPASSWORD=inventory_pass psql -h localhost -U inventory_user -d inventory_db -c "SELECT * FROM pos_configurations;"

# Check APScheduler logs in application logs
docker compose logs inventory-app | grep -i "pos\|scheduler"

# Verify POS API credentials are correct
```

### Redis connection issues
```bash
# Test Redis connectivity
docker compose exec redis redis-cli ping

# Check Redis logs
docker compose logs redis

# Verify REDIS_URL environment variable
grep REDIS_URL /opt/restaurant-system/inventory/.env
```

---

## 📊 System Statistics

- **Database Tables:** 32
- **Database Models:** 25+
- **API Endpoints:** 177+ routes across 21 modules
- **HTML Templates:** 30 files
- **Python Files:** 104 files
- **Lines of Code:** ~15,000+ LOC
- **Completion Status:** 100%+ (Core + Advanced Features)
- **Production Status:** ✅ Production Ready

---

## 👥 Support & Maintenance

**System Administrator:** SW Hospitality Group IT Team
**Production URL:** https://rm.swhgrp.com/inventory/
**Support Email:** support@swhgrp.com
**Documentation:** This README + system-wide docs in `/opt/restaurant-system/docs/`

---

## 📝 Version History

### v2.0.0 - Current Production Release
- ✅ Multi-location inventory management
- ✅ Transfer system with approval workflow
- ✅ Count sessions and templates
- ✅ Usage and variance reports
- ✅ **AI-powered invoice processing** (OpenAI GPT-4)
- ✅ **Recipe management and costing**
- ✅ **POS integration** (Clover, Square, Toast)
- ✅ **Waste tracking and reporting**
- ✅ **Advanced analytics dashboard**
- ✅ **Portal SSO integration**
- ✅ Mobile-responsive UI
- ✅ HTTPS with Let's Encrypt

### v1.0.0 - Initial Release
- Basic inventory tracking
- Count sessions
- Transfer system
- Basic reporting

---

## 📄 License

**Proprietary - SW Hospitality Group**
All rights reserved. Unauthorized use, distribution, or modification is prohibited.

---

## 🙏 Acknowledgments

**Built with:**
- FastAPI - Modern Python web framework
- PostgreSQL - Robust relational database
- Redis - High-performance caching
- OpenAI GPT-4 - AI-powered invoice parsing
- Bootstrap 5 - Responsive UI framework
- Docker - Containerization platform
- Nginx - High-performance web server
- SQLAlchemy - Python ORM
- Alembic - Database migration tool

---

**Last Updated:** December 27, 2025
**Document Version:** 2.2
**System Version:** v2.1.0 Production (Location-Aware Costing)

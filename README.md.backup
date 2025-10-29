# Restaurant Management System

A comprehensive microservices-based restaurant management platform with inventory management, accounting, and future HR capabilities.

## Architecture

This project uses a **microservices architecture** where each business domain is a separate, independently deployable service:

```
restaurant-system/
├── inventory/          # Inventory Management Service
│   ├── src/            # FastAPI application code
│   ├── alembic/        # Database migrations
│   ├── uploads/        # File uploads
│   └── .env            # Service configuration
│
├── accounting/         # Accounting Service
│   ├── src/            # FastAPI application code
│   ├── alembic/        # Database migrations
│   ├── logs/           # Application logs
│   └── .env            # Service configuration
│
├── hr/                 # HR Management Service
│   ├── src/            # FastAPI application code
│   ├── alembic/        # Database migrations
│   ├── documents/      # Employee document storage
│   └── .env            # Service configuration
│
├── integration-hub/    # Integration Hub Service
│   ├── src/            # FastAPI application code
│   ├── alembic/        # Database migrations
│   └── .env            # Service configuration
│
├── portal/             # Central Authentication Portal
│   ├── src/            # FastAPI application code
│   ├── templates/      # Portal pages
│   ├── static/         # Portal assets
│   └── .env            # Service configuration
│
├── docs/               # Documentation
│   ├── status/         # Current status and progress reports
│   ├── guides/         # User and admin guides
│   ├── reference/      # Technical reference documentation
│   └── planning/       # Future planning documents
│
├── shared/             # Shared Infrastructure
│   ├── nginx/          # Reverse proxy configuration
│   ├── certbot/        # SSL certificates
│   └── python/         # Shared Python libraries
│
├── scripts/            # Utility Scripts
│   ├── backup_databases.sh    # Automated database backups
│   ├── health_check.sh        # System health monitoring
│   ├── check_pos_sync.sh      # POS sync monitoring
│   └── tests/                 # Test scripts
│
├── docker-compose.yml  # Multi-service orchestration
├── DOCUMENTATION_INDEX.md  # Documentation navigation
└── README.md          # This file
```

## Services

### 1. Inventory Management Service
- **Port**: Internal (proxied via nginx)
- **Database**: PostgreSQL (`inventory_db`)
- **Features**:
  - Multi-location inventory tracking
  - Vendor management
  - Recipe costing
  - POS integration (Clover, Square, Toast)
  - Purchase orders and receiving
  - Waste tracking
  - Reports and analytics

### 2. Accounting Service
- **Port**: Internal (proxied via nginx at `/accounting/`)
- **Database**: PostgreSQL (`accounting_db`) - Completely isolated
- **Features**:
  - **Full Double-Entry Accounting System**
    - Chart of accounts with hierarchical structure
    - General ledger with drill-down capabilities
    - Journal entries with multi-line support
    - Trial balance and account reconciliation
  - **Financial Reporting**
    - Profit & Loss (P&L) statement with multi-period comparison
    - Balance sheet with visualizations
    - General ledger reports with location filtering
    - Account detail pages with transaction history
  - **Accounts Payable (AP)**
    - Vendor management and bill tracking
    - AP aging reports with aging buckets
    - Bill detail pages with payment history
    - Automated vendor synchronization via Integration Hub
  - **Accounts Receivable (AR)**
    - Customer management and invoice tracking
    - AR aging reports
    - Invoice detail pages
  - **POS Integration** ✨ NEW
    - Clover POS daily sales synchronization
    - Automatic sales data import with detailed breakdowns
    - Payment method tracking (Cash, Card, etc.) with tips
    - Discount and refund tracking by category
    - Automated journal entry creation from sales data
    - Bank reconciliation with transaction matching
    - 100% accuracy with POS reports (zero variance)
  - **Multi-Location Support**
    - 6 locations (Okeechobee, Boynton, Delray, etc.)
    - Consolidated and location-specific reporting
    - Area-based transaction filtering
  - **Dashboard & Analytics**
    - Real-time sales metrics (daily, MTD, YTD)
    - Revenue trends and visualizations
    - Labor expense tracking
    - Key financial KPIs

### 3. HR Management Service
- **Port**: Internal (proxied via nginx at `/hr/`)
- **Database**: PostgreSQL (`hr_db`) - Completely isolated
- **Features**:
  - Employee information management
  - Position and department tracking
  - Document management with encryption
  - Role-based access control
  - Location-based permissions
  - Audit logging
  - SSO integration with portal

### 4. Integration Hub Service
- **Port**: Internal (proxied via nginx at `/hub/`)
- **Database**: PostgreSQL (`hub_db`) - Completely isolated
- **Features**:
  - Centralized vendor management
  - Vendor synchronization across systems
  - Invoice processing and routing
  - Category mapping for GL codes
  - System-to-system integrations
  - Automated data distribution

### 5. Central Authentication Portal
- **URL**: https://rm.swhgrp.com/portal/
- **Database**: PostgreSQL (`portal_db`) - Completely isolated
- **Features**:
  - Single Sign-On (SSO) for all systems
  - Centralized user authentication
  - JWT token-based session management
  - System access management
  - Professional dark theme UI
  - 30-minute inactivity timeout

### 6. Future Services
- **Analytics Dashboard** (planned) - Advanced reporting and data visualization
- **API Gateway** (planned) - Centralized API management and rate limiting

## Service Communication

Services communicate via:
- **REST APIs**: HTTP-based synchronous communication
- **Database Isolation**: Each service has its own database
- **SSO Authentication**: Portal provides SSO tokens for seamless navigation
- **Nginx Routing**:
  - `/` → Portal Landing Page (redirects to `/portal/`)
  - `/portal/` → Central Authentication Portal
  - `/inventory/` → Inventory Service
  - `/accounting/` → Accounting Service
  - `/hr/` → HR Management Service
  - `/hub/` → Integration Hub Service

## Technology Stack

- **Backend**: Python 3.11, FastAPI
- **Databases**: PostgreSQL 15 (one per service)
- **Cache/Queue**: Redis 7
- **Web Server**: Nginx
- **Container Orchestration**: Docker Compose
- **SSL**: Let's Encrypt (Certbot)

## Getting Started

### Prerequisites
- Docker and Docker Compose installed
- Ubuntu Server 20.04+ (production) or any OS with Docker (development)

### Starting All Services

```bash
# Start all services
docker compose up -d

# Check service status
docker compose ps

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f inventory-app
docker compose logs -f accounting-app
```

### Stopping Services

```bash
# Stop all services
docker compose down

# Stop and remove volumes (WARNING: deletes data)
docker compose down -v
```

### Accessing Services

- **Portal Home**: http://rm.swhgrp.com
- **Inventory Management**: http://rm.swhgrp.com/inventory/
- **Accounting System**: http://rm.swhgrp.com/accounting/
- **Inventory API Docs**: http://rm.swhgrp.com/inventory/docs
- **Accounting API Docs**: http://rm.swhgrp.com/accounting/docs

## Development

### Running Individual Services

```bash
# Start only inventory service
docker compose up inventory-db inventory-redis inventory-app

# Start only accounting service
docker compose up accounting-db accounting-app
```

### Database Migrations

```bash
# Inventory service migrations
docker compose exec inventory-app alembic upgrade head

# Accounting service migrations
docker compose exec accounting-app alembic upgrade head
```

### Accessing Databases

```bash
# Inventory database
docker compose exec inventory-db psql -U inventory_user -d inventory_db

# Accounting database
docker compose exec accounting-db psql -U accounting_user -d accounting_db
```

## Configuration

Each service has its own `.env` file:
- `inventory/.env` - Inventory service configuration
- `accounting/.env` - Accounting service configuration

### Environment Variables

See individual service directories for specific configuration options.

## Backup & Recovery

### Automated Backups (Recommended)

Automated daily backups are configured via cron (runs at 2 AM daily):

```bash
# View backup schedule
crontab -l

# Run backup manually
/opt/restaurant-system/scripts/backup_databases.sh

# Backups stored in
/opt/restaurant-system/backups/
```

### Manual Backup

```bash
# Backup inventory database
docker compose exec inventory-db pg_dump -U inventory_user inventory_db > inventory_backup_$(date +%Y%m%d).sql

# Backup accounting database
docker compose exec accounting-db pg_dump -U accounting_user accounting_db > accounting_backup_$(date +%Y%m%d).sql

# Backup entire system
cd /opt
tar -czf restaurant-system-backup-$(date +%Y%m%d).tar.gz restaurant-system/
```

### Restore

```bash
# Restore inventory database
cat inventory_backup_YYYYMMDD.sql | docker compose exec -T inventory-db psql -U inventory_user -d inventory_db

# Restore accounting database
cat accounting_backup_YYYYMMDD.sql | docker compose exec -T accounting-db psql -U accounting_user -d accounting_db
```

## Monitoring

### Automated Health Checks

Health monitoring runs every 5 minutes via cron:

```bash
# View monitoring schedule
crontab -l

# Run health check manually
/opt/restaurant-system/scripts/health_check.sh

# Check POS sync status
/opt/restaurant-system/scripts/check_pos_sync.sh
```

### Manual Monitoring

```bash
# Check service health
docker compose ps

# View resource usage
docker stats

# Check logs for errors
docker compose logs --tail=100 | grep -i error

# Check specific service logs
docker compose logs -f inventory-app
docker compose logs -f accounting-app
```

## Adding New Services

To add a new service (e.g., HR system):

1. Create service directory: `mkdir hr`
2. Add service code and Dockerfile
3. Add service to `docker-compose.yml`
4. Add routing in `shared/nginx/conf.d/app-http.conf`
5. Update this README

Example structure:
```
hr/
├── src/
├── alembic/
├── Dockerfile
├── requirements.txt
└── .env
```

## Security

- Each service has its own isolated database
- Services communicate via private Docker network
- Public access only through Nginx reverse proxy
- SSL/TLS encryption via Let's Encrypt (ready for setup)
- Database credentials stored in environment files (not in code)
- Direct IP address access blocked (must use domain name)
- Location-based access control for non-admin users
- Role-based access control (Admin, Manager, Staff)

## Documentation

- **[OPERATIONS_GUIDE.md](OPERATIONS_GUIDE.md)** - Complete operations manual for daily use
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Quick reference card (print and keep handy)
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Technical architecture documentation
- **[MIGRATION_NOTES.md](MIGRATION_NOTES.md)** - Change history and migration details

## Support

For issues or questions:
1. See **[OPERATIONS_GUIDE.md](OPERATIONS_GUIDE.md)** - Comprehensive troubleshooting
2. See **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Common commands and tasks
3. Check service logs: `docker compose logs <service-name>`
4. Run health check: `/opt/restaurant-system/scripts/health_check.sh`
5. Contact: admin@swhgrp.com

## License

Proprietary - Internal Use Only

## Version History

- **v2.2** (October 24, 2025) - Complete POS integration with Clover, enhanced accounting features
- **v2.1** (October 14, 2025) - Added central portal, automated backups, health monitoring
- **v2.0** (October 13, 2025) - Restructured as microservices architecture
- **v1.0** (October 2025) - Initial monolithic release

## Recent Updates (v2.2)

### POS Integration (Clover)
- **Daily Sales Synchronization**
  - Automatic import of sales data from Clover POS
  - Real-time sales caching with detailed breakdowns
  - Payment method tracking (Cash, Card, Gift Card, etc.)
  - Tips attribution by payment method (business rule: cash never has tips)
  - Discount tracking by category with exact matching
  - Refund tracking and attribution to payment methods
  - Tax and service charge tracking

- **Automated Journal Entries**
  - One-click journal entry generation from daily sales
  - Automatic GL account mapping for:
    - Revenue accounts by category
    - Payment clearing accounts (Cash, Credit Card, etc.)
    - Discount accounts (contra-revenue)
    - Sales Returns & Allowances (refunds)
    - Tax liability accounts
  - Perfect balance validation (debits = credits)
  - 100% accuracy with POS reports (zero variance)

- **Bank Reconciliation**
  - Bank transaction import and management
  - Automatic matching suggestions with journal entries
  - Vendor recognition from transaction descriptions
  - Bill payment matching (single and multi-bill)
  - Clearing entry automation
  - Reconciliation workflow with statement matching

### Dashboard Enhancements
- Real-time sales metrics from posted Daily Sales Summaries
- Daily, MTD, and YTD sales tracking
- Revenue trends with location filtering
- Labor expense monitoring
- Fixed SQLAlchemy join errors for reliable data display

### Technical Improvements
- Enhanced payment breakdown structure (nested JSON with tips)
- Improved discount aggregation (removed per-order normalization)
- Explicit SQLAlchemy join conditions for complex queries
- Fixed frontend debug object initialization
- Added missing JavaScript functions (apiRequest in inventory)

### Data Accuracy
- Achieved 100% accuracy between Clover reports and accounting system
- Zero variance in daily sales reconciliation
- Proper contra-revenue accounting for discounts and refunds
- Accurate tips attribution following business rules

### Documentation
- Comprehensive POS integration documentation
- Database schema changes documented
- API endpoint documentation
- Business logic and accounting rules documented
- See [POS_INTEGRATION_COMPLETE.md](docs/POS_INTEGRATION_COMPLETE.md) for details

## Previous Updates (v2.1)

### Portal Implementation
- Central landing page at http://rm.swhgrp.com
- Path-based routing for all modules
- Dark mode design matching inventory system
- Separate authentication per module

### Automation & Monitoring
- Automated daily database backups (2 AM)
- Health monitoring every 5 minutes
- POS sync monitoring
- All scheduled via cron

### Security Enhancements
- Blocked direct IP address access
- Enhanced location-based access control
- Admin users have access to all locations

### Bug Fixes
- Fixed routing issues with portal integration
- Converted all API paths from absolute to relative
- Added HTML base tag for proper URL resolution
- Fixed settings page and dashboard API calls

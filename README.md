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
├── portal/             # Central Web Portal
│   ├── index.html      # Landing page
│   ├── css/            # Portal styles
│   └── images/         # Portal assets
│
├── shared/             # Shared Infrastructure
│   ├── nginx/          # Reverse proxy configuration
│   └── certbot/        # SSL certificates
│
├── scripts/            # Utility Scripts
│   ├── backup_databases.sh    # Automated database backups
│   ├── health_check.sh        # System health monitoring
│   ├── check_pos_sync.sh      # POS sync monitoring
│   └── tests/                 # Test scripts
│
├── docker-compose.yml  # Multi-service orchestration
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
  - Double-entry bookkeeping
  - Chart of accounts
  - Journal entries
  - Cost of Goods Sold (COGS) tracking
  - Fiscal period management
  - Financial reporting

### 3. Central Portal
- **URL**: http://rm.swhgrp.com
- **Features**:
  - Unified entry point for all modules
  - Dark mode design matching inventory system
  - Path-based routing to each service
  - Separate authentication per module

### 4. Future Services
- **HR System** (planned) - Document retention, employee information, personnel records
- **Analytics Dashboard** (planned) - Advanced reporting and data visualization

## Service Communication

Services communicate via:
- **REST APIs**: HTTP-based synchronous communication
- **Database Isolation**: Each service has its own database
- **Nginx Routing**:
  - `/` → Portal Landing Page
  - `/inventory/` → Inventory Service
  - `/accounting/` → Accounting Service

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

- **v2.1** (October 14, 2025) - Added central portal, automated backups, health monitoring
- **v2.0** (October 13, 2025) - Restructured as microservices architecture
- **v1.0** (October 2025) - Initial monolithic release

## Recent Updates (v2.1)

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

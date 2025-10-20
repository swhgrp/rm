# Restaurant Management System - Architecture Documentation

## System Overview

This is a **microservices-based** restaurant management platform designed to scale with your business needs. Each service is independently deployable, has its own database, and communicates via REST APIs.

## Directory Structure

```
/opt/restaurant-system/
├── inventory/                    # Inventory Management Microservice
│   ├── src/
│   │   └── restaurant_inventory/ # Application code
│   │       ├── api/              # REST API endpoints
│   │       ├── core/             # Core functionality
│   │       ├── models/           # Database models
│   │       ├── services/         # Business logic
│   │       ├── templates/        # HTML templates
│   │       └── static/           # Static assets
│   ├── alembic/                  # Database migrations
│   ├── uploads/                  # File uploads storage
│   ├── Dockerfile                # Container definition
│   ├── requirements.txt          # Python dependencies
│   ├── alembic.ini               # Migration config
│   └── .env                      # Service configuration
│
├── accounting/                   # Accounting Microservice
│   ├── src/
│   │   └── accounting/           # Application code
│   │       ├── api/              # REST API endpoints
│   │       ├── core/             # Core functionality
│   │       ├── models/           # Database models
│   │       ├── db/               # Database utilities
│   │       └── schemas/          # Pydantic schemas
│   ├── alembic/                  # Database migrations
│   ├── logs/                     # Application logs
│   ├── Dockerfile                # Container definition
│   ├── requirements.txt          # Python dependencies
│   ├── alembic.ini               # Migration config
│   └── .env                      # Service configuration
│
├── portal/                       # Central Web Portal
│   ├── index.html                # Landing page
│   ├── css/
│   │   └── portal.css            # Dark mode styles
│   └── images/
│       └── sw-logo.png           # Company logo
│
├── scripts/                      # System Scripts
│   ├── backup_databases.sh       # Automated backups
│   ├── health_check.sh           # Health monitoring
│   ├── check_pos_sync.sh         # POS sync monitoring
│   ├── setup_cron.sh             # Cron job setup
│   └── tests/                    # Test scripts
│
├── shared/                       # Shared Infrastructure
│   ├── nginx/                    # Reverse proxy configs
│   │   ├── nginx.conf            # Main nginx config
│   │   └── conf.d/               # Site configs
│   │       ├── rm.swhgrp.com-http.conf  # Portal routing (HTTP)
│   │       └── app-http.conf     # Legacy routing (HTTP)
│   └── certbot/                  # SSL certificates
│       ├── conf/                 # Certificate storage
│       └── www/                  # ACME challenges
│
├── docker-compose.yml            # Multi-service orchestration
├── .gitignore                    # Git ignore rules
├── README.md                     # Getting started guide
└── ARCHITECTURE.md               # This file
```

## Services Architecture

### 1. Inventory Management Service

**Container**: `inventory-app`
**Port**: 8000 (internal only)
**Database**: `inventory_db` on `inventory-db:5432`
**Cache**: Redis on `inventory-redis:6379`

**Responsibilities**:
- Multi-location inventory tracking
- Vendor and purchase order management
- Recipe costing and menu engineering
- POS integration (Clover, Square, Toast)
- Waste and transfer tracking
- Reporting and analytics
- User authentication and authorization

**API Endpoints**:
- `/` - Main application UI
- `/api/` - REST API endpoints
- `/docs` - OpenAPI documentation
- `/static/` - Static assets
- `/uploads/` - File uploads

### 2. Accounting Service

**Container**: `accounting-app`
**Port**: 8000 (internal only)
**Database**: `accounting_db` on `accounting-db:5432`

**Responsibilities**:
- Double-entry bookkeeping
- Chart of accounts management
- Journal entries (DRAFT → POSTED → REVERSED)
- Cost of Goods Sold (COGS) tracking
- Fiscal period management
- Financial reporting (P&L, Balance Sheet)
- Integration with inventory for automated entries

**API Endpoints**:
- `/accounting/` - Main application UI
- `/accounting/api/` - REST API endpoints
- `/accounting/docs` - OpenAPI documentation

### 3. Infrastructure Services

#### Nginx (Reverse Proxy)
**Container**: `nginx-proxy`
**Ports**: 80 (HTTP), 443 (HTTPS)

**Routing Rules** (rm.swhgrp.com):
```
/                     → Portal landing page (static)
/inventory/*          → inventory-app:8000
/accounting/*         → accounting-app:8000
/css/*                → Portal static assets
/images/*             → Portal static assets
```

**Legacy Routing** (restaurantsystem.swhgrp.com):
```
/                     → inventory-app:8000 (direct access)
/api/*                → inventory-app:8000
/static/*             → inventory static files
/uploads/*            → inventory uploads
/accounting/*         → accounting-app:8000
```

**Security**:
- Direct IP address access blocked (returns 444)
- Must access via domain name only

#### Database Services
- **inventory-db**: PostgreSQL 15 for inventory service
- **accounting-db**: PostgreSQL 15 for accounting service
- **inventory-redis**: Redis 7 for caching and queues

#### SSL/TLS Service
- **certbot**: Automated Let's Encrypt certificate management

## Service Communication

### Inter-Service Communication

```
┌─────────────────┐
│  Inventory      │
│  Service        │
│  (Primary)      │
└────────┬────────┘
         │
         │ REST API
         │ (Read-Only)
         ▼
┌─────────────────┐
│  Accounting     │
│  Service        │
│  (Consumer)     │
└─────────────────┘
```

**Data Flow**:
1. Inventory creates transactions (invoices, waste, sales)
2. Accounting polls Inventory API for new transactions
3. Accounting creates journal entries automatically
4. No writes back to Inventory (one-way integration)

**Authentication**:
- API Key: `INVENTORY_API_KEY` in accounting .env
- Configured in accounting service environment

### External Communication

**Via Portal** (rm.swhgrp.com):
```
User Browser
     │
     ├─ http://rm.swhgrp.com/                    → Portal Home
     ├─ http://rm.swhgrp.com/inventory/          → Inventory UI
     ├─ http://rm.swhgrp.com/inventory/api/*     → Inventory API
     └─ http://rm.swhgrp.com/accounting/         → Accounting UI
```

**Direct Access** (restaurantsystem.swhgrp.com):
```
User Browser
     │
     ├─ http://restaurantsystem.swhgrp.com/      → Inventory UI (direct)
     ├─ http://restaurantsystem.swhgrp.com/api/  → Inventory API
     └─ http://restaurantsystem.swhgrp.com/accounting/ → Accounting UI
```

**Important Notes**:
- Portal uses path-based routing (`/inventory/`, `/accounting/`)
- Each module has separate authentication (no single sign-on)
- Inventory uses `<base href="/inventory/">` for proper URL resolution when accessed via portal

## Database Architecture

### Database Isolation

Each service has its **own PostgreSQL database**:

```
┌──────────────────┐       ┌──────────────────┐
│  inventory-db    │       │  accounting-db   │
│  (PostgreSQL 15) │       │  (PostgreSQL 15) │
│                  │       │                  │
│  • locations     │       │  • accounts      │
│  • items         │       │  • journal_entry │
│  • invoices      │       │  • cogs_trans    │
│  • pos_sales     │       │  • fiscal_period │
│  • vendors       │       │                  │
│  • users         │       │  No shared       │
│  • ...           │       │  tables!         │
└──────────────────┘       └──────────────────┘
        ▲                          ▲
        │                          │
        │                          │
   inventory-app              accounting-app
```

**Why Separate Databases?**
- **Independence**: Services can be deployed separately
- **Scalability**: Each database can be scaled independently
- **Security**: Data isolation and access control
- **Resilience**: Failure in one doesn't affect the other

### Data Synchronization

Accounting service maintains **reference copies** of inventory data:
- Vendor information (cached for reporting)
- Item details (cached for COGS calculations)
- Location data (for multi-location reports)

**Sync Strategy**:
- Real-time: API calls when needed
- Scheduled: 15-minute auto-sync (configurable)
- Manual: On-demand sync via UI

## Networking

### Docker Network

All services communicate via `restaurant-network` (bridge network):

```
restaurant-network (172.x.x.x/16)
├── inventory-app (172.x.x.2)
├── inventory-db (172.x.x.3)
├── inventory-redis (172.x.x.4)
├── accounting-app (172.x.x.5)
├── accounting-db (172.x.x.6)
└── nginx-proxy (172.x.x.7)
```

**Service Discovery**:
- Services reference each other by container name
- Example: `http://inventory-app:8000`
- DNS resolution handled by Docker

### Port Mapping

**External** (Host) → **Internal** (Container):
- `80` → `nginx-proxy:80`
- `443` → `nginx-proxy:443`
- `5432` → `inventory-db:5432` (for admin access only)

**Internal Only** (no external access):
- `inventory-app:8000`
- `accounting-app:8000`
- `accounting-db:5432`
- `inventory-redis:6379`

## Deployment

### Starting Services

```bash
# Start all services
cd /opt/restaurant-system
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f
```

### Service Dependencies

```
inventory-app depends on:
  - inventory-db (healthy)
  - inventory-redis (healthy)

accounting-app depends on:
  - accounting-db (healthy)
  - inventory-app (started)

nginx depends on:
  - inventory-app (started)
  - accounting-app (started)
```

Docker Compose ensures services start in the correct order.

### Health Checks

Each database has a health check:
```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U user -d db"]
  interval: 10s
  timeout: 5s
  retries: 5
```

Applications wait for databases to be healthy before starting.

## Data Persistence

### Docker Volumes

```
inventory_postgres_data    → /var/lib/postgresql/data (inventory-db)
accounting_postgres_data   → /var/lib/postgresql/data (accounting-db)
inventory_redis_data       → /data (inventory-redis)
```

### File Storage

```
./inventory/uploads/       → Vendor invoices, receipts, images
./shared/certbot/conf/     → SSL certificates
./accounting/logs/         → Application logs
```

**Backup Strategy**:
1. **Automated Database Backups**: Daily at 2 AM via cron
   - Script: `/opt/restaurant-system/scripts/backup_databases.sh`
   - Location: `/opt/restaurant-system/backups/`
   - Retention: 7 days
   - Both inventory and accounting databases backed up
2. **File Backups**: User uploads preserved in `/opt/restaurant-system/inventory/uploads/`
3. **Full System Backup**: Manual via `tar` when needed

## Security

### Network Security

- Only nginx exposed to public internet (ports 80, 443)
- All other services on private Docker network
- Database ports not exposed externally (except inventory-db:5432 for admin)

### Application Security

- **Authentication**: JWT token-based with localStorage
- **Authorization**: Role-based access control (Admin, Manager, Staff)
- **Location-Based Access Control**:
  - Admin users: Access to all locations
  - Manager/Staff users: Only assigned locations
  - Filtering applied at API level
- **API Security**: API keys for inter-service communication
- **Database**: Separate credentials per service
- **Secrets**: Stored in `.env` files (not in code)
- **IP Blocking**: Direct IP address access returns 444 (connection closed)

### Data Security

- **Encryption in Transit**: SSL/TLS via Let's Encrypt
- **Encryption at Rest**: Database encryption (optional)
- **Backups**: Encrypted backup files
- **Audit Logs**: All critical operations logged

## Monitoring

### Automated Health Monitoring

**Health Check Script**: Runs every 5 minutes via cron
- Script: `/opt/restaurant-system/scripts/health_check.sh`
- Checks: Docker containers, databases, disk space
- Alerts: Console output (can be extended to email/Slack)

**POS Sync Monitoring**: Runs every 10 minutes via cron
- Script: `/opt/restaurant-system/scripts/check_pos_sync.sh`
- Checks: Last sync time, sync failures
- Auto-sync: Runs every 10 minutes in inventory app

**Cron Schedule**:
```bash
# View all scheduled jobs
crontab -l

# Backup databases daily at 2 AM
0 2 * * * /opt/restaurant-system/scripts/backup_databases.sh

# Health check every 5 minutes
*/5 * * * * /opt/restaurant-system/scripts/health_check.sh

# POS sync check every 10 minutes
*/10 * * * * /opt/restaurant-system/scripts/check_pos_sync.sh
```

### Health Endpoints

```bash
# Inventory health
curl http://localhost/inventory/health

# Accounting health
curl http://localhost/accounting/health
```

### Logs

```bash
# View all logs
docker compose logs -f

# Service-specific logs
docker compose logs -f inventory-app
docker compose logs -f accounting-app

# Database logs
docker compose logs -f inventory-db
docker compose logs -f accounting-db
```

### Metrics

```bash
# Service status
docker compose ps

# Resource usage
docker stats

# Database connections
docker compose exec inventory-db psql -U inventory_user -d inventory_db -c "SELECT count(*) FROM pg_stat_activity;"
```

## Adding New Services

To add a new service (e.g., HR system):

### 1. Create Service Directory

```bash
mkdir -p hr/src/hr
mkdir -p hr/alembic
```

### 2. Add Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ ./src/
CMD ["uvicorn", "hr.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3. Update docker-compose.yml

```yaml
hr-db:
  image: postgres:15
  environment:
    POSTGRES_USER: hr_user
    POSTGRES_PASSWORD: hr_pass
    POSTGRES_DB: hr_db
  volumes:
    - hr_data:/var/lib/postgresql/data
  networks:
    - restaurant-network

hr-app:
  build: ./hr
  volumes:
    - ./hr/src:/app/src
  env_file:
    - ./hr/.env
  depends_on:
    hr-db:
      condition: service_healthy
  networks:
    - restaurant-network
```

### 4. Add Nginx Routing

```nginx
# In shared/nginx/conf.d/app-http.conf
location /hr/ {
    proxy_pass http://hr-app:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### 5. Update Documentation

- Update this file (ARCHITECTURE.md)
- Update README.md
- Document API endpoints

## Maintenance

### Database Migrations

```bash
# Inventory migrations
docker compose exec inventory-app alembic upgrade head

# Accounting migrations
docker compose exec accounting-app alembic upgrade head
```

### Backup

```bash
# Backup everything
cd /opt
sudo tar -czf restaurant-system-backup-$(date +%Y%m%d).tar.gz restaurant-system/

# Backup databases only
docker compose exec inventory-db pg_dump -U inventory_user inventory_db > inventory_backup.sql
docker compose exec accounting-db pg_dump -U accounting_user accounting_db > accounting_backup.sql
```

### Updates

```bash
# Pull latest code
git pull

# Rebuild and restart services
docker compose build
docker compose up -d

# Check for issues
docker compose ps
docker compose logs -f
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker compose logs <service-name>

# Check health
docker compose ps

# Restart service
docker compose restart <service-name>
```

### Database Connection Issues

```bash
# Check database is healthy
docker compose ps | grep db

# Test connection
docker compose exec inventory-app python -c "import psycopg2; psycopg2.connect('postgresql://inventory_user:inventory_pass@inventory-db/inventory_db')"
```

### Nginx Issues

```bash
# Test nginx config
docker compose exec nginx-proxy nginx -t

# Reload nginx
docker compose exec nginx-proxy nginx -s reload
```

## Recent Enhancements (October 2025)

### Central Portal (v2.1 - October 14)
- **URL**: http://rm.swhgrp.com
- **Features**:
  - Unified landing page for all modules
  - Dark mode design matching inventory system
  - Path-based routing (`/inventory/`, `/accounting/`)
  - Separate authentication per module (no SSO)
  - Company branding with SW Hospitality Group logo

### Automation & Monitoring (v2.1 - October 14)
- **Automated Backups**: Daily database backups at 2 AM
- **Health Monitoring**: System health checks every 5 minutes
- **POS Sync Monitoring**: Auto-sync every 10 minutes with monitoring
- **Cron Integration**: All automation scheduled via crontab

### Security Enhancements (v2.1 - October 14)
- **IP Blocking**: Direct IP address access blocked
- **Location Access Control**: Admin users see all locations, others filtered
- **Domain Enforcement**: Must access via rm.swhgrp.com

### Technical Improvements (v2.1 - October 14)
- **Routing Fix**: Added `<base href="/inventory/">` for portal compatibility
- **API Paths**: Converted all absolute paths to relative paths
- **Static Files**: Updated to work with path-based routing
- **Bug Fixes**: Fixed settings page, dashboard, and navigation issues

## Future Enhancements

### Planned Services

1. **HR System**
   - Document retention
   - Employee information
   - Personnel records

2. **Analytics Dashboard**
   - Consolidated reporting
   - Business intelligence
   - Predictive analytics

### Scaling Considerations

- **Horizontal Scaling**: Add multiple instances behind load balancer
- **Database Replication**: Read replicas for reporting
- **Caching Layer**: Redis cluster for improved performance
- **Message Queue**: RabbitMQ/Kafka for async processing

## Contact & Support

For issues or questions:
1. Check service logs
2. Review this architecture document
3. Consult README.md for common operations

---

**Last Updated**: October 14, 2025
**Version**: 2.1 (Portal + Automation)

# Restaurant Inventory Management System

A comprehensive web-based inventory management system built for restaurant operations, supporting multi-location inventory tracking, transfers, and reporting.

## System Overview

**Technology Stack:**
- **Backend:** Python 3.11, FastAPI
- **Database:** PostgreSQL 15
- **Cache/Session:** Redis 7
- **Frontend:** HTML5, JavaScript, Bootstrap 5
- **Web Server:** Nginx (reverse proxy with SSL/TLS)
- **Containerization:** Docker & Docker Compose
- **Database Migrations:** Alembic

**Deployment:**
- Production URL: https://inventory.swhgrp.com:8443 (HTTPS)
- HTTP Access: http://inventory.swhgrp.com:8000
- SSL Certificate: Let's Encrypt (valid until December 30, 2025)

## Core Features

### 1. Authentication & Authorization
- Secure user authentication with JWT tokens
- Role-based access control (Admin/User)
- Password hashing with bcrypt
- Session management via Redis
- Admin-only features:
  - Settings/configuration access
  - User management
  - Inventory record editing/deletion

### 2. Master Item Management
- Create and manage inventory items
- Categorization system
- Vendor/supplier tracking
- Unit of measure (UOM) configuration
- Storage area assignment
- Par level settings
- Cost tracking

### 3. Multi-Location Inventory
- Track inventory across multiple locations
- Location-specific storage areas
- Real-time inventory counts
- Low stock alerts (based on par levels)
- Inventory value calculation
- Filter by location, storage area, category, and stock status

### 4. Inventory Counting
- **Live Count Sessions:** Real-time inventory counting with auto-save
- **Count Templates:** Pre-configured item lists for quick counting
- **Count History:** Review and reopen previous count sessions
- Mobile-responsive interface for on-the-go counting
- Automatic inventory updates upon count completion
- Support for partial counts and adjustments

### 5. Transfer System
- Create transfer requests between locations
- Multi-item transfers with quantities
- Transfer workflow states:
  - PENDING: Awaiting approval
  - IN_TRANSIT: Approved and shipped
  - RECEIVED: Completed
  - REJECTED: Denied
- Transfer actions:
  - Approve (sends items)
  - Ship (updates status)
  - Receive (updates receiving location inventory)
  - Reject (cancels transfer)
- Automatic inventory adjustments on transfer completion
- Transfer history and audit trail

### 6. Reporting
- **Usage Report:** Detailed usage analysis with:
  - Starting inventory
  - Purchases/additions
  - Adjustments
  - Ending inventory
  - Usage calculations
  - Cost analysis
  - Value tracking
  - Collapsible category drill-down
- **Variance Report:** Compare expected vs actual inventory
- Date range filtering
- Location-specific reports
- Export functionality (planned)

### 7. Dashboard
- Quick overview of key metrics
- Recent activity feed
- Low stock alerts
- Pending transfer notifications
- Location selector for filtered views

### 8. User Management (Admin)
- Create/edit/delete users
- Assign roles (Admin/User)
- Password management
- User activity tracking

### 9. Settings & Configuration (Admin)
- **Locations:** Manage restaurant locations
- **Storage Areas:** Define storage locations within each site
- **Categories:** Organize items by category
- **Vendors/Suppliers:** Maintain vendor database
- **Master Items:** Central item catalog management
- **Count Templates:** Create reusable count session templates

## Database Schema

### Core Models

**User**
- id, username, email, hashed_password
- full_name, role (ADMIN/USER)
- is_active, created_at, updated_at

**Location**
- id, name, address, is_active
- created_at, updated_at

**StorageArea**
- id, name, location_id, is_active
- created_at, updated_at

**Category**
- id, name, description

**Vendor**
- id, name, contact_info, email, phone

**Item** (Master Item List)
- id, name, category_id, vendor_id
- unit_of_measure, par_level, cost
- storage_area_id, location_id
- is_active, created_at, updated_at

**Inventory**
- id, item_id, location_id, storage_area_id
- quantity, last_count_date
- created_at, updated_at

**CountSession**
- id, location_id, user_id, template_id
- status (IN_PROGRESS/COMPLETED)
- items (JSONB - array of counted items)
- notes, started_at, completed_at

**CountTemplate**
- id, name, location_id, created_by_id
- items (JSONB - array of item configurations)
- is_active, created_at, updated_at

**Transfer**
- id, from_location_id, to_location_id
- requested_by_id, approved_by_id, received_by_id
- status (PENDING/IN_TRANSIT/RECEIVED/REJECTED)
- items (JSONB - array of transfer items)
- notes, requested_at, shipped_at, received_at

**AuditLog**
- id, user_id, action, entity_type, entity_id
- changes (JSONB), ip_address, user_agent
- created_at

**Waste** (planned feature)
- id, item_id, location_id, quantity
- reason, recorded_by_id, recorded_at

## API Structure

All API endpoints are prefixed with `/api/v1`:

- **/auth** - Login, logout, token refresh
- **/users** - User CRUD operations
- **/locations** - Location management
- **/storage_areas** - Storage area management
- **/categories** - Category management
- **/vendors** - Vendor management
- **/items** - Master item management
- **/inventory** - Inventory CRUD and queries
- **/count_sessions** - Count session management
- **/count_templates** - Template CRUD
- **/transfers** - Transfer creation and management
- **/reports** - Usage and variance reports
- **/audit_log** - Activity audit trail

## Frontend Pages

- **Login** (`/login`) - User authentication
- **Dashboard** (`/dashboard`) - Main overview
- **Inventory** (`/inventory`) - Current inventory view
- **Take Inventory** (`/inventory/count`) - Live counting interface
- **Count History** (`/inventory/count/history`) - Previous counts
- **Reports** (`/reports`) - Usage and variance reports
- **Transfers** (`/transfers`) - Transfer management
- **Settings** (`/settings`) - Admin configuration (locations, items, vendors, etc.)
- **Profile** (`/profile`) - User profile management

## Deployment Architecture

### Network Configuration
- **VM IP:** 192.168.122.249 (internal)
- **Host Server IP:** 10.0.0.65 (internal LAN)
- **Public Domain:** inventory.swhgrp.com
- **Ports:**
  - 8000: HTTP (development/internal)
  - 8443: HTTPS (production with SSL)
  - 5432: PostgreSQL (internal only)

### Docker Services
1. **app** - FastAPI application (Python)
2. **db** - PostgreSQL database
3. **redis** - Redis cache/session store
4. **nginx** - Reverse proxy with SSL termination
5. **certbot** - Let's Encrypt SSL certificate management

### Port Forwarding Chain
```
Internet → Router:8443
  → Host Server (10.0.0.65):8443
    → VM (192.168.122.249):8443
      → Docker nginx:443
        → FastAPI app:8000
```

## Installation & Setup

### Prerequisites
- Docker and Docker Compose installed
- Domain name with DNS A record configured
- Ports 8000 and 8443 available

### Quick Start
```bash
# Clone or navigate to project directory
cd /opt/restaurant-inventory

# Configure environment variables (already set)
# Edit .env if needed

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop services
docker-compose down
```

### Database Migrations
```bash
# Run migrations
docker-compose exec app alembic upgrade head

# Create new migration
docker-compose exec app alembic revision --autogenerate -m "description"
```

### SSL Certificate Renewal

The Let's Encrypt certificate expires **December 30, 2025** and requires manual renewal:

```bash
# Add DNS TXT record when prompted by certbot
# Record name: _acme-challenge.inventory.swhgrp.com
# Then run:
docker-compose stop certbot
echo "" | docker-compose run --rm --entrypoint "" certbot certbot certonly --manual --preferred-challenges dns -d inventory.swhgrp.com --email admin@swhgrp.com --agree-tos --no-eff-email

# Restart nginx to load new certificate
docker-compose restart nginx
```

### Backup & Restore

**Database Backup:**
```bash
docker-compose exec db pg_dump -U inventory_user inventory_db > backup.sql
```

**Database Restore:**
```bash
cat backup.sql | docker-compose exec -T db psql -U inventory_user inventory_db
```

**Uploads Backup:**
```bash
tar -czf uploads-backup.tar.gz uploads/
```

## Configuration Files

- **docker-compose.yml** - Service orchestration
- **Dockerfile** - Application container build
- **.env** - Environment variables and secrets
- **requirements.txt** - Python dependencies
- **alembic.ini** - Database migration config
- **nginx/nginx.conf** - Nginx main config
- **nginx/conf.d/app-http.conf** - HTTP server config
- **nginx/conf.d/app-https.conf** - HTTPS server config

## Security Features

- JWT token-based authentication
- Password hashing with bcrypt
- HTTPS with TLS 1.2/1.3
- HSTS (HTTP Strict Transport Security)
- Role-based access control
- Audit logging for all actions
- CORS protection
- SQL injection prevention (SQLAlchemy ORM)
- XSS protection headers

## Default Credentials

**Admin User:**
- Username: `admin`
- Password: _(should be changed on first login)_

## Troubleshooting

### Application won't start
```bash
docker-compose logs app
# Check for database connection errors
docker-compose ps
```

### Database connection issues
```bash
# Restart database
docker-compose restart db

# Check database logs
docker-compose logs db
```

### HTTPS not working
```bash
# Check nginx logs
docker logs restaurant-inventory-nginx-1

# Verify certificate files exist
ls -la certbot/conf/live/inventory.swhgrp.com/

# Restart nginx
docker-compose restart nginx
```

### Port conflicts
```bash
# Check what's using ports
ss -tlnp | grep -E ':(8000|8443|5432)'

# Stop conflicting services or change port mappings in docker-compose.yml
```

## Planned Features

- Invoice parsing with OCR/AI
- Waste tracking and reporting
- Purchase order management
- Recipe/menu item integration
- Cost analysis and budgeting
- Mobile app (iOS/Android)
- Barcode/QR code scanning
- Automated reorder suggestions
- Multi-language support
- Export to Excel/PDF

## Development

### Project Structure
```
/opt/restaurant-inventory/
├── src/restaurant_inventory/
│   ├── api/api_v1/endpoints/    # API routes
│   ├── core/                     # Config, security, deps
│   ├── db/                       # Database setup
│   ├── models/                   # SQLAlchemy models
│   ├── schemas/                  # Pydantic schemas
│   ├── static/                   # CSS, JS, images
│   └── templates/                # HTML templates
├── alembic/                      # Database migrations
├── nginx/                        # Nginx configuration
├── certbot/                      # SSL certificates
├── uploads/                      # User uploads
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env
```

### Adding New Features

1. Create database model in `src/restaurant_inventory/models/`
2. Create Pydantic schema in `src/restaurant_inventory/schemas/`
3. Create API endpoint in `src/restaurant_inventory/api/api_v1/endpoints/`
4. Create/update HTML template in `src/restaurant_inventory/templates/`
5. Generate migration: `alembic revision --autogenerate -m "description"`
6. Run migration: `alembic upgrade head`
7. Test and restart application

## Support & Maintenance

**System Administrator:** Andy Hammond (andy@hammer)
**VM User:** swh
**Domain Registrar:** _(wherever swhgrp.com is registered)_
**DNS Provider:** _(check domain DNS settings)_

## Version History

- **v1.0.0** - Initial production release
  - Multi-location inventory management
  - Transfer system
  - Count sessions and templates
  - Usage and variance reports
  - HTTPS with Let's Encrypt
  - Mobile-responsive UI

## License

Proprietary - SW Hospitality Group

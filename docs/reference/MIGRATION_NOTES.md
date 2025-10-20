# System Migration & Enhancement Notes

This document tracks major system changes and migrations.

---

# Migration 2: Portal Implementation & Automation
## Date: October 14, 2025

## Overview
Added central web portal, automated backups, health monitoring, and fixed routing issues for portal integration.

## Changes Made

### 1. Central Portal Implementation
**Created**: `/opt/restaurant-system/portal/`

**Files**:
- `index.html` - Landing page with module cards
- `css/portal.css` - Dark mode styling
- `images/sw-logo.png` - Company branding

**Features**:
- Unified entry point at http://rm.swhgrp.com
- Dark mode design matching inventory system
- Path-based routing to modules
- Separate authentication per module (no SSO)
- Coming soon sections for future modules

### 2. Nginx Configuration Updates
**File**: `shared/nginx/conf.d/rm.swhgrp.com-http.conf`

**Routing**:
```
/                   → Portal landing page
/inventory/*        → Inventory service
/accounting/*       → Accounting service
/css/*              → Portal assets
/images/*           → Portal assets
```

**Security**:
- Added default server block to return 444 for IP access
- Domain-only access enforced

### 3. Automated Backups
**Created**: `scripts/backup_databases.sh`

**Features**:
- Backs up both inventory and accounting databases
- Stores in `/opt/restaurant-system/backups/`
- Retains 7 days of backups
- Runs daily at 2 AM via cron

**Cron Entry**:
```
0 2 * * * /opt/restaurant-system/scripts/backup_databases.sh
```

### 4. Health Monitoring
**Created**: `scripts/health_check.sh`

**Checks**:
- Docker container status
- Database connectivity
- Disk space usage
- Running services

**Cron Entry**:
```
*/5 * * * * /opt/restaurant-system/scripts/health_check.sh
```

### 5. POS Sync Monitoring
**Created**: `scripts/check_pos_sync.sh`

**Features**:
- Monitors last POS sync time
- Checks for sync failures
- Alerts if sync is stale (>15 minutes)

**Cron Entry**:
```
*/10 * * * * /opt/restaurant-system/scripts/check_pos_sync.sh
```

### 6. Routing Fixes for Portal Integration

**Problem**: When accessing inventory via `/inventory/`, relative URLs were not resolving correctly.

**Solution**: Added `<base href="/inventory/">` to HTML templates

**Files Modified**:
- `inventory/src/restaurant_inventory/templates/base.html`
  - Added `<base href="/inventory/">` tag
  - Updated all static file paths to absolute (`/inventory/static/...`)
- `inventory/src/restaurant_inventory/templates/login.html`
  - Updated logo path

**Mass API Path Conversion**:
Converted all API paths from absolute to relative across all templates:
- Before: `'/api/locations/'` → After: `'api/locations/'`
- Before: `"/api/users/"` → After: `"api/users/"`
- Before: `` `/api/dashboard/analytics` `` → After: `` `api/dashboard/analytics` ``

**Templates Updated** (21 files):
- settings.html, dashboard.html, vendor_items.html, invoices.html
- count_session_new.html, pos_item_mapping.html, locations.html
- templates_management.html, master_items.html, items.html
- users.html, units_of_measure.html, waste.html, recipes.html
- vendors.html, inventory_movements.html, pos_config.html
- inventory.html, reports.html, transfers.html, count_session.html
- count_history.html

### 7. Repository Cleanup

**Deleted** (10 session history files):
- LOCATION_ACCESS_CONTROL_COMPLETE.md
- LOCATION_FILTERING_IMPLEMENTATION.md
- PERFORMANCE_OPTIMIZATION_COMPLETE.md
- PERFORMANCE_OPTIMIZATIONS.md
- PHASE1_OPTIMIZATION_RESULTS.md
- PHASE2_CACHING_RESULTS.md
- PORTAL_IMPLEMENTATION.md
- PRIORITY1_COMPLETE.md
- RECOMMENDATIONS.md
- SESSION_HISTORY.md

**Moved**:
- Test scripts to `scripts/tests/` directory

**Updated**:
- `.gitignore` to exclude future session files

### 8. Documentation Updates

**README.md**:
- Added portal section
- Updated architecture diagram
- Added automated backup instructions
- Added health monitoring commands
- Updated version to 2.1

**ARCHITECTURE.md**:
- Added portal directory structure
- Updated nginx routing rules
- Added automation & monitoring section
- Added recent enhancements section
- Updated security documentation

## Technical Details

### Base Href Solution
The key to making portal routing work was adding the HTML `<base>` tag:

```html
<base href="/inventory/">
```

This tells the browser that all relative URLs should resolve relative to `/inventory/`, fixing:
- Navigation links (dashboard, reports, etc.)
- API calls (api/locations/, api/users/, etc.)
- Form submissions

### Path Resolution
- User visits: `http://rm.swhgrp.com/inventory/dashboard`
- Link to `reports` resolves to: `/inventory/reports` ✓
- API call to `api/locations/` resolves to: `/inventory/api/locations/` ✓
- Nginx strips `/inventory/` and forwards to inventory app ✓

## Verification Checklist

- [x] Portal accessible at http://rm.swhgrp.com
- [x] Inventory module accessible via portal
- [x] Accounting module accessible via portal
- [x] All navigation working in inventory
- [x] All API calls working (settings, dashboard, etc.)
- [x] Static files loading correctly
- [x] Automated backups scheduled
- [x] Health monitoring scheduled
- [x] POS sync monitoring scheduled
- [x] IP address access blocked
- [x] Documentation updated

## Issues Encountered & Resolved

### Issue 1: API Returning HTML Instead of JSON
**Symptom**: "Unexpected token '<', '<!DOCTYPE'... is not valid JSON"
**Cause**: Absolute API paths (`/api/...`) were hitting portal instead of inventory
**Solution**: Converted all API paths to relative (`api/...`)

### Issue 2: Navigation Links Going to Portal
**Symptom**: Dashboard link taking users back to portal home
**Cause**: Absolute paths like `/dashboard` were being caught by portal routing
**Solution**: Added `<base href="/inventory/">` tag and used relative paths

### Issue 3: Static Files Not Loading
**Symptom**: CSS and images not displaying
**Cause**: Static file paths were relative to base href
**Solution**: Made static file paths absolute (`/inventory/static/...`)

### Issue 4: Login Button Visible on Login Page
**Symptom**: Login button showing in navbar on login page
**Cause**: Path check was exact match (`=== '/login'`) but path was `/inventory/login`
**Solution**: Changed to `endsWith('/login')` to handle both cases

### Issue 5: Inventory Submenu Auto-Expanding
**Symptom**: Inventory submenu opening on every page
**Cause**: Check was `includes('/inventory')` which matched all pages
**Solution**: Made check more specific to only match inventory section pages

## Cron Jobs Summary

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

## Security Enhancements

1. **IP Blocking**: Direct IP access returns 444
2. **Domain Enforcement**: Must use rm.swhgrp.com
3. **Location Access Control**: Admin users see all locations
4. **Separate Authentication**: Each module has own login

## Rollback Instructions

If needed, you can rollback these changes:

```bash
# Revert nginx config
cd /opt/restaurant-system/shared/nginx/conf.d
# Remove or rename rm.swhgrp.com-http.conf

# Remove portal
rm -rf /opt/restaurant-system/portal

# Remove cron jobs
crontab -e
# Delete the three cron entries

# Revert base.html
cd /opt/restaurant-system/inventory/src/restaurant_inventory/templates
git checkout base.html

# Reload nginx
docker exec nginx-proxy nginx -s reload
```

---

# Migration 1: Microservices Restructuring
## Date: October 13, 2025

## What Changed

The system was restructured from a **mixed architecture** to a clean **microservices architecture** where inventory and accounting are peer services.

### Old Structure
```
/opt/restaurant-inventory/
├── src/              # Inventory app (at root)
├── alembic/          # Inventory migrations
├── accounting/       # Accounting service (nested)
│   ├── src/
│   └── alembic/
├── nginx/
├── docker-compose.yml
└── .env
```

### New Structure
```
/opt/restaurant-system/
├── inventory/        # Inventory microservice
│   ├── src/
│   ├── alembic/
│   └── .env
├── accounting/       # Accounting microservice
│   ├── src/
│   ├── alembic/
│   └── .env
├── shared/           # Shared infrastructure
│   ├── nginx/
│   └── certbot/
├── docker-compose.yml
└── README.md
```

## Changes Made

### 1. Directory Restructuring
- Created `/opt/restaurant-system/` as new root
- Moved inventory code to `inventory/` subdirectory
- Accounting remains in `accounting/` but now at peer level
- Created `shared/` for nginx and certbot

### 2. Docker Compose Updates
- Renamed service `app` → `inventory-app`
- Renamed service `db` → `inventory-db`
- Renamed service `redis` → `inventory-redis`
- Updated all volume paths to new structure
- Added explicit container names
- Created dedicated Docker network: `restaurant-network`

### 3. Nginx Configuration
- Updated upstream `backend` to point to `inventory-app:8000` (was `app:8000`)
- Paths updated in volume mounts
- Configuration files moved to `shared/nginx/`

### 4. Environment Configuration
- Accounting `.env` created with proper settings
- Added `INVENTORY_API_KEY` for service authentication
- Updated `INVENTORY_API_URL` to use new service name

### 5. Documentation
- Created comprehensive `README.md`
- Created detailed `ARCHITECTURE.md`
- Added `.gitignore` for root directory
- Created `MIGRATION_NOTES.md` (this file)

## Important Service Name Changes

### Docker Compose Services
- `app` → `inventory-app`
- `db` → `inventory-db`
- `redis` → `inventory-redis`
- `nginx` → `nginx-proxy` (container name)
- `accounting-app` → remains the same
- `accounting-db` → remains the same

### Container Names
- `restaurant-inventory-app-1` → `inventory-app`
- `restaurant-inventory-db-1` → `inventory-db`
- `restaurant-inventory-redis-1` → `inventory-redis`
- `restaurant-inventory-nginx-1` → `nginx-proxy`
- `restaurant-inventory-accounting-app-1` → `accounting-app`
- `restaurant-inventory-accounting-db-1` → `accounting-db`

### Network
- `restaurant-inventory_default` → `restaurant-network`

## What Wasn't Changed

### No Code Changes Required ✅
- Application code remained identical
- Database schemas unchanged
- API endpoints unchanged
- User interface unchanged
- Authentication unchanged

### Data Preserved ✅
- All Docker volumes preserved (data intact)
- Database data migrated automatically
- File uploads copied to new location

## Backup Information

**Backup Location**: `/opt/restaurant-inventory-backup-20251013-223250.tar.gz`
**Backup Size**: 1.4 MB (compressed)
**Contains**: Complete copy of old structure before changes

## Verification Checklist

- [x] All services start successfully
- [x] Inventory app accessible at http://domain.com/
- [x] Accounting app accessible at http://domain.com/accounting/
- [x] Database connections working
- [x] Redis connection working
- [x] Nginx routing correct
- [x] File uploads accessible
- [x] SSL certificates preserved
- [x] All Docker volumes present
- [x] No data loss

## Post-Migration Steps

### Completed ✅
1. Backup created
2. Directory structure created
3. Files copied to new structure
4. Docker Compose updated
5. Nginx configuration updated
6. Services tested and verified
7. Documentation created

### Optional (Can Do Later)
1. Remove old directory `/opt/restaurant-inventory/` (after testing period)
2. Update any external monitoring tools with new container names
3. Update any backup scripts with new paths
4. Update team documentation/runbooks

## Command Reference

### New Working Directory
```bash
cd /opt/restaurant-system
```

### Docker Commands
```bash
# All docker-compose commands now run from new directory
docker compose ps
docker compose logs -f
docker compose restart <service-name>
```

### Accessing Services
```bash
# Inventory database
docker compose exec inventory-db psql -U inventory_user -d inventory_db

# Accounting database
docker compose exec accounting-db psql -U accounting_user -d accounting_db

# Application shells
docker compose exec inventory-app /bin/bash
docker compose exec accounting-app /bin/bash
```

## Rollback Instructions

If needed, you can rollback to the old structure:

```bash
# Stop new system
cd /opt/restaurant-system
docker compose down

# Restore old backup
cd /opt
sudo tar -xzf restaurant-inventory-backup-20251013-223250.tar.gz

# Start old system
cd /opt/restaurant-inventory
docker compose up -d
```

**Note**: Rollback will lose any data changes made after the backup.

## Benefits of New Structure

1. **Clearer Architecture**: Each service is a first-class citizen
2. **Easier Scaling**: Add new services (HR, Analytics) as peers
3. **Better Organization**: Shared infrastructure in dedicated directory
4. **Industry Standard**: Follows microservices best practices
5. **Future-Proof**: Ready for service mesh, Kubernetes, etc.

## Testing Results

### Service Health
```
✓ inventory-app:     Running and healthy
✓ inventory-db:      Running and healthy (PostgreSQL 15)
✓ inventory-redis:   Running and healthy (Redis 7)
✓ accounting-app:    Running and healthy
✓ accounting-db:     Running and healthy (PostgreSQL 15)
✓ nginx-proxy:       Running and routing correctly
✓ certbot:           Running
```

### Endpoint Tests
```
✓ http://localhost/                  → Inventory UI (200 OK)
✓ http://localhost/accounting/       → Accounting UI (200 OK)
✓ http://localhost/accounting/health → Health check (200 OK)
✓ http://localhost/static/*          → Static files (200 OK)
```

## Questions & Support

**Q: Where are the database files?**
A: Docker volumes are preserved. Use `docker volume ls` to see them.

**Q: Did we lose any data?**
A: No, all data was preserved via Docker volumes.

**Q: Can I delete the old directory?**
A: Yes, after confirming everything works for a few days.

**Q: What if something breaks?**
A: Use the rollback instructions above to restore from backup.

**Q: Do I need to update my browser bookmarks?**
A: No, URLs remain the same (http://domain.com/)

## Related Files

- `README.md` - Getting started guide
- `ARCHITECTURE.md` - Detailed architecture documentation
- `docker-compose.yml` - Service orchestration
- `.gitignore` - Git ignore rules

---

**Migration Performed By**: Claude AI Assistant
**Date**: October 13, 2025
**Status**: ✅ Successfully Completed
**Downtime**: < 2 minutes

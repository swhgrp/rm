# CLAUDE.md - SW Hospitality Group Restaurant Management System

## Project Overview
Microservices-based restaurant management platform for SW Hospitality Group.
- **Production URL:** https://rm.swhgrp.com
- **Architecture:** 10 FastAPI microservices behind Nginx reverse proxy, each with its own PostgreSQL database
- **Portal:** Central auth + UI at `/portal/`, serves templates from each service's template directory

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
├── websites/        # Website management
```

## Tech Stack
- **Backend:** FastAPI (Python 3.11), async SQLAlchemy with asyncpg (maintenance), sync SQLAlchemy (most others)
- **Database:** PostgreSQL 15, one DB per service, Alembic migrations
- **Frontend:** Jinja2 templates, Bootstrap Icons, vanilla JS (no frameworks)
- **Infrastructure:** Docker Compose per service, Nginx reverse proxy
- **Auth:** JWT tokens in HTTP-only cookies, portal-based SSO

## Key Patterns

### Service Communication
- Inventory service is **source of truth** for locations - other services fetch via `/inventory/api/locations/_sync`
- Hub is source of truth for vendors, invoices, UOM, and vendor items
- Services communicate via internal HTTP calls on Docker network

### Invoice Cost Update Flow
- Hub's `LocationCostUpdaterService` writes directly to Inventory's PostgreSQL DB (not via API)
- `price_is_per_unit` flag on `hub_invoice_items` — set at mapping time by comparing parsed invoice UOM against vendor item's `purchase_unit_abbr`
- Auto-mapper enriches invoice items: sets `price_is_per_unit`, overrides `pack_size` with vendor's `units_per_case`
- Cost updater uses flag (with string-based fallback for legacy items); weight items handled via `size_unit.measure_type`
- Manual mapping endpoint also sets `price_is_per_unit` from vendor item data

### Database Connections
- Most services: sync SQLAlchemy (`Session`, `get_db`)
- Maintenance service: **async** SQLAlchemy (`AsyncSession`, `get_db`, `asyncpg`)
  - Uses `pool_pre_ping=True`, `pool_recycle=300`
  - Has startup DB warmup with retry (5 attempts, 2s delay) to handle Postgres race conditions

### Portal Templates
- Located in `portal/templates/{service}/` (e.g., `portal/templates/maintenance/`)
- Extend `{service}/base.html`
- Dark theme with CSS variables (`--bg-primary`, `--accent-primary`, etc.)
- Table action buttons use `.actions-wrap` div with `inline-flex` for alignment

### Docker
- Each service has its own `docker-compose.yml` and `Dockerfile`
- Source mounted as read-only volumes: `./src:/app/src:ro`
- Rebuild with: `cd {service} && docker compose up -d --build`

## Common Commands
```bash
# Rebuild a service
cd maintenance && docker compose up -d --build

# Check service logs
docker compose logs --tail=50 maintenance-service

# Run Alembic migration
docker compose exec maintenance-service alembic upgrade head

# Test an API endpoint
curl -s http://localhost:{port}/endpoint | python3 -m json.tool
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

## Important Notes
- Never modify `.env` files (contain production secrets)
- Location data comes from inventory service - don't duplicate
- Maintenance service uses **async** patterns (different from other services)
- CalDAV sync service pushes events to external calendar server
- Customer invoice PDFs can include area/location logos for branding

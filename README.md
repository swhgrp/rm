# SW Hospitality Group - Restaurant Management System

[![Status](https://img.shields.io/badge/status-production-brightgreen)]()
[![Completion](https://img.shields.io/badge/completion-90%25-blue)]()
[![Documentation](https://img.shields.io/badge/docs-up--to--date-brightgreen)]()

**Complete microservices-based restaurant management platform**

**Last Updated:** October 28, 2025  
**Production URL:** https://rm.swhgrp.com  
**Status:** 90% Complete - Production Ready ✅

---

## 🎯 Overview

The SW Hospitality Group Restaurant Management System is a comprehensive microservices platform handling all aspects of restaurant operations including inventory management, human resources, accounting, event planning, and third-party integrations.

### Key Stats
- **7 microservices** running in production
- **356 Python files** across all systems
- **98 HTML templates** for user interfaces
- **74 database models** with full relationships
- **150+ API endpoints** for system integration
- **16 Docker containers** orchestrated via Docker Compose
- **90% completion** - production ready

---

## 📦 System Components

| System | Status | Description | URL |
|--------|--------|-------------|-----|
| **Portal** | 95% ✅ | Authentication & SSO | [/portal/](./portal/README.md) |
| **Inventory** | 100% ✅ | Stock management | [/inventory/](./inventory/README.md) |
| **HR** | 85% ✅ | Employee management | [/hr/](./hr/README.md) |
| **Accounting** | 95% ✅ | Financial management | [/accounting/](./accounting/README.md) |
| **Events** | 85% ✅ | Event planning | [/events/](./events/README.md) |
| **Integration Hub** | 70% 🔄 | API integrations | [/integration-hub/](./integration-hub/README.md) |
| **Files** | 100% ✅ | Document management | Nextcloud |

**Overall:** 90% Complete - Production Ready

---

## 🚀 Quick Start

### Installation

```bash
# Clone repository
git clone git@github.com:swhgrp/restaurant-system.git
cd restaurant-system

# Configure environment
for dir in portal inventory hr accounting events integration-hub; do
    cp $dir/.env.example $dir/.env
done

# Start all services
docker compose up -d

# Run migrations
docker compose exec inventory-app python manage.py migrate
docker compose exec hr-app python manage.py migrate
docker compose exec accounting-app python manage.py migrate
docker compose exec events-app alembic upgrade head

# Create admin users
docker compose exec inventory-app python manage.py createsuperuser
docker compose exec hr-app python manage.py createsuperuser

# Access portal
open https://rm.swhgrp.com/portal/
```

---

## 📚 Documentation

- **[Portal README](./portal/README.md)** - Authentication and SSO
- **[Inventory README](./inventory/README.md)** - Inventory management
- **[HR README](./hr/README.md)** - Human resources
- **[Accounting README](./accounting/README.md)** - Financial management
- **[Events README](./events/README.md)** - Event planning
- **[Integration Hub README](./integration-hub/README.md)** - API integrations
- **[SYSTEM_DOCUMENTATION.md](./SYSTEM_DOCUMENTATION.md)** - Complete system overview

---

## 🛠️ Common Commands

```bash
# View logs
docker compose logs -f [service-name]

# Restart service
docker compose restart [service-name]

# Access database
docker compose exec [service]-db psql -U [user] -d [database]

# Health checks
curl https://rm.swhgrp.com/[system]/health
```

---

## 🏗️ Architecture

**Microservices with:**
- PostgreSQL 15 (separate DB per service)
- Redis 7 (caching & queues)
- Nginx (reverse proxy with SSL)
- JWT authentication via Portal

**Technology Stack:**
- Django 4.2 (Inventory, HR, Accounting, Integration Hub)
- FastAPI (Portal, Events)
- Docker Compose orchestration

---

## ⚠️ Critical Priorities

### Immediate
- [ ] Automated database backups
- [ ] Monitoring and alerting
- [ ] Move secrets out of Git

### Short-Term
- [ ] Error tracking (Sentry)
- [ ] API rate limiting
- [ ] Complete RBAC enforcement

### Medium-Term
- [ ] CI/CD pipeline
- [ ] Comprehensive testing
- [ ] Performance optimization

---

## 📞 Support

**Health Checks:**
- Portal: https://rm.swhgrp.com/portal/health
- Inventory: https://rm.swhgrp.com/inventory/health
- HR: https://rm.swhgrp.com/hr/health
- Accounting: https://rm.swhgrp.com/accounting/health
- Events: https://rm.swhgrp.com/events/health
- Hub: https://rm.swhgrp.com/hub/health

**Logs:**
```bash
docker compose logs -f [service-name]
```

---

## 📄 License

**Proprietary - SW Hospitality Group Internal Use Only**

---

**Version:** 2.0  
**Last Updated:** October 28, 2025  
**Maintained By:** SW Hospitality Group Development Team

For complete system details, see [SYSTEM_DOCUMENTATION.md](./SYSTEM_DOCUMENTATION.md)

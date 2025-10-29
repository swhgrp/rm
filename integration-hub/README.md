# Integration Hub - Third-Party Integration Manager

## Overview

The Integration Hub is the central integration point for all third-party vendor APIs, data synchronization, and webhook management. It handles automated data sync with food distributors, payment processors, and other external services.

## Status: 70% Production Ready 🔄

## Purpose

- Vendor API integration management
- Automated product catalog synchronization
- Pricing and inventory updates from vendors
- Webhook endpoint management
- Data mapping and transformation
- Sync scheduling and monitoring
- Integration error handling and retry logic
- OAuth2 authentication for vendor connections

## Technology Stack

- **Framework:** Django 4.2 (Python)
- **Database:** PostgreSQL 15
- **Task Queue:** Celery with Redis
- **API Client:** httpx (async HTTP)
- **Authentication:** OAuth2, API keys
- **Data Processing:** pandas (for large datasets)

## Features

### ✅ Implemented (70%)

**Vendor Connection Management:**
- [x] Vendor connection registration
- [x] OAuth2 authentication flow
- [x] API credential storage (encrypted)
- [x] Connection status monitoring
- [x] Connection health checks
- [x] Multiple vendor support
- [x] Credential rotation

**Data Synchronization:**
- [x] Product catalog sync (from vendors to Inventory)
- [x] Pricing updates
- [x] Stock level updates
- [x] Order status tracking
- [x] Scheduled sync jobs (Celery)
- [x] Manual sync triggers
- [x] Incremental sync (delta updates)
- [x] Full sync (complete refresh)

**Webhook Management (Partial - 50%):**
- [x] Webhook endpoint registration
- [x] Payload validation
- [x] Event routing to appropriate handlers
- [x] Signature verification
- [ ] Automatic retry logic ❌
- [ ] Dead letter queue for failed webhooks ❌
- [ ] Webhook event history and replay ❌

**Sync Logging:**
- [x] Sync attempt tracking
- [x] Success/failure logs
- [x] Error details and stack traces
- [x] Sync duration monitoring
- [x] Data volume metrics
- [x] Sync history and audit trail

**Data Mapping:**
- [x] Field mapping configuration
- [x] Data transformation rules
- [x] Unit conversion (e.g., case to each)
- [x] Category mapping
- [x] Custom mapping functions

**Supported Vendors:**
- [x] US Foods - Full integration ✅
- [x] Sysco - Full integration ✅
- [x] Restaurant Depot - Partial (70%)
- [ ] Shamrock Foods - Planned ❌
- [ ] Performance Food Group (PFG) - Planned ❌
- [ ] Gordon Food Service - Planned ❌

**API Management:**
- [x] Rate limiting per vendor
- [x] Request throttling
- [x] Timeout management
- [x] Request/response logging
- [x] Error handling and reporting
- [x] Circuit breaker pattern (basic)

**Admin Interface:**
- [x] Connection dashboard
- [x] Sync status monitoring
- [x] Manual sync triggers
- [x] Sync log viewer
- [x] Error notification
- [x] Configuration management

### ❌ Missing (30%)

**Advanced Features:**
- [ ] Webhook retry logic with exponential backoff
- [ ] Dead letter queue for failed events
- [ ] Advanced conflict resolution
- [ ] Bi-directional sync (push to vendors)
- [ ] More vendor integrations
- [ ] Real-time event streaming
- [ ] Advanced data validation
- [ ] Automated testing framework for integrations

**Payment Integration:**
- [ ] Stripe integration
- [ ] Square integration
- [ ] Toast POS integration
- [ ] Payment reconciliation

**Reporting:**
- [ ] Sync analytics dashboard
- [ ] Cost savings reporting
- [ ] Data quality metrics
- [ ] Vendor comparison tools

## Architecture

### Database Schema (5 Models)

**Core Tables:**
- `vendor_connections` - Vendor API connections
- `vendor_types` - Supported vendor categories
- `sync_logs` - Sync attempt tracking
- `sync_status` - Current sync state
- `webhook_endpoints` - Registered webhooks
- `webhook_events` - Incoming webhook events
- `api_credentials` - Encrypted API keys
- `data_mappings` - Field mapping rules

### Key Django Models

```python
class VendorConnection:
    vendor_type: str  # 'us_foods', 'sysco', etc.
    name: str
    is_active: bool
    auth_type: str  # 'oauth2', 'api_key', 'basic'
    credentials: dict  # encrypted JSON
    last_sync: datetime
    sync_frequency: str  # 'hourly', 'daily', 'weekly'

class SyncLog:
    connection: ForeignKey(VendorConnection)
    sync_type: str  # 'product', 'pricing', 'inventory'
    status: str  # 'success', 'failed', 'partial'
    started_at: datetime
    completed_at: datetime
    records_processed: int
    errors_count: int
    error_details: JSONField

class WebhookEndpoint:
    vendor: ForeignKey(VendorConnection)
    url: str
    event_types: list
    is_active: bool
    secret: str  # for signature verification

class DataMapping:
    vendor: ForeignKey(VendorConnection)
    source_field: str
    target_field: str
    transformation: str  # Python function or expression
```

## API Endpoints

### Vendor Connections

**GET /hub/api/connections/**
- List all vendor connections

**POST /hub/api/connections/**
- Create new vendor connection

**GET /hub/api/connections/{id}/**
- Get connection details

**PUT /hub/api/connections/{id}/**
- Update connection

**DELETE /hub/api/connections/{id}/**
- Remove connection

**POST /hub/api/connections/{id}/test/**
- Test connection

### Synchronization

**POST /hub/api/sync/{connection_id}/trigger/**
- Manually trigger sync
- Body: `{"sync_type": "product", "full_sync": false}`

**GET /hub/api/sync/{connection_id}/status/**
- Get current sync status

**GET /hub/api/sync/logs/**
- List sync logs
- Query: `?connection=X&status=failed&start_date=YYYY-MM-DD`

**GET /hub/api/sync/logs/{log_id}/**
- Get detailed sync log

**POST /hub/api/sync/{connection_id}/cancel/**
- Cancel running sync

### Webhooks

**POST /hub/webhooks/{vendor}/{event_type}/**
- Receive webhook from vendor
- Validates signature
- Routes to appropriate handler

**GET /hub/api/webhooks/**
- List webhook endpoints

**POST /hub/api/webhooks/**
- Register webhook endpoint

**DELETE /hub/api/webhooks/{id}/**
- Remove webhook

### Data Mapping

**GET /hub/api/mappings/{connection_id}/**
- Get mappings for connection

**POST /hub/api/mappings/**
- Create data mapping

**PUT /hub/api/mappings/{id}/**
- Update mapping

### Health

**GET /hub/health**
- System health check

## Configuration

### Environment Variables (.env)

```bash
# Database
DATABASE_URL=postgresql://hub_user:password@hub-db:5432/hub_db

# Django Settings
SECRET_KEY=your-django-secret-key
DEBUG=False
ALLOWED_HOSTS=rm.swhgrp.com,integration-hub

# Celery (Background Jobs)
CELERY_BROKER_URL=redis://hub-redis:6379/0
CELERY_RESULT_BACKEND=redis://hub-redis:6379/0

# Vendor API Credentials
USFOOD_API_KEY=your-usfood-api-key
USFOOD_API_SECRET=your-secret
SYSCO_API_KEY=your-sysco-key
SYSCO_API_SECRET=your-secret
RESTAURANT_DEPOT_USERNAME=your-username
RESTAURANT_DEPOT_PASSWORD=your-password

# Integration System URLs
INVENTORY_API_URL=http://inventory-app:8000
ACCOUNTING_API_URL=http://accounting-app:8000

# Sync Settings
DEFAULT_SYNC_FREQUENCY=daily
MAX_RETRY_ATTEMPTS=3
SYNC_TIMEOUT_SECONDS=300

# Webhook Settings
WEBHOOK_SECRET_KEY=your-webhook-secret
WEBHOOK_VERIFY_SIGNATURES=True

# Rate Limiting
REQUESTS_PER_MINUTE=60
REQUESTS_PER_HOUR=1000

# Logging
ENABLE_DETAILED_LOGGING=True
LOG_API_REQUESTS=True
LOG_API_RESPONSES=False  # Can be large
```

## Installation & Setup

### Prerequisites
- Docker and Docker Compose
- PostgreSQL 15
- Redis 7
- Vendor API credentials

### Quick Start

1. **Set up environment:**
```bash
cd /opt/restaurant-system/integration-hub
cp .env.example .env
# Edit .env with vendor credentials
```

2. **Build and start:**
```bash
docker compose up -d integration-hub hub-db hub-redis hub-celery
```

3. **Run migrations:**
```bash
docker compose exec integration-hub python manage.py migrate
```

4. **Load vendor types:**
```bash
docker compose exec integration-hub python manage.py loaddata vendor_types
```

5. **Create superuser:**
```bash
docker compose exec integration-hub python manage.py createsuperuser
```

6. **Access system:**
```
https://rm.swhgrp.com/hub/
```

## Usage

### Adding a Vendor Connection

1. Navigate to https://rm.swhgrp.com/hub/connections/
2. Click "Add Connection"
3. Select vendor type (US Foods, Sysco, etc.)
4. Enter connection name
5. Choose authentication type
6. Enter API credentials
7. Set sync frequency (hourly, daily, weekly)
8. Test connection
9. Activate

### Running a Manual Sync

1. Go to Connections dashboard
2. Find the vendor connection
3. Click "Sync Now"
4. Select sync type:
   - Product Catalog
   - Pricing Updates
   - Inventory Levels
5. Choose full or incremental sync
6. Monitor progress in Sync Logs

### Viewing Sync Logs

1. Navigate to Sync Logs
2. Filter by:
   - Connection
   - Status (success/failed)
   - Date range
   - Sync type
3. Click log entry for details
4. View:
   - Records processed
   - Errors encountered
   - Execution time
   - Data changes

### Configuring Data Mappings

1. Go to Data Mappings
2. Select vendor connection
3. Add field mapping:
   - Source field (vendor field name)
   - Target field (Inventory field name)
   - Transformation (if needed)
4. Test mapping with sample data
5. Save

### Setting Up Webhooks

1. Navigate to Webhooks
2. Click "Register Webhook"
3. Select vendor
4. Choose event types to subscribe to
5. Generate webhook secret
6. Provide webhook URL to vendor
7. Test webhook delivery

## File Structure

```
integration-hub/
├── src/
│   └── hub/
│       ├── models/              # 5 model files
│       │   ├── vendor_connection.py
│       │   ├── sync_log.py
│       │   ├── webhook.py
│       │   ├── data_mapping.py
│       │   └── api_credential.py
│       ├── api/                 # 2 API files
│       │   ├── connections.py
│       │   └── sync.py
│       ├── services/            # 5 service files
│       │   ├── sync_service.py
│       │   ├── usfood_service.py
│       │   ├── sysco_service.py
│       │   ├── webhook_service.py
│       │   └── mapping_service.py
│       ├── tasks/               # Celery tasks
│       │   ├── sync_tasks.py
│       │   └── webhook_tasks.py
│       ├── templates/           # 7 HTML templates
│       │   ├── connections/
│       │   ├── sync_logs/
│       │   └── webhooks/
│       ├── static/
│       ├── core/
│       ├── main.py
│       └── __init__.py
├── celerybeat-schedule/         # Scheduled tasks
├── Dockerfile
├── requirements.txt
├── .env
└── README.md
```

## Vendor Integrations

### US Foods Integration

**Capabilities:**
- Product catalog download
- Pricing updates
- Order submission
- Order status tracking
- Invoice retrieval

**Authentication:** API Key
**Endpoint:** https://api.usfoods.com/v1/
**Sync Frequency:** Daily
**Data Volume:** ~10,000 products

### Sysco Integration

**Capabilities:**
- Product catalog download
- Real-time pricing
- Order submission
- Delivery tracking
- Account statements

**Authentication:** OAuth2
**Endpoint:** https://api.sysco.com/v2/
**Sync Frequency:** Daily
**Data Volume:** ~15,000 products

### Restaurant Depot Integration

**Capabilities:**
- Product catalog (partial)
- Price lookup
- Basic order history

**Authentication:** Username/Password
**Status:** 70% complete
**Endpoint:** Custom scraping API
**Limitations:** No official API, limited data

## Integration with Other Systems

### Inventory System

**Sends to Inventory:**
- Product catalog data
- SKU numbers
- Product descriptions
- Unit of measure
- Pricing information
- Stock availability
- Vendor item codes

**Receives from Inventory:**
- Purchase order data
- Reorder requests
- Stock count results

### Accounting System

**Sends to Accounting:**
- Vendor invoice data
- Payment status
- Order totals
- Tax information

**Receives from Accounting:**
- Payment confirmations
- Reconciliation data

## Troubleshooting

### Issue: Sync fails with authentication error
**Solution:**
- Check API credentials are valid
- Verify credentials haven't expired
- Test connection manually
- Check vendor API status
- Rotate credentials if needed

### Issue: Sync completes but no data updated
**Solution:**
- Check data mappings are correct
- Verify target system API is accessible
- Review sync log for errors
- Check data format compatibility
- Verify permission to update target system

### Issue: Webhook not receiving events
**Solution:**
- Verify webhook URL is accessible from internet
- Check webhook secret matches
- Verify signature validation
- Check vendor webhook configuration
- Review webhook logs for attempts

### Issue: High sync failure rate
**Solution:**
- Check vendor API rate limits
- Verify network connectivity
- Review error patterns in logs
- Adjust timeout settings
- Implement circuit breaker

## Development

### Running Locally

```bash
cd /opt/restaurant-system/integration-hub
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set up database
python manage.py migrate
python manage.py loaddata vendor_types

# Start Celery worker
celery -A hub worker -l info

# Start Celery beat (scheduler)
celery -A hub beat -l info

# Run server
python manage.py runserver
```

### Adding a New Vendor Integration

1. Create vendor service:
```python
# services/new_vendor_service.py
class NewVendorService:
    def authenticate(self, credentials):
        # Authentication logic
        pass

    def sync_products(self, connection):
        # Sync logic
        pass
```

2. Register vendor type in fixtures
3. Create data mappings
4. Add to supported vendors list
5. Test integration
6. Document in README

### Running Tests

```bash
python manage.py test
```

## Monitoring

### Health Check
```bash
curl https://rm.swhgrp.com/hub/health
```

### Celery Status
```bash
docker compose exec hub-celery celery -A hub inspect active
```

### Sync Monitoring
Dashboard at: https://rm.swhgrp.com/hub/dashboard/

### Logs
```bash
docker compose logs -f integration-hub
docker compose logs -f hub-celery
```

## Dependencies

Key packages (see requirements.txt):
- Django 4.2
- djangorestframework
- celery
- redis
- httpx (async HTTP client)
- cryptography (credential encryption)
- pandas (data processing)
- python-jose (JWT handling)

## Security

**Implemented:**
- Encrypted credential storage
- Webhook signature verification
- API rate limiting
- Request throttling
- HTTPS enforcement
- Audit logging

**Best Practices:**
- Rotate API credentials regularly
- Use separate credentials per environment
- Monitor for unusual API activity
- Implement IP whitelisting where possible
- Regular security audits

## Future Enhancements

### Short-Term
- [ ] Complete webhook retry logic
- [ ] Add more vendor integrations
- [ ] Improve error handling
- [ ] Enhanced monitoring dashboard

### Medium-Term
- [ ] Payment processor integrations
- [ ] POS system integration
- [ ] Real-time event streaming
- [ ] Advanced data validation
- [ ] Bi-directional sync

### Long-Term
- [ ] AI-powered data matching
- [ ] Predictive ordering
- [ ] Cost optimization recommendations
- [ ] Blockchain-based audit trail
- [ ] GraphQL API support

## Support

For issues or questions:
- Check logs: `docker compose logs integration-hub`
- Celery status: `docker compose logs hub-celery`
- Health check: https://rm.swhgrp.com/hub/health
- Vendor API status pages
- Contact: Development Team / Vendor Support

## License

Proprietary - SW Hospitality Group Internal Use Only

# Maintenance Service Architecture

## Overview

The Maintenance Service handles equipment tracking, preventive maintenance scheduling, and work order management across all restaurant locations for SW Hospitality Group.

## Service Details

| Property | Value |
|----------|-------|
| Service Name | maintenance-service |
| Container | maintenance-app |
| Database | maintenance_db |
| DB Container | maintenance-db |
| App Port | 8007 (internal) |
| DB Port | 5438 |
| URL Path | /maintenance |

## Database Schema

### Core Tables

```
┌─────────────────────────┐     ┌─────────────────────────┐
│   equipment_categories  │     │       equipment         │
├─────────────────────────┤     ├─────────────────────────┤
│ id (PK)                 │◄────│ id (PK)                 │
│ name                    │     │ category_id (FK)        │
│ default_pm_interval_days│     │ location_id             │
│ criticality             │     │ name                    │
│ created_at              │     │ manufacturer            │
└─────────────────────────┘     │ model_number            │
                                │ serial_number           │
                                │ barcode (unique)        │
                                │ qr_code_id (unique,uuid)│
                                │ purchase_date           │
                                │ purchase_price          │
                                │ warranty_expiration     │
                                │ expected_lifespan_months│
                                │ status                  │
                                │ condition               │
                                │ notes                   │
                                │ is_active               │
                                │ created_at              │
                                │ updated_at              │
                                └───────────┬─────────────┘
                                            │
        ┌───────────────────────────────────┼───────────────────────────────────┐
        │                                   │                                   │
        ▼                                   ▼                                   ▼
┌───────────────────┐           ┌───────────────────────┐           ┌───────────────────┐
│equipment_documents│           │ maintenance_schedules │           │ equipment_photos  │
├───────────────────┤           ├───────────────────────┤           ├───────────────────┤
│ id (PK)           │           │ id (PK)               │           │ id (PK)           │
│ equipment_id (FK) │           │ equipment_id (FK)     │           │ equipment_id (FK) │
│ document_type     │           │ task_name             │           │ file_id           │
│ title             │           │ description           │           │ photo_type        │
│ file_id           │           │ frequency_type        │           │ caption           │
│ expiration_date   │           │ frequency_value       │           │ is_primary        │
│ notes             │           │ last_completed_at     │           │ uploaded_by       │
│ uploaded_at       │           │ next_due_at           │           │ uploaded_at       │
└───────────────────┘           │ assigned_role         │           └───────────────────┘
                                │ estimated_duration    │
                                │ is_active             │
                                └───────────┬───────────┘
                                            │
                                            ▼
                                ┌───────────────────────┐
                                │     work_orders       │
                                ├───────────────────────┤
                                │ id (PK)               │
                                │ equipment_id (FK)     │
                                │ schedule_id (FK, opt) │
                                │ location_id           │
                                │ type                  │
                                │ priority              │
                                │ status                │
                                │ title                 │
                                │ description           │
                                │ reported_by           │
                                │ assigned_to           │
                                │ vendor_id             │
                                │ scheduled_date        │
                                │ started_at            │
                                │ completed_at          │
                                │ resolution_notes      │
                                │ downtime_hours        │
                                │ created_at            │
                                │ updated_at            │
                                └───────────┬───────────┘
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    │                                               │
                    ▼                                               ▼
        ┌───────────────────────┐                       ┌───────────────────────┐
        │   work_order_costs    │                       │  work_order_photos    │
        ├───────────────────────┤                       ├───────────────────────┤
        │ id (PK)               │                       │ id (PK)               │
        │ work_order_id (FK)    │                       │ work_order_id (FK)    │
        │ cost_type             │                       │ file_id               │
        │ description           │                       │ photo_type            │
        │ amount                │                       │ caption               │
        │ invoice_id            │                       │ uploaded_by           │
        │ created_at            │                       │ uploaded_at           │
        └───────────────────────┘                       └───────────────────────┘
```

### Supporting Tables

```
┌───────────────────────┐       ┌───────────────────────┐
│  equipment_vendors    │       │   equipment_history   │
├───────────────────────┤       ├───────────────────────┤
│ id (PK)               │       │ id (PK)               │
│ vendor_id (unique)    │       │ equipment_id (FK)     │
│ service_types[]       │       │ field_changed         │
│ contract_type         │       │ old_value             │
│ contract_expiration   │       │ new_value             │
│ response_time_hours   │       │ changed_by            │
│ notes                 │       │ changed_at            │
│ created_at            │       └───────────────────────┘
│ updated_at            │
└───────────────────────┘
```

## Enums / Constants

### Equipment Status
- `active` - In use
- `out_of_service` - Temporarily unavailable
- `pending_disposal` - Awaiting disposal
- `retired` - No longer in use

### Equipment Condition
- `excellent`
- `good`
- `fair`
- `poor`

### Work Order Type
- `preventive` - Scheduled PM
- `corrective` - Fix something broken
- `emergency` - Urgent repair
- `inspection` - Routine check

### Work Order Priority
- `critical` - Immediate attention
- `high` - Within 24 hours
- `medium` - Within 1 week
- `low` - When convenient

### Work Order Status
- `open` - Newly created
- `in_progress` - Being worked on
- `awaiting_parts` - Waiting for parts
- `completed` - Done
- `cancelled` - Cancelled

### Cost Type
- `parts` - Replacement parts
- `labor` - Labor costs
- `vendor_service` - External vendor
- `other` - Miscellaneous

### Document Type
- `manual` - User manual
- `warranty` - Warranty document
- `lease` - Lease agreement
- `service_contract` - Service contract
- `spec_sheet` - Specification sheet
- `invoice` - Purchase invoice
- `other` - Other

### Photo Type (Equipment)
- `primary` - Main display photo
- `condition` - Current condition
- `nameplate` - Model/serial plate
- `installation` - Installation photo
- `other` - Other

### Photo Type (Work Order)
- `before` - Before repair
- `after` - After repair
- `issue` - Problem documentation
- `parts` - Parts photo

### Equipment Category Criticality
- `critical` - Essential for operations
- `important` - Significant impact if down
- `standard` - Normal priority

### Vendor Service Types
- `hvac`
- `refrigeration`
- `plumbing`
- `electrical`
- `general`
- `pos_tech`
- `fire_safety`

## Cross-Service Integration

### Inventory Service (locations)
- Validate location_id exists
- Get location name for display
- Base URL: `http://inventory-app:8000`

### HR Service (employees)
- Validate employee IDs (reported_by, assigned_to)
- Get employee names for display
- Base URL: `http://hr-app:8000`

### Integration Hub (vendors)
- Validate vendor_id exists
- Get vendor details
- Link costs to invoices
- Base URL: `http://integration-hub:8000`

### Files Service (documents/photos)
- Upload files, get file_id
- Generate download URLs
- Base URL: `http://files-app:8000`

## API Structure

```
/maintenance
├── /categories          # Equipment categories
├── /equipment           # Equipment management
│   ├── /{id}/documents  # Equipment documents
│   ├── /{id}/photos     # Equipment photos
│   ├── /{id}/history    # Change history
│   ├── /{id}/qr-code    # QR code image
│   └── /lookup          # Barcode/QR lookup
├── /schedules           # PM schedules
├── /work-orders         # Work order management
│   ├── /{id}/costs      # Work order costs
│   └── /{id}/photos     # Work order photos
├── /equipment-vendors   # Vendor service capabilities
├── /reports             # Reporting endpoints
├── /dashboard           # Dashboard data
└── /health              # Health check
```

## Work Order Flow

```
                    ┌──────────────┐
                    │  OPEN        │ (New work order created)
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
          ┌────────│ IN_PROGRESS  │────────┐
          │        └──────┬───────┘        │
          │               │                │
          ▼               ▼                ▼
    ┌───────────┐   ┌───────────┐   ┌───────────┐
    │ COMPLETED │   │AWAITING   │   │ CANCELLED │
    └───────────┘   │  PARTS    │   └───────────┘
                    └─────┬─────┘
                          │
                          ▼
                    ┌──────────────┐
                    │ IN_PROGRESS  │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  COMPLETED   │
                    └──────────────┘
```

## PM Schedule Flow

```
┌─────────────────────────────────────────────────────────┐
│                   Daily Background Task                  │
├─────────────────────────────────────────────────────────┤
│ 1. Query all active schedules                           │
│ 2. Find schedules where next_due_at <= today + 7 days   │
│ 3. For each due schedule:                               │
│    a. Check if open work order exists for schedule      │
│    b. If not, create work order (type=preventive)       │
│ 4. When work order completed:                           │
│    a. Update schedule.last_completed_at                 │
│    b. Calculate new next_due_at based on frequency      │
└─────────────────────────────────────────────────────────┘
```

## QR Code System

Each equipment record has:
- `barcode` - Optional field for existing barcodes (manually entered)
- `qr_code_id` - Auto-generated UUID for system QR codes

QR codes encode URL: `https://rm.swhgrp.com/maintenance/equipment/qr/{qr_code_id}`

When scanned:
1. Mobile browser opens URL
2. Portal redirects to equipment detail page
3. User can view details, report issues, etc.

## Default Categories (Seed Data)

| Name | Default PM Interval | Criticality |
|------|---------------------|-------------|
| Refrigeration | 90 days | critical |
| Cooking | 30 days | critical |
| HVAC | 90 days | important |
| Plumbing | 180 days | important |
| POS/Tech | 90 days | critical |
| Furniture | 365 days | standard |
| Safety | 30 days | critical |
| Other | NULL | standard |

## File Structure

```
/maintenance
├── src/
│   └── maintenance/
│       ├── __init__.py
│       ├── main.py              # FastAPI app
│       ├── config.py            # Configuration
│       ├── database.py          # DB connection
│       ├── models/              # SQLAlchemy models
│       │   ├── __init__.py
│       │   ├── category.py
│       │   ├── equipment.py
│       │   ├── document.py
│       │   ├── photo.py
│       │   ├── schedule.py
│       │   ├── work_order.py
│       │   ├── work_order_cost.py
│       │   ├── work_order_photo.py
│       │   ├── equipment_vendor.py
│       │   └── equipment_history.py
│       ├── schemas/             # Pydantic schemas
│       │   └── ...
│       ├── routers/             # API routes
│       │   └── ...
│       ├── services/            # Business logic
│       │   ├── equipment_service.py
│       │   ├── schedule_service.py
│       │   ├── work_order_service.py
│       │   ├── report_service.py
│       │   └── external/        # Service clients
│       │       ├── files_client.py
│       │       ├── inventory_client.py
│       │       ├── hr_client.py
│       │       └── hub_client.py
│       └── utils/
│           ├── qr_generator.py
│           └── date_helpers.py
├── alembic/
│   ├── versions/
│   └── env.py
├── tests/
├── docs/
│   └── ARCHITECTURE.md
├── TODO.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
└── README.md
```

# Events Module Documentation

**Last Updated:** December 2, 2025
**Module Status:** Production
**Endpoint:** https://rm.swhgrp.com/events/

---

## Overview

The Events module manages catering and banquet event bookings for SW Hospitality Group venues. It provides full event lifecycle management from initial inquiry through post-event billing.

## Key Features

### Event Management
- Event creation and editing with full details
- Status workflow: DRAFT → PENDING → CONFIRMED → CLOSED/CANCELED
- Multi-venue support (The Links Grill, SW Grill, Seaside Grill, etc.)
- Client management with contact information
- Guest count tracking

### Menu & Catering
- Package-based pricing with customization
- Custom menu item entry with pricing
- Menu sections (Appetizers, Main Course, Desserts, Beverages)
- Service style selection (Plated, Buffet, Family Style, etc.)
- Bar/beverage service configuration
- Dietary accommodations tracking

### Financials
- Automatic pricing calculation from packages and menu items
- Configurable service charge (default 21%)
- Configurable tax rate (default 7%)
- Toggle service charge/tax for non-profit events
- Deposit tracking and payment recording
- Balance due calculations

### Documents
- **BEO (Banquet Event Order)** - PDF generation for internal use
- Document storage and management
- Email templates for client communication

### Calendar Integration
- CalDAV sync for external calendar apps
- Per-venue calendar feeds
- Status-based color coding on calendar view

---

## BEO (Banquet Event Order) Template

### Current Design (Dec 2025)
One-sheet, two-column industry-standard format optimized for print.

**Header:**
- "BANQUET EVENT ORDER" title
- Venue/location name
- BEO reference number and generation date

**Left Column:**
1. **EVENT INFORMATION**
   - Event Name, Client, Organization
   - Event Date, Time (start - end)
   - Expected Guests (highlighted)
   - Event Type, Status
   - Contact Phone, Email

2. **ROOM & SETUP**
   - Room/Venue
   - Setup Style
   - Tables Needed, Head Table
   - Dance Floor, AV Needs, Decor
   - Setup Time

3. **TIMELINE**
   - Auto-generated from event times, or
   - Custom timeline entries from `requirements_json.timeline`

4. **STAFFING**
   - Banquet Captain, Servers, Bartenders
   - Culinary Staff, Bussers
   - Shows "TBD" if not specified

**Right Column:**
1. **FOOD SERVICE**
   - Service Style, Service Time
   - Menu items organized by section/course
   - Dietary notes

2. **BEVERAGE SERVICE**
   - Bar Type, Bar Hours
   - Signature Cocktails
   - Beverage details

3. **RENTALS / EQUIPMENT**
   - Equipment and rental information

4. **FINANCIAL SUMMARY** (only shows if amounts > 0)
   - Subtotal, Service Charge, Tax, Total
   - Payments made, Balance Due

**Footer:**
- Special Notes / Instructions box
- Generation timestamp, "Internal Use Only"

### Data Sources for BEO

| BEO Section | Database Field |
|-------------|----------------|
| Event Info | `events` table core fields |
| Room & Setup | `events.requirements_json` |
| Timeline | `events.requirements_json.timeline[]` or auto-generated |
| Staffing | `events.requirements_json.staffing` |
| Food Service | `events.menu_json.sections[]` |
| Beverage | `events.menu_json.bar_type`, `bar_hours`, etc. |
| Financials | `events.financials_json` |
| Notes | `events.description`, `requirements_json.special_notes` |

### requirements_json Structure

```json
{
  "setup_style": "Banquet Rounds",
  "tables_needed": "10 rounds of 8",
  "head_table": "Yes - 8 persons",
  "dance_floor": "15x15 in center",
  "av_equipment": "Microphone, projector, screen",
  "decorations": "Client providing centerpieces",
  "rentals": "Additional linens from rental company",
  "equipment": "Chafing dishes, coffee urns",
  "special_notes": "Client allergic to shellfish",
  "timeline": [
    {"time": "4:00 PM", "description": "Staff arrival and setup"},
    {"time": "5:00 PM", "description": "Bar opens"},
    {"time": "6:00 PM", "description": "Guests arrive"},
    {"time": "7:00 PM", "description": "Dinner service"},
    {"time": "9:00 PM", "description": "Event ends"}
  ],
  "staffing": {
    "banquet_captain": "1",
    "servers": "4",
    "bartenders": "2",
    "culinary": "2",
    "busser": "1"
  }
}
```

### menu_json Structure

```json
{
  "service_style": "plated",
  "service_time": "7:00 PM",
  "bar_type": "open_bar",
  "bar_hours": "5:00 PM - 9:00 PM",
  "signature_cocktail": "Venue Sunset Spritz",
  "beverage_details": "Premium liquors, house wines",
  "dietary": ["vegetarian", "gluten_free"],
  "special_requests": "Birthday cake service at 8:30 PM",
  "equipment": "Additional plates for dessert",
  "sections": [
    {
      "name": "Appetizers",
      "type": "appetizer",
      "items": [
        {"name": "Bruschetta", "price": 12.00, "description": "Tomato basil"},
        {"name": "Shrimp Cocktail", "price": 18.00, "quantity": 2}
      ]
    },
    {
      "name": "Main Course",
      "type": "entree",
      "items": [
        {"name": "Filet Mignon", "price": 45.00},
        {"name": "Grilled Salmon", "price": 38.00}
      ]
    }
  ]
}
```

### financials_json Structure

```json
{
  "subtotal": 2500.00,
  "service_rate": 0.21,
  "service_charge": 525.00,
  "apply_service_charge": true,
  "tax_rate": 0.07,
  "tax": 211.75,
  "apply_tax": true,
  "total": 3236.75,
  "deposit_required": 1000.00,
  "payments": [
    {"date": "2025-11-15", "amount": 1000.00, "method": "check", "reference": "Check #1234"}
  ]
}
```

---

## API Endpoints

### Events
- `GET /api/events/` - List events (with filters)
- `GET /api/events/{id}` - Get event details
- `POST /api/events/` - Create event
- `PUT /api/events/{id}` - Update event
- `DELETE /api/events/{id}` - Delete event

### Documents
- `GET /api/documents/events/{event_id}/beo-pdf` - Generate BEO PDF
- `GET /api/documents/events/{event_id}` - List event documents
- `POST /api/documents/events/{event_id}/upload` - Upload document

### Calendar
- `GET /api/calendar/caldav/{venue}` - CalDAV feed for venue
- `GET /api/calendar/events` - Events for calendar view

### Clients
- `GET /api/clients/` - List clients
- `POST /api/clients/` - Create client

---

## Database Models

### Event Model
```python
class Event(BaseModel):
    __tablename__ = "events"

    title = Column(String(255), nullable=False)
    event_type = Column(String(100), nullable=False)
    status = Column(SQLEnum(EventStatus), default=EventStatus.DRAFT)

    venue_id = Column(UUID, ForeignKey('venues.id'))
    client_id = Column(UUID, ForeignKey('clients.id'), nullable=False)
    package_id = Column(UUID, ForeignKey('event_packages.id'))

    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    setup_start_at = Column(DateTime(timezone=True))
    teardown_end_at = Column(DateTime(timezone=True))

    guest_count = Column(Integer)
    location = Column(String(255))  # Location name from settings
    description = Column(Text)

    menu_json = Column(JSONB)
    requirements_json = Column(JSONB)
    financials_json = Column(JSONB)
```

### EventStatus Enum
```python
class EventStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CLOSED = "CLOSED"
    CANCELED = "CANCELED"
```

---

## Technical Notes

### PDF Generation
- Uses **WeasyPrint 60.2** for HTML-to-PDF conversion
- Requires `pydyf<0.10` due to compatibility issue with newer versions
- Templates use Jinja2 with special handling for dict access (`section['items']` not `section.items`)

### Known Issues & Solutions

1. **WeasyPrint pydyf Error**
   - Error: `PDF.__init__() takes 1 positional argument but 3 were given`
   - Solution: Pin `pydyf<0.10` in requirements.txt

2. **Jinja2 Dict Access**
   - Error: `'builtin_function_or_method' object is not iterable`
   - Cause: `section.items` conflicts with dict.items() method
   - Solution: Use `section['items']` bracket notation

3. **Enum in Templates**
   - Use: `event.status.value if event.status.value else event.status`
   - This handles both enum objects and string values

4. **Financial Summary Display**
   - Only show when `subtotal > 0 || total > 0`
   - Prevents showing $0.00 summaries

---

## File Structure

```
events/
├── src/events/
│   ├── main.py                 # FastAPI app entry
│   ├── api/
│   │   ├── events.py           # Event CRUD endpoints
│   │   ├── documents.py        # BEO PDF generation
│   │   ├── calendar.py         # CalDAV endpoints
│   │   ├── clients.py          # Client management
│   │   └── emails.py           # Email endpoints
│   ├── models/
│   │   ├── event.py            # Event, EventPackage models
│   │   ├── client.py           # Client model
│   │   ├── document.py         # Document model
│   │   └── venue.py            # Venue model
│   ├── schemas/                # Pydantic schemas
│   ├── templates/
│   │   ├── admin/              # Web UI templates
│   │   │   ├── event_detail.html
│   │   │   ├── calendar.html
│   │   │   └── ...
│   │   ├── pdf/
│   │   │   └── beo_template.html  # BEO PDF template
│   │   └── emails/             # Email templates
│   └── static/                 # CSS, JS assets
├── requirements.txt
└── Dockerfile
```

---

## Related Documentation

- [CalDAV Calendar Sync](./events-caldav-calendar-sync.md)
- [claude.md](../claude.md) - Session notes and recent changes

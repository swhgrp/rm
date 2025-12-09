# Website Management System

## Overview

The Website Management System is a FastAPI-based application for managing restaurant website content. It provides a comprehensive admin interface for managing multiple restaurant websites, including menus, pages, hours, images, and form submissions.

## Status: Production Ready ✅

## Purpose

- Multi-site website content management
- Menu and menu item management with categories
- Page builder with customizable blocks
- Business hours and special hours management
- Image gallery management
- Contact form submission handling
- Activity logging and audit trail

## Technology Stack

- **Framework:** FastAPI (Python 3.11)
- **Database:** PostgreSQL 15
- **ORM:** SQLAlchemy 2.0
- **Frontend:** Bootstrap 5, HTMX, Jinja2 templates
- **Authentication:** Portal SSO via JWT tokens
- **Image Processing:** Pillow

## Features

### ✅ IMPLEMENTED

**Site Management:**
- ✅ Multi-site support with site switcher
- ✅ Site settings (name, domain, theme, colors)
- ✅ Site-specific configurations
- ✅ Activity logging per site

**Menu Management:**
- ✅ Multiple menus per site (Lunch, Dinner, etc.)
- ✅ Menu categories with sorting
- ✅ Menu items with prices, descriptions, images
- ✅ Item availability toggles
- ✅ Dietary flags (vegetarian, gluten-free, etc.)
- ✅ Drag-and-drop reordering

**Page Management:**
- ✅ Custom pages with URL slugs
- ✅ Page blocks (hero, text, gallery, hours, menu preview, etc.)
- ✅ Block reordering and visibility controls
- ✅ Rich text content editing

**Hours Management:**
- ✅ Regular business hours by day of week
- ✅ Special hours (holidays, events)
- ✅ Open/closed status per day

**Image Management:**
- ✅ Image uploads with automatic resizing
- ✅ Gallery organization
- ✅ Alt text support

**Form Submissions:**
- ✅ Contact form submission storage
- ✅ Read/unread status tracking
- ✅ Form data viewing

**Activity Logging:**
- ✅ All actions logged with user, timestamp, entity
- ✅ Activity feed per site

### ❌ NOT IMPLEMENTED

- ❌ Static site generation (stub endpoints exist)
- ❌ Email notifications for form submissions
- ❌ Custom themes beyond color settings
- ❌ SEO meta tag management
- ❌ Sitemap generation
- ❌ Analytics integration

## Architecture

### Database Schema

**Implemented Tables:**
- `sites` - Website configurations
- `menus` - Menu definitions
- `menu_categories` - Menu category groupings
- `menu_items` - Individual menu items
- `hours` - Regular business hours
- `special_hours` - Special/holiday hours
- `pages` - Website pages
- `page_blocks` - Page content blocks
- `images` - Uploaded images
- `form_submissions` - Contact form entries
- `activity_logs` - User activity audit trail

### Models

**Implemented SQLAlchemy Models:**
- `Site` - Website configuration
- `Menu` - Menu container
- `MenuCategory` - Category within a menu
- `MenuItem` - Individual item with price
- `Hours` - Day-of-week hours
- `SpecialHours` - Date-specific hours
- `Page` - Website page
- `PageBlock` - Content block within page
- `Image` - Uploaded image metadata
- `FormSubmission` - Contact form data
- `ActivityLog` - Audit trail entries

## API Endpoints

### Site Management

- `GET /` - Admin dashboard
- `GET /sites/{site_id}` - Site detail view
- `POST /api/sites` - Create new site
- `PUT /api/sites/{site_id}` - Update site
- `DELETE /api/sites/{site_id}` - Delete site

### Menu Management

- `GET /sites/{site_id}/menus` - List menus
- `POST /api/sites/{site_id}/menus` - Create menu
- `PUT /api/menus/{menu_id}` - Update menu
- `DELETE /api/menus/{menu_id}` - Delete menu
- `POST /api/menus/{menu_id}/categories` - Add category
- `POST /api/categories/{category_id}/items` - Add item

### Page Management

- `GET /sites/{site_id}/pages` - List pages
- `POST /api/sites/{site_id}/pages` - Create page
- `PUT /api/pages/{page_id}` - Update page
- `POST /api/pages/{page_id}/blocks` - Add block
- `PUT /api/blocks/{block_id}` - Update block
- `POST /api/pages/{page_id}/blocks/reorder` - Reorder blocks

### Hours Management

- `GET /sites/{site_id}/hours` - View hours
- `PUT /api/sites/{site_id}/hours` - Update hours
- `POST /api/sites/{site_id}/special-hours` - Add special hours

### Image Management

- `GET /sites/{site_id}/images` - Image gallery
- `POST /api/sites/{site_id}/images` - Upload image
- `DELETE /api/images/{image_id}` - Delete image

### Form Submissions

- `GET /sites/{site_id}/submissions` - View submissions
- `PATCH /api/submissions/{id}/read` - Mark as read

## Configuration

### Environment Variables (.env)

```bash
# Database
DATABASE_URL=postgresql://websites_user:password@websites-db:5432/websites_db

# Security
SECRET_KEY=your-secret-key
PORTAL_SSO_SECRET=shared-sso-secret

# File Storage
UPLOAD_DIR=/app/uploads

# Debug
DEBUG=False
```

## Installation & Setup

### Prerequisites
- Docker and Docker Compose
- PostgreSQL 15

### Quick Start

1. **Set up environment:**
```bash
cd /opt/restaurant-system/websites
cp .env.example .env
# Edit .env with your configuration
```

2. **Build and start:**
```bash
docker compose up -d websites-app websites-db
```

3. **Access system:**
```
https://rm.swhgrp.com/websites/
```

## File Structure

```
websites/
├── src/
│   └── websites/
│       ├── main.py              # FastAPI application
│       ├── database.py          # SQLAlchemy setup
│       ├── models.py            # Database models
│       ├── schemas.py           # Pydantic schemas
│       ├── auth.py              # SSO authentication
│       ├── config.py            # Settings
│       ├── templates/           # Jinja2 templates
│       │   ├── base.html
│       │   ├── dashboard.html
│       │   ├── site_*.html
│       │   └── partials/        # HTMX partials
│       └── static/              # CSS, JS files
├── uploads/                     # Uploaded images
├── generated/                   # Generated static sites (future)
├── alembic/                     # Database migrations
├── Dockerfile
├── requirements.txt
├── .env
└── README.md
```

## Integration with Other Systems

### Portal Integration

- SSO authentication via JWT tokens
- Users authenticated through Portal
- Session cookie `portal_token` for auth state

### Menu Preview

- Websites can display menu data from the Menu system
- Menu blocks pull current menu items

## Development

### Running Locally

```bash
cd /opt/restaurant-system/websites

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=postgresql://...
export SECRET_KEY=your-secret

# Run development server
uvicorn websites.main:app --reload --host 0.0.0.0 --port 8000
```

## Monitoring

### Health Check
```bash
curl https://rm.swhgrp.com/websites/health
```

### Logs
```bash
docker compose logs -f websites-app
```

## Dependencies

Key packages:
- FastAPI
- SQLAlchemy 2.0
- psycopg2-binary
- python-jose (JWT)
- pydantic / pydantic-settings
- jinja2
- python-multipart (file uploads)
- pillow (image processing)
- uvicorn (ASGI server)

## Security

**Authentication & Authorization:**
- Portal SSO integration via JWT tokens
- Secure session cookies (HttpOnly, Secure)
- All admin actions require authentication

**Application Security:**
- SQL injection prevention (SQLAlchemy ORM)
- XSS protection (Jinja2 auto-escaping)
- File upload validation
- Input validation via Pydantic

## Known Issues

1. **Site generation not implemented** - The "Generate Site" feature is stubbed out
2. **Special hours endpoint missing** - Create endpoint exists but update doesn't
3. **Unused imports** - Some schema classes imported but not used

## Future Enhancements

- [ ] Static site generation to HTML files
- [ ] Email notifications for form submissions
- [ ] SEO meta tag management per page
- [ ] Sitemap.xml generation
- [ ] Custom CSS/theme editing
- [ ] Image optimization pipeline
- [ ] Preview mode for unpublished changes
- [ ] Version history for content changes

## Support

For issues or questions:
- Check logs: `docker compose logs websites-app`
- Health check: https://rm.swhgrp.com/websites/health
- Contact: Development Team

## License

Proprietary - SW Hospitality Group Internal Use Only

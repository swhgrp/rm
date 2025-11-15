# CalDAV Setup Guide for Events System

This guide explains how to set up CalDAV synchronization for the Events system, allowing users to sync their assigned events to their phones, Outlook, Apple Calendar, and other CalDAV-compatible clients.

## Overview

The CalDAV integration allows:
- **Automatic sync** of events to users' calendar apps
- **Read-only access** to events based on assigned locations/venues
- **Real-time updates** when events are created, updated, or canceled
- **Cross-platform support** (iOS, Android, macOS, Windows, Linux)

## Architecture

```
Events Database → CalDAV Sync Service → Radicale CalDAV Server → User Devices
```

## Option 1: Radicale (Recommended)

### Step 1: Add CalDAV Service to Docker Compose

Add this to `/opt/restaurant-system/docker-compose.yml` after the events-app service:

```yaml
  caldav:
    build: ./caldav
    container_name: caldav
    volumes:
      - caldav_data:/data/collections
    environment:
      - TZ=America/New_York
    restart: unless-stopped
    networks:
      - restaurant-network
```

And add the volume at the bottom:

```yaml
volumes:
  caldav_data:
```

### Step 2: Update Events .env

Add to `/opt/restaurant-system/events/.env`:

```bash
# CalDAV Configuration
CALDAV_URL=http://caldav:5232
CALDAV_ENABLED=true
```

### Step 3: Install CalDAV Python Dependencies

Add to `/opt/restaurant-system/events/requirements.txt`:

```
caldav==1.3.9
icalendar==5.0.11
```

### Step 4: Configure Nginx for CalDAV

Add to `/opt/restaurant-system/shared/nginx/conf.d/rm.swhgrp.com-http.conf`:

```nginx
# CalDAV endpoint
location /caldav/ {
    proxy_pass http://caldav:5232/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Remote-User $http_x_forwarded_user;

    # CalDAV-specific headers
    proxy_set_header Depth $http_depth;
    proxy_set_header Destination $http_destination;
    proxy_pass_header Authorization;

    # Disable buffering for CalDAV
    proxy_buffering off;
    proxy_request_buffering off;
}
```

### Step 5: Add Automatic Sync Hooks

Update `/opt/restaurant-system/events/src/events/api/events.py` to trigger CalDAV sync:

```python
from events.services.caldav_sync_service import CalDAVSyncService
from events.core.config import settings

# After event creation/update
if settings.CALDAV_ENABLED:
    caldav_service = CalDAVSyncService()
    # Sync to all users with access to this event's venue
    from events.models.user import UserLocation
    user_ids = db.query(UserLocation.user_id).filter(
        UserLocation.venue_id == event.venue_id
    ).all()

    for user_id_tuple in user_ids:
        user = db.query(User).filter(User.id == user_id_tuple[0]).first()
        if user:
            try:
                caldav_service.sync_event_to_caldav(event, user.email)
            except Exception as e:
                logger.error(f"CalDAV sync failed for {user.email}: {e}")
```

### Step 6: Start the Services

```bash
cd /opt/restaurant-system
docker compose up caldav -d
docker compose restart events-app nginx-proxy
```

## Connecting Devices

### iOS (iPhone/iPad)

1. Go to **Settings → Calendar → Accounts → Add Account**
2. Tap **Other → Add CalDAV Account**
3. Enter:
   - **Server**: `rm.swhgrp.com/caldav`
   - **User Name**: Your email (e.g., `andy@swhgrp.com`)
   - **Password**: Your portal password
   - **Description**: SW Hospitality Events
4. Tap **Next** and enable **Calendars**

### Android

1. Install **DAVx⁵** from Google Play Store (free, open source)
2. Open DAVx⁵ and tap **+** to add account
3. Select **Login with URL and username**
4. Enter:
   - **Base URL**: `https://rm.swhgrp.com/caldav`
   - **User name**: Your email
   - **Password**: Your portal password
5. Tap **Login** and select the calendars to sync

### macOS Calendar

1. Open **Calendar** app
2. Go to **Calendar → Add Account**
3. Select **Other CalDAV Account**
4. Enter:
   - **Account Type**: Advanced
   - **User Name**: Your email
   - **Password**: Your portal password
   - **Server Address**: `rm.swhgrp.com`
   - **Server Path**: `/caldav/{your-email}/events/`
   - **Port**: 443
   - **Use SSL**: Yes
5. Click **Sign In**

### Microsoft Outlook

1. Go to **File → Account Settings → Account Settings**
2. Click **New → Manual setup**
3. Select **Internet Calendar (iCalendar) Subscription**
4. Enter URL: `https://rm.swhgrp.com/caldav/{your-email}/events/`
5. Enter your credentials when prompted

### Thunderbird

1. Install **TbSync** and **Provider for CalDAV & CardDAV** add-ons
2. Go to **Tools → Synchronization Settings (TbSync)**
3. Click **Account Actions → Add CalDAV & CardDAV account**
4. Choose **Automatic configuration**
5. Enter:
   - **Server**: `https://rm.swhgrp.com/caldav`
   - **User**: Your email
   - **Password**: Your portal password

## Option 2: Baikal (Alternative)

If you prefer a web UI for CalDAV management:

```yaml
  caldav:
    image: ckulka/baikal:latest
    container_name: caldav
    volumes:
      - caldav_data:/var/www/baikal/Specific
    environment:
      - BAIKAL_SERVERNAME=rm.swhgrp.com
    restart: unless-stopped
    networks:
      - restaurant-network
```

Access Baikal admin at: `https://rm.swhgrp.com/caldav/admin`

## Manual Sync Script

To manually sync all events for all users:

```bash
docker exec events-app python3 << 'PYEOF'
from events.core.database import SessionLocal
from events.services.caldav_sync_service import CalDAVSyncService
from events.models import User

db = SessionLocal()
caldav_service = CalDAVSyncService()

users = db.query(User).filter(User.is_active == True).all()

for user in users:
    print(f"Syncing events for {user.email}...")
    try:
        caldav_service.sync_all_events_for_user(db, user)
        print(f"✓ Synced for {user.email}")
    except Exception as e:
        print(f"✗ Failed for {user.email}: {e}")

db.close()
PYEOF
```

## Automatic Sync via Cron

Add to server crontab to sync every 15 minutes:

```bash
*/15 * * * * docker exec events-app python3 /app/src/events/scripts/caldav_sync.py
```

Create `/opt/restaurant-system/events/src/events/scripts/caldav_sync.py`:

```python
#!/usr/bin/env python3
"""Sync all events to CalDAV"""
import sys
sys.path.insert(0, '/app/src')

from events.core.database import SessionLocal
from events.services.caldav_sync_service import CalDAVSyncService
from events.models import User
from events.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not settings.CALDAV_ENABLED:
    logger.info("CalDAV sync disabled, exiting")
    sys.exit(0)

db = SessionLocal()
caldav_service = CalDAVSyncService()

try:
    users = db.query(User).filter(User.is_active == True).all()

    for user in users:
        try:
            caldav_service.sync_all_events_for_user(db, user)
        except Exception as e:
            logger.error(f"Failed to sync for {user.email}: {e}")

    logger.info(f"CalDAV sync completed for {len(users)} users")
finally:
    db.close()
```

## Troubleshooting

### Events Not Syncing

1. Check CalDAV service is running:
   ```bash
   docker ps | grep caldav
   docker logs caldav
   ```

2. Verify settings:
   ```bash
   docker exec events-app python3 -c "from events.core.config import settings; print(f'CalDAV Enabled: {settings.CALDAV_ENABLED}, URL: {settings.CALDAV_URL}')"
   ```

3. Test manual sync:
   ```bash
   docker exec events-app python3 /app/src/events/scripts/caldav_sync.py
   ```

### Connection Issues

1. Verify nginx proxy configuration:
   ```bash
   docker exec nginx-proxy nginx -t
   docker exec nginx-proxy nginx -s reload
   ```

2. Check CalDAV endpoint is accessible:
   ```bash
   curl -I https://rm.swhgrp.com/caldav/
   ```

### Authentication Problems

CalDAV uses the same Portal SSO credentials. Ensure:
- User account is active in Portal
- User has assigned venues/locations
- Portal session is valid

## Security Notes

- CalDAV traffic goes through nginx SSL
- Users can only access events for their assigned locations
- Read-only access (users cannot modify events via CalDAV)
- All changes must be made through Events UI

## Performance

- Initial sync may take 30-60 seconds for users with many events
- Incremental syncs are fast (< 1 second per event)
- CalDAV clients typically cache data locally
- Recommended sync interval: 15 minutes

## Future Enhancements

- [ ] Two-way sync (allow event updates from calendar apps)
- [ ] Task synchronization
- [ ] Shared calendars per venue/location
- [ ] Calendar subscriptions (webcal:// URLs)
- [ ] Email invitations with .ics attachments

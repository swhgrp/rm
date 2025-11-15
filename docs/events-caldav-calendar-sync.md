# Events Calendar Synchronization (CalDAV)

**Status:** ✅ Production Ready
**Last Updated:** November 14, 2025
**Module:** Events Management System

## Overview

The Events system includes full CalDAV calendar synchronization, allowing events to automatically sync to iPhones, Android devices, and desktop calendar applications. Events are organized into separate calendars by venue for easy color-coding and filtering.

## Features

### 1. CalDAV Server (Radicale)
- **Server:** Radicale 3.5.8 running in Docker
- **URL:** `https://rm.swhgrp.com/caldav/`
- **Authentication:** Nginx HTTP Basic Auth (trusted X-Remote-User header)
- **Storage:** Persistent Docker volume at `/opt/restaurant-system/caldav/data`

### 2. Venue-Based Calendar Organization
Events are automatically organized into separate calendars by venue:
- `the-links-grill` → The Links Grill
- `sw-grill` → SW Grill
- `seaside-grill` → Seaside Grill
- `park-bistro` → Park Bistro
- `okee-grill` → Okee Grill
- `the-nest-eatery` → The Nest Eatery
- `unassigned` → Unassigned Events

**Benefits:**
- Color-code each venue differently in iOS/Android calendar apps
- Filter calendars by venue
- Toggle venue visibility on/off

### 3. Automatic Synchronization
Events automatically sync to CalDAV when:
- ✅ New event is created (via admin or public intake form)
- ✅ Event is updated (title, time, venue, client, guest count, etc.)
- ✅ Event is marked CANCELED or CLOSED (automatically removed from CalDAV)

**Sync Direction:** One-way (Events DB → CalDAV → Devices)
- Events created/edited in the Events system sync to phones
- Changes made on phones do NOT sync back to the Events system
- To delete an event, mark it as CANCELED in the Events system

### 4. Event Information Synced
Each calendar event includes:
- **Summary:** Event title
- **Start/End Time:** Event schedule
- **Location:** Venue name
- **Description:** Includes:
  - Event description
  - Guest count
  - Client name and email
- **UID:** Unique identifier (`{event_id}@swhgrp.com`)

## iOS/iPhone Setup

1. Open **Settings** → **Calendar** → **Accounts**
2. Tap **Add Account** → **Other** → **Add CalDAV Account**
3. Enter the following:
   - **Server:** `rm.swhgrp.com`
   - **User Name:** Your portal username (e.g., `andy`)
   - **Password:** Your portal password
   - **Description:** SW Hospitality Events
4. Tap **Next** → **Save**
5. Events will appear in your Calendar app within seconds

**Color Coding:**
- Go to **Settings** → **Calendar** → **Calendars**
- Tap on each venue calendar (The Links Grill, SW Grill, etc.)
- Tap the color circle to choose a custom color

## Android Setup

1. Open **Settings** → **Accounts** → **Add Account**
2. Select **CalDAV** (or use DAVx⁵ app from Google Play)
3. Enter:
   - **Server:** `https://rm.swhgrp.com/caldav/`
   - **Username:** Your portal username
   - **Password:** Your portal password
4. Select which calendars to sync
5. Open Google Calendar app to view events

## Desktop Calendar Setup

### macOS Calendar
1. Open **Calendar** app
2. Go to **Calendar** → **Add Account** → **Other CalDAV Account**
3. Enter:
   - **Account Type:** Advanced
   - **User Name:** Your portal username
   - **Password:** Your portal password
   - **Server Address:** `rm.swhgrp.com`
   - **Server Path:** `/caldav/`
   - **Port:** 443
   - **Use SSL:** ✓ Yes
4. Click **Sign In**

### Outlook
1. Open Outlook
2. Go to **File** → **Account Settings** → **Internet Calendars**
3. Click **New** and enter: `https://rm.swhgrp.com/caldav/andy/the-links-grill/`
4. Repeat for each venue calendar

### Thunderbird
1. Install **Lightning** calendar add-on
2. Right-click **Calendars** → **New Calendar** → **On the Network**
3. Select **CalDAV**
4. Enter: `https://rm.swhgrp.com/caldav/andy/the-links-grill/`
5. Enter username and password when prompted

## Technical Architecture

### File Structure
```
/opt/restaurant-system/
├── caldav/
│   ├── Dockerfile                    # Radicale server image
│   ├── config                        # Radicale configuration
│   ├── rights                        # Access control rules
│   └── data/                         # Persistent calendar data
│       └── collection-root/
│           └── {username}/
│               ├── the-links-grill/
│               ├── sw-grill/
│               └── ...
├── events/
│   └── src/events/
│       ├── services/
│       │   └── caldav_sync_service.py   # CalDAV sync logic
│       ├── api/
│       │   ├── events.py                # Event CRUD endpoints
│       │   └── public.py                # Public intake form
│       └── schemas/
│           └── event.py                 # Event models
└── shared/nginx/conf.d/
    └── rm.swhgrp.com-http.conf          # Nginx CalDAV proxy config
```

### CalDAV Sync Service

**File:** `events/src/events/services/caldav_sync_service.py`

**Key Methods:**

```python
class CalDAVSyncService:
    def sync_event_to_caldav(self, event: Event, user_email: str):
        """
        Sync a single event to venue-specific CalDAV calendar
        - Determines calendar name from event.venue
        - Creates iCalendar (.ics) event with full event details
        - Uploads to CalDAV server
        """

    def remove_event_from_caldav(self, event, user_email: str):
        """
        Remove event from CalDAV (for CANCELED/CLOSED events)
        - Searches across all venue calendars
        - Deletes event .ics file
        """
```

**Integration Points:**

1. **Event Creation** (`events/api/events.py:289`)
   ```python
   if settings.CALDAV_ENABLED:
       caldav_service.sync_event_to_caldav(event, current_user.email)
   ```

2. **Event Update** (`events/api/events.py:384`)
   ```python
   if event.status in [EventStatus.CANCELED, EventStatus.CLOSED]:
       caldav_service.remove_event_from_caldav(event, current_user.email)
   else:
       caldav_service.sync_event_to_caldav(event, current_user.email)
   ```

3. **Public Intake Form** (`events/api/public.py:27`)
   ```python
   if settings.CALDAV_ENABLED:
       caldav_service.sync_event_to_caldav(event, 'andy')  # Sync to admin
   ```

### Nginx Configuration

**File:** `shared/nginx/conf.d/rm.swhgrp.com-http.conf`

```nginx
# CalDAV auto-discovery for iOS
location = /.well-known/caldav {
    return 301 $scheme://$host/caldav/;
}

# CalDAV server proxy
location /caldav/ {
    proxy_pass http://caldav:5232/;
    proxy_set_header X-Remote-User $remote_user;
    # ... CalDAV-specific headers
}

# CalDAV user paths (must come before Portal catch-all)
location ~ ^/(andy|principals)/ {
    proxy_pass http://caldav:5232;
    proxy_set_header X-Remote-User $remote_user;
}
```

### Docker Compose Configuration

**File:** `docker-compose.yml`

```yaml
caldav:
  build: ./caldav
  container_name: caldav
  restart: unless-stopped
  volumes:
    - caldav_data:/data
  networks:
    - app_network

volumes:
  caldav_data:
    driver: local
```

## Environment Configuration

**File:** `events/.env`

```bash
CALDAV_ENABLED=true
CALDAV_URL=http://caldav:5232
```

## Troubleshooting

### iOS "Cannot Connect Using SSL"
**Cause:** Auto-discovery endpoint missing or nginx not proxying CalDAV requests
**Solution:** Ensure `.well-known/caldav` location exists in nginx config

### Events Not Showing on Phone After Connection
**Cause:** Existing events not synced retroactively
**Solution:** Events only sync when created/updated. Edit an existing event to trigger sync.

### Event Deleted on Phone Still in System
**Expected Behavior:** Sync is one-way (DB → CalDAV → Phone)
**Solution:** Mark event as CANCELED in Events system to remove from phone

### "409 Conflict" When Syncing Event
**Cause:** Calendar collection doesn't exist
**Solution:** Calendar is automatically created when first event for that venue is synced

### Wrong Username (email vs. username)
**Cause:** Portal usernames are short (e.g., `andy`), not emails
**Solution:** Use portal username, not email address, when setting up calendar

## Calendar Status Color Indicators

The Events calendar view uses colored left borders to indicate event status:

- 🟠 **Orange** = PENDING (needs confirmation)
- 🔵 **Blue** = CONFIRMED (locked in)
- 🟢 **Green** = CLOSED/COMPLETED (event finished)
- 🔴 **Red** = CANCELED (event cancelled)
- ⚫ **Gray** = DRAFT (not yet finalized)
- 🟣 **Purple** = IN_PROGRESS (event currently happening)

Text color indicates the venue:
- Purple text = The Links Grill
- Pink text = SW Grill
- Blue text = Okee Grill
- Orange text = Park Bistro
- Green text = Seaside Grill
- Red text = The Nest Eatery

## Email Integration

Event notification emails include "View Event Details" links that take staff directly to the event page.

**Fixed Issue (Nov 14, 2025):** Email links were returning 404 errors due to incorrect URL patterns. Now fixed:
- ✅ Correct URL: `https://rm.swhgrp.com/events/event?id={event_id}`
- ❌ Old wrong URLs:
  - `/events/admin/events/{id}`
  - `/events/event/{id}` (missing query parameter)

**Affected Templates:**
- `events/src/events/templates/emails/internal_new_event.html`
- `events/src/events/templates/emails/internal_update.html`

## Performance Considerations

- **Sync Time:** ~100-200ms per event (synchronous)
- **Scalability:** Tested with 20+ events, performs well
- **Error Handling:** Sync failures are logged but don't block event creation
- **Retry Logic:** Not implemented - manual retry by re-editing event

## Future Enhancements

**Potential Improvements:**
1. ⏳ Two-way sync (phone changes sync back to Events system)
2. ⏳ Async sync using background jobs
3. ⏳ Bulk re-sync functionality for existing events
4. ⏳ Sync status indicator in Events UI
5. ⏳ Per-user calendar subscriptions (currently admin-only)
6. ⏳ Calendar sharing/delegation

## Related Documentation

- [Events Module Overview](events-module.md)
- [Email Notification System](events-email-notifications.md)
- [CalDAV RFC 4791](https://tools.ietf.org/html/rfc4791)
- [Radicale Documentation](https://radicale.org/v3.html)

## Support

For issues with CalDAV sync:
1. Check Events app logs: `docker logs events-app`
2. Check CalDAV server logs: `docker logs caldav`
3. Verify nginx proxy configuration
4. Test sync by creating/editing test event
5. Check calendar .ics files: `ls -la /opt/restaurant-system/caldav/data/collection-root/andy/the-links-grill/`

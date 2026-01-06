"""CalDAV synchronization service"""
import caldav
from caldav.elements import dav, cdav
from icalendar import Calendar, Event as ICalEvent
from datetime import datetime
from typing import List
from sqlalchemy.orm import Session
from events.models import Event, User
from events.core.config import settings
import logging

logger = logging.getLogger(__name__)


class CalDAVSyncService:
    """Syncs events from Events DB to CalDAV server"""

    def __init__(self):
        self.caldav_url = settings.CALDAV_URL or "http://caldav:5232"
        self.use_internal_api = True  # Internal service bypasses nginx auth

    def _get_caldav_username(self, user_email: str) -> str:
        """
        Extract username from email for CalDAV path.
        CalDAV calendars are organized by username (before @), not full email.
        This ensures consistency between iOS/Android clients and server-side sync.

        Example: andy@swhgrp.com -> andy
        """
        if '@' in user_email:
            return user_email.split('@')[0]
        return user_email

    def sync_event_to_caldav(self, event: Event, user_email: str):
        """
        Sync a single event to CalDAV calendar
        Events are organized by venue - each venue gets its own calendar

        Args:
            event: Event object from database
            user_email: Email of user to sync calendar for
        """
        try:
            # Create iCalendar event
            cal = Calendar()
            cal.add('prodid', '-//SW Hospitality Events//EN')
            cal.add('version', '2.0')

            ical_event = ICalEvent()
            ical_event.add('uid', f'{event.id}@swhgrp.com')
            ical_event.add('summary', event.title)
            ical_event.add('dtstart', event.start_at)
            ical_event.add('dtend', event.end_at)

            if event.venue:
                ical_event.add('location', event.venue.name)

            # Build comprehensive description with all event details
            description_parts = []

            # Event description/notes first (main content)
            if event.description:
                description_parts.append(event.description)

            # Separator if we have description and more details
            if event.description and (event.guest_count or event.client or event.event_type):
                description_parts.append("\n---")

            # Event details section
            if event.event_type:
                description_parts.append(f"Type: {event.event_type}")
            if event.guest_count:
                description_parts.append(f"Guests: {event.guest_count}")
            if event.status:
                status_display = str(event.status.value) if hasattr(event.status, 'value') else str(event.status)
                description_parts.append(f"Status: {status_display}")

            # Client information
            if event.client:
                description_parts.append("")  # Blank line before client section
                description_parts.append(f"Client: {event.client.name}")
                if event.client.phone:
                    description_parts.append(f"Phone: {event.client.phone}")
                if event.client.email:
                    description_parts.append(f"Email: {event.client.email}")
                if event.client.org:
                    description_parts.append(f"Organization: {event.client.org}")

            # Setup/teardown times if different from event times
            if event.setup_start_at and event.setup_start_at != event.start_at:
                setup_time = event.setup_start_at.strftime("%I:%M %p")
                description_parts.append(f"\nSetup: {setup_time}")
            if event.teardown_end_at and event.teardown_end_at != event.end_at:
                teardown_time = event.teardown_end_at.strftime("%I:%M %p")
                description_parts.append(f"Teardown: {teardown_time}")

            # Venue address if available
            if event.venue and event.venue.address:
                description_parts.append(f"\nAddress: {event.venue.address}")

            if description_parts:
                ical_event.add('description', '\n'.join(description_parts))
            ical_event.add('status', self._map_status_to_ical(event.status))

            # Add categories based on event type
            ical_event.add('categories', [event.event_type])

            cal.add_component(ical_event)

            # Determine calendar name based on venue
            # Create separate calendar for each venue for better organization and color coding
            if event.venue:
                # Create URL-safe calendar name from venue name
                calendar_name = event.venue.name.lower().replace(' ', '-').replace("'", '')
                calendar_display_name = event.venue.name
            else:
                calendar_name = 'unassigned'
                calendar_display_name = 'Unassigned Events'

            # Connect to CalDAV server
            # Set X-Remote-User header for http_x_remote_user auth
            # Use username only (not full email) for consistent CalDAV paths
            caldav_username = self._get_caldav_username(user_email)
            client = caldav.DAVClient(
                url=self.caldav_url,
                headers={'X-Remote-User': caldav_username}
            )

            # Use venue-specific calendar
            calendar_url = f"{self.caldav_url}/{caldav_username}/{calendar_name}/"
            from caldav import Calendar as CalDAVCalendar
            venue_cal = CalDAVCalendar(client=client, url=calendar_url, name=calendar_display_name)

            # Add or update event in calendar
            venue_cal.save_event(cal.to_ical())

            logger.info(f"Synced event {event.id} to CalDAV calendar '{calendar_display_name}' for {caldav_username}")

        except Exception as e:
            logger.error(f"Failed to sync event {event.id} to CalDAV: {e}")
            raise

    def sync_all_events_for_user(self, db: Session, user: User):
        """
        Sync all events for a user based on their assigned locations

        Args:
            db: Database session
            user: User object
        """
        from events.models.user import UserLocation

        # Get user's assigned venues
        user_venues = db.query(UserLocation.venue_id).filter(
            UserLocation.user_id == user.id
        ).all()
        user_venue_ids = [v[0] for v in user_venues]

        if not user_venue_ids:
            logger.info(f"User {user.email} has no assigned venues, skipping sync")
            return

        # Get all active events for user's venues
        events = db.query(Event).filter(
            Event.venue_id.in_(user_venue_ids),
            Event.status.in_(['PENDING', 'CONFIRMED'])
        ).all()

        synced_count = 0
        for event in events:
            try:
                self.sync_event_to_caldav(event, user.email)
                synced_count += 1
            except Exception as e:
                logger.error(f"Failed to sync event {event.id}: {e}")

        logger.info(f"Synced {synced_count}/{len(events)} events for {user.email}")

    def remove_event_from_caldav(self, event, user_email: str):
        """
        Remove an event from CalDAV calendar (for canceled/deleted events)
        Searches across all venue calendars to find and delete the event

        Args:
            event: Event object (or event_id string for backward compatibility)
            user_email: User email
        """
        try:
            # Handle both Event object and string event_id for backward compatibility
            if isinstance(event, str):
                event_id = event
                venue_calendars = ['the-links-grill', 'sw-grill', 'seaside-grill',
                                 'park-bistro', 'okee-grill', 'the-nest-eatery', 'unassigned']
            else:
                event_id = str(event.id)
                # Determine which calendar the event is in based on venue
                if event.venue:
                    calendar_name = event.venue.name.lower().replace(' ', '-').replace("'", '')
                    venue_calendars = [calendar_name]
                else:
                    venue_calendars = ['unassigned']

            # Use username only for consistent CalDAV paths
            caldav_username = self._get_caldav_username(user_email)
            client = caldav.DAVClient(
                url=self.caldav_url,
                headers={'X-Remote-User': caldav_username}
            )

            # Try to delete from relevant venue calendar(s)
            for calendar_name in venue_calendars:
                try:
                    calendar_url = f"{self.caldav_url}/{caldav_username}/{calendar_name}/"
                    from caldav import Calendar as CalDAVCalendar
                    venue_cal = CalDAVCalendar(client=client, url=calendar_url)

                    # Try to delete the specific event file
                    event_filename = f"{event_id}@swhgrp.com.ics"
                    import requests
                    delete_url = f"{calendar_url}{event_filename}"

                    # Use requests to delete with proper auth header
                    response = requests.delete(
                        delete_url,
                        headers={'X-Remote-User': caldav_username}
                    )

                    if response.status_code in [200, 204, 404]:
                        logger.info(f"Deleted event {event_id} from CalDAV calendar '{calendar_name}' for {caldav_username}")
                        return
                except Exception as e:
                    logger.debug(f"Event {event_id} not in calendar {calendar_name}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to remove event {event_id} from CalDAV: {e}")

    def _map_status_to_ical(self, status: str) -> str:
        """Map event status to iCalendar status"""
        status_map = {
            'DRAFT': 'TENTATIVE',
            'PENDING': 'TENTATIVE',
            'CONFIRMED': 'CONFIRMED',
            'CLOSED': 'CONFIRMED',
            'CANCELED': 'CANCELLED'
        }
        return status_map.get(status, 'TENTATIVE')

    def poll_caldav_for_quick_holds(self, db: Session, user_email: str) -> dict:
        """
        Poll CalDAV server for events created from phone calendar.
        Import any events that don't match existing Events as Quick Holds.

        This enables two-way sync:
        - Events created in the web app -> pushed to phone calendar
        - Events created on phone -> imported as Quick Holds

        Args:
            db: Database session
            user_email: Email of user to poll calendar for

        Returns:
            dict with counts: {'imported': N, 'skipped': N, 'errors': N}
        """
        from events.models import QuickHold, QuickHoldStatus, QuickHoldSource, Event
        from datetime import datetime, timedelta, timezone
        import pytz

        results = {'imported': 0, 'skipped': 0, 'errors': 0, 'details': []}

        try:
            caldav_username = self._get_caldav_username(user_email)
            client = caldav.DAVClient(
                url=self.caldav_url,
                headers={'X-Remote-User': caldav_username}
            )

            # Get the principal (user's calendars)
            principal = client.principal()
            calendars = principal.calendars()

            if not calendars:
                logger.info(f"No calendars found for {caldav_username}")
                return results

            # Get existing Event UIDs and QuickHold CalDAV UIDs to avoid duplicates
            existing_event_uids = set()
            for event in db.query(Event).all():
                existing_event_uids.add(f"{event.id}@swhgrp.com")

            existing_hold_uids = set()
            for hold in db.query(QuickHold).filter(
                QuickHold.caldav_uid.isnot(None)
            ).all():
                existing_hold_uids.add(hold.caldav_uid)

            # Search for events in date range (past month to next year)
            now = datetime.now(timezone.utc)
            start_date = now - timedelta(days=30)
            end_date = now + timedelta(days=365)

            for cal in calendars:
                try:
                    calendar_name = cal.name or "unnamed"
                    logger.info(f"Polling calendar: {calendar_name}")

                    # Fetch events in date range
                    events = cal.date_search(start=start_date, end=end_date)

                    for cal_event in events:
                        try:
                            # Parse the iCalendar data
                            ical_data = cal_event.data
                            ical = Calendar.from_ical(ical_data)

                            for component in ical.walk():
                                if component.name != "VEVENT":
                                    continue

                                uid = str(component.get('uid', ''))
                                summary = str(component.get('summary', 'Untitled'))

                                # Skip if this is an Event we pushed to CalDAV
                                if uid in existing_event_uids:
                                    results['skipped'] += 1
                                    continue

                                # Skip if we already imported this as a QuickHold
                                if uid in existing_hold_uids:
                                    results['skipped'] += 1
                                    continue

                                # Parse dates
                                dtstart = component.get('dtstart')
                                dtend = component.get('dtend')

                                if not dtstart:
                                    continue

                                start_dt = dtstart.dt
                                end_dt = dtend.dt if dtend else start_dt

                                # Check if all-day event (date vs datetime)
                                all_day = False
                                if not isinstance(start_dt, datetime):
                                    # It's a date, not datetime - all day event
                                    all_day = True
                                    start_dt = datetime.combine(start_dt, datetime.min.time()).replace(tzinfo=timezone.utc)
                                    end_dt = datetime.combine(end_dt, datetime.min.time()).replace(tzinfo=timezone.utc)
                                else:
                                    # Ensure timezone awareness
                                    if start_dt.tzinfo is None:
                                        start_dt = start_dt.replace(tzinfo=timezone.utc)
                                    if end_dt.tzinfo is None:
                                        end_dt = end_dt.replace(tzinfo=timezone.utc)

                                # Get other fields
                                description = str(component.get('description', '')) or None
                                location = str(component.get('location', '')) or None

                                # Get etag and href for change tracking
                                etag = getattr(cal_event, 'etag', None)
                                href = str(cal_event.url) if cal_event.url else None

                                # Create QuickHold
                                quick_hold = QuickHold(
                                    title=summary,
                                    description=description,
                                    start_at=start_dt,
                                    end_at=end_dt,
                                    all_day=all_day,
                                    location_text=location,
                                    status=QuickHoldStatus.HOLD,
                                    source=QuickHoldSource.PHONE_CALENDAR,
                                    caldav_uid=uid,
                                    caldav_etag=etag,
                                    caldav_href=href
                                )

                                db.add(quick_hold)
                                results['imported'] += 1
                                results['details'].append(f"Imported: {summary}")
                                logger.info(f"Imported QuickHold from phone: {summary} ({uid})")

                        except Exception as e:
                            logger.error(f"Error processing calendar event: {e}")
                            results['errors'] += 1

                except Exception as e:
                    logger.error(f"Error processing calendar {calendar_name}: {e}")
                    results['errors'] += 1

            db.commit()
            logger.info(f"CalDAV poll complete for {caldav_username}: {results}")

        except Exception as e:
            logger.error(f"Failed to poll CalDAV for {user_email}: {e}")
            results['errors'] += 1
            db.rollback()

        return results

    def sync_quick_hold_changes(self, db: Session, user_email: str) -> dict:
        """
        Check for changes to existing QuickHolds in CalDAV (updates/deletions).

        Args:
            db: Database session
            user_email: User email

        Returns:
            dict with counts
        """
        from events.models import QuickHold, QuickHoldStatus

        results = {'updated': 0, 'deleted': 0, 'errors': 0}

        try:
            caldav_username = self._get_caldav_username(user_email)
            client = caldav.DAVClient(
                url=self.caldav_url,
                headers={'X-Remote-User': caldav_username}
            )

            principal = client.principal()
            calendars = principal.calendars()

            # Get all active QuickHolds from phone
            holds = db.query(QuickHold).filter(
                QuickHold.source == QuickHoldSource.PHONE_CALENDAR,
                QuickHold.status == QuickHoldStatus.HOLD,
                QuickHold.caldav_uid.isnot(None)
            ).all()

            for hold in holds:
                found = False
                for cal in calendars:
                    try:
                        # Try to find the event by UID
                        cal_event = cal.event_by_uid(hold.caldav_uid)
                        if cal_event:
                            found = True
                            # Check if etag changed (event was updated)
                            current_etag = getattr(cal_event, 'etag', None)
                            if current_etag and hold.caldav_etag != current_etag:
                                # Event was updated, re-parse
                                ical = Calendar.from_ical(cal_event.data)
                                for component in ical.walk():
                                    if component.name == "VEVENT":
                                        hold.title = str(component.get('summary', hold.title))
                                        hold.description = str(component.get('description', '')) or None
                                        hold.location_text = str(component.get('location', '')) or None

                                        dtstart = component.get('dtstart')
                                        dtend = component.get('dtend')
                                        if dtstart:
                                            hold.start_at = dtstart.dt if isinstance(dtstart.dt, datetime) else datetime.combine(dtstart.dt, datetime.min.time()).replace(tzinfo=timezone.utc)
                                        if dtend:
                                            hold.end_at = dtend.dt if isinstance(dtend.dt, datetime) else datetime.combine(dtend.dt, datetime.min.time()).replace(tzinfo=timezone.utc)

                                        hold.caldav_etag = current_etag
                                        results['updated'] += 1
                                        break
                            break
                    except Exception:
                        continue

                if not found:
                    # Event was deleted from phone calendar
                    hold.status = QuickHoldStatus.CANCELED
                    results['deleted'] += 1
                    logger.info(f"QuickHold {hold.id} was deleted from phone calendar")

            db.commit()

        except Exception as e:
            logger.error(f"Failed to sync QuickHold changes: {e}")
            results['errors'] += 1
            db.rollback()

        return results

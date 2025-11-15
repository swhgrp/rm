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
            if event.description:
                description_parts.append(event.description)
            if event.guest_count:
                description_parts.append(f"\nGuests: {event.guest_count}")
            if event.client:
                description_parts.append(f"Client: {event.client.name}")
                if event.client.email:
                    description_parts.append(f"Email: {event.client.email}")

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
            client = caldav.DAVClient(
                url=self.caldav_url,
                headers={'X-Remote-User': user_email}
            )

            # Use venue-specific calendar
            calendar_url = f"{self.caldav_url}/{user_email}/{calendar_name}/"
            from caldav import Calendar as CalDAVCalendar
            venue_cal = CalDAVCalendar(client=client, url=calendar_url, name=calendar_display_name)

            # Add or update event in calendar
            venue_cal.save_event(cal.to_ical())

            logger.info(f"Synced event {event.id} to CalDAV calendar '{calendar_display_name}' for {user_email}")

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

            client = caldav.DAVClient(
                url=self.caldav_url,
                headers={'X-Remote-User': user_email}
            )

            # Try to delete from relevant venue calendar(s)
            for calendar_name in venue_calendars:
                try:
                    calendar_url = f"{self.caldav_url}/{user_email}/{calendar_name}/"
                    from caldav import Calendar as CalDAVCalendar
                    venue_cal = CalDAVCalendar(client=client, url=calendar_url)

                    # Try to delete the specific event file
                    event_filename = f"{event_id}@swhgrp.com.ics"
                    import requests
                    delete_url = f"{calendar_url}{event_filename}"

                    # Use requests to delete with proper auth header
                    response = requests.delete(
                        delete_url.replace('http://caldav:5232', 'http://caldav:5232'),
                        headers={'X-Remote-User': user_email}
                    )

                    if response.status_code in [200, 204, 404]:
                        logger.info(f"Deleted event {event_id} from CalDAV calendar '{calendar_name}' for {user_email}")
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

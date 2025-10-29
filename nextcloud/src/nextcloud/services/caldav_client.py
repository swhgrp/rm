"""
Nextcloud CalDAV client for calendar operations
"""
from typing import List, Optional
from datetime import datetime, timedelta
import caldav
from caldav.elements import dav, cdav
from icalendar import Calendar, Event as ICalEvent
import uuid

from nextcloud.core.config import settings
from nextcloud.core.security import decrypt_credential
from nextcloud.models.user import User


class NextcloudCalDAVClient:
    """
    CalDAV client for Nextcloud calendar operations

    Handles calendar listing, event creation, updates, and deletion.
    """

    def __init__(self, user: User):
        """
        Initialize CalDAV client with user credentials

        Args:
            user: User object with Nextcloud credentials
        """
        if not user.nextcloud_username or not user.nextcloud_encrypted_password:
            raise ValueError("User does not have Nextcloud credentials configured")

        # Decrypt password
        password = decrypt_credential(user.nextcloud_encrypted_password)

        # CalDAV URL
        caldav_url = f"{settings.NEXTCLOUD_URL}{settings.NEXTCLOUD_CALDAV_PATH}"

        # Connect to CalDAV server
        self.client = caldav.DAVClient(
            url=caldav_url,
            username=user.nextcloud_username,
            password=password
        )

        self.principal = self.client.principal()
        self.user = user

    def list_calendars(self) -> List[dict]:
        """
        List all calendars for the user

        Returns:
            List of calendar dictionaries
        """
        try:
            calendars = self.principal.calendars()

            result = []
            for calendar in calendars:
                # Get calendar properties
                props = calendar.get_properties([dav.DisplayName(), cdav.CalendarColor(), cdav.CalendarDescription()])

                calendar_info = {
                    'name': calendar.name if hasattr(calendar, 'name') else str(calendar.url),
                    'display_name': props.get('{DAV:}displayname', 'Unnamed Calendar'),
                    'url': str(calendar.url),
                    'color': props.get('{http://apple.com/ns/ical/}calendar-color'),
                    'description': props.get('{urn:ietf:params:xml:ns:caldav}calendar-description')
                }
                result.append(calendar_info)

            return result

        except Exception as e:
            raise Exception(f"Failed to list calendars: {str(e)}")

    def get_events(
        self,
        calendar_url: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[dict]:
        """
        Get events from a calendar within a date range

        Args:
            calendar_url: Calendar URL (if None, gets from all calendars)
            start_date: Start date for events (default: 30 days ago)
            end_date: End date for events (default: 30 days from now)

        Returns:
            List of event dictionaries
        """
        try:
            # Default date range
            if start_date is None:
                start_date = datetime.now() - timedelta(days=30)
            if end_date is None:
                end_date = datetime.now() + timedelta(days=30)

            # Get calendar(s)
            if calendar_url:
                calendars = [self.principal.calendar(url=calendar_url)]
            else:
                calendars = self.principal.calendars()

            all_events = []

            for calendar in calendars:
                # Search for events in date range
                events = calendar.date_search(start=start_date, end=end_date)

                for event in events:
                    try:
                        # Parse iCal data
                        ical = Calendar.from_ical(event.data)

                        for component in ical.walk():
                            if component.name == "VEVENT":
                                # Extract event data
                                event_data = {
                                    'uid': str(component.get('UID', str(uuid.uuid4()))),
                                    'summary': str(component.get('SUMMARY', 'Untitled Event')),
                                    'description': str(component.get('DESCRIPTION', '')),
                                    'location': str(component.get('LOCATION', '')),
                                    'start': component.get('DTSTART').dt if component.get('DTSTART') else None,
                                    'end': component.get('DTEND').dt if component.get('DTEND') else None,
                                    'all_day': not isinstance(component.get('DTSTART').dt, datetime) if component.get('DTSTART') else False,
                                    'calendar_name': calendar.name if hasattr(calendar, 'name') else 'Unknown',
                                    'created': component.get('CREATED').dt if component.get('CREATED') else None,
                                    'last_modified': component.get('LAST-MODIFIED').dt if component.get('LAST-MODIFIED') else None
                                }
                                all_events.append(event_data)

                    except Exception as e:
                        # Skip malformed events
                        continue

            return all_events

        except Exception as e:
            raise Exception(f"Failed to get events: {str(e)}")

    def create_event(
        self,
        calendar_url: str,
        summary: str,
        start: datetime,
        end: datetime,
        description: Optional[str] = None,
        location: Optional[str] = None,
        all_day: bool = False
    ) -> dict:
        """
        Create a new calendar event

        Args:
            calendar_url: Calendar URL to add event to
            summary: Event title
            start: Start date/time
            end: End date/time
            description: Event description (optional)
            location: Event location (optional)
            all_day: Is this an all-day event

        Returns:
            Created event dictionary
        """
        try:
            # Get calendar
            calendar = self.principal.calendar(url=calendar_url)

            # Create iCal event
            ical = Calendar()
            ical.add('prodid', '-//Nextcloud Integration//Restaurant System//EN')
            ical.add('version', '2.0')

            event = ICalEvent()
            event.add('uid', str(uuid.uuid4()))
            event.add('summary', summary)
            event.add('dtstart', start.date() if all_day else start)
            event.add('dtend', end.date() if all_day else end)

            if description:
                event.add('description', description)
            if location:
                event.add('location', location)

            event.add('dtstamp', datetime.now())
            event.add('created', datetime.now())

            ical.add_component(event)

            # Add event to calendar
            calendar.add_event(ical.to_ical().decode('utf-8'))

            return {
                'success': True,
                'uid': event.get('uid'),
                'summary': summary
            }

        except Exception as e:
            raise Exception(f"Failed to create event: {str(e)}")

    def update_event(
        self,
        calendar_url: str,
        event_uid: str,
        summary: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None
    ) -> dict:
        """
        Update an existing calendar event

        Args:
            calendar_url: Calendar URL
            event_uid: Event UID to update
            summary: New event title
            start: New start date/time
            end: New end date/time
            description: New description
            location: New location

        Returns:
            Updated event dictionary
        """
        try:
            # Get calendar
            calendar = self.principal.calendar(url=calendar_url)

            # Find event by UID
            events = calendar.events()
            target_event = None

            for event in events:
                ical = Calendar.from_ical(event.data)
                for component in ical.walk():
                    if component.name == "VEVENT" and str(component.get('UID')) == event_uid:
                        target_event = event
                        break
                if target_event:
                    break

            if not target_event:
                raise Exception(f"Event with UID {event_uid} not found")

            # Parse and update event
            ical = Calendar.from_ical(target_event.data)

            for component in ical.walk():
                if component.name == "VEVENT":
                    if summary:
                        component['SUMMARY'] = summary
                    if start:
                        component['DTSTART'].dt = start
                    if end:
                        component['DTEND'].dt = end
                    if description is not None:
                        component['DESCRIPTION'] = description
                    if location is not None:
                        component['LOCATION'] = location

                    component['LAST-MODIFIED'].dt = datetime.now()

            # Save updated event
            target_event.data = ical.to_ical()
            target_event.save()

            return {
                'success': True,
                'uid': event_uid
            }

        except Exception as e:
            raise Exception(f"Failed to update event: {str(e)}")

    def delete_event(self, calendar_url: str, event_uid: str) -> dict:
        """
        Delete a calendar event

        Args:
            calendar_url: Calendar URL
            event_uid: Event UID to delete

        Returns:
            Success dictionary
        """
        try:
            # Get calendar
            calendar = self.principal.calendar(url=calendar_url)

            # Find and delete event
            events = calendar.events()

            for event in events:
                ical = Calendar.from_ical(event.data)
                for component in ical.walk():
                    if component.name == "VEVENT" and str(component.get('UID')) == event_uid:
                        event.delete()
                        return {'success': True, 'uid': event_uid}

            raise Exception(f"Event with UID {event_uid} not found")

        except Exception as e:
            raise Exception(f"Failed to delete event: {str(e)}")

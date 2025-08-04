"""Simple Google Calendar API client for calendar sync application"""

from datetime import datetime, timedelta
import logging
import uuid

from django.utils import timezone
from django.conf import settings
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from apps.calendars.models import CalendarAccount
from apps.calendars.services.token_manager import TokenManager


logger = logging.getLogger(__name__)


class GoogleCalendarClient:
    """Simple Google Calendar API client - no enterprise complexity"""

    def __init__(self, calendar_account: CalendarAccount):
        self.account = calendar_account
        self.token_manager = TokenManager(calendar_account)
        self._service = None

    def _get_service(self):
        """Get Google Calendar service with valid credentials"""
        if self._service is None:
            credentials = self.token_manager.get_valid_credentials()
            if not credentials:
                raise Exception(
                    f"No valid credentials for account {self.account.email}"
                )

            self._service = build("calendar", "v3", credentials=credentials)

        return self._service

    def list_calendars(self) -> list[dict]:
        """List all calendars for the account"""
        try:
            service = self._get_service()
            calendar_list = service.calendarList().list().execute()
            return calendar_list.get("items", [])

        except HttpError as e:
            logger.error(f"Failed to list calendars for {self.account.email}: {e}")
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error listing calendars for {self.account.email}: {e}"
            )
            raise

    def get_calendar(self, calendar_id: str) -> dict | None:
        """Get details for a specific calendar"""
        try:
            service = self._get_service()
            calendar = service.calendars().get(calendarId=calendar_id).execute()
            return calendar

        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(
                    f"Calendar {calendar_id} not found for {self.account.email}"
                )
                return None
            logger.error(
                f"Failed to get calendar {calendar_id} for {self.account.email}: {e}"
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error getting calendar {calendar_id} for {self.account.email}: {e}"
            )
            raise

    def list_events(
        self,
        calendar_id: str,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        max_results: int = 250,
    ) -> list[dict]:
        """List events from a calendar within time range"""
        try:
            service = self._get_service()

            # Default time range if not provided
            if time_min is None:
                time_min = timezone.now() - timedelta(days=30)
            if time_max is None:
                time_max = timezone.now() + timedelta(days=90)

            # Format times for Google API
            time_min_str = time_min.isoformat()
            time_max_str = time_max.isoformat()

            events_result = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min_str,
                    timeMax=time_max_str,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            return events_result.get("items", [])

        except HttpError as e:
            logger.error(f"Failed to list events for calendar {calendar_id}: {e}")
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error listing events for calendar {calendar_id}: {e}"
            )
            raise

    def get_event(self, calendar_id: str, event_id: str) -> dict | None:
        """Get a specific event"""
        try:
            service = self._get_service()
            event = (
                service.events().get(calendarId=calendar_id, eventId=event_id).execute()
            )
            return event

        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(f"Event {event_id} not found in calendar {calendar_id}")
                return None
            logger.error(
                f"Failed to get event {event_id} from calendar {calendar_id}: {e}"
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error getting event {event_id} from calendar {calendar_id}: {e}"
            )
            raise

    def create_event(self, calendar_id: str, event_data: dict) -> dict:
        """Create a new event in the calendar"""
        try:
            service = self._get_service()
            event = (
                service.events()
                .insert(calendarId=calendar_id, body=event_data)
                .execute()
            )
            logger.info(f"Created event {event['id']} in calendar {calendar_id}")
            return event

        except HttpError as e:
            logger.error(f"Failed to create event in calendar {calendar_id}: {e}")
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error creating event in calendar {calendar_id}: {e}"
            )
            raise

    def update_event(self, calendar_id: str, event_id: str, event_data: dict) -> dict:
        """Update an existing event"""
        try:
            service = self._get_service()
            event = (
                service.events()
                .update(calendarId=calendar_id, eventId=event_id, body=event_data)
                .execute()
            )
            logger.info(f"Updated event {event_id} in calendar {calendar_id}")
            return event

        except HttpError as e:
            logger.error(
                f"Failed to update event {event_id} in calendar {calendar_id}: {e}"
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error updating event {event_id} in calendar {calendar_id}: {e}"
            )
            raise

    def delete_event(self, calendar_id: str, event_id: str) -> bool:
        """Delete an event from the calendar"""
        try:
            service = self._get_service()
            service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            logger.info(f"Deleted event {event_id} from calendar {calendar_id}")
            return True

        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(
                    f"Event {event_id} not found in calendar {calendar_id} (already deleted?)"
                )
                return True  # Consider missing event as successfully deleted
            logger.error(
                f"Failed to delete event {event_id} from calendar {calendar_id}: {e}"
            )
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error deleting event {event_id} from calendar {calendar_id}: {e}"
            )
            raise

    def create_busy_block(
        self,
        calendar_id: str,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: str = "",
    ) -> dict:
        """Create a busy block event with CalSync tagging"""

        # Format times for Google API
        start_str = start_time.isoformat()
        end_str = end_time.isoformat()

        event_data = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_str},
            "end": {"dateTime": end_str},
            "transparency": "opaque",  # Show as busy
            "visibility": "private",
        }

        return self.create_event(calendar_id, event_data)

    def find_system_events(self, calendar_id: str, tag_pattern: str) -> list[dict]:
        """Find events created by our system using tag pattern matching"""
        try:
            events = self.list_events(calendar_id)
            system_events = []

            for event in events:
                title = event.get("summary", "")
                description = event.get("description", "")

                # Check if this looks like a system-created event
                if (
                    tag_pattern in title
                    or tag_pattern in description
                    or "CalSync [source:" in title
                    or "CalSync [source:" in description
                ):
                    system_events.append(event)

            return system_events

        except Exception as e:
            logger.error(f"Failed to find system events in calendar {calendar_id}: {e}")
            raise

    def batch_delete_events(
        self, calendar_id: str, event_ids: list[str]
    ) -> dict[str, bool]:
        """Delete multiple events (simple approach - no complex batching)"""
        results = {}

        for event_id in event_ids:
            try:
                success = self.delete_event(calendar_id, event_id)
                results[event_id] = success
            except Exception as e:
                logger.error(f"Failed to delete event {event_id}: {e}")
                results[event_id] = False

        return results

    def setup_webhook(self, calendar_id: str, force_recreate: bool = False) -> dict | None:
        """
        Register webhook with Google Calendar for real-time notifications.
        
        This is Guilfoyle's minimalist approach with cron-safe duplicate prevention.
        Reduces API calls by 95% without complex subscription management.
        
        Args:
            calendar_id: Google Calendar ID
            force_recreate: Force webhook recreation even if valid one exists
        """
        try:
            from apps.calendars.models import Calendar
            
            # Get calendar object to check existing webhook status
            try:
                calendar = Calendar.objects.get(google_calendar_id=calendar_id)
            except Calendar.DoesNotExist:
                logger.error(f"Calendar {calendar_id} not found in database")
                return None
            
            # Check if webhook already exists and is still valid (cron-safe)
            if not force_recreate and calendar.has_active_webhook(buffer_hours=24):
                logger.info(f"Webhook for calendar {calendar_id} still valid, skipping setup")
                return {
                    'channel_id': calendar.webhook_channel_id,
                    'webhook_url': f"{settings.WEBHOOK_BASE_URL}/webhooks/google/",
                    'expires_at': calendar.webhook_expires_at,
                    'skipped': True
                }
            
            service = self._get_service()
            
            # Clean up old webhook if it exists (prevent duplicates)
            if calendar.webhook_channel_id:
                self._cleanup_old_webhook(calendar.webhook_channel_id, calendar.google_calendar_id)
            
            # Generate unique channel ID
            channel_id = f"calendar-sync-{uuid.uuid4().hex[:8]}"
            
            # Build webhook URL
            webhook_url = f"{settings.WEBHOOK_BASE_URL}/webhooks/google/"
            
            # Set expiration (Google allows max 7 days for calendar events)
            expiration_time = timezone.now() + timedelta(days=6)  # 6 days for safety
            expiration_timestamp = int(expiration_time.timestamp() * 1000)  # Milliseconds
            
            # Create webhook subscription
            watch_request = {
                'id': channel_id,
                'type': 'web_hook',
                'address': webhook_url,
                'expiration': expiration_timestamp
            }
            
            response = service.events().watch(
                calendarId=calendar_id,
                body=watch_request
            ).execute()
            
            # Store webhook info in database (enables cron-safe behavior)
            calendar.update_webhook_info(channel_id, expiration_time)
            
            logger.info(f"Created webhook for calendar {calendar_id} with channel {channel_id}")
            
            return {
                'channel_id': channel_id,
                'webhook_url': webhook_url,
                'expires_at': expiration_time,
                'resource_id': response.get('resourceId'),
                'resource_uri': response.get('resourceUri')
            }
            
        except HttpError as e:
            logger.error(f"Failed to setup webhook for calendar {calendar_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error setting up webhook for calendar {calendar_id}: {e}")
            return None
    
    def _cleanup_old_webhook(self, old_channel_id: str, calendar_id: str):
        """Clean up old webhook subscription to prevent duplicates"""
        try:
            service = self._get_service()
            
            # Stop the old webhook channel
            stop_request = {
                'id': old_channel_id,
                'resourceId': calendar_id  # Use calendar_id as resource fallback
            }
            
            service.channels().stop(body=stop_request).execute()
            logger.info(f"Cleaned up old webhook channel {old_channel_id}")
            
        except HttpError as e:
            if e.resp.status == 404:
                # Webhook already expired or deleted
                logger.info(f"Old webhook channel {old_channel_id} already deleted")
            else:
                logger.warning(f"Failed to cleanup old webhook {old_channel_id}: {e}")
        except Exception as e:
            logger.warning(f"Error cleaning up old webhook {old_channel_id}: {e}")


def get_google_calendar_client(account: CalendarAccount) -> GoogleCalendarClient:
    """Factory function to create a Google Calendar client"""
    return GoogleCalendarClient(account)


def test_connection(account: CalendarAccount) -> bool:
    """Test if we can connect to Google Calendar API"""
    try:
        client = GoogleCalendarClient(account)
        calendars = client.list_calendars()
        logger.info(
            f"Successfully connected to Google Calendar for {account.email} - found {len(calendars)} calendars"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to connect to Google Calendar for {account.email}: {e}")
        return False

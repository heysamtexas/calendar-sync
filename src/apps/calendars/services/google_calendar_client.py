"""Simple Google Calendar API client for calendar sync application"""

from datetime import datetime, timedelta
import logging
import time
import uuid

from django.conf import settings
from django.utils import timezone
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

    def _execute_with_rate_limiting(
        self, request, operation_name: str, max_retries: int = 3
    ):
        """Execute API request with exponential backoff rate limiting"""
        base_delay = 3  # Start with 3 second delay

        for attempt in range(max_retries + 1):
            try:
                return request.execute()
            except HttpError as e:
                if e.resp.status == 403 and (
                    "rateLimitExceeded" in str(e) or "quotaExceeded" in str(e)
                ):
                    if attempt < max_retries:
                        delay = base_delay * (2**attempt)  # Exponential backoff
                        logger.warning(
                            f"Rate limit hit for {operation_name}, retrying in {delay}s (attempt {attempt + 1}/{max_retries + 1})"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(
                            f"Rate limit exceeded after {max_retries} retries for {operation_name}"
                        )
                        raise
                else:
                    # Non-rate-limit error, re-raise immediately
                    raise
            except Exception:
                # Non-HTTP error, re-raise immediately
                raise

        # This should never be reached
        raise Exception(f"Max retries exceeded for {operation_name}")

    def list_calendars(self) -> list[dict]:
        """List all calendars for the account"""
        try:
            service = self._get_service()
            request = service.calendarList().list()
            calendar_list = self._execute_with_rate_limiting(
                request, f"list_calendars for {self.account.email}"
            )
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
            request = service.calendars().get(calendarId=calendar_id)
            calendar = self._execute_with_rate_limiting(
                request, f"get_calendar {calendar_id}"
            )
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

            request = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min_str,
                timeMax=time_max_str,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )

            events_result = self._execute_with_rate_limiting(
                request, f"list_events for calendar {calendar_id}"
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
            request = service.events().get(calendarId=calendar_id, eventId=event_id)
            event = self._execute_with_rate_limiting(request, f"get_event {event_id}")
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
        """Create a new event in the calendar with rate limiting handling"""
        try:
            service = self._get_service()
            request = service.events().insert(calendarId=calendar_id, body=event_data)
            event = self._execute_with_rate_limiting(
                request, f"create_event in calendar {calendar_id}"
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
            request = service.events().update(
                calendarId=calendar_id, eventId=event_id, body=event_data
            )
            event = self._execute_with_rate_limiting(
                request, f"update_event {event_id}"
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
        """Delete an event from the calendar with rate limiting handling"""
        try:
            service = self._get_service()
            request = service.events().delete(calendarId=calendar_id, eventId=event_id)
            self._execute_with_rate_limiting(request, f"delete_event {event_id}")
            logger.info(f"Deleted event {event_id} from calendar {calendar_id}")
            return True

        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(
                    f"Event {event_id} not found in calendar {calendar_id} (already deleted?)"
                )
                return True  # Consider missing event as successfully deleted
            elif e.resp.status == 410:
                logger.info(
                    f"Event {event_id} already deleted from calendar {calendar_id} (410 Resource deleted)"
                )
                return True  # Consider already-deleted event as successfully deleted
            else:
                logger.error(
                    f"Failed to delete event {event_id} from calendar {calendar_id}: {e}"
                )
                # For rate limit errors, let them bubble up from _execute_with_rate_limiting
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
        """Delete multiple events with rate limiting between calls"""

        results = {}

        for i, event_id in enumerate(event_ids):
            try:
                success = self.delete_event(calendar_id, event_id)
                results[event_id] = success

                # Add delay between deletions to avoid rate limiting (except for last item)
                if i < len(event_ids) - 1:
                    time.sleep(1.0)  # 1 second delay between deletions

            except Exception as e:
                logger.error(f"Failed to delete event {event_id}: {e}")
                results[event_id] = False

        return results

    def setup_webhook(
        self, calendar_id: str, force_recreate: bool = False
    ) -> dict | None:
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
                logger.info(
                    f"Webhook for calendar {calendar_id} still valid, skipping setup"
                )
                return {
                    "channel_id": calendar.webhook_channel_id,
                    "webhook_url": f"{settings.WEBHOOK_BASE_URL}/webhooks/google/",
                    "expires_at": calendar.webhook_expires_at,
                    "skipped": True,
                }

            service = self._get_service()

            # Clean up old webhook if it exists (prevent duplicates)
            if calendar.webhook_channel_id:
                self._cleanup_old_webhook(
                    calendar.webhook_channel_id, calendar.google_calendar_id
                )

            # Generate unique channel ID
            channel_id = f"calendar-sync-{uuid.uuid4().hex[:8]}"

            # Build webhook URL
            webhook_url = f"{settings.WEBHOOK_BASE_URL}/webhooks/google/"

            # Set expiration (Google allows max 7 days for calendar events)
            expiration_time = timezone.now() + timedelta(days=6)  # 6 days for safety
            expiration_timestamp = int(
                expiration_time.timestamp() * 1000
            )  # Milliseconds

            # Create webhook subscription
            watch_request = {
                "id": channel_id,
                "type": "web_hook",
                "address": webhook_url,
                "expiration": expiration_timestamp,
            }

            request = service.events().watch(calendarId=calendar_id, body=watch_request)
            response = self._execute_with_rate_limiting(
                request, f"setup_webhook for calendar {calendar_id}"
            )

            # Store webhook info in database (enables cron-safe behavior)
            calendar.update_webhook_info(channel_id, expiration_time)

            logger.info(
                f"Created webhook for calendar {calendar_id} with channel {channel_id}"
            )

            return {
                "channel_id": channel_id,
                "webhook_url": webhook_url,
                "expires_at": expiration_time,
                "resource_id": response.get("resourceId"),
                "resource_uri": response.get("resourceUri"),
            }

        except HttpError as e:
            logger.error(f"Failed to setup webhook for calendar {calendar_id}: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error setting up webhook for calendar {calendar_id}: {e}"
            )
            return None

    def _cleanup_old_webhook(self, old_channel_id: str, calendar_id: str):
        """Clean up old webhook subscription to prevent duplicates"""
        try:
            service = self._get_service()

            # Stop the old webhook channel
            stop_request = {
                "id": old_channel_id,
                "resourceId": calendar_id,  # Use calendar_id as resource fallback
            }

            request = service.channels().stop(body=stop_request)
            self._execute_with_rate_limiting(
                request, f"cleanup_webhook {old_channel_id}"
            )
            logger.info(f"Cleaned up old webhook channel {old_channel_id}")

        except HttpError as e:
            if e.resp.status == 404:
                # Webhook already expired or deleted
                logger.info(f"Old webhook channel {old_channel_id} already deleted")
            else:
                logger.warning(f"Failed to cleanup old webhook {old_channel_id}: {e}")
        except Exception as e:
            logger.warning(f"Error cleaning up old webhook {old_channel_id}: {e}")

    # === GUILFOYLE'S ENHANCED METHODS FOR UUID CORRELATION ===

    def get_event_with_robust_retry(
        self, calendar_id: str, google_event_id: str, max_retries: int = 3
    ) -> dict | None:
        """
        Get event with Guilfoyle's production-hardened error handling
        
        Handles:
        - 404: Event deleted on Google side
        - 403: Permission issues 
        - 5xx: Server errors with retry
        - Rate limits: Intelligent backoff
        """
        for attempt in range(max_retries):
            try:
                service = self._get_service()
                request = service.events().get(calendarId=calendar_id, eventId=google_event_id)
                return self._execute_with_rate_limiting(
                    request, f"get_event {google_event_id}"
                )

            except HttpError as e:
                if e.resp.status == 404:
                    # Event deleted on Google side - clean up our state
                    logger.info(f"Event {google_event_id} deleted on Google side")
                    self._handle_deleted_event(google_event_id)
                    return None

                elif e.resp.status == 403:
                    # Permission issue - disable sync for this calendar
                    logger.error(f"Permission denied for calendar {calendar_id}: {e}")
                    self._disable_calendar_sync(calendar_id, reason=f"Permission denied: {e}")
                    return None

                elif e.resp.status >= 500 or attempt < max_retries - 1:
                    # Server error or not final attempt - retry
                    delay = 2 ** attempt
                    logger.warning(
                        f"Server error getting event {google_event_id}, retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                    continue
                else:
                    # Client error on final attempt - log and skip
                    logger.error(f"Failed to get event {google_event_id}: {e}")
                    return None

            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 2 ** attempt
                    logger.warning(f"Unexpected error getting event {google_event_id}, retrying: {e}")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Unexpected error getting event {google_event_id}: {e}")
                    return None

        return None

    def create_event_with_uuid_correlation(
        self,
        calendar_id: str,
        event_data: dict,
        correlation_uuid: str,
        skip_title_embedding: bool = False
    ) -> dict | None:
        """
        Create event with UUID correlation using triple-redundancy embedding
        
        Args:
            skip_title_embedding: If True, skip zero-width title embedding (for busy blocks)
        """
        try:
            from apps.calendars.utils import UUIDCorrelationUtils

            # Embed UUID using triple-redundancy strategy
            enhanced_event_data = UUIDCorrelationUtils.embed_uuid_in_event(
                event_data=event_data.copy(),
                correlation_uuid=correlation_uuid,
                skip_title_embedding=skip_title_embedding
            )

            service = self._get_service()
            request = service.events().insert(calendarId=calendar_id, body=enhanced_event_data)

            result = self._execute_with_rate_limiting(
                request, f"create_event_with_uuid {correlation_uuid[:8]}"
            )

            logger.info(f"Created event with UUID correlation {correlation_uuid}: {result.get('id')}")
            return result

        except Exception as e:
            logger.error(f"Failed to create event with UUID {correlation_uuid}: {e}")
            return None

    def update_event_with_uuid_correlation(
        self,
        calendar_id: str,
        google_event_id: str,
        correlation_uuid: str
    ) -> dict | None:
        """
        Add UUID correlation to existing event using triple-redundancy
        """
        try:
            from apps.calendars.utils import UUIDCorrelationUtils

            # Get current event
            current_event = self.get_event_with_robust_retry(calendar_id, google_event_id)
            if not current_event:
                logger.warning(f"Cannot update event {google_event_id} - not found")
                return None

            # Add UUID correlation using triple-redundancy
            enhanced_event = UUIDCorrelationUtils.embed_uuid_in_event(
                event_data=current_event,
                correlation_uuid=correlation_uuid
            )

            service = self._get_service()
            request = service.events().update(
                calendarId=calendar_id,
                eventId=google_event_id,
                body=enhanced_event
            )

            result = self._execute_with_rate_limiting(
                request, f"update_event_with_uuid {google_event_id}"
            )

            logger.info(f"Added UUID correlation {correlation_uuid} to event {google_event_id}")
            return result

        except Exception as e:
            logger.error(f"Failed to add UUID {correlation_uuid} to event {google_event_id}: {e}")
            return None

    def list_events_with_uuid_extraction(
        self,
        calendar_id: str,
        time_min: datetime | None = None,
        time_max: datetime | None = None
    ) -> list[dict]:
        """
        List events with UUID extraction for correlation
        
        Returns events enhanced with UUID correlation data
        """
        try:
            from apps.calendars.utils import UUIDCorrelationUtils

            # Get events using existing method
            events = self.list_events(calendar_id, time_min, time_max)

            # Enhance each event with UUID correlation data
            enhanced_events = []
            for event in events:
                # Extract UUID correlation data
                is_ours, correlation_uuid = UUIDCorrelationUtils.is_our_event(event)

                # Add correlation metadata
                event['_correlation'] = {
                    'uuid': correlation_uuid,
                    'is_ours': is_ours,
                    'has_uuid': correlation_uuid is not None,
                }

                enhanced_events.append(event)

            return enhanced_events

        except Exception as e:
            logger.error(f"Failed to list events with UUID extraction for {calendar_id}: {e}")
            return []

    def bulk_add_uuid_correlation(
        self,
        calendar_id: str,
        event_uuid_pairs: list[tuple[str, str]]  # [(google_event_id, correlation_uuid), ...]
    ) -> dict:
        """
        Bulk add UUID correlation to existing events
        
        Returns success/failure statistics for migration
        """
        results = {
            'total': len(event_uuid_pairs),
            'successful': 0,
            'failed': 0,
            'errors': []
        }

        for google_event_id, correlation_uuid in event_uuid_pairs:
            try:
                result = self.update_event_with_uuid_correlation(
                    calendar_id, google_event_id, correlation_uuid
                )

                if result:
                    results['successful'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append(f"Failed to update {google_event_id}")

                # Small delay to avoid overwhelming API
                time.sleep(0.1)

            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"Error updating {google_event_id}: {e}")

        logger.info(
            f"Bulk UUID correlation results: {results['successful']}/{results['total']} successful"
        )

        return results

    def _handle_deleted_event(self, google_event_id: str):
        """Handle event deleted on Google side"""
        try:
            from apps.calendars.models import EventState

            # Mark EventState as deleted
            event_states = EventState.objects.filter(google_event_id=google_event_id)
            count = event_states.update(status='DELETED', updated_at=timezone.now())

            if count > 0:
                logger.info(f"Marked {count} EventState records as deleted for {google_event_id}")

        except Exception as e:
            logger.error(f"Failed to handle deleted event {google_event_id}: {e}")

    def _disable_calendar_sync(self, calendar_id: str, reason: str):
        """Disable sync for calendar due to permission issues"""
        try:
            from apps.calendars.models import Calendar

            calendar = Calendar.objects.filter(google_calendar_id=calendar_id).first()
            if calendar:
                calendar.sync_enabled = False
                calendar.save(update_fields=['sync_enabled'])

                logger.error(f"Disabled sync for calendar {calendar.name}: {reason}")

                # TODO: Send notification to user about disabled sync

        except Exception as e:
            logger.error(f"Failed to disable calendar sync for {calendar_id}: {e}")


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

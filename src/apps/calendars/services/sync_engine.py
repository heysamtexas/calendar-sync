"""Core synchronization engine for calendar sync application"""

from datetime import datetime, timedelta
import logging

from django.utils import timezone

from apps.calendars.constants import BusyBlock
from apps.calendars.models import Calendar, CalendarAccount, Event, SyncLog
from apps.calendars.services.google_calendar_client import GoogleCalendarClient


logger = logging.getLogger(__name__)


class SyncEngine:
    """Core synchronization engine - simple bi-directional sync"""

    def __init__(self):
        self.sync_results = {
            "calendars_processed": 0,
            "events_created": 0,
            "events_updated": 0,
            "events_deleted": 0,
            "busy_blocks_created": 0,
            "busy_blocks_updated": 0,
            "busy_blocks_deleted": 0,
            "errors": [],
        }

    def sync_all_calendars(self, verbose: bool = False) -> dict:
        """Sync all active calendars"""
        logger.info("Starting full calendar sync")

        active_calendars = Calendar.objects.filter(
            sync_enabled=True, calendar_account__is_active=True
        ).select_related("calendar_account")

        if not active_calendars.exists():
            logger.info("No active calendars found")
            return self.sync_results

        for calendar in active_calendars:
            try:
                if verbose:
                    logger.info(
                        f"Syncing calendar: {calendar.name} ({calendar.google_calendar_id})"
                    )

                self._sync_single_calendar(calendar)
                self.sync_results["calendars_processed"] += 1

            except Exception as e:
                error_msg = f"Failed to sync calendar {calendar.name}: {e}"
                logger.error(error_msg)
                self.sync_results["errors"].append(error_msg)

                # Log sync error
                SyncLog.objects.create(
                    calendar_account=calendar.calendar_account,
                    sync_type="full",
                    status="error",
                    error_message=error_msg,
                    events_processed=0,
                )

        # Now create busy blocks across calendars
        self._create_cross_calendar_busy_blocks()

        logger.info(f"Sync complete: {self.sync_results}")
        return self.sync_results

    def sync_specific_calendar(self, calendar_id: int) -> dict:
        """Sync a specific calendar by ID"""
        try:
            calendar = Calendar.objects.get(
                id=calendar_id, sync_enabled=True, calendar_account__is_active=True
            )

            logger.info(f"Syncing specific calendar: {calendar.name}")
            self._sync_single_calendar(calendar)
            self.sync_results["calendars_processed"] = 1

            return self.sync_results

        except Calendar.DoesNotExist:
            error_msg = f"Calendar with ID {calendar_id} not found or inactive"
            logger.error(error_msg)
            self.sync_results["errors"].append(error_msg)
            return self.sync_results

    def _sync_single_calendar(self, calendar: Calendar):
        """Sync events for a single calendar"""
        client = GoogleCalendarClient(calendar.calendar_account)

        # Get time range for sync (30 days past to 90 days future)
        time_min = timezone.now() - timedelta(days=30)
        time_max = timezone.now() + timedelta(days=90)

        try:
            # Fetch events from Google Calendar
            google_events = client.list_events(
                calendar.google_calendar_id, time_min=time_min, time_max=time_max
            )

            logger.info(f"Fetched {len(google_events)} events from Google Calendar")

            # Process each event
            events_processed = 0
            for google_event in google_events:
                try:
                    self._process_google_event(calendar, google_event)
                    events_processed += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to process event {google_event.get('id', 'unknown')}: {e}"
                    )

            # Clean up deleted events
            self._cleanup_deleted_events(calendar, google_events)

            # Log successful sync
            SyncLog.objects.create(
                calendar_account=calendar.calendar_account,
                sync_type="incremental",
                status="success",
                events_processed=events_processed,
            )

        except Exception as e:
            logger.error(f"Failed to sync calendar {calendar.name}: {e}")
            raise

    def _process_google_event(self, calendar: Calendar, google_event: dict):
        """Process a single Google Calendar event"""
        google_event_id = google_event.get("id")
        if not google_event_id:
            return

        # Skip system-created busy blocks (tagged with CalSync)
        summary = google_event.get("summary", "")
        description = google_event.get("description", "")

        if BusyBlock.is_system_busy_block(summary) or BusyBlock.is_system_busy_block(
            description
        ):
            return

        # Get or create event
        event, created = Event.objects.get_or_create(
            calendar=calendar,
            google_event_id=google_event_id,
            defaults=self._extract_event_data(google_event),
        )

        if created:
            logger.debug(f"Created new event: {event.title}")
            self.sync_results["events_created"] += 1
        else:
            # Update existing event if changed
            updated_data = self._extract_event_data(google_event)
            if self._event_needs_update(event, updated_data):
                for field, value in updated_data.items():
                    setattr(event, field, value)
                event.save()
                logger.debug(f"Updated event: {event.title}")
                self.sync_results["events_updated"] += 1

    def _extract_event_data(self, google_event: dict) -> dict:
        """Extract event data from Google Calendar event"""
        start_time = self._parse_event_time(google_event.get("start", {}))
        end_time = self._parse_event_time(google_event.get("end", {}))

        return {
            "title": google_event.get("summary", "Untitled Event"),
            "description": google_event.get("description", ""),
            "start_time": start_time,
            "end_time": end_time,
            "is_all_day": "date" in google_event.get("start", {}),
        }

    def _parse_event_time(self, time_data: dict) -> datetime:
        """Parse event time from Google Calendar format"""
        if "dateTime" in time_data:
            # Parse ISO format datetime
            time_str = time_data["dateTime"]
            if time_str.endswith("Z"):
                time_str = time_str[:-1] + "+00:00"
            return datetime.fromisoformat(time_str)
        elif "date" in time_data:
            # All-day event - use date at midnight
            date_str = time_data["date"]
            return datetime.fromisoformat(f"{date_str}T00:00:00+00:00")
        else:
            # Fallback to current time
            return timezone.now()

    def _event_needs_update(self, event: Event, new_data: dict) -> bool:
        """Check if event needs updating"""
        fields_to_check = [
            "title",
            "description",
            "start_time",
            "end_time",
            "is_all_day",
        ]

        for field in fields_to_check:
            if getattr(event, field) != new_data.get(field):
                return True
        return False

    def _cleanup_deleted_events(self, calendar: Calendar, google_events: list[dict]):
        """Remove events that no longer exist in Google Calendar"""
        google_event_ids = {
            event.get("id") for event in google_events if event.get("id")
        }

        # Find events in our database that aren't in Google Calendar anymore
        deleted_events = Event.objects.filter(
            calendar=calendar,
            is_busy_block=False,  # Don't delete our own busy blocks
        ).exclude(google_event_id__in=google_event_ids)

        deleted_count = deleted_events.count()
        if deleted_count > 0:
            logger.info(
                f"Deleting {deleted_count} events that no longer exist in Google Calendar"
            )
            deleted_events.delete()
            self.sync_results["events_deleted"] += deleted_count

    def _create_cross_calendar_busy_blocks(self):
        """Create busy blocks in other calendars based on events"""
        logger.info("Creating cross-calendar busy blocks")

        # Get all active calendars grouped by account
        accounts = CalendarAccount.objects.filter(
            is_active=True, calendars__sync_enabled=True
        ).distinct()

        for account in accounts:
            calendars = list(account.calendars.filter(sync_enabled=True))
            if len(calendars) < 2:
                continue  # Need at least 2 calendars to sync

            self._sync_calendars_for_account(account, calendars)

    def _sync_calendars_for_account(
        self, account: CalendarAccount, calendars: list[Calendar]
    ):
        """Sync calendars within a single account"""
        client = GoogleCalendarClient(account)

        # Get time range for busy blocks (next 90 days)
        time_min = timezone.now()
        time_max = timezone.now() + timedelta(days=90)

        for source_calendar in calendars:
            # Get events from source calendar
            source_events = Event.objects.filter(
                calendar=source_calendar,
                start_time__gte=time_min,
                end_time__lte=time_max,
                is_busy_block=False,  # Only real events, not our busy blocks
            )

            # Create busy blocks in other calendars
            for target_calendar in calendars:
                if target_calendar.id == source_calendar.id:
                    continue

                self._create_busy_blocks_for_calendar(
                    client, source_calendar, target_calendar, source_events
                )

    def _create_busy_blocks_for_calendar(
        self,
        client: GoogleCalendarClient,
        source_calendar: Calendar,
        target_calendar: Calendar,
        events: list[Event],
    ):
        """Create busy blocks in target calendar for events from source calendar"""

        # First, clean up existing busy blocks from this source
        self._cleanup_existing_busy_blocks(client, source_calendar, target_calendar)

        # Create new busy blocks
        for event in events:
            try:
                busy_block_title = BusyBlock.generate_title(event.title)
                busy_block_description = f"CalSync [source:{source_calendar.google_calendar_id}:{event.google_event_id}]"

                google_event = client.create_busy_block(
                    target_calendar.google_calendar_id,
                    busy_block_title,
                    event.start_time,
                    event.end_time,
                    busy_block_description,
                )

                # Save busy block in our database
                Event.objects.create(
                    calendar=target_calendar,
                    google_event_id=google_event["id"],
                    title=busy_block_title,
                    description=busy_block_description,
                    start_time=event.start_time,
                    end_time=event.end_time,
                    is_busy_block=True,
                    source_event=event,
                    busy_block_tag=busy_block_description,
                )

                self.sync_results["busy_blocks_created"] += 1

            except Exception as e:
                logger.warning(
                    f"Failed to create busy block for event {event.title}: {e}"
                )

    def _cleanup_existing_busy_blocks(
        self,
        client: GoogleCalendarClient,
        source_calendar: Calendar,
        target_calendar: Calendar,
    ):
        """Remove existing busy blocks from source calendar in target calendar"""

        # Find existing busy blocks from this source
        tag_pattern = f"CalSync [source:{source_calendar.google_calendar_id}:"

        try:
            system_events = client.find_system_events(
                target_calendar.google_calendar_id, tag_pattern
            )

            if system_events:
                event_ids = [event["id"] for event in system_events]
                results = client.batch_delete_events(
                    target_calendar.google_calendar_id, event_ids
                )

                # Clean up from our database too
                Event.objects.filter(
                    calendar=target_calendar,
                    is_busy_block=True,
                    busy_block_tag__contains=f"[source:{source_calendar.google_calendar_id}:",
                ).delete()

                deleted_count = sum(1 for success in results.values() if success)
                self.sync_results["busy_blocks_deleted"] += deleted_count

        except Exception as e:
            logger.warning(f"Failed to cleanup busy blocks: {e}")


# Utility functions
def sync_all_calendars(verbose: bool = False) -> dict:
    """Sync all calendars - utility function for management command"""
    engine = SyncEngine()
    return engine.sync_all_calendars(verbose=verbose)


def sync_calendar(calendar_id: int) -> dict:
    """Sync specific calendar - utility function"""
    engine = SyncEngine()
    return engine.sync_specific_calendar(calendar_id)


def reset_calendar_busy_blocks(calendar_id: int) -> dict:
    """Reset all busy blocks for a calendar"""
    try:
        calendar = Calendar.objects.get(id=calendar_id, sync_enabled=True)
        client = GoogleCalendarClient(calendar.calendar_account)

        # Find all system events (busy blocks)
        system_events = client.find_system_events(
            calendar.google_calendar_id, "CalSync"
        )

        if system_events:
            event_ids = [event["id"] for event in system_events]
            results = client.batch_delete_events(calendar.google_calendar_id, event_ids)

            # Clean up from database
            Event.objects.filter(calendar=calendar, is_busy_block=True).delete()

            deleted_count = sum(1 for success in results.values() if success)

            return {
                "success": True,
                "deleted_count": deleted_count,
                "calendar_name": calendar.name,
            }

        return {"success": True, "deleted_count": 0, "calendar_name": calendar.name}

    except Calendar.DoesNotExist:
        return {"success": False, "error": f"Calendar with ID {calendar_id} not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}

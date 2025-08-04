"""Core synchronization engine for calendar sync application"""

from datetime import datetime, timedelta
import logging
import sys

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
        """Sync all active calendars (scheduled sync with cross-calendar busy blocks)"""
        logger.info(
            "Starting full scheduled calendar sync (includes cross-calendar busy blocks)"
        )

        active_calendars = Calendar.objects.filter(
            sync_enabled=True, calendar_account__is_active=True
        ).select_related("calendar_account")

        if not active_calendars.exists():
            logger.info("No active calendars found")
            return self.sync_results

        for calendar in active_calendars:
            try:
                # Global sync coordination: Skip if webhook is already syncing this calendar
                from django.core.cache import cache

                global_cache_key = f"calendar_sync_lock_{calendar.id}"

                existing_sync = cache.get(global_cache_key)
                if existing_sync:
                    logger.info(
                        f"🔒 SYNC COORDINATION: Skipping calendar {calendar.name} - already being synced by {existing_sync}"
                    )
                    continue

                if verbose:
                    logger.info(
                        f"Syncing calendar: {calendar.name} ({calendar.google_calendar_id})"
                    )

                self._sync_single_calendar(calendar, webhook_triggered=False)
                self.sync_results["calendars_processed"] += 1

            except Exception as e:
                error_msg = f"Failed to sync calendar {calendar.name}: {e}"
                logger.error(error_msg)
                self.sync_results["errors"].append(error_msg)

                # Log sync error with proper completion timestamp
                sync_log = SyncLog.objects.create(
                    calendar_account=calendar.calendar_account,
                    sync_type="full",
                    status="in_progress",  # Create as in_progress first
                    events_processed=0,
                )
                # Mark as completed with error to set the completed_at timestamp
                sync_log.mark_completed(status="error", error_message=error_msg)

        # Now create busy blocks across calendars (scheduled sync only)
        logger.info("Starting cross-calendar busy block creation for scheduled sync")
        self._create_cross_calendar_busy_blocks()

        logger.info(f"Scheduled sync complete: {self.sync_results}")
        return self.sync_results

    def sync_specific_calendar(
        self, calendar_id: int, webhook_triggered: bool = False
    ) -> dict:
        """Sync a specific calendar by ID with global sync coordination"""
        try:
            calendar = Calendar.objects.get(
                id=calendar_id, sync_enabled=True, calendar_account__is_active=True
            )

            sync_type = "webhook-triggered" if webhook_triggered else "scheduled"

            # Global sync coordination for scheduled syncs
            if not webhook_triggered:
                from django.core.cache import cache

                global_cache_key = f"calendar_sync_lock_{calendar_id}"

                # Check if webhook sync is already running
                existing_sync = cache.get(global_cache_key)
                if existing_sync:
                    logger.info(
                        f"🔒 SYNC COORDINATION: Skipping scheduled sync - calendar {calendar.name} already being synced by {existing_sync}"
                    )
                    return self.sync_results

                # Set scheduled sync lock (shorter duration than webhook)
                logger.info(
                    f"🔒 SYNC COORDINATION: Acquiring scheduled sync lock for calendar {calendar.name}"
                )
                cache.set(global_cache_key, "scheduled", 90)  # 1.5 minutes

            logger.info(f"Syncing specific calendar ({sync_type}): {calendar.name}")

            try:
                self._sync_single_calendar(
                    calendar, webhook_triggered=webhook_triggered
                )
                self.sync_results["calendars_processed"] = 1
            finally:
                # Clean up scheduled sync lock (webhook locks are cleaned up in webhook handler)
                if not webhook_triggered:
                    from django.core.cache import cache

                    global_cache_key = f"calendar_sync_lock_{calendar_id}"
                    logger.info(
                        f"🔒 SYNC COORDINATION: Releasing scheduled sync lock for calendar {calendar.name}"
                    )
                    cache.delete(global_cache_key)

            return self.sync_results

        except Calendar.DoesNotExist:
            error_msg = f"Calendar with ID {calendar_id} not found or inactive"
            logger.error(error_msg)
            self.sync_results["errors"].append(error_msg)
            return self.sync_results

    def _sync_single_calendar(
        self, calendar: Calendar, webhook_triggered: bool = False
    ):
        """Sync events for a single calendar"""
        # Store webhook context for use in other methods
        self.webhook_triggered = webhook_triggered

        client = GoogleCalendarClient(calendar.calendar_account)

        # Get time range for sync (30 days past to 90 days future)
        time_min = timezone.now() - timedelta(days=30)
        time_max = timezone.now() + timedelta(days=90)

        try:
            # Fetch events from Google Calendar
            sync_start = timezone.now()
            print(
                f"STDERR [{sync_start.isoformat()}]: 🔍 FETCHING events for {calendar.name} from Google",
                file=sys.stderr,
                flush=True,
            )

            google_events = client.list_events(
                calendar.google_calendar_id, time_min=time_min, time_max=time_max
            )

            fetch_duration = (timezone.now() - sync_start).total_seconds()
            print(
                f"STDERR [{timezone.now().isoformat()}]: 🔍 FETCHED {len(google_events)} events in {fetch_duration:.2f}s",
                file=sys.stderr,
                flush=True,
            )

            logger.info(f"Fetched {len(google_events)} events from Google Calendar")

            # Process each event
            events_processed = 0
            events_created = 0
            events_updated = 0

            for google_event in google_events:
                try:
                    action = self._process_google_event(calendar, google_event)
                    events_processed += 1
                    if action == "created":
                        events_created += 1
                    elif action == "updated":
                        events_updated += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to process event {google_event.get('id', 'unknown')}: {e}"
                    )

            # Clean up deleted events
            deleted_count = self._cleanup_deleted_events(calendar, google_events)

            print(
                f"STDERR [{timezone.now().isoformat()}]: 📊 SYNC RESULTS: {events_created} created, {events_updated} updated, {deleted_count} deleted",
                file=sys.stderr,
                flush=True,
            )

            # Log successful sync with proper completion timestamp
            sync_log = SyncLog.objects.create(
                calendar_account=calendar.calendar_account,
                sync_type="incremental",
                status="in_progress",  # Create as in_progress first
                events_processed=events_processed,
            )
            # Mark as completed to set the completed_at timestamp
            sync_log.mark_completed(status="success")

        except Exception as e:
            logger.error(f"Failed to sync calendar {calendar.name}: {e}")
            raise

    def _process_google_event(self, calendar: Calendar, google_event: dict):
        """Process a single Google Calendar event with decline filtering"""
        google_event_id = google_event.get("id")
        if not google_event_id:
            return None

        # Skip system-created busy blocks (tagged with CalSync)
        summary = google_event.get("summary", "")
        description = google_event.get("description", "")

        if BusyBlock.is_system_busy_block(summary) or BusyBlock.is_system_busy_block(
            description
        ):
            return "skipped_system"

        # Extract event data including decline status
        event_data = self._extract_event_data(google_event)

        # Skip declined meetings (privacy-first: don't sync declined invites)
        if event_data.get("user_declined", False):
            logger.debug(f"Skipping declined meeting: {event_data['title']}")
            return "skipped_declined"

        # Remove user_declined from data (not stored in database)
        event_data_to_store = {
            k: v for k, v in event_data.items() if k != "user_declined"
        }

        # Get or create event
        event, created = Event.objects.get_or_create(
            calendar=calendar,
            google_event_id=google_event_id,
            defaults=event_data_to_store,
        )

        if created:
            logger.debug(
                f"Created new event: {event.title} (Meeting: {event.is_meeting_invite})"
            )
            self.sync_results["events_created"] += 1
            return "created"
        # Update existing event if changed
        elif self._event_needs_update(event, event_data_to_store):
            for field, value in event_data_to_store.items():
                setattr(event, field, value)
            event.save()
            logger.debug(
                f"Updated event: {event.title} (Meeting: {event.is_meeting_invite})"
            )
            self.sync_results["events_updated"] += 1
            return "updated"

        return "unchanged"

    def _extract_event_data(self, google_event: dict) -> dict:
        """Extract event data from Google Calendar event with meeting invite detection"""
        start_time = self._parse_event_time(google_event.get("start", {}))
        end_time = self._parse_event_time(google_event.get("end", {}))

        # Extract attendee information for meeting detection (privacy-first approach)
        attendees = google_event.get("attendees", [])
        is_meeting_invite = len(attendees) > 0

        # Check if the user declined this meeting (skip from sync if declined)
        user_declined = False
        if is_meeting_invite:
            # Find the current user's response status in attendees
            for attendee in attendees:
                # Check if this is the calendar owner (primary invitee)
                if (
                    attendee.get("self", False)
                    and attendee.get("responseStatus") == "declined"
                ):
                    user_declined = True
                    break

        return {
            "title": google_event.get("summary", "Untitled Event"),
            "description": google_event.get("description", ""),
            "start_time": start_time,
            "end_time": end_time,
            "is_all_day": "date" in google_event.get("start", {}),
            "is_meeting_invite": is_meeting_invite,
            "user_declined": user_declined,  # Used for filtering, not stored
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
            "is_meeting_invite",
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

        return deleted_count

    def _create_cross_calendar_busy_blocks(self):
        """Create busy blocks across ALL sync-enabled calendars (global cross-account sync)"""
        logger.info("Creating global cross-calendar busy blocks")

        # Get ALL sync-enabled calendars across ALL accounts for this user
        # This enables true conflict prevention across different Google accounts
        all_calendars = list(
            Calendar.objects.filter(
                calendar_account__user__isnull=False,  # Has associated user
                sync_enabled=True,
                calendar_account__is_active=True,
            ).select_related("calendar_account", "calendar_account__user")
        )

        if len(all_calendars) < 2:
            logger.info(
                "Need at least 2 sync-enabled calendars for busy block creation"
            )
            return

        logger.info(
            f"Creating busy blocks across {len(all_calendars)} calendars from multiple accounts"
        )

        # Create busy blocks from every calendar to every other calendar
        # This replaces the per-account limitation with global user-wide sync
        for source_calendar in all_calendars:
            for target_calendar in all_calendars:
                if source_calendar.id == target_calendar.id:
                    continue  # Skip self

                # Only create busy blocks for calendars belonging to the same user
                if (
                    source_calendar.calendar_account.user_id
                    != target_calendar.calendar_account.user_id
                ):
                    continue

                self._create_cross_account_busy_blocks(source_calendar, target_calendar)

    def _create_cross_account_busy_blocks(
        self, source_calendar: Calendar, target_calendar: Calendar
    ):
        """Create busy blocks from source calendar to target calendar (may be different accounts)"""
        try:
            # Get time range for busy blocks (next 90 days)
            time_min = timezone.now()
            time_max = timezone.now() + timedelta(days=90)

            # Get events from source calendar (only real events, not existing busy blocks)
            source_events = Event.objects.filter(
                calendar=source_calendar,
                start_time__gte=time_min,
                end_time__lte=time_max,
                is_busy_block=False,  # Only real events, not our busy blocks
            )

            if not source_events.exists():
                logger.debug(
                    f"No events found in source calendar {source_calendar.name}"
                )
                return

            # Create client for the TARGET calendar's account (may be different from source)
            target_client = GoogleCalendarClient(target_calendar.calendar_account)

            # Clean up existing busy blocks from this source calendar
            self._cleanup_cross_account_busy_blocks(
                target_client, source_calendar, target_calendar
            )

            # Create new busy blocks in target calendar
            for event in source_events:
                try:
                    # Enhanced busy block title and description with account info
                    busy_block_title = BusyBlock.generate_title(event.title)
                    busy_block_description = (
                        f"CalSync [source:{source_calendar.calendar_account.email}:"
                        f"{source_calendar.google_calendar_id}:{event.google_event_id}]"
                    )

                    google_event = target_client.create_busy_block(
                        target_calendar.google_calendar_id,
                        busy_block_title,
                        event.start_time,
                        event.end_time,
                        busy_block_description,
                    )

                    # Generate proper busy block tag using the BusyBlock utility
                    busy_block_tag = BusyBlock.generate_tag(
                        target_calendar.id, event.id
                    )

                    # Save busy block in our database with meeting status from source
                    Event.objects.create(
                        calendar=target_calendar,
                        google_event_id=google_event["id"],
                        title=busy_block_title,
                        description=busy_block_description,
                        start_time=event.start_time,
                        end_time=event.end_time,
                        is_busy_block=True,
                        is_meeting_invite=event.is_meeting_invite,  # Inherit from source event
                        source_event=event,
                        busy_block_tag=busy_block_tag,
                    )

                    self.sync_results["busy_blocks_created"] += 1
                    logger.debug(
                        f"Created busy block in {target_calendar.name} for event {event.title}"
                    )

                except Exception as e:
                    logger.warning(
                        f"Failed to create busy block for event {event.title}: {e}"
                    )

        except Exception as e:
            logger.error(
                f"Failed to create cross-account busy blocks from {source_calendar.name} to {target_calendar.name}: {e}"
            )

    def _cleanup_cross_account_busy_blocks(
        self,
        target_client: GoogleCalendarClient,
        source_calendar: Calendar,
        target_calendar: Calendar,
    ):
        """Remove existing busy blocks from source calendar in target calendar (enhanced for cross-account)"""
        try:
            # Enhanced tag pattern includes source account email
            tag_pattern = f"CalSync [source:{source_calendar.calendar_account.email}:{source_calendar.google_calendar_id}:"

            system_events = target_client.find_system_events(
                target_calendar.google_calendar_id, tag_pattern
            )

            if system_events:
                event_ids = [event["id"] for event in system_events]
                results = target_client.batch_delete_events(
                    target_calendar.google_calendar_id, event_ids
                )

                # Clean up from our database too
                Event.objects.filter(
                    calendar=target_calendar,
                    is_busy_block=True,
                    busy_block_tag__contains=f"[source:{source_calendar.calendar_account.email}:{source_calendar.google_calendar_id}:",
                ).delete()

                deleted_count = sum(1 for success in results.values() if success)
                self.sync_results["busy_blocks_deleted"] += deleted_count
                logger.debug(
                    f"Cleaned up {deleted_count} existing busy blocks from {source_calendar.name} in {target_calendar.name}"
                )

        except Exception as e:
            logger.warning(f"Failed to cleanup busy blocks: {e}")

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

                # Generate proper busy block tag using the BusyBlock utility
                busy_block_tag = BusyBlock.generate_tag(target_calendar.id, event.id)

                # Save busy block in our database with meeting status from source
                Event.objects.create(
                    calendar=target_calendar,
                    google_event_id=google_event["id"],
                    title=busy_block_title,
                    description=busy_block_description,
                    start_time=event.start_time,
                    end_time=event.end_time,
                    is_busy_block=True,
                    is_meeting_invite=event.is_meeting_invite,  # Inherit from source event
                    source_event=event,
                    busy_block_tag=busy_block_tag,
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
    """Sync specific calendar - utility function for scheduled syncs"""
    engine = SyncEngine()
    return engine.sync_specific_calendar(calendar_id, webhook_triggered=False)


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

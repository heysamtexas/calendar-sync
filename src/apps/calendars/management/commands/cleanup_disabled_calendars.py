"""
Management command to perform async cleanup of disabled calendars.

This command implements Guilfoyle's async cleanup pattern by processing
calendars marked with cleanup_pending=True.
"""

from datetime import timedelta
import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.calendars.models import Calendar


class Command(BaseCommand):
    help = "Process async cleanup for calendars with sync disabled"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=getattr(settings, 'CLEANUP_BATCH_SIZE', 100),
            help='Number of calendars to process in each batch'
        )
        parser.add_argument(
            '--min-age-seconds',
            type=int,
            default=30,
            help='Minimum age in seconds before processing cleanup request'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned up without making changes'
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        min_age_seconds = options['min_age_seconds']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )

        # Find calendars pending cleanup (with age buffer to avoid race conditions)
        cutoff_time = timezone.now() - timedelta(seconds=min_age_seconds)

        pending_calendars = Calendar.objects.filter(
            cleanup_pending=True,
            cleanup_requested_at__lt=cutoff_time
        ).select_related('calendar_account')[:batch_size]

        if not pending_calendars:
            self.stdout.write("No calendars pending cleanup")
            return

        total_processed = 0
        total_errors = 0

        for calendar in pending_calendars:
            try:
                if dry_run:
                    self._show_cleanup_preview(calendar)
                else:
                    self._process_calendar_cleanup(calendar)

                total_processed += 1

                if total_processed % 10 == 0:
                    self.stdout.write(f"Processed {total_processed} calendars...")

            except Exception as e:
                total_errors += 1
                self.logger.error(
                    f"Failed to cleanup calendar {calendar.id} ({calendar.name}): {e}"
                )
                self.stdout.write(
                    self.style.ERROR(
                        f"Error cleaning up {calendar.name}: {e}"
                    )
                )

        # Summary
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"DRY RUN: Would process {total_processed} calendars"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Completed cleanup for {total_processed} calendars "
                    f"({total_errors} errors)"
                )
            )

    def _show_cleanup_preview(self, calendar):
        """Show what would be cleaned up for this calendar"""
        # Count events that would be deleted
        total_events = calendar.event_states.count()
        user_events = calendar.event_states.filter(is_busy_block=False).count()
        busy_blocks = calendar.event_states.filter(is_busy_block=True).count()

        # Count outbound busy blocks that would be deleted
        if user_events > 0:
            user_event_uuids = list(
                calendar.event_states.filter(is_busy_block=False)
                .values_list('uuid', flat=True)
            )

            from apps.calendars.models import EventState
            outbound_busy_blocks = EventState.objects.filter(
                source_uuid__in=user_event_uuids,
                is_busy_block=True
            ).exclude(calendar=calendar).count()
        else:
            outbound_busy_blocks = 0

        self.stdout.write(
            f"  📅 {calendar.name} ({calendar.calendar_account.email}):"
        )
        self.stdout.write(f"    - Local events: {total_events}")
        self.stdout.write(f"    - User events: {user_events}")
        self.stdout.write(f"    - Local busy blocks: {busy_blocks}")
        self.stdout.write(f"    - Outbound busy blocks: {outbound_busy_blocks}")

    def _process_calendar_cleanup(self, calendar):
        """Process cleanup for a single calendar (Guilfoyle's bulletproof pattern)"""
        self.logger.debug(f"Starting cleanup for calendar {calendar.name}")

        # Import here to avoid circular imports
        from apps.calendars.services.calendar_service import CalendarService

        # Create service instance with the calendar's user
        service = CalendarService(user=calendar.calendar_account.user)

        cleanup_completed = False
        local_cleaned = 0
        outbound_cleaned = 0

        try:
            # Execute the same cleanup logic as the original sync method
            cleanup_stats = service._analyze_cleanup_scope(calendar)
            outbound_cleaned = service._cleanup_outbound_busy_blocks(calendar)
            local_cleaned = service._cleanup_calendar_events(calendar)

            cleanup_completed = True

            self.logger.info(
                f"Completed cleanup for {calendar.name}: "
                f"{local_cleaned} local events, {outbound_cleaned} outbound busy blocks"
            )

            self.stdout.write(
                f"✅ Cleaned up {calendar.name}: "
                f"{local_cleaned} local + {outbound_cleaned} outbound events"
            )

        except Exception as e:
            self.logger.error(f"Cleanup failed for {calendar.name}: {e}")
            self.stdout.write(
                self.style.ERROR(f"❌ Failed to clean up {calendar.name}: {e}")
            )
            # Don't re-raise - we want to clear the flag and continue

        finally:
            # CRITICAL: Always clear the cleanup_pending flag (Guilfoyle's requirement)
            try:
                calendar.refresh_from_db()
                calendar.cleanup_pending = False
                if cleanup_completed:
                    calendar.cleanup_requested_at = None
                calendar.save(update_fields=['cleanup_pending', 'cleanup_requested_at'])

                self.logger.info(f"Cleared cleanup_pending flag for {calendar.name}")
            except Exception as e:
                # This is really bad - we can't clear the flag
                self.logger.critical(
                    f"CRITICAL: Failed to clear cleanup_pending for calendar {calendar.id}: {e}"
                )
                self.stdout.write(
                    self.style.ERROR(f"CRITICAL: Calendar {calendar.name} may be stuck in cleanup state")
                )

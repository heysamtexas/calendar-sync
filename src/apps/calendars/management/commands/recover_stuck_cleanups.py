"""
Management command to detect and recover calendars stuck in cleanup state.

This command implements Guilfoyle's stuck state detection by finding calendars
that have been in cleanup_pending=True state for too long and clearing the flag.
"""

from datetime import timedelta
import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.calendars.models import Calendar


User = get_user_model()


class Command(BaseCommand):
    help = "Detect and recover calendars stuck in cleanup state"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout-minutes',
            type=int,
            default=10,
            help='Consider cleanup stuck after this many minutes (default: 10)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be recovered without making changes'
        )

    def handle(self, *args, **options):
        timeout_minutes = options['timeout_minutes']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )

        # Find calendars stuck in cleanup
        stuck_threshold = timezone.now() - timedelta(minutes=timeout_minutes)
        stuck_calendars = Calendar.objects.filter(
            cleanup_pending=True,
            updated_at__lt=stuck_threshold
        ).select_related('calendar_account')

        if not stuck_calendars:
            self.stdout.write("No stuck cleanups found")
            return

        self.stdout.write(
            f"Found {stuck_calendars.count()} calendars stuck in cleanup state "
            f"for more than {timeout_minutes} minutes:"
        )

        total_recovered = 0
        total_errors = 0

        for calendar in stuck_calendars:
            stuck_duration = timezone.now() - calendar.updated_at
            stuck_hours = stuck_duration.total_seconds() / 3600

            self.stdout.write(
                f"  📅 {calendar.name} ({calendar.calendar_account.email}) - "
                f"stuck for {stuck_hours:.1f} hours"
            )

            if not dry_run:
                try:
                    # Clear the stuck state
                    calendar.cleanup_pending = False
                    calendar.save(update_fields=['cleanup_pending'])

                    total_recovered += 1
                    self.stdout.write("    ✅ Recovered")

                    self.logger.info(
                        f"Recovered stuck cleanup for calendar {calendar.id} "
                        f"({calendar.name}) - was stuck for {stuck_hours:.1f} hours"
                    )

                except Exception as e:
                    total_errors += 1
                    self.stdout.write(
                        self.style.ERROR(f"    ❌ Failed to recover: {e}")
                    )
                    self.logger.error(
                        f"Failed to recover stuck calendar {calendar.id}: {e}"
                    )

        # Summary
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"DRY RUN: Would recover {stuck_calendars.count()} stuck calendars"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Recovery complete: {total_recovered} recovered, {total_errors} errors"
                )
            )

            # Log aggregate stats
            if total_recovered > 0:
                self.logger.info(
                    f"Stuck cleanup recovery completed: "
                    f"{total_recovered} recovered, {total_errors} errors"
                )

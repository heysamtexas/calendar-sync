"""
Django management command for syncing calendars

Usage:
    python manage.py sync_calendars                    # Sync all active calendars
    python manage.py sync_calendars --user-email=...  # Sync calendars for specific user
    python manage.py sync_calendars --calendar-id=... # Sync specific calendar
    python manage.py sync_calendars --dry-run         # Show what would be synced
"""

import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.calendars.models import Calendar
from apps.calendars.services.uuid_sync_engine import sync_calendar_yolo


User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Sync calendars using UUID correlation engine"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-email",
            type=str,
            help="Sync calendars for specific user email",
        )
        parser.add_argument(
            "--calendar-id",
            type=int,
            help="Sync specific calendar by ID",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be synced without actually syncing",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force sync even if calendars appear inactive",
        )

    def handle(self, *args, **options):
        """Execute the sync command"""
        self.stdout.write("Starting calendar sync...")

        try:
            # Get calendars to sync based on options
            calendars = self._get_calendars_to_sync(options)

            if not calendars:
                self.stdout.write(
                    self.style.WARNING("No calendars found to sync")
                )
                return

            # Show what will be synced
            self._show_sync_plan(calendars, options["dry_run"])

            if options["dry_run"]:
                return

            # Execute sync
            self._execute_sync(calendars, options["force"])

        except Exception as e:
            logger.error(f"Sync command failed: {e}")
            raise CommandError(f"Sync failed: {e}")

    def _get_calendars_to_sync(self, options):
        """Get calendars to sync based on command options"""
        if options["calendar_id"]:
            # Sync specific calendar
            try:
                calendar = Calendar.objects.select_related(
                    "calendar_account__user"
                ).get(id=options["calendar_id"])
                return [calendar]
            except Calendar.DoesNotExist:
                raise CommandError(f"Calendar {options['calendar_id']} not found")

        elif options["user_email"]:
            # Sync calendars for specific user
            try:
                user = User.objects.get(email=options["user_email"])
                calendars = Calendar.objects.filter(
                    calendar_account__user=user,
                    sync_enabled=True,
                    calendar_account__is_active=True,
                    cleanup_pending=False,  # Exclude calendars in cleanup state
                ).select_related("calendar_account__user")
                return list(calendars)
            except User.DoesNotExist:
                raise CommandError(f"User {options['user_email']} not found")

        else:
            # Sync all active calendars
            calendars = Calendar.objects.filter(
                sync_enabled=True,
                calendar_account__is_active=True,
                cleanup_pending=False,  # Exclude calendars in cleanup state
            ).select_related("calendar_account__user")
            return list(calendars)

    def _show_sync_plan(self, calendars, is_dry_run):
        """Display what will be synced"""
        self.stdout.write(
            f"\n{'DRY RUN - ' if is_dry_run else ''}Will sync {len(calendars)} calendars:"
        )

        for calendar in calendars:
            status_info = []

            if calendar.calendar_account.is_token_expired:
                status_info.append("TOKEN EXPIRED")
            elif calendar.calendar_account.needs_token_refresh():
                status_info.append("TOKEN REFRESH NEEDED")

            if not calendar.sync_enabled:
                status_info.append("SYNC DISABLED")
            elif calendar.cleanup_pending:
                status_info.append("CLEANUP IN PROGRESS")

            status_str = f" [{', '.join(status_info)}]" if status_info else ""

            self.stdout.write(
                f"  - {calendar.name} ({calendar.calendar_account.email}){status_str}"
            )

        if is_dry_run:
            self.stdout.write(
                self.style.SUCCESS("\nDry run complete. Use without --dry-run to execute.")
            )

    def _execute_sync(self, calendars, force_sync):
        """Execute the actual sync"""
        total_success = 0
        total_errors = 0
        sync_results = {}

        self.stdout.write("\nStarting sync execution...")

        for calendar in calendars:
            try:
                # Check if calendar can be synced
                if not force_sync:
                    can_sync, reason = calendar.can_sync()
                    if not can_sync:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Skipping {calendar.name}: {reason}"
                            )
                        )
                        continue

                # Execute sync
                self.stdout.write(f"Syncing {calendar.name}...")

                with transaction.atomic():
                    result = sync_calendar_yolo(calendar)
                    sync_results[calendar.id] = result
                    total_success += 1

                # Show results
                self._show_sync_result(calendar, result)

            except Exception as e:
                total_errors += 1
                error_msg = f"Failed to sync {calendar.name}: {e}"
                logger.error(error_msg)
                self.stdout.write(self.style.ERROR(error_msg))

        # Show summary
        self._show_sync_summary(total_success, total_errors, sync_results)

    def _show_sync_result(self, calendar, result):
        """Show individual sync result"""
        if result.get("errors"):
            self.stdout.write(
                self.style.WARNING(
                    f"  {calendar.name}: Completed with {len(result['errors'])} errors"
                )
            )
            for error in result["errors"]:
                self.stdout.write(f"    Error: {error}")
        else:
            stats = [
                f"{result.get('user_events_found', 0)} user events",
                f"{result.get('busy_blocks_created', 0)} busy blocks created",
                f"{result.get('our_events_skipped', 0)} our events skipped",
            ]
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {calendar.name}: Success ({', '.join(stats)})"
                )
            )

    def _show_sync_summary(self, total_success, total_errors, sync_results):
        """Show final sync summary"""
        self.stdout.write(f"\n{'='*50}")
        self.stdout.write("SYNC SUMMARY")
        self.stdout.write(f"{'='*50}")

        if total_success > 0:
            self.stdout.write(
                self.style.SUCCESS(f"✓ Successfully synced: {total_success} calendars")
            )

        if total_errors > 0:
            self.stdout.write(
                self.style.ERROR(f"✗ Failed to sync: {total_errors} calendars")
            )

        # Aggregate stats
        total_stats = {
            "calendars_processed": total_success,
            "user_events_found": 0,
            "busy_blocks_created": 0,
            "our_events_skipped": 0,
            "events_processed": 0,
        }

        for result in sync_results.values():
            for key in total_stats:
                if key in result:
                    total_stats[key] += result[key]

        self.stdout.write("\nAggregate Statistics:")
        for key, value in total_stats.items():
            self.stdout.write(f"  {key.replace('_', ' ').title()}: {value}")

        if total_errors == 0 and total_success > 0:
            self.stdout.write(
                self.style.SUCCESS("\n🎉 All calendars synced successfully!")
            )
        elif total_success > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\n⚠️  Sync completed with {total_errors} errors. Check logs for details."
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR("\n❌ Sync failed for all calendars.")
            )

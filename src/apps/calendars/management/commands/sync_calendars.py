"""Django management command for calendar synchronization"""

from django.core.management.base import BaseCommand, CommandError

from apps.calendars.services.sync_engine import sync_all_calendars, sync_calendar


class Command(BaseCommand):
    help = "Synchronize calendar events across Google calendars"

    def add_arguments(self, parser):
        parser.add_argument(
            "--calendar-id",
            type=int,
            help="Sync specific calendar ID only",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Enable verbose output",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be synced without making changes",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )
            # TODO: Implement dry run functionality
            self.stdout.write("Dry run functionality not yet implemented")
            return

        verbose = options["verbose"]

        if verbose:
            self.stdout.write("Starting calendar synchronization...")

        try:
            if options["calendar_id"]:
                self._sync_specific_calendar(options["calendar_id"], verbose)
            else:
                self._sync_all_calendars(verbose)

        except Exception as e:
            raise CommandError(f"Sync failed: {e}") from e

    def _sync_specific_calendar(self, calendar_id: int, verbose: bool):
        """Sync a specific calendar"""
        if verbose:
            self.stdout.write(f"Syncing calendar ID: {calendar_id}")

        results = sync_calendar(calendar_id)

        if results["errors"]:
            self.stdout.write(self.style.ERROR("Sync completed with errors:"))
            for error in results["errors"]:
                self.stdout.write(f"  - {error}")
        else:
            self.stdout.write(
                self.style.SUCCESS("Calendar sync completed successfully")
            )

        self._print_sync_summary(results, verbose)

    def _sync_all_calendars(self, verbose: bool):
        """Sync all active calendars"""
        if verbose:
            self.stdout.write("Syncing all active calendars...")

        results = sync_all_calendars(verbose=verbose)

        if results["errors"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Sync completed with {len(results['errors'])} errors:"
                )
            )
            for error in results["errors"]:
                self.stdout.write(f"  - {error}")
        else:
            self.stdout.write(self.style.SUCCESS("All calendars synced successfully"))

        self._print_sync_summary(results, verbose)

    def _print_sync_summary(self, results: dict, verbose: bool):
        """Print sync results summary"""
        if verbose or results["calendars_processed"] > 0:
            self.stdout.write("\nSync Summary:")
            self.stdout.write("=" * 40)
            self.stdout.write(f"Calendars processed: {results['calendars_processed']}")
            self.stdout.write(f"Events created: {results['events_created']}")
            self.stdout.write(f"Events updated: {results['events_updated']}")
            self.stdout.write(f"Events deleted: {results['events_deleted']}")
            self.stdout.write(f"Busy blocks created: {results['busy_blocks_created']}")
            self.stdout.write(f"Busy blocks updated: {results['busy_blocks_updated']}")
            self.stdout.write(f"Busy blocks deleted: {results['busy_blocks_deleted']}")

            if results["errors"]:
                self.stdout.write(f"Errors: {len(results['errors'])}")

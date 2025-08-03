"""Django management command for resetting calendar busy blocks"""

from django.core.management.base import BaseCommand, CommandError

from apps.calendars.models import Calendar
from apps.calendars.services.sync_engine import reset_calendar_busy_blocks


class Command(BaseCommand):
    help = "Reset calendar by removing all system-created busy blocks"

    def add_arguments(self, parser):
        parser.add_argument(
            "--calendar-id",
            type=int,
            required=True,
            help="Calendar ID to reset",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm the reset operation",
        )

    def handle(self, *args, **options):
        calendar_id = options["calendar_id"]

        # Get calendar info for confirmation
        try:
            calendar = Calendar.objects.get(id=calendar_id)
        except Calendar.DoesNotExist:
            raise CommandError(f"Calendar with ID {calendar_id} not found")

        # Show what will be reset
        self.stdout.write(f"Calendar: {calendar.name}")
        self.stdout.write(f"Google Calendar ID: {calendar.google_calendar_id}")
        self.stdout.write(f"Account: {calendar.calendar_account.email}")
        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                "This will remove ALL system-created busy blocks from this calendar."
            )
        )
        self.stdout.write("User-created events will NOT be affected.")

        # Require confirmation
        if not options["confirm"]:
            self.stdout.write("")
            self.stdout.write(
                self.style.ERROR(
                    "Add --confirm flag to proceed with the reset operation"
                )
            )
            return

        # Perform reset
        self.stdout.write("")
        self.stdout.write("Resetting calendar...")

        try:
            results = reset_calendar_busy_blocks(calendar_id)

            if results["success"]:
                deleted_count = results["deleted_count"]
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully reset calendar '{results['calendar_name']}'"
                    )
                )
                self.stdout.write(f"Removed {deleted_count} busy blocks")
            else:
                self.stdout.write(self.style.ERROR(f"Reset failed: {results['error']}"))

        except Exception as e:
            raise CommandError(f"Reset operation failed: {e}") from e

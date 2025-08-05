"""Django management command for resetting calendar busy blocks"""

from django.core.management.base import BaseCommand, CommandError

from apps.calendars.models import Calendar


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
            # Reset using UUID correlation - find and delete all busy blocks for this calendar
            from apps.calendars.models import EventState
            from apps.calendars.services.google_calendar_client import (
                GoogleCalendarClient,
            )

            # Find all busy blocks created in this calendar
            busy_blocks = EventState.objects.filter(
                calendar=calendar,
                is_busy_block=True,
                status="SYNCED"
            )

            deleted_count = 0
            client = GoogleCalendarClient(calendar.calendar_account)

            # Delete from Google Calendar first
            for busy_block in busy_blocks:
                if busy_block.google_event_id:
                    try:
                        success = client.delete_event(
                            calendar.google_calendar_id,
                            busy_block.google_event_id
                        )
                        if success:
                            deleted_count += 1
                    except Exception as e:
                        self.stdout.write(f"Warning: Failed to delete event {busy_block.google_event_id}: {e}")

            # Mark all busy blocks as deleted in database
            busy_blocks.update(status="DELETED")

            self.stdout.write(
                self.style.SUCCESS(f"Successfully reset calendar '{calendar.name}'")
            )
            self.stdout.write(f"Removed {deleted_count} busy blocks")

        except Exception as e:
            raise CommandError(f"Reset operation failed: {e}") from e

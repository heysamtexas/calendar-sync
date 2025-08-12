"""
Management command to repair EventState records with null start_time/end_time.

This command fixes the data integrity issue where busy blocks were created in Google Calendar
but the local EventState records have null timestamps, making them invisible to database queries.
"""

from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.calendars.models import EventState
from apps.calendars.services.google_calendar_client import GoogleCalendarClient


class Command(BaseCommand):
    help = 'Repair EventState records with null start_time/end_time by fetching data from Google Calendar'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Maximum number of records to process (default: 100)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']

        self.stdout.write("🔍 Looking for EventState records with null timestamps...")

        # Find busy blocks with null start_time
        null_records = EventState.objects.filter(
            is_busy_block=True,
            start_time__isnull=True
        ).select_related('calendar__calendar_account')[:limit]

        total_found = null_records.count()
        self.stdout.write(f"Found {total_found} records with null start_time")

        if total_found == 0:
            self.stdout.write(self.style.SUCCESS("✅ No records need repair!"))
            return

        if dry_run:
            self.stdout.write("\n🧪 DRY RUN MODE - No changes will be made")

        repaired_count = 0
        failed_count = 0
        skipped_count = 0

        # Group by calendar account to minimize API client creation
        account_groups = {}
        for record in null_records:
            account = record.calendar.calendar_account
            if account not in account_groups:
                account_groups[account] = []
            account_groups[account].append(record)

        for account, records in account_groups.items():
            self.stdout.write(f"\n📅 Processing {len(records)} records for {account.email}")

            try:
                client = GoogleCalendarClient(account)

                for record in records:
                    try:
                        # Try to get the event from Google Calendar
                        google_event = client.get_event(
                            record.calendar.google_calendar_id,
                            record.google_event_id
                        )

                        if not google_event:
                            self.stdout.write(f"  ❌ Event not found in Google: {record.google_event_id}")
                            failed_count += 1
                            continue

                        # Extract start and end times
                        start_info = google_event.get('start', {})
                        end_info = google_event.get('end', {})

                        start_time_str = start_info.get('dateTime') or start_info.get('date')
                        end_time_str = end_info.get('dateTime') or end_info.get('date')

                        if not start_time_str or not end_time_str:
                            self.stdout.write(f"  ⚠️  No time info in Google event: {record.title}")
                            skipped_count += 1
                            continue

                        # Parse the datetime strings
                        start_time = self._parse_google_datetime(start_time_str)
                        end_time = self._parse_google_datetime(end_time_str)

                        if not start_time or not end_time:
                            self.stdout.write(f"  ⚠️  Could not parse times: {start_time_str}, {end_time_str}")
                            skipped_count += 1
                            continue

                        # Update the record
                        if not dry_run:
                            with transaction.atomic():
                                record.start_time = start_time
                                record.end_time = end_time
                                record.save(update_fields=['start_time', 'end_time', 'updated_at'])

                        self.stdout.write(f"  ✅ {record.title[:40]}... -> {start_time.strftime('%Y-%m-%d %H:%M')}")
                        repaired_count += 1

                    except Exception as e:
                        self.stdout.write(f"  ❌ Error processing {record.google_event_id}: {e}")
                        failed_count += 1

            except Exception as e:
                self.stdout.write(f"❌ Error with account {account.email}: {e}")
                failed_count += len(records)

        # Summary
        self.stdout.write("\n📊 Summary:")
        self.stdout.write(f"  ✅ Repaired: {repaired_count}")
        self.stdout.write(f"  ❌ Failed: {failed_count}")
        self.stdout.write(f"  ⚠️  Skipped: {skipped_count}")
        self.stdout.write(f"  📝 Total processed: {repaired_count + failed_count + skipped_count}")

        if dry_run:
            self.stdout.write("\n🧪 This was a dry run. Run without --dry-run to apply changes.")
        else:
            if repaired_count > 0:
                self.stdout.write(self.style.SUCCESS(f"\n🎉 Successfully repaired {repaired_count} records!"))
            if failed_count > 0:
                self.stdout.write(self.style.WARNING(f"⚠️  {failed_count} records could not be repaired"))

    def _parse_google_datetime(self, datetime_str):
        """Parse Google Calendar datetime string"""
        try:
            # Handle full datetime with timezone
            if 'T' in datetime_str:
                # Remove timezone suffix for parsing (Google handles timezone)
                if datetime_str.endswith('Z'):
                    datetime_str = datetime_str[:-1] + '+00:00'

                from django.utils.dateparse import parse_datetime
                return parse_datetime(datetime_str)

            # Handle date-only (all-day events)
            else:
                from django.utils.dateparse import parse_date
                date_obj = parse_date(datetime_str)
                if date_obj:
                    from django.utils import timezone
                    return timezone.make_aware(datetime.combine(date_obj, datetime.min.time()))

        except Exception as e:
            self.stdout.write(f"    Error parsing datetime '{datetime_str}': {e}")
            return None

        return None

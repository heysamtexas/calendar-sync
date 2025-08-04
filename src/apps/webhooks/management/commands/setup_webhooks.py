"""
Management command for Guilfoyle's Minimalist Webhook Setup

Simple one-time setup command to register webhooks with Google Calendar.
No complex subscription management - just register and go.
"""

from django.core.management.base import BaseCommand
from django.conf import settings

from apps.calendars.models import Calendar
from apps.calendars.services.google_calendar_client import GoogleCalendarClient


class Command(BaseCommand):
    help = "Setup Google Calendar webhooks for all active calendars (Guilfoyle's minimalist approach)"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--calendar-id',
            type=int,
            help='Setup webhook for specific calendar ID only'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually setting up webhooks'
        )
    
    def handle(self, *args, **options):
        """Setup webhooks for active calendars"""
        
        if not hasattr(settings, 'WEBHOOK_BASE_URL'):
            self.stdout.write(
                self.style.ERROR('WEBHOOK_BASE_URL not configured in settings')
            )
            return
        
        webhook_url = f"{settings.WEBHOOK_BASE_URL}/webhooks/google/"
        self.stdout.write(f"Webhook URL: {webhook_url}")
        
        if options['calendar_id']:
            # Setup webhook for specific calendar
            self._setup_single_calendar(options['calendar_id'], options['dry_run'])
        else:
            # Setup webhooks for all active calendars
            self._setup_all_calendars(options['dry_run'])
    
    def _setup_all_calendars(self, dry_run):
        """Setup webhooks for all active sync-enabled calendars"""
        
        calendars = Calendar.objects.filter(
            sync_enabled=True,
            calendar_account__is_active=True
        ).select_related('calendar_account')
        
        if not calendars.exists():
            self.stdout.write("No active sync-enabled calendars found")
            return
        
        self.stdout.write(f"Found {calendars.count()} active calendars")
        
        success_count = 0
        failure_count = 0
        
        for calendar in calendars:
            if dry_run:
                self.stdout.write(
                    f"[DRY RUN] Would setup webhook for {calendar.name} ({calendar.google_calendar_id})"
                )
                continue
            
            if self._setup_calendar_webhook(calendar):
                success_count += 1
            else:
                failure_count += 1
        
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"Successfully setup {success_count} webhooks")
            )
            if failure_count > 0:
                self.stdout.write(
                    self.style.WARNING(f"Failed to setup {failure_count} webhooks")
                )
    
    def _setup_single_calendar(self, calendar_id, dry_run):
        """Setup webhook for specific calendar"""
        
        try:
            calendar = Calendar.objects.get(
                id=calendar_id,
                sync_enabled=True,
                calendar_account__is_active=True
            )
        except Calendar.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"Calendar {calendar_id} not found or not active")
            )
            return
        
        if dry_run:
            self.stdout.write(
                f"[DRY RUN] Would setup webhook for {calendar.name} ({calendar.google_calendar_id})"
            )
            return
        
        if self._setup_calendar_webhook(calendar):
            self.stdout.write(
                self.style.SUCCESS(f"Successfully setup webhook for {calendar.name}")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"Failed to setup webhook for {calendar.name}")
            )
    
    def _setup_calendar_webhook(self, calendar):
        """Setup webhook for a single calendar"""
        
        try:
            client = GoogleCalendarClient(calendar.calendar_account)
            
            # Use the new webhook setup method
            webhook_info = client.setup_webhook(calendar.google_calendar_id)
            
            if webhook_info:
                self.stdout.write(
                    f"✓ {calendar.name}: Channel {webhook_info['channel_id']} "
                    f"(expires {webhook_info['expires_at'].strftime('%Y-%m-%d %H:%M')})"
                )
                return True
            else:
                self.stdout.write(
                    self.style.ERROR(f"✗ {calendar.name}: Failed to create webhook")
                )
                return False
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"✗ {calendar.name}: {e}")
            )
            return False
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
    help = "Setup Google Calendar webhooks for all active calendars (Guilfoyle's minimalist approach - cron-safe)"
    
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
        parser.add_argument(
            '--check-expiring',
            action='store_true',
            help='Only setup webhooks for calendars with expiring or missing webhooks (cron-safe)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of all webhooks regardless of expiration status'
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
            self._setup_single_calendar(
                options['calendar_id'], 
                options['dry_run'], 
                force=options['force']
            )
        else:
            # Setup webhooks for all active calendars
            self._setup_all_calendars(
                options['dry_run'], 
                check_expiring_only=options['check_expiring'],
                force=options['force']
            )
    
    def _setup_all_calendars(self, dry_run, check_expiring_only=False, force=False):
        """Setup webhooks for all active sync-enabled calendars (cron-safe)"""
        
        calendars = Calendar.objects.filter(
            sync_enabled=True,
            calendar_account__is_active=True
        ).select_related('calendar_account')
        
        if not calendars.exists():
            self.stdout.write("No active sync-enabled calendars found")
            return
        
        # Filter calendars based on webhook status (cron-safe)
        if check_expiring_only and not force:
            # Only process calendars that need webhook renewal
            calendars_to_process = []
            for calendar in calendars:
                if calendar.needs_webhook_renewal():
                    calendars_to_process.append(calendar)
            calendars = calendars_to_process
            
            if not calendars:
                self.stdout.write("No calendars need webhook renewal")
                return
            
            self.stdout.write(f"Found {len(calendars)} calendars needing webhook renewal")
        else:
            self.stdout.write(f"Found {calendars.count()} active calendars")
        
        success_count = 0
        failure_count = 0
        skipped_count = 0
        
        for calendar in calendars:
            if dry_run:
                webhook_status = calendar.get_webhook_status()
                self.stdout.write(
                    f"[DRY RUN] {calendar.name}: {webhook_status}"
                )
                if check_expiring_only and not calendar.needs_webhook_renewal():
                    self.stdout.write(f"[DRY RUN] Would skip (webhook still valid)")
                else:
                    self.stdout.write(f"[DRY RUN] Would setup webhook")
                continue
            
            result = self._setup_calendar_webhook(calendar, force=force)
            if result == 'success':
                success_count += 1
            elif result == 'skipped':
                skipped_count += 1
            else:
                failure_count += 1
        
        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(f"Successfully setup {success_count} webhooks")
            )
            if skipped_count > 0:
                self.stdout.write(f"Skipped {skipped_count} calendars (webhooks still valid)")
            if failure_count > 0:
                self.stdout.write(
                    self.style.WARNING(f"Failed to setup {failure_count} webhooks")
                )
    
    def _setup_single_calendar(self, calendar_id, dry_run, force=False):
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
            webhook_status = calendar.get_webhook_status()
            self.stdout.write(f"[DRY RUN] {calendar.name}: {webhook_status}")
            if not force and calendar.has_active_webhook():
                self.stdout.write("[DRY RUN] Would skip (webhook still valid)")
            else:
                self.stdout.write("[DRY RUN] Would setup webhook")
            return
        
        result = self._setup_calendar_webhook(calendar, force=force)
        if result == 'success':
            self.stdout.write(
                self.style.SUCCESS(f"Successfully setup webhook for {calendar.name}")
            )
        elif result == 'skipped':
            self.stdout.write(f"Skipped {calendar.name} (webhook still valid)")
        else:
            self.stdout.write(
                self.style.ERROR(f"Failed to setup webhook for {calendar.name}")
            )
    
    def _setup_calendar_webhook(self, calendar, force=False):
        """Setup webhook for a single calendar (cron-safe)"""
        
        try:
            client = GoogleCalendarClient(calendar.calendar_account)
            
            # Use the enhanced cron-safe webhook setup method
            webhook_info = client.setup_webhook(calendar.google_calendar_id, force_recreate=force)
            
            if webhook_info:
                if webhook_info.get('skipped'):
                    self.stdout.write(
                        f"⏭ {calendar.name}: Webhook still valid "
                        f"(expires {webhook_info['expires_at'].strftime('%Y-%m-%d %H:%M')})"
                    )
                    return 'skipped'
                else:
                    self.stdout.write(
                        f"✓ {calendar.name}: Channel {webhook_info['channel_id']} "
                        f"(expires {webhook_info['expires_at'].strftime('%Y-%m-%d %H:%M')})"
                    )
                    return 'success'
            else:
                self.stdout.write(
                    self.style.ERROR(f"✗ {calendar.name}: Failed to create webhook")
                )
                return 'failed'
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"✗ {calendar.name}: {e}")
            )
            return 'failed'
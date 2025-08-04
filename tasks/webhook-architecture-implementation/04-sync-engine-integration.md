# Sync Engine Integration - Webhook Implementation

## Webhook Architecture Terminology Reference

For consistent terminology across all documents, see [00-webhook-strategy-overview.md](00-webhook-strategy-overview.md#webhook-architecture-terminology).

## Objective

Integrate webhook-driven calendar synchronization with the existing SyncEngine, creating a hybrid architecture that combines real-time webhook notification processing with polling fallback while maintaining the current cross-calendar busy block system.

## Architecture Integration Strategy

### Hybrid Sync Architecture
```
Webhook-Driven Sync (Primary - 95%)
├── Real-time notifications from Google/Microsoft
├── Targeted calendar sync (single calendar)
├── Immediate cross-calendar busy block updates
└── <2 minute end-to-end sync latency

Polling Fallback Sync (Secondary - 5%)
├── Calendars without webhook support (iCloud)
├── Webhook failure detection and recovery
├── Periodic health check syncs
└── Reduced frequency (1-2 hours vs 15 minutes)

Emergency Full Sync (Nuclear Option - <1%)
├── System health issues
├── Data consistency validation failures
├── User-requested reset operations
└── Daily safety net execution
```

## Enhanced Sync Engine Implementation

### WebhookAwareSyncEngine
```python
# apps/calendars/services/sync_engine.py (enhanced)
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction

from .google_calendar_client import GoogleCalendarClient
from ..models import Calendar, CalendarAccount, Event, SyncLog
from ..constants import BusyBlock

logger = logging.getLogger(__name__)

class WebhookAwareSyncEngine:
    """Enhanced sync engine with webhook integration and polling fallback"""
    
    def __init__(self):
        self.sync_results = {
            "calendars_processed": 0,
            "events_created": 0,
            "events_updated": 0,
            "events_deleted": 0,
            "busy_blocks_created": 0,
            "busy_blocks_updated": 0,
            "busy_blocks_deleted": 0,
            "webhook_triggered": 0,
            "polling_fallback": 0,
            "errors": [],
        }
    
    def sync_from_webhook(self, calendar_id, webhook_data=None):
        """Sync specific calendar triggered by webhook notification"""
        
        try:
            calendar = Calendar.objects.get(
                id=calendar_id,
                sync_enabled=True,
                calendar_account__is_active=True
            )
            
            logger.info(f"Starting webhook-triggered sync for calendar: {calendar.name}")
            
            # Update webhook activity tracking
            calendar.update_webhook_activity()
            
            # Perform targeted sync
            sync_result = self._sync_single_calendar_from_webhook(calendar, webhook_data)
            
            # Update metrics
            self.sync_results["webhook_triggered"] += 1
            self.sync_results["calendars_processed"] += 1
            
            # Create/update cross-calendar busy blocks
            self._update_cross_calendar_busy_blocks_for_calendar(calendar)
            
            logger.info(f"Webhook sync completed for calendar: {calendar.name}")
            return sync_result
            
        except Calendar.DoesNotExist:
            error_msg = f"Calendar {calendar_id} not found for webhook sync"
            logger.error(error_msg)
            self.sync_results["errors"].append(error_msg)
            return None
        except Exception as e:
            error_msg = f"Webhook sync failed for calendar {calendar_id}: {e}"
            logger.error(error_msg)
            self.sync_results["errors"].append(error_msg)
            
            # Increment failure counter
            try:
                calendar = Calendar.objects.get(id=calendar_id)
                calendar.increment_webhook_failures()
            except Calendar.DoesNotExist:
                pass
            
            raise
    
    def sync_calendars_needing_polling(self):
        """Sync calendars that need polling fallback"""
        
        logger.info("Starting polling fallback sync for calendars needing it")
        
        # Get calendars that need polling
        calendars_needing_polling = self._get_calendars_needing_polling()
        
        if not calendars_needing_polling:
            logger.info("No calendars need polling fallback")
            return self.sync_results
        
        logger.info(f"Found {len(calendars_needing_polling)} calendars needing polling fallback")
        
        for calendar in calendars_needing_polling:
            try:
                logger.info(f"Polling sync for calendar: {calendar.name}")
                
                # Perform polling sync
                self._sync_single_calendar_polling(calendar)
                
                # Update polling timestamp
                calendar.last_polling_sync = timezone.now()
                calendar.save(update_fields=['last_polling_sync'])
                
                # Update metrics
                self.sync_results["polling_fallback"] += 1
                self.sync_results["calendars_processed"] += 1
                
            except Exception as e:
                error_msg = f"Polling sync failed for calendar {calendar.name}: {e}"
                logger.error(error_msg)
                self.sync_results["errors"].append(error_msg)
        
        # Update cross-calendar busy blocks for all affected calendars
        self._create_cross_calendar_busy_blocks()
        
        logger.info(f"Polling fallback sync completed: {self.sync_results}")
        return self.sync_results
    
    def sync_all_calendars_legacy(self, verbose: bool = False):
        """Legacy full sync method - kept for emergency use"""
        
        logger.info("Starting legacy full sync (emergency mode)")
        
        active_calendars = Calendar.objects.filter(
            sync_enabled=True, 
            calendar_account__is_active=True
        ).select_related("calendar_account")
        
        if not active_calendars.exists():
            logger.info("No active calendars found")
            return self.sync_results
        
        for calendar in active_calendars:
            try:
                if verbose:
                    logger.info(f"Legacy syncing calendar: {calendar.name}")
                
                self._sync_single_calendar_legacy(calendar)
                self.sync_results["calendars_processed"] += 1
                
            except Exception as e:
                error_msg = f"Legacy sync failed for calendar {calendar.name}: {e}"
                logger.error(error_msg)
                self.sync_results["errors"].append(error_msg)
        
        # Full cross-calendar busy block recreation
        self._create_cross_calendar_busy_blocks()
        
        logger.info(f"Legacy full sync completed: {self.sync_results}")
        return self.sync_results
    
    def _sync_single_calendar_from_webhook(self, calendar, webhook_data=None):
        """Sync single calendar triggered by webhook with targeted processing"""
        
        client = GoogleCalendarClient(calendar.calendar_account)
        
        try:
            # Determine sync window based on webhook data
            if webhook_data and 'resource_state' in webhook_data:
                # For sync messages, do a broader sync
                if webhook_data['resource_state'] == 'sync':
                    time_min = timezone.now() - timedelta(days=7)
                    time_max = timezone.now() + timedelta(days=30)
                else:
                    # For change notifications, sync recent events
                    time_min = timezone.now() - timedelta(days=1)
                    time_max = timezone.now() + timedelta(days=7)
            else:
                # Default webhook sync window
                time_min = timezone.now() - timedelta(days=1) 
                time_max = timezone.now() + timedelta(days=7)
            
            # Fetch recent events from Google Calendar
            google_events = client.list_events(
                calendar.google_calendar_id, 
                time_min=time_min, 
                time_max=time_max
            )
            
            logger.info(f"Webhook sync fetched {len(google_events)} events from Google Calendar")
            
            # Process events with change detection
            events_processed = 0
            for google_event in google_events:
                try:
                    if self._process_google_event_with_change_detection(calendar, google_event):
                        events_processed += 1
                except Exception as e:
                    logger.warning(f"Failed to process event {google_event.get('id', 'unknown')}: {e}")
            
            # Clean up deleted events (limited scope for webhook sync)
            self._cleanup_deleted_events_targeted(calendar, google_events, time_min, time_max)
            
            # Log successful webhook sync
            sync_log = SyncLog.objects.create(
                calendar_account=calendar.calendar_account,
                sync_type="webhook",
                status="in_progress",
                events_processed=events_processed,
            )
            sync_log.mark_completed(status="success")
            
            return {
                'events_processed': events_processed,
                'sync_type': 'webhook',
                'time_window': f"{time_min} to {time_max}"
            }
            
        except Exception as e:
            logger.error(f"Webhook sync failed for calendar {calendar.name}: {e}")
            
            # Log failed sync
            sync_log = SyncLog.objects.create(
                calendar_account=calendar.calendar_account,
                sync_type="webhook",
                status="in_progress",
                events_processed=0,
            )
            sync_log.mark_completed(status="error", error_message=str(e))
            
            raise
    
    def _sync_single_calendar_polling(self, calendar):
        """Sync single calendar using polling method"""
        
        client = GoogleCalendarClient(calendar.calendar_account)
        
        # Use standard polling time range
        time_min = timezone.now() - timedelta(days=30)
        time_max = timezone.now() + timedelta(days=90)
        
        try:
            # Fetch events from Google Calendar
            google_events = client.list_events(
                calendar.google_calendar_id, 
                time_min=time_min, 
                time_max=time_max
            )
            
            logger.info(f"Polling sync fetched {len(google_events)} events from Google Calendar")
            
            # Process each event
            events_processed = 0
            for google_event in google_events:
                try:
                    self._process_google_event(calendar, google_event)
                    events_processed += 1
                except Exception as e:
                    logger.warning(f"Failed to process event {google_event.get('id', 'unknown')}: {e}")
            
            # Clean up deleted events
            self._cleanup_deleted_events(calendar, google_events)
            
            # Log successful polling sync
            sync_log = SyncLog.objects.create(
                calendar_account=calendar.calendar_account,
                sync_type="polling",
                status="in_progress",
                events_processed=events_processed,
            )
            sync_log.mark_completed(status="success")
            
        except Exception as e:
            logger.error(f"Polling sync failed for calendar {calendar.name}: {e}")
            
            # Log failed sync
            sync_log = SyncLog.objects.create(
                calendar_account=calendar.calendar_account,
                sync_type="polling",
                status="in_progress",
                events_processed=0,
            )
            sync_log.mark_completed(status="error", error_message=str(e))
            
            raise
    
    def _sync_single_calendar_legacy(self, calendar):
        """Legacy sync method - full recreation approach"""
        
        # This is the existing sync logic - kept for emergency use
        client = GoogleCalendarClient(calendar.calendar_account)
        
        time_min = timezone.now() - timedelta(days=30)
        time_max = timezone.now() + timedelta(days=90)
        
        try:
            google_events = client.list_events(
                calendar.google_calendar_id, 
                time_min=time_min, 
                time_max=time_max
            )
            
            logger.info(f"Legacy sync fetched {len(google_events)} events from Google Calendar")
            
            events_processed = 0
            for google_event in google_events:
                try:
                    self._process_google_event(calendar, google_event)
                    events_processed += 1
                except Exception as e:
                    logger.warning(f"Failed to process event {google_event.get('id', 'unknown')}: {e}")
            
            self._cleanup_deleted_events(calendar, google_events)
            
            # Log successful legacy sync
            sync_log = SyncLog.objects.create(
                calendar_account=calendar.calendar_account,
                sync_type="full",
                status="in_progress",
                events_processed=events_processed,
            )
            sync_log.mark_completed(status="success")
            
        except Exception as e:
            logger.error(f"Legacy sync failed for calendar {calendar.name}: {e}")
            raise
    
    def _get_calendars_needing_polling(self):
        """Get calendars that need polling fallback"""
        
        # Calendars that need polling:
        # 1. Don't have webhook support
        # 2. Have unhealthy webhook subscriptions
        # 3. Haven't been polled recently and have no recent webhook activity
        
        polling_needed = []
        
        all_calendars = Calendar.objects.filter(
            sync_enabled=True,
            calendar_account__is_active=True
        ).select_related('calendar_account')
        
        for calendar in all_calendars:
            if calendar.needs_polling_fallback():
                polling_needed.append(calendar)
        
        return polling_needed
    
    def _process_google_event_with_change_detection(self, calendar, google_event):
        """Process Google event with change detection for webhook sync"""
        
        google_event_id = google_event.get("id")
        if not google_event_id:
            return False
        
        # Skip system-created busy blocks
        summary = google_event.get("summary", "")
        description = google_event.get("description", "")
        
        if BusyBlock.is_system_busy_block(summary) or BusyBlock.is_system_busy_block(description):
            return False
        
        # Extract event data
        event_data = self._extract_event_data(google_event)
        
        # Skip declined meetings
        if event_data.get("user_declined", False):
            logger.debug(f"Skipping declined meeting: {event_data['title']}")
            return False
        
        # Remove user_declined from stored data
        event_data_to_store = {k: v for k, v in event_data.items() if k != "user_declined"}
        
        # Get or create event with change detection
        try:
            event = Event.objects.get(
                calendar=calendar,
                google_event_id=google_event_id
            )
            
            # Check if event actually changed
            if self._event_needs_update(event, event_data_to_store):
                # Update existing event
                for field, value in event_data_to_store.items():
                    setattr(event, field, value)
                event.save()
                
                logger.debug(f"Updated event: {event.title}")
                self.sync_results["events_updated"] += 1
                return True
            else:
                # No changes needed
                return False
                
        except Event.DoesNotExist:
            # Create new event
            event = Event.objects.create(
                calendar=calendar,
                google_event_id=google_event_id,
                **event_data_to_store
            )
            
            logger.debug(f"Created new event: {event.title}")
            self.sync_results["events_created"] += 1
            return True
    
    def _update_cross_calendar_busy_blocks_for_calendar(self, source_calendar):
        """Update cross-calendar busy blocks for a specific calendar (webhook-triggered)"""
        
        logger.info(f"Updating cross-calendar busy blocks for calendar: {source_calendar.name}")
        
        # Get all target calendars for this user
        target_calendars = Calendar.objects.filter(
            calendar_account__user=source_calendar.calendar_account.user,
            sync_enabled=True,
            calendar_account__is_active=True
        ).exclude(id=source_calendar.id)
        
        if not target_calendars.exists():
            logger.info("No target calendars found for cross-calendar sync")
            return
        
        # Get future events from source calendar (next 90 days)
        time_min = timezone.now()
        time_max = timezone.now() + timedelta(days=90)
        
        source_events = Event.objects.filter(
            calendar=source_calendar,
            start_time__gte=time_min,
            end_time__lte=time_max,
            is_busy_block=False,  # Only real events
        )
        
        # Update busy blocks in each target calendar
        for target_calendar in target_calendars:
            try:
                self._update_busy_blocks_for_target_calendar(
                    source_calendar, target_calendar, source_events
                )
            except Exception as e:
                logger.error(f"Failed to update busy blocks in {target_calendar.name}: {e}")
    
    def _update_busy_blocks_for_target_calendar(self, source_calendar, target_calendar, source_events):
        """Update busy blocks in target calendar from source calendar events"""
        
        try:
            target_client = GoogleCalendarClient(target_calendar.calendar_account)
            
            # Clean up existing busy blocks from this source calendar
            self._cleanup_busy_blocks_from_source(target_client, source_calendar, target_calendar)
            
            # Create new busy blocks for current events
            busy_blocks_created = 0
            for event in source_events:
                try:
                    # Create busy block
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
                    
                    # Save in database
                    busy_block_tag = BusyBlock.generate_tag(target_calendar.id, event.id)
                    
                    Event.objects.create(
                        calendar=target_calendar,
                        google_event_id=google_event["id"],
                        title=busy_block_title,
                        description=busy_block_description,
                        start_time=event.start_time,
                        end_time=event.end_time,
                        is_busy_block=True,
                        is_meeting_invite=event.is_meeting_invite,
                        source_event=event,
                        busy_block_tag=busy_block_tag,
                    )
                    
                    busy_blocks_created += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to create busy block for event {event.title}: {e}")
            
            if busy_blocks_created > 0:
                logger.info(f"Created {busy_blocks_created} busy blocks in {target_calendar.name}")
                self.sync_results["busy_blocks_created"] += busy_blocks_created
            
        except Exception as e:
            logger.error(f"Failed to update busy blocks from {source_calendar.name} to {target_calendar.name}: {e}")
            raise
    
    def _cleanup_busy_blocks_from_source(self, target_client, source_calendar, target_calendar):
        """Clean up existing busy blocks from specific source calendar"""
        
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
                
                # Clean up from database
                Event.objects.filter(
                    calendar=target_calendar,
                    is_busy_block=True,
                    source_event__calendar=source_calendar,
                ).delete()
                
                deleted_count = sum(1 for success in results.values() if success)
                if deleted_count > 0:
                    logger.debug(f"Cleaned up {deleted_count} existing busy blocks")
                    self.sync_results["busy_blocks_deleted"] += deleted_count
                    
        except Exception as e:
            logger.warning(f"Failed to cleanup existing busy blocks: {e}")
    
    def _cleanup_deleted_events_targeted(self, calendar, google_events, time_min, time_max):
        """Clean up deleted events within specific time window (for webhook sync)"""
        
        google_event_ids = {
            event.get("id") for event in google_events if event.get("id")
        }
        
        # Only check events within the sync time window
        deleted_events = Event.objects.filter(
            calendar=calendar,
            is_busy_block=False,
            start_time__gte=time_min,
            end_time__lte=time_max,
        ).exclude(google_event_id__in=google_event_ids)
        
        deleted_count = deleted_events.count()
        if deleted_count > 0:
            logger.info(f"Deleting {deleted_count} events no longer in Google Calendar (targeted cleanup)")
            
            # Before deleting, clean up associated busy blocks
            for event in deleted_events:
                self._cleanup_busy_blocks_for_deleted_event(event)
            
            deleted_events.delete()
            self.sync_results["events_deleted"] += deleted_count
    
    def _cleanup_busy_blocks_for_deleted_event(self, deleted_event):
        """Clean up busy blocks when source event is deleted"""
        
        # Find all busy blocks created from this event
        busy_blocks = Event.objects.filter(
            source_event=deleted_event,
            is_busy_block=True
        ).select_related('calendar', 'calendar__calendar_account')
        
        for busy_block in busy_blocks:
            try:
                # Delete from Google Calendar
                client = GoogleCalendarClient(busy_block.calendar.calendar_account)
                client.delete_event(
                    busy_block.calendar.google_calendar_id, 
                    busy_block.google_event_id
                )
                
                # Delete from database
                busy_block.delete()
                self.sync_results["busy_blocks_deleted"] += 1
                
            except Exception as e:
                logger.warning(f"Failed to delete busy block {busy_block.google_event_id}: {e}")
    
    # Include existing methods from original SyncEngine
    def _process_google_event(self, calendar, google_event):
        """Original event processing method - kept for compatibility"""
        # [Include original implementation from sync_engine.py]
        pass
    
    def _extract_event_data(self, google_event):
        """Original event data extraction - kept for compatibility"""  
        # [Include original implementation from sync_engine.py]
        pass
    
    def _parse_event_time(self, time_data):
        """Original time parsing - kept for compatibility"""
        # [Include original implementation from sync_engine.py]
        pass
    
    def _event_needs_update(self, event, new_data):
        """Original update detection - kept for compatibility"""
        # [Include original implementation from sync_engine.py]
        pass
    
    def _cleanup_deleted_events(self, calendar, google_events):
        """Original cleanup method - kept for compatibility"""
        # [Include original implementation from sync_engine.py]
        pass
    
    def _create_cross_calendar_busy_blocks(self):
        """Original cross-calendar method - kept for full sync scenarios"""
        # [Include original implementation from sync_engine.py]
        pass


# Factory function for backward compatibility
def get_sync_engine():
    """Get appropriate sync engine instance"""
    return WebhookAwareSyncEngine()
```

## LLM Sync Engine Integration Guide

### Primary Integration Points (AI Agents: Use These Entry Points)

#### 1. Webhook-Triggered Sync (MAIN ENTRY POINT)
```python
# ENTRY POINT: When webhook notification received from Google/Microsoft
sync_engine = WebhookAwareSyncEngine()
result = sync_engine.sync_from_webhook(calendar_id, webhook_data)

# EXPECTED RESULT FORMAT: 
# {
#   'events_processed': int,        # Number of events processed
#   'sync_type': 'webhook',         # Always 'webhook' for this method  
#   'time_window': 'datetime_range' # Time range that was synced
# }

# SUCCESS CRITERIA: result is not None and events_processed >= 0
# FAILURE HANDLING: Method raises exception - enable polling fallback
```

#### 2. Polling Fallback Sync (SCHEDULED TASK ENTRY POINT)  
```python
# ENTRY POINT: Cron job or webhook failure recovery
sync_engine = WebhookAwareSyncEngine()
result = sync_engine.sync_calendars_needing_polling()

# PROCESSING LOGIC INSIDE METHOD:
# 1. Find calendars with needs_polling_fallback() == True
# 2. Sync each calendar individually using _sync_single_calendar_polling()
# 3. Update last_polling_sync timestamp on each calendar
# 4. Create cross-calendar busy blocks for all affected calendars

# SUCCESS CRITERIA: result contains calendars_processed > 0
```

#### 3. Emergency Full Sync (ADMIN/RESET ENTRY POINT)
```python
# ENTRY POINT: User-requested reset or system recovery
sync_engine = WebhookAwareSyncEngine()
result = sync_engine.sync_all_calendars_legacy(verbose=True)

# USE CASES:
# - User clicks "Reset All Calendars" button
# - System health check detects major inconsistencies  
# - Manual administrative intervention needed
```

### Sync Method Decision Matrix (LLM: Use This Logic)

| Calendar Condition | Sync Method | Entry Point | Action |
|-------------------|-------------|-------------|---------|
| Active webhook subscription + recent notifications | Webhook-Driven | `sync_from_webhook()` | Process single calendar immediately |
| Active webhook subscription + no recent notifications | Polling + Repair | `sync_calendars_needing_polling()` | Sync calendar AND attempt subscription renewal |
| No webhook subscription | Polling Only | `sync_calendars_needing_polling()` | Standard polling sync |
| Emergency/User-requested | Full Legacy | `sync_all_calendars_legacy()` | Complete system reset |

### Implementation Validation (LLM: Check These Conditions)

#### Before Webhook Sync (`sync_from_webhook`):
```python
# MANDATORY PRE-CONDITIONS:
assert calendar_id is not None, "Calendar ID required"
assert isinstance(calendar_id, int), "Calendar ID must be integer"

# VALIDATE CALENDAR EXISTS AND IS ACTIVE:
calendar = Calendar.objects.get(
    id=calendar_id,
    sync_enabled=True,
    calendar_account__is_active=True
)

# VALIDATE WEBHOOK SUBSCRIPTION EXISTS:
subscription = WebhookSubscription.objects.get(
    calendar=calendar,
    status='active'
)
```

#### After Any Sync Operation:
```python
# MANDATORY POST-CONDITIONS:
assert result is not None, "Sync result must not be None"
assert 'sync_type' in result, "Result must contain sync_type"
assert result['sync_type'] in ['webhook', 'polling', 'full'], "Invalid sync_type"

# UPDATE CALENDAR TIMESTAMPS:
calendar.last_sync = timezone.now()
calendar.save(update_fields=['last_sync'])
```

### Error Recovery Protocol (LLM: Handle These Errors)

| Error Type | Condition | Recovery Action | Fallback |
|------------|-----------|-----------------|----------|
| `Calendar.DoesNotExist` | Invalid calendar_id | Log error, return None | Skip processing |
| `WebhookSubscription.DoesNotExist` | No active subscription | Enable polling fallback | Use polling sync |
| `GoogleCalendarClient` exception | API failure | Increment failure_count | Retry with backoff |
| `DatabaseError` | DB connection issue | Log critical error | Alert administrators |

## Webhook Handler Integration

### Google Webhook Handler
```python
# apps/webhooks/services/google_handler.py
import logging
from django.utils import timezone

from apps.calendars.services.sync_engine import get_sync_engine

logger = logging.getLogger(__name__)

class GoogleWebhookHandler:
    """Process Google Calendar webhook notifications"""
    
    def process_notification(self, notification):
        """Process Google Calendar webhook notification"""
        
        try:
            # Extract information from notification
            webhook_data = self._extract_google_webhook_data(notification)
            
            # Get calendar from subscription
            calendar = notification.subscription.calendar
            
            # Trigger webhook sync
            sync_engine = get_sync_engine()
            sync_result = sync_engine.sync_from_webhook(calendar.id, webhook_data)
            
            if sync_result:
                events_processed = sync_result.get('events_processed', 0)
                logger.info(f"Processed {events_processed} events from Google webhook for calendar {calendar.name}")
                return events_processed, 0  # events_processed, busy_blocks_updated
            else:
                logger.warning(f"No sync result from Google webhook for calendar {calendar.name}")
                return 0, 0
                
        except Exception as e:
            logger.error(f"Failed to process Google webhook notification {notification.id}: {e}")
            raise
    
    def _extract_google_webhook_data(self, notification):
        """Extract useful data from Google webhook notification"""
        
        headers = notification.headers
        
        return {
            'resource_state': headers.get('X-Goog-Resource-State', 'exists'),
            'message_number': headers.get('X-Goog-Message-Number'),
            'resource_id': headers.get('X-Goog-Resource-ID'),
            'resource_uri': headers.get('X-Goog-Resource-URI'),
        }
```

## Management Commands Integration

### Webhook-Aware Sync Commands
```python
# apps/calendars/management/commands/sync_calendars.py (enhanced)
from django.core.management.base import BaseCommand
from apps.calendars.services.sync_engine import get_sync_engine

class Command(BaseCommand):
    help = 'Sync calendars with webhook-aware engine'
    
    def add_arguments(self, parser):
        parser.add_argument('--mode', 
                          choices=['webhook-fallback', 'legacy-full', 'polling-only'], 
                          default='webhook-fallback',
                          help='Sync mode to use')
        parser.add_argument('--calendar-id', type=int, help='Sync specific calendar ID')
        parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    def handle(self, *args, **options):
        sync_engine = get_sync_engine()
        
        if options['calendar_id']:
            # Sync specific calendar via webhook method
            results = sync_engine.sync_from_webhook(options['calendar_id'])
        elif options['mode'] == 'webhook-fallback':
            # Sync calendars needing polling fallback
            results = sync_engine.sync_calendars_needing_polling()
        elif options['mode'] == 'legacy-full':
            # Full legacy sync
            results = sync_engine.sync_all_calendars_legacy(verbose=options['verbose'])
        elif options['mode'] == 'polling-only':
            # Only polling fallback
            results = sync_engine.sync_calendars_needing_polling()
        
        # Output results
        self.stdout.write(f"Sync completed: {results}")
        
        if results['errors']:
            self.stdout.write("Errors occurred:")
            for error in results['errors']:
                self.stdout.write(f"  - {error}")
```

### Enhanced Scheduler Command
```python
# apps/calendars/management/commands/run_scheduler.py (enhanced)
import time
import signal
import threading
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone

class Command(BaseCommand):
    help = 'Run enhanced calendar sync scheduler with webhook support'
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.last_polling_sync = None
        self.last_subscription_maintenance = None
    
    def add_arguments(self, parser):
        parser.add_argument('--polling-interval', type=int, default=3600, 
                          help='Polling fallback interval in seconds (default: 1 hour)')
        parser.add_argument('--maintenance-interval', type=int, default=1800,
                          help='Subscription maintenance interval in seconds (default: 30 minutes)')
    
    def handle(self, *args, **options):
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        polling_interval = options['polling_interval']
        maintenance_interval = options['maintenance_interval']
        
        self.stdout.write(f"Starting enhanced scheduler:")
        self.stdout.write(f"  - Polling fallback every {polling_interval} seconds")
        self.stdout.write(f"  - Subscription maintenance every {maintenance_interval} seconds")
        
        # Start background threads
        polling_thread = threading.Thread(
            target=self._run_polling_sync, 
            args=(polling_interval,),
            daemon=True
        )
        maintenance_thread = threading.Thread(
            target=self._run_subscription_maintenance,
            args=(maintenance_interval,),
            daemon=True
        )
        
        polling_thread.start()
        maintenance_thread.start()
        
        # Main loop
        while self.running:
            time.sleep(1)
        
        self.stdout.write("Scheduler stopped")
    
    def _run_polling_sync(self, interval):
        """Run polling fallback sync in background thread"""
        
        while self.running:
            current_time = time.time()
            
            if (self.last_polling_sync is None or 
                current_time - self.last_polling_sync >= interval):
                
                try:
                    self.stdout.write("Running polling fallback sync...")
                    call_command('sync_calendars', '--mode=webhook-fallback', verbosity=0)
                    self.last_polling_sync = current_time
                    
                except Exception as e:
                    self.stdout.write(f"Polling sync error: {e}")
            
            time.sleep(30)  # Check every 30 seconds
    
    def _run_subscription_maintenance(self, interval):
        """Run subscription maintenance in background thread"""
        
        while self.running:
            current_time = time.time()
            
            if (self.last_subscription_maintenance is None or 
                current_time - self.last_subscription_maintenance >= interval):
                
                try:
                    self.stdout.write("Running subscription maintenance...")
                    call_command('subscription_maintenance', verbosity=0)
                    self.last_subscription_maintenance = current_time
                    
                except Exception as e:
                    self.stdout.write(f"Subscription maintenance error: {e}")
            
            time.sleep(60)  # Check every minute
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.stdout.write(f"Received signal {signum}, shutting down...")
        self.running = False
```

## Integration Testing Framework

### Webhook Sync Testing
```python
# apps/calendars/tests/test_webhook_sync_integration.py
from django.test import TestCase
from unittest.mock import patch, Mock
from django.utils import timezone
from datetime import timedelta

from apps.calendars.models import Calendar, Event
from apps.calendars.services.sync_engine import WebhookAwareSyncEngine
from apps.webhooks.models import WebhookSubscription, WebhookNotification

class WebhookSyncIntegrationTests(TestCase):
    """Test webhook sync engine integration"""
    
    def setUp(self):
        self.calendar = self.create_test_calendar()
        self.sync_engine = WebhookAwareSyncEngine()
        
        # Create webhook subscription
        self.subscription = WebhookSubscription.objects.create(
            calendar=self.calendar,
            provider='google',
            subscription_id='test-subscription',
            webhook_url='https://test.com/webhook',
            resource_id=self.calendar.google_calendar_id,
            expires_at=timezone.now() + timedelta(days=7),
            status='active'
        )
    
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.list_events')
    def test_webhook_triggered_sync(self, mock_list_events):
        """Test that webhook-triggered sync processes events correctly"""
        
        # Mock Google API response
        mock_list_events.return_value = [
            {
                'id': 'webhook_event_123',
                'summary': 'Webhook Test Event',
                'start': {'dateTime': '2024-01-15T10:00:00Z'},
                'end': {'dateTime': '2024-01-15T11:00:00Z'},
            }
        ]
        
        # Trigger webhook sync
        result = self.sync_engine.sync_from_webhook(self.calendar.id)
        
        # Verify sync occurred
        self.assertIsNotNone(result)
        self.assertEqual(result['events_processed'], 1)
        self.assertEqual(result['sync_type'], 'webhook')
        
        # Verify event was created
        event = Event.objects.get(
            calendar=self.calendar,
            google_event_id='webhook_event_123'
        )
        self.assertEqual(event.title, 'Webhook Test Event')
        
        # Verify metrics updated
        self.assertEqual(self.sync_engine.sync_results['webhook_triggered'], 1)
        self.assertEqual(self.sync_engine.sync_results['events_created'], 1)
    
    def test_polling_fallback_detection(self):
        """Test that calendars needing polling fallback are detected"""
        
        # Mark calendar as needing polling fallback
        self.calendar.webhook_failure_streak = 3
        self.calendar.save()
        
        # Get calendars needing polling
        calendars_needing_polling = self.sync_engine._get_calendars_needing_polling()
        
        # Verify calendar is detected
        self.assertIn(self.calendar, calendars_needing_polling)
    
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.list_events')
    def test_cross_calendar_busy_block_update(self, mock_list_events):
        """Test that webhook sync triggers cross-calendar busy block updates"""
        
        # Create target calendar
        target_calendar = self.create_test_calendar(user=self.calendar.calendar_account.user)
        
        # Mock event in source calendar
        mock_list_events.return_value = [
            {
                'id': 'cross_calendar_event',
                'summary': 'Cross Calendar Event',
                'start': {'dateTime': '2024-01-16T14:00:00Z'},
                'end': {'dateTime': '2024-01-16T15:00:00Z'},
            }
        ]
        
        with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.create_busy_block') as mock_create:
            mock_create.return_value = {'id': 'busy_block_123'}
            
            # Trigger webhook sync
            self.sync_engine.sync_from_webhook(self.calendar.id)
        
        # Verify busy block was created in target calendar
        busy_block = Event.objects.get(
            calendar=target_calendar,
            is_busy_block=True,
            source_event__google_event_id='cross_calendar_event'
        )
        
        self.assertTrue(busy_block.title.startswith('🔒'))
        self.assertEqual(self.sync_engine.sync_results['busy_blocks_created'], 1)
```

## Success Criteria

### Integration Success
- **Seamless Webhook Processing**: Webhook notifications trigger targeted calendar sync within 30 seconds
- **Reliable Fallback Operation**: Polling fallback activates automatically for failed webhook calendars
- **Cross-Calendar Consistency**: Busy blocks updated across all calendars within 2 minutes of webhook

### Performance Success  
- **95% Webhook Efficiency**: 95% of syncs triggered by webhooks vs polling
- **API Call Reduction**: >90% reduction in total API calls compared to polling-only approach
- **Sync Latency**: Calendar changes reflected across all calendars within 2 minutes

### Reliability Success
- **Zero Data Loss**: No calendar events or busy blocks lost during sync transitions  
- **Graceful Degradation**: System maintains functionality when webhooks fail
- **Error Recovery**: Failed webhook syncs automatically fall back to polling without user intervention

This sync engine integration provides a robust foundation for webhook-driven calendar synchronization while maintaining compatibility with existing functionality and providing comprehensive fallback mechanisms.

## Related Documentation

**Prerequisites:**
- **Strategy**: Read [00-webhook-strategy-overview.md](00-webhook-strategy-overview.md) for hybrid architecture overview
- **Database**: Implement [01-database-infrastructure.md](01-database-infrastructure.md) for webhook models
- **Endpoints**: Setup [02-webhook-endpoints-and-validation.md](02-webhook-endpoints-and-validation.md) for notification receipt
- **Subscriptions**: Configure [03-subscription-management.md](03-subscription-management.md) for subscription lifecycle

**Next Implementation Steps:**
- **Testing**: Follow [05-testing-and-development-strategy.md](05-testing-and-development-strategy.md) for sync engine testing
- **Deployment**: Reference [06-deployment-and-monitoring.md](06-deployment-and-monitoring.md) for sync monitoring setup
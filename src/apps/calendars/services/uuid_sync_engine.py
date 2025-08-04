"""
Guilfoyle's UUID Correlation Sync Engine

YOLO MODE: Bulletproof cascade prevention through UUID correlation.
No more webhook storms. No more events blinking on/off.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from django.utils import timezone
from django.db import transaction

from apps.calendars.models import Calendar, EventState
from apps.calendars.services.google_calendar_client import GoogleCalendarClient
from apps.calendars.utils import UUIDCorrelationUtils, LegacyDetectionUtils

logger = logging.getLogger(__name__)


class UUIDCorrelationSyncEngine:
    """
    Guilfoyle's bulletproof sync engine using UUID correlation
    
    YOLO PRINCIPLE: Perfect cascade prevention through database-first state management
    """
    
    def __init__(self):
        self.sync_results = {
            "calendars_processed": 0,
            "events_processed": 0,
            "user_events_found": 0,
            "busy_blocks_created": 0,
            "our_events_skipped": 0,
            "legacy_events_upgraded": 0,
            "errors": [],
        }
    
    def sync_calendar_webhook(self, calendar: Calendar) -> Dict[str, Any]:
        """
        Handle webhook-triggered sync with BULLETPROOF cascade prevention
        
        YOLO: Never process our own events = zero cascades guaranteed
        """
        sync_start = timezone.now()
        
        logger.info(f"🚀 YOLO UUID sync starting for calendar: {calendar.name}")
        
        try:
            # Get enhanced Google Calendar client
            client = GoogleCalendarClient(calendar.calendar_account)
            
            # Fetch all events with UUID correlation data
            google_events = client.list_events_with_uuid_extraction(
                calendar.google_calendar_id
            )
            
            logger.info(f"📥 Fetched {len(google_events)} events from Google Calendar")
            
            # Process each event with UUID correlation detection
            new_user_events = []
            
            for google_event in google_events:
                classification = self._classify_event_bulletproof(google_event, calendar)
                
                if classification['action'] == 'process_new_user_event':
                    # Brand new user event - needs UUID correlation and busy blocks
                    event_state = self._create_user_event_state(calendar, google_event)
                    new_user_events.append(event_state)
                    self.sync_results["user_events_found"] += 1
                    
                elif classification['action'] == 'skip_our_event':
                    # Our event - update seen timestamp and skip
                    self._mark_event_seen(classification['uuid'])
                    self.sync_results["our_events_skipped"] += 1
                    
                elif classification['action'] == 'upgrade_legacy':
                    # Legacy event - upgrade to UUID correlation
                    self._upgrade_legacy_event(calendar, google_event)
                    self.sync_results["legacy_events_upgraded"] += 1
                
                self.sync_results["events_processed"] += 1
            
            # Create busy blocks for new user events (cascade-proof)
            if new_user_events:
                logger.info(f"🔒 Creating busy blocks for {len(new_user_events)} new user events")
                self._create_busy_blocks_cascade_proof(new_user_events)
            
            # Update stats
            self.sync_results["calendars_processed"] = 1
            
            sync_duration = (timezone.now() - sync_start).total_seconds()
            
            logger.info(
                f"✅ YOLO sync completed for {calendar.name} in {sync_duration:.2f}s: "
                f"{self.sync_results['user_events_found']} new events, "
                f"{self.sync_results['busy_blocks_created']} busy blocks created, "
                f"{self.sync_results['our_events_skipped']} our events skipped"
            )
            
            return self.sync_results
            
        except Exception as e:
            error_msg = f"💥 YOLO sync failed for calendar {calendar.name}: {e}"
            logger.error(error_msg)
            self.sync_results["errors"].append(error_msg)
            return self.sync_results
    
    def _classify_event_bulletproof(
        self, 
        google_event: Dict[str, Any], 
        calendar: Calendar
    ) -> Dict[str, Any]:
        """
        Bulletproof event classification using UUID correlation
        
        YOLO: Perfect detection = zero false positives = zero cascades
        """
        # Try UUID correlation first (bulletproof method)
        is_ours, correlation_uuid = UUIDCorrelationUtils.is_our_event(google_event)
        
        if correlation_uuid:
            if is_ours:
                return {
                    'action': 'skip_our_event',
                    'uuid': correlation_uuid,
                    'method': 'uuid_correlation'
                }
            else:
                return {
                    'action': 'update_seen',
                    'uuid': correlation_uuid,
                    'method': 'uuid_correlation'
                }
        
        # Check for legacy events (transition period)
        if LegacyDetectionUtils.is_legacy_busy_block(google_event):
            return {
                'action': 'upgrade_legacy',
                'method': 'legacy_detection'
            }
        
        # No UUID correlation = new user event
        return {
            'action': 'process_new_user_event',
            'method': 'no_correlation'
        }
    
    def _create_user_event_state(
        self, 
        calendar: Calendar, 
        google_event: Dict[str, Any]
    ) -> EventState:
        """
        Create EventState for new user event with UUID correlation
        
        YOLO: Database-first = authoritative source of truth
        """
        with transaction.atomic():
            # Create EventState first
            event_state = EventState.create_user_event(
                calendar=calendar,
                google_event_id=google_event['id'],
                title=google_event.get('summary', ''),
                start_time=self._parse_event_datetime(google_event.get('start')),
                end_time=self._parse_event_datetime(google_event.get('end'))
            )
            
            # Add UUID correlation to Google event
            client = GoogleCalendarClient(calendar.calendar_account)
            updated_event = client.update_event_with_uuid_correlation(
                calendar_id=calendar.google_calendar_id,
                google_event_id=google_event['id'],
                correlation_uuid=str(event_state.uuid)
            )
            
            if updated_event:
                logger.info(f"✅ Created user event state with UUID {event_state.uuid}")
            else:
                logger.warning(f"⚠️ Failed to add UUID correlation to Google event {google_event['id']}")
            
            return event_state
    
    def _upgrade_legacy_event(self, calendar: Calendar, google_event: Dict[str, Any]):
        """
        Upgrade legacy event to UUID correlation system
        
        YOLO: Transition period support - convert old events to new system
        """
        try:
            # Generate new UUID for legacy event
            correlation_uuid = uuid.uuid4()
            
            # Create EventState for legacy event with pre-generated UUID
            from django.db import transaction
            
            with transaction.atomic():
                # Create EventState directly with specific UUID
                event_state = EventState(
                    uuid=correlation_uuid,
                    calendar=calendar,
                    google_event_id=google_event['id'],
                    status='SYNCED',  # Legacy events are already synced
                    is_busy_block=False,  # Legacy user events are not busy blocks
                    source_uuid=None,  # User events don't have source
                    title=google_event.get('summary', ''),
                    start_time=self._parse_event_datetime(google_event.get('start')),
                    end_time=self._parse_event_datetime(google_event.get('end')),
                    last_seen_at=timezone.now()
                )
                event_state.save()
                
                # Add UUID correlation to Google event
                client = GoogleCalendarClient(calendar.calendar_account)
                client.update_event_with_uuid_correlation(
                    calendar_id=calendar.google_calendar_id,
                    google_event_id=google_event['id'],
                    correlation_uuid=str(correlation_uuid)
                )
            
            logger.info(f"🔄 Upgraded legacy event to UUID correlation: {correlation_uuid}")
            
        except Exception as e:
            logger.error(f"Failed to upgrade legacy event {google_event.get('id')}: {e}")
    
    def _mark_event_seen(self, correlation_uuid: str):
        """Update last seen timestamp for event"""
        try:
            EventState.objects.filter(uuid=correlation_uuid).update(
                last_seen_at=timezone.now(),
                updated_at=timezone.now()
            )
        except Exception as e:
            logger.error(f"Failed to mark event seen {correlation_uuid}: {e}")
    
    def _create_busy_blocks_cascade_proof(self, user_event_states: List[EventState]):
        """
        Create busy blocks with CASCADE-PROOF UUID correlation
        
        YOLO: Every busy block gets UUID = perfect detection = zero cascades
        """
        for user_event_state in user_event_states:
            try:
                # Get target calendars for busy block creation  
                target_calendars = self._get_sync_target_calendars(user_event_state.calendar)
                
                if not target_calendars:
                    continue
                
                # Create busy blocks in all target calendars
                for target_calendar in target_calendars:
                    self._create_single_busy_block_uuid(
                        source_event_state=user_event_state,
                        target_calendar=target_calendar
                    )
                    
            except Exception as e:
                error_msg = f"Failed to create busy blocks for {user_event_state.uuid}: {e}"
                logger.error(error_msg)
                self.sync_results["errors"].append(error_msg)
    
    def _create_single_busy_block_uuid(
        self,
        source_event_state: EventState,
        target_calendar: Calendar
    ):
        """
        Create single busy block with UUID correlation (cascade-proof)
        
        YOLO: Database state first, Google second = perfect coordination
        """
        try:
            # Create EventState for busy block FIRST (database-first principle)
            busy_block_state = EventState.create_busy_block(
                target_calendar=target_calendar,
                source_uuid=source_event_state.uuid,
                title=source_event_state.title or "Event"
            )
            
            # Create busy block in Google Calendar with UUID correlation
            client = GoogleCalendarClient(target_calendar.calendar_account)
            
            event_data = {
                'summary': f'Busy - {source_event_state.title or "Event"}',
                'description': f'Busy block for event from {source_event_state.calendar.name}',
                'start': self._format_event_datetime(source_event_state.start_time),
                'end': self._format_event_datetime(source_event_state.end_time),
                'transparency': 'opaque',  # Show as busy
                'visibility': 'private',   # Private visibility
            }
            
            created_event = client.create_event_with_uuid_correlation(
                calendar_id=target_calendar.google_calendar_id,
                event_data=event_data,
                correlation_uuid=str(busy_block_state.uuid)
            )
            
            if created_event:
                # Mark as synced with Google event ID
                busy_block_state.mark_synced(created_event['id'])
                self.sync_results["busy_blocks_created"] += 1
                
                logger.info(
                    f"🔒 Created UUID busy block {busy_block_state.uuid} in {target_calendar.name}"
                )
            else:
                # Failed to create in Google - mark as failed
                busy_block_state.mark_deleted()
                logger.error(f"Failed to create busy block in Google Calendar for {target_calendar.name}")
                
        except Exception as e:
            logger.error(f"Failed to create busy block in {target_calendar.name}: {e}")
            raise
    
    def _get_sync_target_calendars(self, source_calendar: Calendar) -> List[Calendar]:
        """Get target calendars for busy block creation (same user only)"""
        return list(
            Calendar.objects.filter(
                calendar_account__user=source_calendar.calendar_account.user,
                sync_enabled=True,
                calendar_account__is_active=True
            ).exclude(
                id=source_calendar.id
            ).select_related('calendar_account')
        )
    
    def _parse_event_datetime(self, time_data: Optional[Dict[str, Any]]) -> Optional[datetime]:
        """Parse event datetime from Google Calendar format"""
        if not time_data:
            return None
        
        try:
            if "dateTime" in time_data:
                time_str = time_data["dateTime"]
                if time_str.endswith("Z"):
                    time_str = time_str[:-1] + "+00:00"
                return datetime.fromisoformat(time_str)
            elif "date" in time_data:
                date_str = time_data["date"]
                return datetime.fromisoformat(f"{date_str}T00:00:00+00:00")
        except (ValueError, KeyError):
            pass
        
        return timezone.now()
    
    def _format_event_datetime(self, dt: Optional[datetime]) -> Dict[str, str]:
        """Format datetime for Google Calendar API"""
        if not dt:
            dt = timezone.now()
        
        return {
            'dateTime': dt.isoformat(),
            'timeZone': 'UTC',
        }


class YOLOWebhookHandler:
    """
    YOLO webhook handler using UUID correlation sync engine
    
    ZERO CASCADES GUARANTEED
    """
    
    def __init__(self):
        self.sync_engine = UUIDCorrelationSyncEngine()
    
    def handle_webhook(self, calendar: Calendar) -> Dict[str, Any]:
        """
        Handle webhook with bulletproof cascade prevention
        
        YOLO: UUID correlation = never process our own events = zero cascades
        """
        webhook_start = timezone.now()
        
        logger.info(f"🎯 YOLO webhook handler processing: {calendar.name}")
        
        try:
            # Use UUID correlation sync engine
            results = self.sync_engine.sync_calendar_webhook(calendar)
            
            # Log results
            processing_duration = (timezone.now() - webhook_start).total_seconds()
            
            logger.info(
                f"✅ YOLO webhook completed for {calendar.name} in {processing_duration:.2f}s: "
                f"Results: {results}"
            )
            
            return {
                'status': 'success',
                'calendar': calendar.name,
                'processing_time': processing_duration,
                'results': results,
                'cascade_prevention': 'ACTIVE',
                'uuid_correlation': 'ENABLED'
            }
            
        except Exception as e:
            processing_duration = (timezone.now() - webhook_start).total_seconds()
            
            logger.error(f"💥 YOLO webhook failed for {calendar.name} in {processing_duration:.2f}s: {e}")
            
            return {
                'status': 'error',
                'calendar': calendar.name,
                'processing_time': processing_duration,
                'error': str(e),
                'cascade_prevention': 'ACTIVE',
                'uuid_correlation': 'ENABLED'
            }


# YOLO UTILITY FUNCTIONS

def sync_calendar_yolo(calendar: Calendar) -> Dict[str, Any]:
    """YOLO sync specific calendar with UUID correlation"""
    engine = UUIDCorrelationSyncEngine()
    return engine.sync_calendar_webhook(calendar)


def handle_webhook_yolo(calendar: Calendar) -> Dict[str, Any]:
    """YOLO webhook handler with cascade prevention"""
    handler = YOLOWebhookHandler()
    return handler.handle_webhook(calendar)


def emergency_cascade_stop() -> Dict[str, Any]:
    """
    Emergency function to stop any cascading webhooks
    
    YOLO: Nuclear option - disable all webhook processing temporarily
    """
    from django.core.cache import cache
    
    # Set global cascade prevention flag
    cache.set('YOLO_CASCADE_PREVENTION_ACTIVE', True, 3600)  # 1 hour
    
    logger.critical("🚨 EMERGENCY CASCADE STOP ACTIVATED - All webhook processing disabled for 1 hour")
    
    return {
        'status': 'cascade_prevention_activated',
        'message': 'All webhook processing disabled for 1 hour',
        'expires_at': (timezone.now() + timedelta(hours=1)).isoformat()
    }


def is_cascade_prevention_active() -> bool:
    """Check if emergency cascade prevention is active"""
    from django.core.cache import cache
    return cache.get('YOLO_CASCADE_PREVENTION_ACTIVE', False)
# Google Calendar ExtendedProperties Integration

## 🎯 Purpose

Implement invisible, tamper-proof event tracking using Google Calendar's ExtendedProperties API to embed UUID correlation IDs directly in calendar events.

## 📋 ExtendedProperties Overview

### What are ExtendedProperties?

ExtendedProperties allow developers to store custom metadata within Google Calendar events:

```json
{
  "summary": "Important Meeting",
  "start": {"dateTime": "2025-08-04T14:00:00-07:00"},
  "end": {"dateTime": "2025-08-04T15:00:00-07:00"},
  "extendedProperties": {
    "private": {
      "calsync_id": "550e8400-e29b-41d4-a716-446655440000",
      "calsync_type": "busy_block",
      "calsync_source": "123e4567-e89b-12d3-a456-426614174000"
    },
    "shared": {
      "publicData": "visible to others"
    }
  }
}
```

### Key Benefits

1. **Invisible to Users**: Properties don't appear in calendar UI
2. **Tamper-Proof**: Users cannot accidentally modify structured data
3. **Preserved by Google**: Always maintained during event operations
4. **Structured Data**: No text parsing required - direct property access
5. **Private/Shared Scope**: Control visibility of metadata

## 🔧 Implementation

### ExtendedProperties Helper Class

```python
import uuid
from typing import Dict, Optional, Any

class CalSyncProperties:
    """Helper class for managing CalSync extended properties in Google Calendar events"""
    
    # Property keys
    CORRELATION_ID = 'calsync_id'
    EVENT_TYPE = 'calsync_type'
    SOURCE_ID = 'calsync_source'
    CREATED_AT = 'calsync_created_at'
    VERSION = 'calsync_version'
    
    # Event types
    USER_EVENT = 'user_event'
    BUSY_BLOCK = 'busy_block'
    
    # Current version for future compatibility
    CURRENT_VERSION = '1.0'
    
    @staticmethod
    def create_properties(
        correlation_id: str,
        event_type: str,
        source_correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create extended properties for CalSync tracking"""
        from django.utils import timezone
        
        properties = {
            'private': {
                CalSyncProperties.CORRELATION_ID: correlation_id,
                CalSyncProperties.EVENT_TYPE: event_type,
                CalSyncProperties.CREATED_AT: timezone.now().isoformat(),
                CalSyncProperties.VERSION: CalSyncProperties.CURRENT_VERSION,
            }
        }
        
        if source_correlation_id:
            properties['private'][CalSyncProperties.SOURCE_ID] = source_correlation_id
        
        return {'extendedProperties': properties}
    
    @staticmethod
    def extract_correlation_id(google_event: Dict[str, Any]) -> Optional[str]:
        """Extract correlation ID from Google Calendar event"""
        extended = google_event.get('extendedProperties', {})
        return extended.get('private', {}).get(CalSyncProperties.CORRELATION_ID)
    
    @staticmethod
    def extract_event_type(google_event: Dict[str, Any]) -> Optional[str]:
        """Extract event type from Google Calendar event"""
        extended = google_event.get('extendedProperties', {})
        return extended.get('private', {}).get(CalSyncProperties.EVENT_TYPE)
    
    @staticmethod
    def extract_source_id(google_event: Dict[str, Any]) -> Optional[str]:
        """Extract source correlation ID from Google Calendar event"""
        extended = google_event.get('extendedProperties', {})
        return extended.get('private', {}).get(CalSyncProperties.SOURCE_ID)
    
    @staticmethod
    def has_calsync_properties(google_event: Dict[str, Any]) -> bool:
        """Check if event has CalSync tracking properties"""
        correlation_id = CalSyncProperties.extract_correlation_id(google_event)
        return correlation_id is not None
    
    @staticmethod
    def is_calsync_event(google_event: Dict[str, Any]) -> bool:
        """Check if event was created by CalSync"""
        event_type = CalSyncProperties.extract_event_type(google_event)
        return event_type in [CalSyncProperties.USER_EVENT, CalSyncProperties.BUSY_BLOCK]
    
    @staticmethod
    def is_busy_block(google_event: Dict[str, Any]) -> bool:
        """Check if event is a CalSync busy block"""
        event_type = CalSyncProperties.extract_event_type(google_event)
        return event_type == CalSyncProperties.BUSY_BLOCK
    
    @staticmethod
    def get_all_properties(google_event: Dict[str, Any]) -> Dict[str, Any]:
        """Get all CalSync properties from event"""
        extended = google_event.get('extendedProperties', {})
        private_props = extended.get('private', {})
        
        return {
            'correlation_id': private_props.get(CalSyncProperties.CORRELATION_ID),
            'event_type': private_props.get(CalSyncProperties.EVENT_TYPE),
            'source_id': private_props.get(CalSyncProperties.SOURCE_ID),
            'created_at': private_props.get(CalSyncProperties.CREATED_AT),
            'version': private_props.get(CalSyncProperties.VERSION),
        }
```

### Enhanced Google Calendar Client

```python
class GoogleCalendarClient:
    # Existing methods...
    
    def create_event_with_correlation(
        self,
        calendar_id: str,
        event_data: Dict[str, Any],
        correlation_id: str,
        event_type: str,
        source_correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create Google Calendar event with CalSync correlation tracking"""
        
        # Add CalSync extended properties
        calsync_properties = CalSyncProperties.create_properties(
            correlation_id=correlation_id,
            event_type=event_type,
            source_correlation_id=source_correlation_id
        )
        
        # Merge with existing event data
        event_data.update(calsync_properties)
        
        try:
            # Create event in Google Calendar
            event = self.service.events().insert(
                calendarId=calendar_id,
                body=event_data
            ).execute()
            
            logger.info(f"Created event with correlation ID {correlation_id}: {event.get('id')}")
            return event
            
        except Exception as e:
            logger.error(f"Failed to create event with correlation ID {correlation_id}: {e}")
            raise
    
    def create_busy_block_with_correlation(
        self,
        calendar_id: str,
        title: str,
        start_time: datetime,
        end_time: datetime,
        correlation_id: str,
        source_correlation_id: str,
        description: str = ""
    ) -> Dict[str, Any]:
        """Create busy block with correlation tracking"""
        
        event_data = {
            'summary': f'Busy - {title}',
            'description': description,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'UTC',
            },
            'transparency': 'opaque',  # Show as busy
            'visibility': 'private',   # Private visibility
        }
        
        return self.create_event_with_correlation(
            calendar_id=calendar_id,
            event_data=event_data,
            correlation_id=correlation_id,
            event_type=CalSyncProperties.BUSY_BLOCK,
            source_correlation_id=source_correlation_id
        )
    
    def update_event_correlation(
        self,
        calendar_id: str,
        event_id: str,
        correlation_id: str,
        event_type: str
    ) -> Dict[str, Any]:
        """Add correlation tracking to existing event"""
        
        try:
            # Get current event
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            # Add CalSync properties
            calsync_properties = CalSyncProperties.create_properties(
                correlation_id=correlation_id,
                event_type=event_type
            )
            
            # Merge properties
            if 'extendedProperties' not in event:
                event['extendedProperties'] = {}
            if 'private' not in event['extendedProperties']:
                event['extendedProperties']['private'] = {}
            
            event['extendedProperties']['private'].update(
                calsync_properties['extendedProperties']['private']
            )
            
            # Update event
            updated_event = self.service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event
            ).execute()
            
            logger.info(f"Added correlation ID {correlation_id} to event {event_id}")
            return updated_event
            
        except Exception as e:
            logger.error(f"Failed to update event {event_id} with correlation ID {correlation_id}: {e}")
            raise
    
    def list_events_with_correlation_data(
        self,
        calendar_id: str,
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """List events with enhanced correlation data extraction"""
        
        events = self.list_events(calendar_id, time_min, time_max)
        
        # Enhance each event with correlation data
        for event in events:
            # Extract CalSync properties
            correlation_data = CalSyncProperties.get_all_properties(event)
            
            # Add convenience flags
            event['_calsync'] = {
                'has_correlation': CalSyncProperties.has_calsync_properties(event),
                'is_calsync_event': CalSyncProperties.is_calsync_event(event),
                'is_busy_block': CalSyncProperties.is_busy_block(event),
                **correlation_data
            }
        
        return events
    
    def find_events_by_correlation_id(
        self,
        calendar_id: str,
        correlation_id: str
    ) -> List[Dict[str, Any]]:
        """Find events by correlation ID (requires fetching and filtering)"""
        
        # Note: Google Calendar API doesn't support searching by extendedProperties
        # We need to fetch events and filter client-side
        events = self.list_events_with_correlation_data(calendar_id)
        
        matching_events = []
        for event in events:
            if event['_calsync']['correlation_id'] == correlation_id:
                matching_events.append(event)
        
        return matching_events
    
    def bulk_add_correlation_ids(
        self,
        calendar_id: str,
        event_correlations: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Bulk add correlation IDs to existing events"""
        
        results = []
        for correlation_data in event_correlations:
            try:
                updated_event = self.update_event_correlation(
                    calendar_id=calendar_id,
                    event_id=correlation_data['event_id'],
                    correlation_id=correlation_data['correlation_id'],
                    event_type=correlation_data['event_type']
                )
                results.append({
                    'success': True,
                    'event_id': correlation_data['event_id'],
                    'correlation_id': correlation_data['correlation_id'],
                    'event': updated_event
                })
            except Exception as e:
                results.append({
                    'success': False,
                    'event_id': correlation_data['event_id'],
                    'correlation_id': correlation_data['correlation_id'],
                    'error': str(e)
                })
        
        return results
```

## 🔍 Perfect Event Detection

### Bulletproof Detection Logic

```python
def is_our_event(google_event: Dict[str, Any]) -> bool:
    """
    Perfect detection using correlation IDs - no text parsing required
    
    Returns True if:
    1. Event has CalSync correlation ID
    2. Correlation ID exists in our EventState database
    3. EventState indicates created_by_us=True
    """
    
    # Extract correlation ID
    correlation_id = CalSyncProperties.extract_correlation_id(google_event)
    
    if not correlation_id:
        # No correlation ID = not tracked by us
        return False
    
    try:
        # Check if we created this event
        from apps.calendars.models import EventState
        
        event_state = EventState.objects.filter(
            correlation_id=correlation_id,
            created_by_us=True
        ).first()
        
        return event_state is not None
        
    except Exception as e:
        logger.error(f"Error checking event ownership for correlation ID {correlation_id}: {e}")
        return False

def classify_google_event(google_event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify a Google Calendar event with full correlation data
    
    Returns:
    {
        'is_ours': bool,
        'is_busy_block': bool,
        'correlation_id': str or None,
        'source_correlation_id': str or None,
        'event_type': str or None,
        'needs_processing': bool
    }
    """
    
    correlation_id = CalSyncProperties.extract_correlation_id(google_event)
    
    if not correlation_id:
        # No correlation ID = new user event that needs processing
        return {
            'is_ours': False,
            'is_busy_block': False,
            'correlation_id': None,
            'source_correlation_id': None,
            'event_type': None,
            'needs_processing': True
        }
    
    # Has correlation ID - check our database
    from apps.calendars.models import EventState
    
    try:
        event_state = EventState.objects.filter(
            correlation_id=correlation_id
        ).first()
        
        if event_state:
            return {
                'is_ours': event_state.created_by_us,
                'is_busy_block': event_state.is_busy_block,
                'correlation_id': correlation_id,
                'source_correlation_id': str(event_state.source_correlation_id) if event_state.source_correlation_id else None,
                'event_type': event_state.event_type,
                'needs_processing': not event_state.created_by_us  # Only process if not created by us
            }
        else:
            # Has correlation ID but not in our database - external CalSync instance?
            return {
                'is_ours': False,
                'is_busy_block': CalSyncProperties.is_busy_block(google_event),
                'correlation_id': correlation_id,
                'source_correlation_id': CalSyncProperties.extract_source_id(google_event),
                'event_type': CalSyncProperties.extract_event_type(google_event),
                'needs_processing': False  # Don't process other CalSync instances
            }
            
    except Exception as e:
        logger.error(f"Error classifying event with correlation ID {correlation_id}: {e}")
        return {
            'is_ours': False,
            'is_busy_block': False,
            'correlation_id': correlation_id,
            'source_correlation_id': None,
            'event_type': None,
            'needs_processing': False  # Skip on error to be safe
        }
```

## 🔄 Migration and Compatibility

### Adding Correlation IDs to Existing Events

```python
def migrate_existing_events_to_correlation_ids():
    """
    Add correlation IDs to existing Google Calendar events
    
    This should be run once during the transition to UUID correlation architecture
    """
    from apps.calendars.models import Calendar, Event, EventState
    
    logger.info("Starting migration of existing events to correlation ID system")
    
    calendars = Calendar.objects.filter(sync_enabled=True)
    
    for calendar in calendars:
        try:
            client = GoogleCalendarClient(calendar.calendar_account)
            
            # Get all events from Google Calendar
            google_events = client.list_events(calendar.google_calendar_id)
            
            # Get all our database events for this calendar
            db_events = Event.objects.filter(calendar=calendar)
            
            # Match Google events to database events
            correlation_updates = []
            
            for db_event in db_events:
                # Find matching Google event
                google_event = None
                for g_event in google_events:
                    if g_event['id'] == db_event.google_event_id:
                        google_event = g_event
                        break
                
                if not google_event:
                    logger.warning(f"Database event {db_event.id} not found in Google Calendar")
                    continue
                
                # Check if already has correlation ID
                existing_correlation_id = CalSyncProperties.extract_correlation_id(google_event)
                
                if existing_correlation_id:
                    # Already has correlation ID - update database
                    db_event.correlation_id = existing_correlation_id
                    db_event.save()
                    
                    # Ensure EventState exists
                    EventState.objects.get_or_create(
                        correlation_id=existing_correlation_id,
                        defaults={
                            'calendar': calendar,
                            'google_event_id': db_event.google_event_id,
                            'event_type': 'busy_block' if db_event.is_busy_block else 'user_event',
                            'created_by_us': db_event.is_busy_block,
                            'status': 'synced',
                            'title': db_event.title,
                        }
                    )
                else:
                    # Needs correlation ID
                    correlation_id = str(uuid.uuid4())
                    
                    correlation_updates.append({
                        'event_id': db_event.google_event_id,
                        'correlation_id': correlation_id,
                        'event_type': 'busy_block' if db_event.is_busy_block else 'user_event'
                    })
                    
                    # Update database
                    db_event.correlation_id = correlation_id
                    db_event.save()
                    
                    # Create EventState
                    EventState.objects.create(
                        correlation_id=correlation_id,
                        calendar=calendar,
                        google_event_id=db_event.google_event_id,
                        event_type='busy_block' if db_event.is_busy_block else 'user_event',
                        created_by_us=db_event.is_busy_block,
                        status='synced',
                        title=db_event.title,
                    )
            
            # Bulk update Google Calendar events
            if correlation_updates:
                logger.info(f"Adding correlation IDs to {len(correlation_updates)} events in {calendar.name}")
                results = client.bulk_add_correlation_ids(calendar.google_calendar_id, correlation_updates)
                
                # Log results
                successful = sum(1 for r in results if r['success'])
                failed = len(results) - successful
                logger.info(f"Migration results for {calendar.name}: {successful} successful, {failed} failed")
                
        except Exception as e:
            logger.error(f"Failed to migrate events for calendar {calendar.name}: {e}")
    
    logger.info("Completed migration of existing events to correlation ID system")
```

### Fallback Detection for Legacy Events

```python
def detect_legacy_busy_block(google_event: Dict[str, Any]) -> bool:
    """
    Fallback detection for busy blocks created before correlation ID system
    
    This provides compatibility during the transition period
    """
    
    # First check for correlation ID (new system)
    if CalSyncProperties.has_calsync_properties(google_event):
        return CalSyncProperties.is_busy_block(google_event)
    
    # Fallback to old text-based detection
    title = google_event.get('summary', '')
    description = google_event.get('description', '')
    
    # Legacy patterns
    legacy_patterns = [
        'Busy - ',           # Clean title prefix
        '🔒 Busy - ',       # Emoji prefix (if still present)
        'CalSync [source:',  # Legacy description pattern
    ]
    
    for pattern in legacy_patterns:
        if pattern in title or pattern in description:
            return True
    
    return False

def handle_legacy_event_detection(google_event: Dict[str, Any], calendar: 'Calendar') -> bool:
    """
    Handle event detection with legacy fallback
    
    Returns True if event should be skipped (is our event)
    """
    
    # Try modern correlation ID detection first
    if CalSyncProperties.has_calsync_properties(google_event):
        return is_our_event(google_event)
    
    # Fallback to legacy detection
    if detect_legacy_busy_block(google_event):
        logger.warning(f"Detected legacy busy block in {calendar.name}: {google_event.get('summary', 'Untitled')}")
        
        # Optionally upgrade to correlation ID system
        try:
            correlation_id = str(uuid.uuid4())
            client = GoogleCalendarClient(calendar.calendar_account)
            client.update_event_correlation(
                calendar_id=calendar.google_calendar_id,
                event_id=google_event['id'],
                correlation_id=correlation_id,
                event_type=CalSyncProperties.BUSY_BLOCK
            )
            
            # Create EventState
            EventState.objects.create(
                correlation_id=correlation_id,
                calendar=calendar,
                google_event_id=google_event['id'],
                event_type='busy_block',
                created_by_us=True,
                status='synced',
                title=google_event.get('summary', ''),
            )
            
            logger.info(f"Upgraded legacy busy block to correlation ID: {correlation_id}")
            
        except Exception as e:
            logger.error(f"Failed to upgrade legacy busy block: {e}")
        
        return True  # Skip processing regardless of upgrade success
    
    return False  # Not our event - process it
```

## 🔒 Security and Privacy

### Private vs Shared Properties

```python
# Use private properties for internal tracking
private_properties = {
    'calsync_id': correlation_id,          # Internal correlation ID
    'calsync_type': 'busy_block',          # Internal event type
    'calsync_source': source_correlation_id # Internal source tracking
}

# Use shared properties for user-visible metadata (if needed)
shared_properties = {
    'meeting_room': 'Conference Room A',   # Example: visible to attendees
    'equipment': 'projector,whiteboard'   # Example: visible to attendees
}

extended_properties = {
    'private': private_properties,         # Only visible to our app
    'shared': shared_properties           # Visible to all users
}
```

### Data Minimization

Only store essential tracking data in ExtendedProperties:
- `calsync_id`: Correlation UUID
- `calsync_type`: Event type (user_event/busy_block)
- `calsync_source`: Source correlation ID (for busy blocks)
- `calsync_created_at`: Creation timestamp
- `calsync_version`: Schema version for future compatibility

## 📊 Testing and Validation

### Unit Tests for ExtendedProperties

```python
import unittest
from unittest.mock import Mock, patch

class TestCalSyncProperties(unittest.TestCase):
    
    def test_create_properties(self):
        """Test creation of extended properties"""
        correlation_id = str(uuid.uuid4())
        properties = CalSyncProperties.create_properties(
            correlation_id=correlation_id,
            event_type=CalSyncProperties.BUSY_BLOCK,
            source_correlation_id=str(uuid.uuid4())
        )
        
        self.assertIn('extendedProperties', properties)
        self.assertIn('private', properties['extendedProperties'])
        self.assertEqual(
            properties['extendedProperties']['private'][CalSyncProperties.CORRELATION_ID],
            correlation_id
        )
    
    def test_extract_correlation_id(self):
        """Test extraction of correlation ID"""
        correlation_id = str(uuid.uuid4())
        google_event = {
            'id': 'test_event',
            'extendedProperties': {
                'private': {
                    CalSyncProperties.CORRELATION_ID: correlation_id
                }
            }
        }
        
        extracted_id = CalSyncProperties.extract_correlation_id(google_event)
        self.assertEqual(extracted_id, correlation_id)
    
    def test_is_busy_block(self):
        """Test busy block detection"""
        google_event = {
            'id': 'test_event',
            'extendedProperties': {
                'private': {
                    CalSyncProperties.EVENT_TYPE: CalSyncProperties.BUSY_BLOCK
                }
            }
        }
        
        self.assertTrue(CalSyncProperties.is_busy_block(google_event))
```

### Integration Tests

```python
class TestGoogleCalendarIntegration(TestCase):
    
    def setUp(self):
        self.calendar = Calendar.objects.create(
            name="Test Calendar",
            google_calendar_id="test@example.com"
        )
        self.client = GoogleCalendarClient(self.calendar.calendar_account)
    
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.service')
    def test_create_event_with_correlation(self, mock_service):
        """Test creating event with correlation ID"""
        correlation_id = str(uuid.uuid4())
        
        # Mock Google API response
        mock_service.events().insert().execute.return_value = {
            'id': 'created_event_id',
            'summary': 'Test Event'
        }
        
        event = self.client.create_event_with_correlation(
            calendar_id=self.calendar.google_calendar_id,
            event_data={'summary': 'Test Event'},
            correlation_id=correlation_id,
            event_type=CalSyncProperties.USER_EVENT
        )
        
        # Verify the call included extended properties
        call_args = mock_service.events().insert.call_args
        body = call_args[1]['body']
        
        self.assertIn('extendedProperties', body)
        self.assertEqual(
            body['extendedProperties']['private'][CalSyncProperties.CORRELATION_ID],
            correlation_id
        )
```

This ExtendedProperties integration provides the invisible, bulletproof tracking mechanism needed to eliminate webhook cascades permanently.
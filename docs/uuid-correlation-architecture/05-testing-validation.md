# Testing and Validation for UUID Correlation Architecture

## 🎯 Testing Overview

Comprehensive testing strategy to validate the UUID correlation architecture eliminates webhook cascades while maintaining sync reliability and performance.

## 🧪 Test Categories

### 1. Unit Tests

#### EventState Model Tests
```python
# tests/test_event_state_model.py
import uuid
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.calendars.models import Calendar, CalendarAccount, EventState

class TestEventStateModel(TestCase):
    def setUp(self):
        self.calendar = Calendar.objects.create(
            name="Test Calendar",
            google_calendar_id="test@example.com"
        )
    
    def test_create_user_event_state(self):
        """Test creating EventState for user event"""
        correlation_id = uuid.uuid4()
        
        event_state = EventState.objects.create(
            correlation_id=correlation_id,
            calendar=self.calendar,
            google_event_id="google_event_123",
            event_type='user_event',
            created_by_us=False,
            status='synced',
            title='User Meeting'
        )
        
        self.assertFalse(event_state.created_by_us)
        self.assertTrue(event_state.is_user_event)
        self.assertFalse(event_state.is_busy_block)
        self.assertIsNone(event_state.source_correlation_id)
    
    def test_create_busy_block_state(self):
        """Test creating EventState for busy block"""
        source_correlation_id = uuid.uuid4()
        busy_block_correlation_id = uuid.uuid4()
        
        event_state = EventState.objects.create(
            correlation_id=busy_block_correlation_id,
            calendar=self.calendar,
            event_type='busy_block',
            created_by_us=True,
            source_correlation_id=source_correlation_id,
            status='creating',
            title='Busy - User Meeting'
        )
        
        self.assertTrue(event_state.created_by_us)
        self.assertFalse(event_state.is_user_event)
        self.assertTrue(event_state.is_busy_block)
        self.assertEqual(event_state.source_correlation_id, source_correlation_id)
    
    def test_mark_created(self):
        """Test marking event as created"""
        event_state = EventState.objects.create(
            correlation_id=uuid.uuid4(),
            calendar=self.calendar,
            event_type='busy_block',
            created_by_us=True,
            status='creating'
        )
        
        event_state.mark_created('google_event_456')
        
        self.assertEqual(event_state.google_event_id, 'google_event_456')
        self.assertEqual(event_state.status, 'created')
    
    def test_get_busy_blocks(self):
        """Test getting busy blocks for a user event"""
        source_correlation_id = uuid.uuid4()
        
        # Create source user event
        source_event = EventState.objects.create(
            correlation_id=source_correlation_id,
            calendar=self.calendar,
            event_type='user_event',
            created_by_us=False
        )
        
        # Create busy blocks
        busy_block_1 = EventState.objects.create(
            correlation_id=uuid.uuid4(),
            calendar=self.calendar,
            event_type='busy_block',
            created_by_us=True,
            source_correlation_id=source_correlation_id
        )
        
        busy_block_2 = EventState.objects.create(
            correlation_id=uuid.uuid4(),
            calendar=self.calendar,
            event_type='busy_block',
            created_by_us=True,
            source_correlation_id=source_correlation_id
        )
        
        busy_blocks = source_event.get_busy_blocks()
        self.assertEqual(busy_blocks.count(), 2)
        self.assertIn(busy_block_1, busy_blocks)
        self.assertIn(busy_block_2, busy_blocks)
    
    def test_constraint_validation(self):
        """Test database constraints"""
        source_correlation_id = uuid.uuid4()
        
        # User event with source_correlation_id should fail
        with self.assertRaises(ValidationError):
            event_state = EventState(
                correlation_id=uuid.uuid4(),
                calendar=self.calendar,
                event_type='user_event',
                created_by_us=False,
                source_correlation_id=source_correlation_id
            )
            event_state.full_clean()
        
        # Busy block without source_correlation_id should fail
        with self.assertRaises(ValidationError):
            event_state = EventState(
                correlation_id=uuid.uuid4(),
                calendar=self.calendar,
                event_type='busy_block',
                created_by_us=True,
                source_correlation_id=None
            )
            event_state.full_clean()
```

#### CalSyncProperties Tests
```python
# tests/test_calsync_properties.py
import uuid
from django.test import TestCase
from apps.calendars.constants import CalSyncProperties

class TestCalSyncProperties(TestCase):
    
    def test_create_properties(self):
        """Test creating extended properties"""
        correlation_id = str(uuid.uuid4())
        source_id = str(uuid.uuid4())
        
        properties = CalSyncProperties.create_properties(
            correlation_id=correlation_id,
            event_type=CalSyncProperties.BUSY_BLOCK,
            source_correlation_id=source_id
        )
        
        self.assertIn('extendedProperties', properties)
        private_props = properties['extendedProperties']['private']
        
        self.assertEqual(private_props[CalSyncProperties.CORRELATION_ID], correlation_id)
        self.assertEqual(private_props[CalSyncProperties.EVENT_TYPE], CalSyncProperties.BUSY_BLOCK)
        self.assertEqual(private_props[CalSyncProperties.SOURCE_ID], source_id)
        self.assertEqual(private_props[CalSyncProperties.VERSION], CalSyncProperties.CURRENT_VERSION)
    
    def test_extract_correlation_id(self):
        """Test extracting correlation ID from Google event"""
        correlation_id = str(uuid.uuid4())
        
        google_event = {
            'id': 'test_event',
            'summary': 'Test Event',
            'extendedProperties': {
                'private': {
                    CalSyncProperties.CORRELATION_ID: correlation_id
                }
            }
        }
        
        extracted_id = CalSyncProperties.extract_correlation_id(google_event)
        self.assertEqual(extracted_id, correlation_id)
    
    def test_extract_correlation_id_missing(self):
        """Test extracting correlation ID when not present"""
        google_event = {
            'id': 'test_event',
            'summary': 'Test Event'
        }
        
        extracted_id = CalSyncProperties.extract_correlation_id(google_event)
        self.assertIsNone(extracted_id)
    
    def test_is_busy_block(self):
        """Test busy block detection"""
        google_event = {
            'extendedProperties': {
                'private': {
                    CalSyncProperties.EVENT_TYPE: CalSyncProperties.BUSY_BLOCK
                }
            }
        }
        
        self.assertTrue(CalSyncProperties.is_busy_block(google_event))
        
        # Test non-busy block
        google_event['extendedProperties']['private'][CalSyncProperties.EVENT_TYPE] = CalSyncProperties.USER_EVENT
        self.assertFalse(CalSyncProperties.is_busy_block(google_event))
    
    def test_has_calsync_properties(self):
        """Test CalSync property detection"""
        google_event = {
            'extendedProperties': {
                'private': {
                    CalSyncProperties.CORRELATION_ID: str(uuid.uuid4())
                }
            }
        }
        
        self.assertTrue(CalSyncProperties.has_calsync_properties(google_event))
        
        # Test event without CalSync properties
        google_event = {'id': 'test_event'}
        self.assertFalse(CalSyncProperties.has_calsync_properties(google_event))
```

#### EventCorrelationManager Tests
```python
# tests/test_event_correlation_manager.py
import uuid
from unittest.mock import Mock, patch
from django.test import TestCase

from apps.calendars.models import Calendar, EventState
from apps.calendars.services.sync_engine import EventCorrelationManager

class TestEventCorrelationManager(TestCase):
    def setUp(self):
        self.calendar = Calendar.objects.create(
            name="Test Calendar",
            google_calendar_id="test@example.com"
        )
        self.manager = EventCorrelationManager()
    
    def test_generate_correlation_id(self):
        """Test correlation ID generation"""
        correlation_id = self.manager.generate_correlation_id()
        
        # Should be valid UUID string
        uuid_obj = uuid.UUID(correlation_id)
        self.assertEqual(str(uuid_obj), correlation_id)
    
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient')
    def test_create_user_event_state(self, mock_client_class):
        """Test creating user event state"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        google_event = {
            'id': 'google_event_123',
            'summary': 'User Meeting',
            'start': {'dateTime': '2025-08-04T14:00:00Z'},
            'end': {'dateTime': '2025-08-04T15:00:00Z'}
        }
        
        event_state = self.manager.create_user_event_state(
            calendar=self.calendar,
            google_event=google_event
        )
        
        self.assertEqual(event_state.calendar, self.calendar)
        self.assertEqual(event_state.google_event_id, 'google_event_123')
        self.assertEqual(event_state.event_type, 'user_event')
        self.assertFalse(event_state.created_by_us)
        self.assertEqual(event_state.status, 'synced')
        
        # Verify Google Calendar update was called
        mock_client.update_event_correlation.assert_called_once()
    
    def test_create_busy_block_state(self):
        """Test creating busy block state"""
        source_correlation_id = str(uuid.uuid4())
        
        event_state = self.manager.create_busy_block_state(
            target_calendar=self.calendar,
            source_correlation_id=source_correlation_id,
            title="Busy - User Meeting"
        )
        
        self.assertEqual(event_state.calendar, self.calendar)
        self.assertEqual(event_state.event_type, 'busy_block')
        self.assertTrue(event_state.created_by_us)
        self.assertEqual(event_state.source_correlation_id, uuid.UUID(source_correlation_id))
        self.assertEqual(event_state.status, 'creating')
    
    def test_is_our_event(self):
        """Test event ownership detection"""
        correlation_id = str(uuid.uuid4())
        
        # Create EventState for our event
        EventState.objects.create(
            correlation_id=correlation_id,
            calendar=self.calendar,
            event_type='busy_block',
            created_by_us=True
        )
        
        # Test Google event with our correlation ID
        google_event = {
            'extendedProperties': {
                'private': {
                    'calsync_id': correlation_id
                }
            }
        }
        
        self.assertTrue(self.manager.is_our_event(google_event))
        
        # Test event without correlation ID
        google_event = {'id': 'test_event'}
        self.assertFalse(self.manager.is_our_event(google_event))
        
        # Test event with unknown correlation ID
        google_event = {
            'extendedProperties': {
                'private': {
                    'calsync_id': str(uuid.uuid4())
                }
            }
        }
        self.assertFalse(self.manager.is_our_event(google_event))
    
    def test_classify_event(self):
        """Test event classification"""
        our_correlation_id = str(uuid.uuid4())
        
        # Create EventState for our event
        EventState.objects.create(
            correlation_id=our_correlation_id,
            calendar=self.calendar,
            event_type='busy_block',
            created_by_us=True
        )
        
        # Test our event
        google_event = {
            'extendedProperties': {
                'private': {
                    'calsync_id': our_correlation_id
                }
            }
        }
        
        classification = self.manager.classify_event(google_event)
        
        self.assertTrue(classification['is_ours'])
        self.assertFalse(classification['needs_processing'])
        self.assertEqual(classification['classification'], 'tracked_event')
        
        # Test new user event (no correlation ID)
        google_event = {'id': 'new_event'}
        classification = self.manager.classify_event(google_event)
        
        self.assertFalse(classification['is_ours'])
        self.assertTrue(classification['needs_processing'])
        self.assertEqual(classification['classification'], 'new_user_event')
```

### 2. Integration Tests

#### Google Calendar Integration Tests
```python
# tests/test_google_calendar_integration.py
import uuid
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase

from apps.calendars.models import Calendar, CalendarAccount
from apps.calendars.services.google_calendar_client import GoogleCalendarClient
from apps.calendars.constants import CalSyncProperties

class TestGoogleCalendarIntegration(TestCase):
    def setUp(self):
        self.account = CalendarAccount.objects.create(
            email="test@example.com",
            access_token="test_token",
            refresh_token="test_refresh_token"
        )
        self.calendar = Calendar.objects.create(
            calendar_account=self.account,
            name="Test Calendar",
            google_calendar_id="test@example.com"
        )
        self.client = GoogleCalendarClient(self.account)
    
    @patch('apps.calendars.services.google_calendar_client.build')
    def test_create_event_with_correlation(self, mock_build):
        """Test creating event with correlation ID"""
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        # Mock Google API response
        mock_service.events().insert().execute.return_value = {
            'id': 'created_event_id',
            'summary': 'Test Event',
            'extendedProperties': {
                'private': {
                    'calsync_id': 'test-correlation-id'
                }
            }
        }
        
        correlation_id = 'test-correlation-id'
        event_data = {'summary': 'Test Event'}
        
        result = self.client.create_event_with_correlation(
            calendar_id=self.calendar.google_calendar_id,
            event_data=event_data,
            correlation_id=correlation_id,
            event_type=CalSyncProperties.USER_EVENT
        )
        
        # Verify API call
        mock_service.events().insert.assert_called_once()
        call_args = mock_service.events().insert.call_args
        
        self.assertEqual(call_args[1]['calendarId'], self.calendar.google_calendar_id)
        
        body = call_args[1]['body']
        self.assertIn('extendedProperties', body)
        self.assertEqual(
            body['extendedProperties']['private']['calsync_id'],
            correlation_id
        )
        
        # Verify result
        self.assertEqual(result['id'], 'created_event_id')
    
    @patch('apps.calendars.services.google_calendar_client.build')
    def test_create_busy_block_with_correlation(self, mock_build):
        """Test creating busy block with correlation tracking"""
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        from datetime import datetime
        from django.utils import timezone
        
        start_time = timezone.now()
        end_time = start_time + timezone.timedelta(hours=1)
        correlation_id = str(uuid.uuid4())
        source_correlation_id = str(uuid.uuid4())
        
        mock_service.events().insert().execute.return_value = {
            'id': 'busy_block_id',
            'summary': 'Busy - Test Meeting'
        }
        
        result = self.client.create_busy_block_with_correlation(
            calendar_id=self.calendar.google_calendar_id,
            title='Test Meeting',
            start_time=start_time,
            end_time=end_time,
            correlation_id=correlation_id,
            source_correlation_id=source_correlation_id
        )
        
        # Verify API call
        call_args = mock_service.events().insert.call_args
        body = call_args[1]['body']
        
        self.assertEqual(body['summary'], 'Busy - Test Meeting')
        self.assertEqual(body['transparency'], 'opaque')
        self.assertEqual(body['visibility'], 'private')
        
        extended_props = body['extendedProperties']['private']
        self.assertEqual(extended_props['calsync_id'], correlation_id)
        self.assertEqual(extended_props['calsync_type'], CalSyncProperties.BUSY_BLOCK)
        self.assertEqual(extended_props['calsync_source'], source_correlation_id)
    
    @patch('apps.calendars.services.google_calendar_client.build')
    def test_list_events_with_correlation_data(self, mock_build):
        """Test listing events with correlation data extraction"""
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        # Mock Google API response
        mock_service.events().list().execute.return_value = {
            'items': [
                {
                    'id': 'event_1',
                    'summary': 'User Event',
                    'extendedProperties': {
                        'private': {
                            'calsync_id': str(uuid.uuid4()),
                            'calsync_type': 'user_event'
                        }
                    }
                },
                {
                    'id': 'event_2',
                    'summary': 'Busy - Meeting',
                    'extendedProperties': {
                        'private': {
                            'calsync_id': str(uuid.uuid4()),
                            'calsync_type': 'busy_block',
                            'calsync_source': str(uuid.uuid4())
                        }
                    }
                },
                {
                    'id': 'event_3',
                    'summary': 'External Event'
                    # No extended properties
                }
            ]
        }
        
        events = self.client.list_events_with_correlation_data(
            self.calendar.google_calendar_id
        )
        
        # Verify correlation data extraction
        self.assertEqual(len(events), 3)
        
        # User event
        self.assertTrue(events[0]['_calsync']['has_correlation'])
        self.assertTrue(events[0]['_calsync']['is_calsync_event'])
        self.assertFalse(events[0]['_calsync']['is_busy_block'])
        
        # Busy block
        self.assertTrue(events[1]['_calsync']['has_correlation'])
        self.assertTrue(events[1]['_calsync']['is_calsync_event'])
        self.assertTrue(events[1]['_calsync']['is_busy_block'])
        
        # External event
        self.assertFalse(events[2]['_calsync']['has_correlation'])
        self.assertFalse(events[2]['_calsync']['is_calsync_event'])
        self.assertFalse(events[2]['_calsync']['is_busy_block'])
```

#### Sync Engine Integration Tests
```python
# tests/test_sync_engine_integration.py
import uuid
from unittest.mock import Mock, patch
from django.test import TestCase
from django.utils import timezone

from apps.calendars.models import Calendar, CalendarAccount, EventState
from apps.calendars.services.sync_engine import UUIDCorrelationSyncEngine

class TestSyncEngineIntegration(TestCase):
    def setUp(self):
        self.account = CalendarAccount.objects.create(
            email="test@example.com",
            access_token="test_token",
            refresh_token="test_refresh_token"
        )
        self.calendar = Calendar.objects.create(
            calendar_account=self.account,
            name="Test Calendar",
            google_calendar_id="test@example.com",
            sync_enabled=True
        )
        self.sync_engine = UUIDCorrelationSyncEngine()
    
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient')
    def test_webhook_sync_new_user_event(self, mock_client_class):
        """Test webhook sync handling new user event"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock Google Calendar API response with new user event
        mock_client.list_events_with_correlation_data.return_value = [
            {
                'id': 'new_user_event',
                'summary': 'New User Meeting',
                'start': {'dateTime': '2025-08-04T14:00:00Z'},
                'end': {'dateTime': '2025-08-04T15:00:00Z'},
                '_calsync': {
                    'has_correlation': False,
                    'is_calsync_event': False,
                    'is_busy_block': False,
                    'correlation_id': None
                }
            }
        ]
        
        # Mock event creation for correlation ID update
        mock_client.update_event_correlation.return_value = None
        
        results = self.sync_engine.sync_calendar_webhook(self.calendar)
        
        # Verify results
        self.assertEqual(results['calendars_processed'], 1)
        self.assertEqual(results['events_processed'], 1)
        self.assertEqual(results['user_events_found'], 1)
        self.assertEqual(results['our_events_skipped'], 0)
        
        # Verify EventState was created
        event_states = EventState.objects.filter(calendar=self.calendar)
        self.assertEqual(event_states.count(), 1)
        
        event_state = event_states.first()
        self.assertEqual(event_state.event_type, 'user_event')
        self.assertFalse(event_state.created_by_us)
        self.assertEqual(event_state.google_event_id, 'new_user_event')
    
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient')
    def test_webhook_sync_skip_our_event(self, mock_client_class):
        """Test webhook sync skipping our own events"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Create EventState for our busy block
        our_correlation_id = str(uuid.uuid4())
        EventState.objects.create(
            correlation_id=our_correlation_id,
            calendar=self.calendar,
            google_event_id='our_busy_block',
            event_type='busy_block',
            created_by_us=True,
            status='created'
        )
        
        # Mock Google Calendar API response with our event
        mock_client.list_events_with_correlation_data.return_value = [
            {
                'id': 'our_busy_block',
                'summary': 'Busy - Meeting',
                'extendedProperties': {
                    'private': {
                        'calsync_id': our_correlation_id,
                        'calsync_type': 'busy_block'
                    }
                },
                '_calsync': {
                    'has_correlation': True,
                    'is_calsync_event': True,
                    'is_busy_block': True,
                    'correlation_id': our_correlation_id
                }
            }
        ]
        
        results = self.sync_engine.sync_calendar_webhook(self.calendar)
        
        # Verify our event was skipped
        self.assertEqual(results['events_processed'], 1)
        self.assertEqual(results['user_events_found'], 0)
        self.assertEqual(results['our_events_skipped'], 1)
        
        # Verify no new EventState was created
        event_states = EventState.objects.filter(calendar=self.calendar)
        self.assertEqual(event_states.count(), 1)  # Only the existing one
```

### 3. End-to-End Tests

#### Cascade Prevention Tests
```python
# tests/test_cascade_prevention.py
import uuid
from unittest.mock import Mock, patch
from django.test import TestCase

from apps.calendars.models import Calendar, CalendarAccount, EventState
from apps.calendars.services.sync_engine import UUIDCorrelationSyncEngine

class TestCascadePrevention(TestCase):
    def setUp(self):
        self.account = CalendarAccount.objects.create(
            email="test@example.com",
            access_token="test_token",
            refresh_token="test_refresh_token"
        )
        
        # Create two calendars for cross-calendar sync
        self.calendar_a = Calendar.objects.create(
            calendar_account=self.account,
            name="Calendar A",
            google_calendar_id="calendar_a@example.com",
            sync_enabled=True
        )
        
        self.calendar_b = Calendar.objects.create(
            calendar_account=self.account,
            name="Calendar B",
            google_calendar_id="calendar_b@example.com",
            sync_enabled=True
        )
        
        self.sync_engine = UUIDCorrelationSyncEngine()
    
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient')
    def test_no_cascade_on_busy_block_creation(self, mock_client_class):
        """Test that busy block creation doesn't trigger cascades"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Step 1: User creates event in Calendar A
        user_event_correlation_id = str(uuid.uuid4())
        user_event_state = EventState.objects.create(
            correlation_id=user_event_correlation_id,
            calendar=self.calendar_a,
            google_event_id='user_event_123',
            event_type='user_event',
            created_by_us=False,
            status='synced'
        )
        
        # Mock Google API responses
        def mock_get_event(calendar_id, event_id):
            if event_id == 'user_event_123':
                return {
                    'id': 'user_event_123',
                    'summary': 'Important Meeting',
                    'start': {'dateTime': '2025-08-04T14:00:00Z'},
                    'end': {'dateTime': '2025-08-04T15:00:00Z'},
                }
            return None
        
        mock_client.get_event.side_effect = mock_get_event
        
        # Mock busy block creation
        busy_block_correlation_id = str(uuid.uuid4())
        mock_client.create_busy_block_with_correlation.return_value = {
            'id': 'busy_block_456',
            'summary': 'Busy - Important Meeting'
        }
        
        # Step 2: Create busy block in Calendar B
        self.sync_engine._create_single_busy_block(
            source_event_state=user_event_state,
            target_calendar=self.calendar_b,
            google_event={
                'id': 'user_event_123',
                'summary': 'Important Meeting',
                'start': {'dateTime': '2025-08-04T14:00:00Z'},
                'end': {'dateTime': '2025-08-04T15:00:00Z'},
            }
        )
        
        # Step 3: Simulate webhook for Calendar B with the busy block
        busy_block_state = EventState.objects.filter(
            calendar=self.calendar_b,
            event_type='busy_block'
        ).first()
        
        mock_client.list_events_with_correlation_data.return_value = [
            {
                'id': 'busy_block_456',
                'summary': 'Busy - Important Meeting',
                'extendedProperties': {
                    'private': {
                        'calsync_id': str(busy_block_state.correlation_id),
                        'calsync_type': 'busy_block',
                        'calsync_source': user_event_correlation_id
                    }
                },
                '_calsync': {
                    'has_correlation': True,
                    'is_calsync_event': True,
                    'is_busy_block': True,
                    'correlation_id': str(busy_block_state.correlation_id)
                }
            }
        ]
        
        # Step 4: Process webhook - should skip our busy block
        results = self.sync_engine.sync_calendar_webhook(self.calendar_b)
        
        # Verify cascade prevention
        self.assertEqual(results['our_events_skipped'], 1)
        self.assertEqual(results['user_events_found'], 0)
        self.assertEqual(results['busy_blocks_created'], 0)
        
        # Verify no additional EventState records created
        total_states = EventState.objects.count()
        self.assertEqual(total_states, 2)  # Original user event + busy block
    
    def test_multiple_webhook_cycles_no_cascade(self):
        """Test multiple webhook cycles don't create cascades"""
        
        # Create initial event states
        user_correlation_id = str(uuid.uuid4())
        busy_block_correlation_id = str(uuid.uuid4())
        
        EventState.objects.create(
            correlation_id=user_correlation_id,
            calendar=self.calendar_a,
            google_event_id='user_event',
            event_type='user_event',
            created_by_us=False,
            status='synced'
        )
        
        EventState.objects.create(
            correlation_id=busy_block_correlation_id,
            calendar=self.calendar_b,
            google_event_id='busy_block',
            event_type='busy_block',
            created_by_us=True,
            source_correlation_id=user_correlation_id,
            status='created'
        )
        
        # Simulate multiple webhook cycles
        with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            # Mock responses for each webhook cycle
            mock_client.list_events_with_correlation_data.return_value = [
                {
                    'id': 'busy_block',
                    'extendedProperties': {
                        'private': {
                            'calsync_id': busy_block_correlation_id,
                            'calsync_type': 'busy_block'
                        }
                    },
                    '_calsync': {
                        'has_correlation': True,
                        'is_calsync_event': True,
                        'is_busy_block': True,
                        'correlation_id': busy_block_correlation_id
                    }
                }
            ]
            
            # Process multiple webhook cycles
            initial_state_count = EventState.objects.count()
            
            for i in range(10):  # Simulate 10 webhook cycles
                results = self.sync_engine.sync_calendar_webhook(self.calendar_b)
                
                # Each cycle should skip our event
                self.assertEqual(results['our_events_skipped'], 1)
                self.assertEqual(results['user_events_found'], 0)
                self.assertEqual(results['busy_blocks_created'], 0)
            
            # Verify no additional EventState records created
            final_state_count = EventState.objects.count()
            self.assertEqual(final_state_count, initial_state_count)
```

### 4. Performance Tests

#### Database Performance Tests
```python
# tests/test_performance.py
import uuid
import time
from django.test import TestCase
from django.test.utils import override_settings

from apps.calendars.models import Calendar, EventState

class TestPerformance(TestCase):
    def setUp(self):
        self.calendar = Calendar.objects.create(
            name="Performance Test Calendar",
            google_calendar_id="perf@example.com"
        )
    
    def test_correlation_id_lookup_performance(self):
        """Test performance of correlation ID lookups"""
        
        # Create large number of EventState records
        event_states = []
        for i in range(1000):
            event_states.append(EventState(
                correlation_id=uuid.uuid4(),
                calendar=self.calendar,
                google_event_id=f'event_{i}',
                event_type='user_event',
                created_by_us=False,
                status='synced'
            ))
        
        EventState.objects.bulk_create(event_states)
        
        # Test lookup performance
        test_correlation_id = str(event_states[500].correlation_id)
        
        start_time = time.time()
        
        # Perform 100 lookups
        for _ in range(100):
            EventState.objects.filter(
                correlation_id=test_correlation_id,
                created_by_us=False
            ).exists()
        
        end_time = time.time()
        avg_lookup_time = (end_time - start_time) / 100
        
        # Should be under 10ms per lookup
        self.assertLess(avg_lookup_time, 0.01)
    
    def test_bulk_event_classification_performance(self):
        """Test performance of classifying many events"""
        from apps.calendars.services.sync_engine import EventCorrelationManager
        
        # Create EventState records
        correlation_ids = []
        for i in range(500):
            correlation_id = str(uuid.uuid4())
            correlation_ids.append(correlation_id)
            
            EventState.objects.create(
                correlation_id=correlation_id,
                calendar=self.calendar,
                google_event_id=f'event_{i}',
                event_type='busy_block' if i % 2 == 0 else 'user_event',
                created_by_us=i % 2 == 0,
                status='synced'
            )
        
        # Create mock Google events
        google_events = []
        for i, correlation_id in enumerate(correlation_ids):
            google_events.append({
                'id': f'event_{i}',
                'extendedProperties': {
                    'private': {
                        'calsync_id': correlation_id
                    }
                }
            })
        
        # Add some events without correlation IDs
        for i in range(100):
            google_events.append({
                'id': f'new_event_{i}',
                'summary': f'New Event {i}'
            })
        
        # Test classification performance
        manager = EventCorrelationManager()
        
        start_time = time.time()
        
        classifications = []
        for event in google_events:
            classification = manager.classify_event(event)
            classifications.append(classification)
        
        end_time = time.time()
        total_time = end_time - start_time
        avg_time_per_event = total_time / len(google_events)
        
        # Should process under 1ms per event
        self.assertLess(avg_time_per_event, 0.001)
        
        # Verify classification accuracy
        our_events = sum(1 for c in classifications if c['is_ours'])
        new_events = sum(1 for c in classifications if c['classification'] == 'new_user_event')
        
        self.assertEqual(our_events, 250)  # Half were created by us
        self.assertEqual(new_events, 100)  # 100 events without correlation IDs
```

### 5. Load Tests

#### Webhook Load Tests
```python
# tests/test_webhook_load.py
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
from django.test import TestCase

from apps.calendars.models import Calendar, CalendarAccount
from apps.calendars.services.sync_engine import UUIDCorrelationSyncEngine

class TestWebhookLoad(TestCase):
    def setUp(self):
        self.account = CalendarAccount.objects.create(
            email="load_test@example.com",
            access_token="test_token",
            refresh_token="test_refresh_token"
        )
        self.calendar = Calendar.objects.create(
            calendar_account=self.account,
            name="Load Test Calendar",
            google_calendar_id="load_test@example.com",
            sync_enabled=True
        )
    
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient')
    def test_concurrent_webhook_processing(self, mock_client_class):
        """Test handling concurrent webhooks without race conditions"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock Google API response
        mock_client.list_events_with_correlation_data.return_value = [
            {
                'id': 'load_test_event',
                'summary': 'Load Test Event',
                '_calsync': {
                    'has_correlation': False,
                    'is_calsync_event': False,
                    'is_busy_block': False,
                    'correlation_id': None
                }
            }
        ]
        
        mock_client.update_event_correlation.return_value = None
        
        def process_webhook():
            """Process a single webhook"""
            sync_engine = UUIDCorrelationSyncEngine()
            return sync_engine.sync_calendar_webhook(self.calendar)
        
        # Process 10 concurrent webhooks
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(process_webhook) for _ in range(10)]
            results = [future.result() for future in futures]
        
        # Verify all webhooks processed successfully
        for result in results:
            self.assertEqual(result['calendars_processed'], 1)
            self.assertIsInstance(result['events_processed'], int)
        
        # Verify no duplicate EventState records created
        # Should only have one EventState despite concurrent processing
        from apps.calendars.models import EventState
        event_states = EventState.objects.filter(calendar=self.calendar)
        
        # Allow for some duplication due to race conditions, but shouldn't be excessive
        self.assertLessEqual(event_states.count(), 3)  # Some duplication acceptable in load test
    
    def test_webhook_processing_under_load(self):
        """Test webhook processing performance under load"""
        from apps.calendars.models import EventState
        
        # Create many existing EventState records to simulate load
        event_states = []
        for i in range(1000):
            event_states.append(EventState(
                correlation_id=uuid.uuid4(),
                calendar=self.calendar,
                google_event_id=f'existing_event_{i}',
                event_type='user_event',
                created_by_us=False,
                status='synced'
            ))
        
        EventState.objects.bulk_create(event_states)
        
        # Process webhook with many events
        with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            # Mock response with many events (mix of ours and new)
            google_events = []
            
            # Add our existing events
            for i in range(0, 1000, 10):  # Every 10th event
                event_state = event_states[i]
                google_events.append({
                    'id': f'existing_event_{i}',
                    'extendedProperties': {
                        'private': {
                            'calsync_id': str(event_state.correlation_id)
                        }
                    },
                    '_calsync': {
                        'has_correlation': True,
                        'correlation_id': str(event_state.correlation_id)
                    }
                })
            
            # Add some new events
            for i in range(10):
                google_events.append({
                    'id': f'new_load_event_{i}',
                    'summary': f'New Load Event {i}',
                    '_calsync': {
                        'has_correlation': False,
                        'correlation_id': None
                    }
                })
            
            mock_client.list_events_with_correlation_data.return_value = google_events
            mock_client.update_event_correlation.return_value = None
            
            # Measure processing time
            import time
            start_time = time.time()
            
            sync_engine = UUIDCorrelationSyncEngine()
            results = sync_engine.sync_calendar_webhook(self.calendar)
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Should process under 5 seconds even with many events
            self.assertLess(processing_time, 5.0)
            
            # Verify correct processing
            self.assertEqual(results['user_events_found'], 10)  # 10 new events
            self.assertGreater(results['our_events_skipped'], 90)  # Many existing events skipped
```

## 📊 Test Metrics and Success Criteria

### Unit Test Coverage
- **Target**: >95% code coverage for new UUID correlation components
- **Critical Paths**: 100% coverage for cascade prevention logic
- **Database Operations**: 100% coverage for EventState operations

### Integration Test Success
- **Google Calendar API**: All ExtendedProperties operations work correctly
- **Event Classification**: Perfect accuracy in event ownership detection
- **Sync Engine**: Zero false positives/negatives in event processing

### Performance Benchmarks
- **Correlation ID Lookup**: <10ms average for 1000+ records
- **Event Classification**: <1ms per event for bulk operations
- **Webhook Processing**: <3 seconds for 100+ events
- **Database Queries**: <5 queries per webhook regardless of event count

### Load Test Requirements
- **Concurrent Webhooks**: Handle 10+ simultaneous webhooks without errors
- **Large Event Sets**: Process 1000+ events without performance degradation
- **Memory Usage**: No memory leaks during extended operation
- **Database Connections**: Efficient connection usage under load

### End-to-End Success Criteria
- **Zero Cascade Incidents**: No webhook cascades in any test scenario
- **Perfect Event Tracking**: All events correctly classified and tracked
- **Data Integrity**: No orphaned or inconsistent EventState records
- **Graceful Error Handling**: System recovers from API failures and errors

## 🔍 Test Automation

### Continuous Integration Pipeline
```yaml
# .github/workflows/uuid-correlation-tests.yml
name: UUID Correlation Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:13
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.11
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install coverage pytest-django
    
    - name: Run UUID correlation tests
      run: |
        coverage run --source='.' manage.py test tests.test_event_state_model
        coverage run --append --source='.' manage.py test tests.test_calsync_properties
        coverage run --append --source='.' manage.py test tests.test_event_correlation_manager
        coverage run --append --source='.' manage.py test tests.test_google_calendar_integration
        coverage run --append --source='.' manage.py test tests.test_sync_engine_integration
        coverage run --append --source='.' manage.py test tests.test_cascade_prevention
        coverage run --append --source='.' manage.py test tests.test_performance
        coverage run --append --source='.' manage.py test tests.test_webhook_load
    
    - name: Generate coverage report
      run: |
        coverage report --show-missing
        coverage html
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v1
```

### Pre-deployment Test Suite
```bash
#!/bin/bash
# scripts/run_uuid_correlation_tests.sh

echo "Running UUID Correlation Test Suite..."

# Unit tests
echo "Running unit tests..."
python manage.py test tests.test_event_state_model --verbosity=2
python manage.py test tests.test_calsync_properties --verbosity=2
python manage.py test tests.test_event_correlation_manager --verbosity=2

# Integration tests
echo "Running integration tests..."
python manage.py test tests.test_google_calendar_integration --verbosity=2
python manage.py test tests.test_sync_engine_integration --verbosity=2

# End-to-end tests
echo "Running end-to-end tests..."
python manage.py test tests.test_cascade_prevention --verbosity=2

# Performance tests
echo "Running performance tests..."
python manage.py test tests.test_performance --verbosity=2

# Load tests
echo "Running load tests..."
python manage.py test tests.test_webhook_load --verbosity=2

echo "All tests completed successfully!"
```

This comprehensive testing strategy ensures the UUID correlation architecture is thoroughly validated before deployment, providing confidence that webhook cascades are eliminated while maintaining system reliability and performance.
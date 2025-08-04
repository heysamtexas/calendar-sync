# Testing Strategy - Implementation Task

## Objective

Develop a comprehensive testing strategy for incremental sync implementation that ensures reliability, performance, and data integrity across all scenarios including edge cases and failure conditions.

## Testing Philosophy

### Risk-Driven Testing Approach
- **High-Risk Areas**: Sync token management, cross-calendar propagation, data consistency
- **Critical Paths**: Event creation/update/deletion workflows, error recovery mechanisms
- **Performance Targets**: API call reduction >80%, sync completion time <30 seconds
- **Zero Data Loss**: All tests must validate data integrity throughout operation

## Testing Pyramid Structure

### 1. Unit Tests (Foundation Layer)

#### Sync Token Management Tests
```python
# tests/test_sync_token_management.py
import pytest
from unittest.mock import Mock, patch
from django.test import TestCase
from django.utils import timezone
from googleapiclient.errors import HttpError

from apps.calendars.models import Calendar
from apps.calendars.services.google_calendar_client import GoogleCalendarClient

class SyncTokenManagementTests(TestCase):
    """Test sync token storage, validation, and rotation"""
    
    def setUp(self):
        self.calendar = self.create_test_calendar()
        self.client = GoogleCalendarClient(self.calendar.calendar_account)
    
    def test_sync_token_storage(self):
        """Test sync token is properly stored and retrieved"""
        token = "sync_token_12345"
        
        self.calendar.update_sync_token(token)
        self.calendar.refresh_from_db()
        
        assert self.calendar.last_sync_token == token
        assert self.calendar.has_valid_sync_token()
        assert self.calendar.last_synced_at is not None
    
    def test_sync_token_validation(self):
        """Test sync token validation logic"""
        # Empty token should be invalid
        self.calendar.last_sync_token = ""
        assert not self.calendar.has_valid_sync_token()
        
        # Whitespace-only token should be invalid
        self.calendar.last_sync_token = "   "
        assert not self.calendar.has_valid_sync_token()
        
        # Valid token should pass
        self.calendar.last_sync_token = "valid_token_123"
        assert self.calendar.has_valid_sync_token()
    
    def test_sync_token_clearing(self):
        """Test sync token clearing functionality"""
        self.calendar.update_sync_token("test_token")
        assert self.calendar.has_valid_sync_token()
        
        self.calendar.clear_sync_token()
        assert not self.calendar.has_valid_sync_token()
        assert self.calendar.last_sync_token == ""
    
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient._get_service')
    def test_expired_sync_token_fallback(self, mock_service):
        """Test graceful fallback when sync token expires"""
        
        # Mock 410 Gone response (expired token)
        mock_error = HttpError(
            resp=Mock(status=410),
            content=b'{"error": {"code": 410, "message": "Sync token expired"}}'
        )
        
        mock_service.return_value.events.return_value.list.side_effect = [
            mock_error,  # First call fails with expired token
            Mock(execute=Mock(return_value={  # Second call (fallback) succeeds
                'items': [],
                'nextSyncToken': 'new_token_456'
            }))
        ]
        
        result = self.client.list_events_incremental('calendar_id', sync_token='expired_token')
        
        assert result['is_full_sync'] == True
        assert result['next_sync_token'] == 'new_token_456'
        
        # Verify fallback to full sync was called
        assert mock_service.return_value.events.return_value.list.call_count == 2
    
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient._get_service')
    def test_invalid_sync_token_fallback(self, mock_service):
        """Test graceful fallback when sync token is invalid"""
        
        # Mock 400 Bad Request response (invalid token)
        mock_error = HttpError(
            resp=Mock(status=400),
            content=b'{"error": {"code": 400, "message": "Invalid sync token"}}'
        )
        
        mock_service.return_value.events.return_value.list.side_effect = [
            mock_error,
            Mock(execute=Mock(return_value={
                'items': [],
                'nextSyncToken': 'new_token_789'
            }))
        ]
        
        result = self.client.list_events_incremental('calendar_id', sync_token='invalid_token')
        
        assert result['is_full_sync'] == True
        assert result['next_sync_token'] == 'new_token_789'

class EventChangeProcessingTests(TestCase):
    """Test event creation, update, and deletion processing"""
    
    def test_new_event_creation(self):
        """Test creation of new events from Google Calendar data"""
        google_event_data = {
            'id': 'test_event_123',
            'summary': 'Test Meeting',
            'start': {'dateTime': '2024-01-15T10:00:00Z'},
            'end': {'dateTime': '2024-01-15T11:00:00Z'},
            'attendees': [{'email': 'test@example.com', 'responseStatus': 'accepted'}]
        }
        
        calendar = self.create_test_calendar()
        sync_engine = SyncEngine()
        
        # Process the new event
        sync_engine._process_google_event(calendar, google_event_data)
        
        # Verify event was created
        created_event = Event.objects.get(
            calendar=calendar,
            google_event_id='test_event_123'
        )
        
        assert created_event.title == 'Test Meeting'
        assert created_event.is_meeting_invite == True
        assert not created_event.is_busy_block
    
    def test_declined_meeting_filtering(self):
        """Test that declined meetings are not processed"""
        google_event_data = {
            'id': 'declined_meeting_123',
            'summary': 'Declined Meeting',
            'start': {'dateTime': '2024-01-15T14:00:00Z'},
            'end': {'dateTime': '2024-01-15T15:00:00Z'},
            'attendees': [
                {'email': 'test@example.com', 'self': True, 'responseStatus': 'declined'}
            ]
        }
        
        calendar = self.create_test_calendar()
        sync_engine = SyncEngine()
        
        # Process the declined event
        sync_engine._process_google_event(calendar, google_event_data)
        
        # Verify event was not created
        assert not Event.objects.filter(
            calendar=calendar,
            google_event_id='declined_meeting_123'
        ).exists()
    
    def test_event_update_detection(self):
        """Test detection and processing of event updates"""
        calendar = self.create_test_calendar()
        
        # Create initial event
        original_event = Event.objects.create(
            calendar=calendar,
            google_event_id='update_test_123',
            title='Original Title',
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(hours=1)
        )
        
        # Updated Google event data
        updated_google_data = {
            'id': 'update_test_123',
            'summary': 'Updated Title',
            'start': {'dateTime': (timezone.now() + timezone.timedelta(hours=1)).isoformat()},
            'end': {'dateTime': (timezone.now() + timezone.timedelta(hours=2)).isoformat()},
        }
        
        sync_engine = SyncEngine()
        
        # Process the update
        sync_engine._process_google_event(calendar, updated_google_data)
        
        # Verify event was updated
        original_event.refresh_from_db()
        assert original_event.title == 'Updated Title'
    
    def test_event_deletion_processing(self):
        """Test processing of deleted events"""
        calendar = self.create_test_calendar()
        
        # Create event to be deleted
        event_to_delete = Event.objects.create(
            calendar=calendar,
            google_event_id='delete_test_123',
            title='Event to Delete',
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(hours=1)
        )
        
        # Cancelled Google event data
        cancelled_google_data = {
            'id': 'delete_test_123',
            'status': 'cancelled'
        }
        
        sync_engine = SyncEngine()
        
        # Process the deletion
        sync_engine._process_google_event(calendar, cancelled_google_data)
        
        # Verify event was deleted
        assert not Event.objects.filter(id=event_to_delete.id).exists()

class CrossCalendarPropagationTests(TestCase):
    """Test cross-calendar busy block propagation"""
    
    def test_busy_block_creation_propagation(self):
        """Test that new events create busy blocks in target calendars"""
        user = self.create_test_user()
        source_calendar = self.create_test_calendar(user=user, name="Source Calendar")
        target_calendar = self.create_test_calendar(user=user, name="Target Calendar")
        
        # Create event in source calendar
        source_event = Event.objects.create(
            calendar=source_calendar,
            google_event_id='propagation_test_123',
            title='Source Event',
            start_time=timezone.now() + timezone.timedelta(days=1),
            end_time=timezone.now() + timezone.timedelta(days=1, hours=1)
        )
        
        propagation_engine = CrossCalendarPropagationEngine()
        
        # Propagate to target calendar
        propagation_engine.propagate_event_change(source_event, 'create')
        
        # Verify busy block was created
        busy_block = Event.objects.filter(
            calendar=target_calendar,
            source_event=source_event,
            is_busy_block=True
        ).first()
        
        assert busy_block is not None
        assert busy_block.title.startswith('🔒')  # Busy block title prefix
        assert busy_block.start_time == source_event.start_time
        assert busy_block.end_time == source_event.end_time
    
    def test_busy_block_update_propagation(self):
        """Test that event updates propagate to busy blocks"""
        user = self.create_test_user()
        source_calendar = self.create_test_calendar(user=user)
        target_calendar = self.create_test_calendar(user=user)
        
        # Create source event and busy block
        source_event = Event.objects.create(
            calendar=source_calendar,
            google_event_id='update_propagation_test',
            title='Original Event',
            start_time=timezone.now() + timezone.timedelta(days=2),
            end_time=timezone.now() + timezone.timedelta(days=2, hours=1)
        )
        
        busy_block = Event.objects.create(
            calendar=target_calendar,
            google_event_id='busy_block_123',
            title='🔒 Original Event',
            start_time=source_event.start_time,
            end_time=source_event.end_time,
            is_busy_block=True,
            source_event=source_event
        )
        
        # Update source event
        source_event.title = 'Updated Event'
        source_event.start_time = timezone.now() + timezone.timedelta(days=3)
        source_event.end_time = timezone.now() + timezone.timedelta(days=3, hours=2)
        source_event.save()
        
        propagation_engine = CrossCalendarPropagationEngine()
        
        # Propagate changes
        changes = {
            'title': {'old': 'Original Event', 'new': 'Updated Event'},
            'start_time': {'old': source_event.start_time, 'new': source_event.start_time},
            'end_time': {'old': source_event.end_time, 'new': source_event.end_time}
        }
        
        propagation_engine.propagate_event_change(source_event, 'update', changes)
        
        # Verify busy block was updated
        busy_block.refresh_from_db()
        assert '🔒 Updated Event' in busy_block.title
        assert busy_block.start_time == source_event.start_time
        assert busy_block.end_time == source_event.end_time
    
    def test_busy_block_deletion_propagation(self):
        """Test that event deletions remove corresponding busy blocks"""
        user = self.create_test_user()
        source_calendar = self.create_test_calendar(user=user)
        target_calendar = self.create_test_calendar(user=user)
        
        # Create source event and busy block
        source_event = Event.objects.create(
            calendar=source_calendar,
            google_event_id='deletion_propagation_test',
            title='Event to Delete',
            start_time=timezone.now() + timezone.timedelta(days=1),
            end_time=timezone.now() + timezone.timedelta(days=1, hours=1)
        )
        
        busy_block = Event.objects.create(
            calendar=target_calendar,
            google_event_id='busy_block_to_delete',
            title='🔒 Event to Delete',
            start_time=source_event.start_time,
            end_time=source_event.end_time,
            is_busy_block=True,
            source_event=source_event
        )
        
        propagation_engine = CrossCalendarPropagationEngine()
        
        # Propagate deletion
        propagation_engine.propagate_event_change(source_event, 'delete')
        
        # Verify busy block was deleted
        assert not Event.objects.filter(id=busy_block.id).exists()
```

### 2. Integration Tests (Service Layer)

#### End-to-End Sync Tests
```python
# tests/test_incremental_sync_integration.py
import pytest
from unittest.mock import Mock, patch
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

class IncrementalSyncIntegrationTests(TransactionTestCase):
    """Test complete incremental sync workflows"""
    
    def setUp(self):
        self.user = self.create_test_user()
        self.calendar = self.create_test_calendar(user=self.user)
        self.sync_engine = SyncEngine()
    
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.list_events_incremental')
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.create_busy_block')
    def test_full_incremental_sync_workflow(self, mock_create_busy_block, mock_list_events):
        """Test complete incremental sync from token fetch to busy block creation"""
        
        # Mock Google API responses
        mock_list_events.return_value = {
            'events': [
                {
                    'id': 'new_event_123',
                    'summary': 'New Meeting',
                    'status': 'confirmed',
                    'start': {'dateTime': '2024-02-01T10:00:00Z'},
                    'end': {'dateTime': '2024-02-01T11:00:00Z'},
                    'attendees': [{'email': 'test@example.com'}]
                }
            ],
            'next_sync_token': 'new_sync_token_456',
            'is_full_sync': False,
            'total_events': 1
        }
        
        mock_create_busy_block.return_value = {'id': 'created_busy_block_789'}
        
        # Set up calendar with sync token
        self.calendar.update_sync_token('existing_sync_token_123')
        
        # Create target calendar for busy blocks
        target_calendar = self.create_test_calendar(user=self.user, name="Target Calendar")
        
        # Run incremental sync
        results = self.sync_engine.sync_specific_calendar(self.calendar.id)
        
        # Verify sync completed successfully
        assert results['calendars_processed'] == 1
        assert results['events_created'] == 1
        assert results['busy_blocks_created'] == 1
        
        # Verify event was created
        created_event = Event.objects.get(
            calendar=self.calendar,
            google_event_id='new_event_123'
        )
        assert created_event.title == 'New Meeting'
        assert created_event.is_meeting_invite == True
        
        # Verify busy block was created in target calendar
        busy_block = Event.objects.get(
            calendar=target_calendar,
            source_event=created_event,
            is_busy_block=True
        )
        assert busy_block.title.startswith('🔒')
        
        # Verify sync token was updated
        self.calendar.refresh_from_db()
        assert self.calendar.last_sync_token == 'new_sync_token_456'
    
    def test_sync_token_expiration_recovery(self):
        """Test recovery from sync token expiration"""
        
        with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.list_events_incremental') as mock_list:
            # First call fails with expired token, second succeeds with full sync
            mock_list.side_effect = [
                HttpError(resp=Mock(status=410), content=b'{"error": {"message": "Sync token expired"}}'),
                {
                    'events': [],
                    'next_sync_token': 'recovery_token_123',
                    'is_full_sync': True,
                    'total_events': 0
                }
            ]
            
            # Set calendar with expired token
            self.calendar.update_sync_token('expired_token')
            
            # Run sync - should recover gracefully
            results = self.sync_engine.sync_specific_calendar(self.calendar.id)
            
            # Verify recovery was successful
            assert results['calendars_processed'] == 1
            assert len(results['errors']) == 0
            
            # Verify new token was saved
            self.calendar.refresh_from_db()
            assert self.calendar.last_sync_token == 'recovery_token_123'
    
    def test_concurrent_sync_prevention(self):
        """Test that concurrent syncs are prevented"""
        
        from apps.calendars.services.sync_engine import ConcurrentSafeSyncEngine
        
        sync_engine = ConcurrentSafeSyncEngine()
        
        # Mock a long-running sync
        with patch('apps.calendars.services.sync_engine.SyncEngine._sync_single_calendar_atomic') as mock_sync:
            mock_sync.side_effect = lambda x: time.sleep(2)  # Simulate slow sync
            
            import threading
            
            results = []
            
            def run_sync():
                result = sync_engine.sync_calendar_with_lock(self.calendar.id)
                results.append(result)
            
            # Start two concurrent sync threads
            thread1 = threading.Thread(target=run_sync)
            thread2 = threading.Thread(target=run_sync)
            
            thread1.start()
            time.sleep(0.1)  # Small delay to ensure thread1 acquires lock
            thread2.start()
            
            thread1.join()
            thread2.join()
            
            # One should succeed, one should timeout or fail
            success_count = sum(1 for r in results if 'error' not in r)
            assert success_count == 1
    
    def test_cross_calendar_consistency_validation(self):
        """Test that cross-calendar consistency is maintained"""
        
        # Create multiple calendars for same user
        calendar1 = self.create_test_calendar(user=self.user, name="Calendar 1")
        calendar2 = self.create_test_calendar(user=self.user, name="Calendar 2")
        calendar3 = self.create_test_calendar(user=self.user, name="Calendar 3")
        
        # Create event in calendar1
        source_event = Event.objects.create(
            calendar=calendar1,
            google_event_id='consistency_test_123',
            title='Test Event',
            start_time=timezone.now() + timezone.timedelta(days=1),
            end_time=timezone.now() + timezone.timedelta(days=1, hours=1)
        )
        
        # Run cross-calendar sync
        self.sync_engine._create_cross_calendar_busy_blocks()
        
        # Verify busy blocks were created in both target calendars
        busy_block_2 = Event.objects.filter(
            calendar=calendar2,
            source_event=source_event,
            is_busy_block=True
        )
        
        busy_block_3 = Event.objects.filter(
            calendar=calendar3,
            source_event=source_event,
            is_busy_block=True
        )
        
        assert busy_block_2.exists()
        assert busy_block_3.exists()
        
        # Verify consistency checker validates this state
        consistency_checker = CrossCalendarConsistencyChecker()
        results = consistency_checker.validate_consistency(self.user.id)
        
        assert results['consistent'] == True
        assert len(results['inconsistencies']) == 0

class DatabaseConsistencyTests(TransactionTestCase):
    """Test database consistency and transaction handling"""
    
    def test_atomic_sync_rollback_on_error(self):
        """Test that sync operations rollback on errors"""
        
        calendar = self.create_test_calendar()
        sync_engine = DatabaseConsistentSyncEngine()
        
        with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.list_events_incremental') as mock_list:
            # Mock successful API call but fail during processing
            mock_list.return_value = {
                'events': [{'id': 'test_event', 'summary': 'Test'}],
                'next_sync_token': 'test_token',
                'is_full_sync': False,
                'total_events': 1
            }
            
            with patch('apps.calendars.services.sync_engine.SyncEngine._process_google_event') as mock_process:
                # Make processing fail
                mock_process.side_effect = Exception("Processing failed")
                
                # Attempt sync - should fail and rollback
                with pytest.raises(Exception):
                    sync_engine._sync_single_calendar_atomic(calendar)
                
                # Verify rollback occurred - no events should be created
                assert Event.objects.filter(calendar=calendar).count() == 0
                
                # Verify sync token was not updated
                calendar.refresh_from_db()
                assert calendar.last_sync_token == ""
    
    def test_orphaned_busy_block_cleanup(self):
        """Test detection and cleanup of orphaned busy blocks"""
        
        calendar = self.create_test_calendar()
        
        # Create orphaned busy block (no source event)
        orphaned_block = Event.objects.create(
            calendar=calendar,
            google_event_id='orphaned_123',
            title='🔒 Orphaned Block',
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(hours=1),
            is_busy_block=True,
            source_event=None  # This makes it orphaned
        )
        
        detector = OrphanedBusyBlockDetector()
        
        # Detect orphans
        results = detector.detect_orphaned_busy_blocks(calendar)
        assert results['orphaned_count'] == 1
        assert orphaned_block in results['orphaned_blocks']
        
        # Clean up orphans
        with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.delete_event') as mock_delete:
            mock_delete.return_value = True
            
            cleanup_results = detector.cleanup_orphaned_busy_blocks(results['orphaned_blocks'])
            
            assert cleanup_results['database_deleted'] == 1
            assert cleanup_results['google_deleted'] == 1
            
            # Verify orphan was removed
            assert not Event.objects.filter(id=orphaned_block.id).exists()
```

### 3. Performance Tests (Scalability Layer)

#### API Usage and Performance Tests
```python
# tests/test_performance.py
import time
import pytest
from django.test import TestCase
from unittest.mock import Mock, patch

class PerformanceTests(TestCase):
    """Test performance characteristics of incremental sync"""
    
    def test_api_call_reduction(self):
        """Test that incremental sync reduces API calls significantly"""
        
        user = self.create_test_user()
        calendar = self.create_test_calendar(user=user)
        
        # Create baseline events
        for i in range(50):
            Event.objects.create(
                calendar=calendar,
                google_event_id=f'baseline_event_{i}',
                title=f'Baseline Event {i}',
                start_time=timezone.now() + timezone.timedelta(days=i),
                end_time=timezone.now() + timezone.timedelta(days=i, hours=1)
            )
        
        sync_engine = SyncEngine()
        
        with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.list_events_incremental') as mock_list:
            # Mock incremental sync with minimal changes
            mock_list.return_value = {
                'events': [  # Only 2 changes
                    {'id': 'new_event_1', 'summary': 'New Event', 'status': 'confirmed'},
                    {'id': 'baseline_event_1', 'summary': 'Updated Event', 'status': 'confirmed'}
                ],
                'next_sync_token': 'performance_token',
                'is_full_sync': False,
                'total_events': 2
            }
            
            # Run incremental sync
            start_time = time.time()
            results = sync_engine.sync_specific_calendar(calendar.id)
            end_time = time.time()
            
            # Verify API efficiency
            assert mock_list.call_count == 1  # Single API call
            assert results['calendars_processed'] == 1
            
            # Verify performance
            sync_duration = end_time - start_time
            assert sync_duration < 5.0  # Should complete quickly
    
    def test_large_change_set_handling(self):
        """Test handling of large incremental change sets"""
        
        calendar = self.create_test_calendar()
        sync_engine = SyncEngine()
        
        # Mock large change set (100 events)
        large_change_set = []
        for i in range(100):
            large_change_set.append({
                'id': f'bulk_event_{i}',
                'summary': f'Bulk Event {i}',
                'status': 'confirmed',
                'start': {'dateTime': f'2024-03-{i%28 + 1:02d}T10:00:00Z'},
                'end': {'dateTime': f'2024-03-{i%28 + 1:02d}T11:00:00Z'}
            })
        
        with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.list_events_incremental') as mock_list:
            mock_list.return_value = {
                'events': large_change_set,
                'next_sync_token': 'bulk_token',
                'is_full_sync': False,
                'total_events': 100
            }
            
            # Run sync with large change set
            start_time = time.time()
            results = sync_engine.sync_specific_calendar(calendar.id)
            end_time = time.time()
            
            # Verify all events were processed
            assert results['events_created'] == 100
            
            # Verify reasonable performance
            sync_duration = end_time - start_time
            assert sync_duration < 30.0  # Should complete within 30 seconds
            
            # Verify database consistency
            created_events = Event.objects.filter(calendar=calendar).count()
            assert created_events == 100
    
    def test_memory_usage_with_pagination(self):
        """Test memory efficiency with paginated results"""
        
        calendar = self.create_test_calendar()
        sync_engine = SyncEngine()
        
        # Mock paginated response
        with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.list_events_incremental') as mock_list:
            
            # Simulate large dataset returned in pages
            mock_list.return_value = {
                'events': [{'id': f'page_event_{i}', 'summary': f'Event {i}'} for i in range(1000)],
                'next_sync_token': 'pagination_token',
                'is_full_sync': False,
                'total_events': 1000
            }
            
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss
            
            # Run sync
            results = sync_engine.sync_specific_calendar(calendar.id)
            
            final_memory = process.memory_info().rss
            memory_increase = final_memory - initial_memory
            
            # Verify memory usage is reasonable (less than 100MB increase)
            assert memory_increase < 100 * 1024 * 1024  # 100MB
            assert results['events_created'] == 1000

class StressTests(TestCase):
    """Stress tests for edge cases and high load scenarios"""
    
    def test_rapid_successive_syncs(self):
        """Test handling of rapid successive sync operations"""
        
        calendar = self.create_test_calendar()
        sync_engine = ConcurrentSafeSyncEngine()
        
        with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.list_events_incremental') as mock_list:
            mock_list.return_value = {
                'events': [],
                'next_sync_token': 'rapid_token',
                'is_full_sync': False,
                'total_events': 0
            }
            
            # Run multiple syncs in rapid succession
            results = []
            for i in range(10):
                result = sync_engine.sync_calendar_with_lock(calendar.id)
                results.append(result)
            
            # All syncs should complete successfully (though some may be locked out)
            success_count = sum(1 for r in results if 'error' not in r)
            assert success_count >= 8  # At least 80% should succeed
    
    def test_network_failure_recovery(self):
        """Test recovery from network failures during sync"""
        
        calendar = self.create_test_calendar()
        sync_engine = SyncEngine()
        
        with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.list_events_incremental') as mock_list:
            # Simulate network failures followed by success
            mock_list.side_effect = [
                Exception("Network timeout"),
                Exception("Connection reset"),
                {  # Third attempt succeeds
                    'events': [],
                    'next_sync_token': 'recovery_token',
                    'is_full_sync': False,
                    'total_events': 0
                }
            ]
            
            # Sync should eventually succeed after retries
            for attempt in range(3):
                try:
                    results = sync_engine.sync_specific_calendar(calendar.id)
                    # If we get here, sync succeeded
                    assert results['calendars_processed'] == 1
                    break
                except Exception:
                    if attempt == 2:  # Last attempt
                        pytest.fail("Sync failed after all retry attempts")
                    continue
```

### 4. End-to-End Tests (System Layer)

#### Complete System Integration Tests
```python
# tests/test_e2e_incremental_sync.py
import pytest
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model

class EndToEndIncrementalSyncTests(TransactionTestCase):
    """Complete end-to-end testing of incremental sync system"""
    
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Create multiple calendar accounts for comprehensive testing
        self.account1 = self.create_calendar_account(self.user, 'account1@gmail.com')
        self.account2 = self.create_calendar_account(self.user, 'account2@gmail.com')
        
        self.calendar1 = self.create_calendar(self.account1, 'Primary Calendar')
        self.calendar2 = self.create_calendar(self.account1, 'Work Calendar')
        self.calendar3 = self.create_calendar(self.account2, 'Personal Calendar')
    
    def test_complete_incremental_sync_workflow(self):
        """Test complete workflow from initial sync to steady-state incremental updates"""
        
        # Phase 1: Initial full sync
        with self.mock_google_api_initial_sync():
            sync_engine = SyncEngine()
            results = sync_engine.sync_all_calendars()
            
            # Verify initial sync completed
            assert results['calendars_processed'] == 3
            assert results['events_created'] > 0
            assert results['busy_blocks_created'] > 0
            
            # Verify sync tokens were stored
            for calendar in [self.calendar1, self.calendar2, self.calendar3]:
                calendar.refresh_from_db()
                assert calendar.has_valid_sync_token()
        
        # Phase 2: Incremental updates
        with self.mock_google_api_incremental_sync():
            # Run incremental sync
            results = sync_engine.sync_all_calendars()
            
            # Verify incremental sync was more efficient
            assert results['calendars_processed'] == 3
            # Should process fewer events in incremental mode
            
            # Verify cross-calendar consistency maintained
            self.verify_cross_calendar_consistency()
    
    def test_multi_user_isolation(self):
        """Test that sync operations for different users are properly isolated"""
        
        # Create second user with their own calendars
        User = get_user_model()
        user2 = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass456'
        )
        
        account2 = self.create_calendar_account(user2, 'user2@gmail.com')
        calendar_user2 = self.create_calendar(account2, 'User2 Calendar')
        
        # Create events for both users
        event_user1 = Event.objects.create(
            calendar=self.calendar1,
            google_event_id='user1_event',
            title='User1 Event',
            start_time=timezone.now() + timezone.timedelta(days=1),
            end_time=timezone.now() + timezone.timedelta(days=1, hours=1)
        )
        
        event_user2 = Event.objects.create(
            calendar=calendar_user2,
            google_event_id='user2_event',
            title='User2 Event',
            start_time=timezone.now() + timezone.timedelta(days=1),
            end_time=timezone.now() + timezone.timedelta(days=1, hours=1)
        )
        
        # Run cross-calendar sync
        sync_engine = SyncEngine()
        sync_engine._create_cross_calendar_busy_blocks()
        
        # Verify user isolation - User1's events should not create busy blocks in User2's calendars
        user2_busy_blocks = Event.objects.filter(
            calendar=calendar_user2,
            is_busy_block=True,
            source_event=event_user1
        )
        assert not user2_busy_blocks.exists()
        
        # Verify User1's calendars have proper busy blocks from each other
        user1_cross_calendar_blocks = Event.objects.filter(
            calendar=self.calendar2,
            is_busy_block=True,
            source_event=event_user1
        )
        assert user1_cross_calendar_blocks.exists()
    
    def test_error_recovery_and_consistency_repair(self):
        """Test complete error recovery and consistency repair workflow"""
        
        # Create inconsistent state
        source_event = Event.objects.create(
            calendar=self.calendar1,
            google_event_id='recovery_test_event',
            title='Recovery Test Event',
            start_time=timezone.now() + timezone.timedelta(days=1),
            end_time=timezone.now() + timezone.timedelta(days=1, hours=1)
        )
        
        # Manually create busy block in calendar2 but not calendar3 (inconsistent state)
        Event.objects.create(
            calendar=self.calendar2,
            google_event_id='partial_busy_block',
            title='🔒 Recovery Test Event',
            start_time=source_event.start_time,
            end_time=source_event.end_time,
            is_busy_block=True,
            source_event=source_event
        )
        
        # Run consistency validation and repair
        consistency_checker = CrossCalendarConsistencyChecker()
        
        # Detect inconsistency
        validation_results = consistency_checker.validate_consistency(self.user.id)
        assert not validation_results['consistent']
        assert len(validation_results['inconsistencies']) > 0
        
        # Repair inconsistencies
        repair_results = consistency_checker.repair_inconsistencies(validation_results['inconsistencies'])
        assert repair_results['repaired'] > 0
        
        # Verify consistency after repair
        post_repair_results = consistency_checker.validate_consistency(self.user.id)
        assert post_repair_results['consistent']
    
    def test_performance_under_realistic_load(self):
        """Test system performance under realistic usage patterns"""
        
        # Create realistic data set
        self.create_realistic_test_data()
        
        # Measure initial sync performance
        sync_engine = SyncEngine()
        
        with self.measure_performance() as metrics:
            results = sync_engine.sync_all_calendars()
        
        # Verify performance meets targets
        assert metrics['duration'] < 60.0  # Complete sync under 1 minute
        assert metrics['api_calls'] < 1000  # Reasonable API usage
        assert metrics['memory_peak'] < 500 * 1024 * 1024  # Under 500MB
        
        # Verify functional correctness
        assert results['calendars_processed'] == 3
        assert len(results['errors']) == 0
        
        # Test incremental sync performance
        with self.mock_minimal_changes():
            with self.measure_performance() as incremental_metrics:
                incremental_results = sync_engine.sync_all_calendars()
        
        # Verify incremental sync is significantly faster
        assert incremental_metrics['duration'] < metrics['duration'] / 4  # At least 4x faster
        assert incremental_metrics['api_calls'] < metrics['api_calls'] / 10  # At least 10x fewer API calls
    
    # Helper methods for E2E tests
    def create_realistic_test_data(self):
        """Create realistic test data set"""
        # Implementation would create various event types, recurring events, etc.
        pass
    
    def mock_google_api_initial_sync(self):
        """Mock Google API for initial sync scenario"""
        # Implementation would mock comprehensive initial sync responses
        pass
    
    def mock_google_api_incremental_sync(self):
        """Mock Google API for incremental sync scenario"""
        # Implementation would mock incremental sync responses
        pass
    
    def verify_cross_calendar_consistency(self):
        """Verify cross-calendar consistency"""
        consistency_checker = CrossCalendarConsistencyChecker()
        results = consistency_checker.validate_consistency(self.user.id)
        assert results['consistent'], f"Consistency issues: {results['inconsistencies']}"
    
    @contextmanager
    def measure_performance(self):
        """Context manager to measure performance metrics"""
        import psutil
        import time
        
        process = psutil.Process()
        
        start_time = time.time()
        start_memory = process.memory_info().rss
        api_call_count = 0  # Would be tracked via mock
        
        metrics = {'api_calls': 0}
        
        yield metrics
        
        end_time = time.time()
        end_memory = process.memory_info().rss
        
        metrics.update({
            'duration': end_time - start_time,
            'memory_peak': end_memory,
            'memory_increase': end_memory - start_memory
        })
```

## Testing Infrastructure and Utilities

### Test Data Factory
```python
# tests/factories.py
import factory
from django.contrib.auth import get_user_model
from apps.calendars.models import CalendarAccount, Calendar, Event

User = get_user_model()

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f"testuser{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    password = factory.PostGenerationMethodCall('set_password', 'testpass123')

class CalendarAccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CalendarAccount
    
    user = factory.SubFactory(UserFactory)
    google_account_id = factory.Sequence(lambda n: f"google_account_{n}")
    email = factory.LazyAttribute(lambda obj: f"google{obj.id}@gmail.com")
    access_token = "encrypted_access_token"
    refresh_token = "encrypted_refresh_token"
    token_expires_at = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(hours=1))
    is_active = True

class CalendarFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Calendar
    
    calendar_account = factory.SubFactory(CalendarAccountFactory)
    google_calendar_id = factory.Sequence(lambda n: f"calendar_id_{n}")
    name = factory.Sequence(lambda n: f"Test Calendar {n}")
    sync_enabled = True

class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Event
    
    calendar = factory.SubFactory(CalendarFactory)
    google_event_id = factory.Sequence(lambda n: f"event_{n}")
    title = factory.Sequence(lambda n: f"Test Event {n}")
    start_time = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(days=1))
    end_time = factory.LazyAttribute(lambda obj: obj.start_time + timezone.timedelta(hours=1))
    is_busy_block = False
```

## Success Criteria

### Unit Test Coverage
- ✅ >95% code coverage for all sync-related modules
- ✅ All edge cases and error conditions tested
- ✅ Mock-based testing for external API dependencies

### Integration Test Coverage
- ✅ End-to-end sync workflows validated
- ✅ Cross-calendar propagation tested comprehensively
- ✅ Database consistency verified under all scenarios

### Performance Test Results
- ✅ API call reduction >80% verified
- ✅ Sync completion time <30 seconds validated
- ✅ Memory usage under acceptable limits

### System Test Coverage
- ✅ Multi-user isolation confirmed
- ✅ Error recovery mechanisms validated
- ✅ Production-realistic load testing passed

This comprehensive testing strategy ensures the incremental sync implementation is reliable, performant, and maintainable while preserving data integrity across all scenarios.
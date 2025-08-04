"""
Tests for UUID correlation architecture components

Following Guilfoyle's principle: test the critical paths first
"""

from unittest.mock import Mock, patch
import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from apps.calendars.models import Calendar, CalendarAccount, EventState
from apps.calendars.utils import LegacyDetectionUtils, UUIDCorrelationUtils


class TestEventStateModel(TestCase):
    """Test Guilfoyle's simplified EventState model"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass"
        )
        self.account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="test_google_id",
            email="test@example.com",
            access_token="test_token",
            refresh_token="test_refresh_token",
            token_expires_at=timezone.now() + timezone.timedelta(hours=1)
        )
        self.calendar = Calendar.objects.create(
            calendar_account=self.account,
            name="Test Calendar",
            google_calendar_id="test@example.com"
        )

    def test_create_user_event(self):
        """Test creating user event state"""
        event_state = EventState.create_user_event(
            calendar=self.calendar,
            google_event_id="google_123",
            title="User Meeting",
            start_time=timezone.now(),
            end_time=timezone.now() + timezone.timedelta(hours=1)
        )

        self.assertFalse(event_state.is_busy_block)
        self.assertEqual(event_state.status, 'SYNCED')
        self.assertEqual(event_state.google_event_id, "google_123")
        self.assertIsNone(event_state.source_uuid)
        self.assertEqual(event_state.title, "User Meeting")

    def test_create_busy_block(self):
        """Test creating busy block state"""
        source_uuid = uuid.uuid4()

        busy_block = EventState.create_busy_block(
            target_calendar=self.calendar,
            source_uuid=source_uuid,
            title="Important Meeting"
        )

        self.assertTrue(busy_block.is_busy_block)
        self.assertEqual(busy_block.status, 'PENDING')
        self.assertEqual(busy_block.source_uuid, source_uuid)
        self.assertEqual(busy_block.title, "Busy - Important Meeting")
        self.assertIsNone(busy_block.google_event_id)  # Not synced yet

    def test_mark_synced(self):
        """Test marking event as synced"""
        event_state = EventState.create_busy_block(
            target_calendar=self.calendar,
            source_uuid=uuid.uuid4(),
            title="Test Event"
        )

        event_state.mark_synced("google_456")

        self.assertEqual(event_state.status, 'SYNCED')
        self.assertEqual(event_state.google_event_id, "google_456")
        self.assertIsNotNone(event_state.last_seen_at)

    def test_busy_block_source_constraint(self):
        """Test database constraint for busy blocks requiring source_uuid"""
        from django.core.exceptions import ValidationError

        # Busy block without source_uuid should fail validation
        busy_block = EventState(
            calendar=self.calendar,
            is_busy_block=True,
            source_uuid=None,  # This should cause validation error
            status='PENDING'
        )

        with self.assertRaises(ValidationError):
            busy_block.full_clean()

    def test_user_event_source_constraint(self):
        """Test database constraint for user events not having source_uuid"""
        from django.core.exceptions import ValidationError

        # User event with source_uuid should fail validation
        user_event = EventState(
            calendar=self.calendar,
            is_busy_block=False,
            source_uuid=uuid.uuid4(),  # This should cause validation error
            status='SYNCED'
        )

        with self.assertRaises(ValidationError):
            user_event.full_clean()

    def test_manager_methods(self):
        """Test EventStateManager custom methods"""
        # Create test data
        user_event = EventState.create_user_event(
            calendar=self.calendar,
            google_event_id="user_event"
        )

        busy_block = EventState.create_busy_block(
            target_calendar=self.calendar,
            source_uuid=user_event.uuid,
            title="Meeting"
        )

        # Test manager methods
        our_events = EventState.objects.our_events(self.calendar)
        self.assertIn(busy_block, our_events)
        self.assertNotIn(user_event, our_events)

        user_events = EventState.objects.user_events(self.calendar)
        self.assertIn(user_event, user_events)
        self.assertNotIn(busy_block, user_events)

        pending_events = EventState.objects.pending_sync()
        self.assertIn(busy_block, pending_events)
        self.assertNotIn(user_event, pending_events)


class TestUUIDCorrelationUtils(TestCase):
    """Test Guilfoyle's triple-redundancy UUID utilities"""

    def test_embed_uuid_triple_redundancy(self):
        """Test UUID embedding using all three methods"""
        correlation_uuid = str(uuid.uuid4())
        event_data = {
            'summary': 'Test Event',
            'description': 'Test Description'
        }

        enhanced_data = UUIDCorrelationUtils.embed_uuid_in_event(
            event_data=event_data,
            correlation_uuid=correlation_uuid
        )

        # Check ExtendedProperties (primary)
        self.assertIn('extendedProperties', enhanced_data)
        private_props = enhanced_data['extendedProperties']['private']
        self.assertEqual(private_props['calendar_bridge_uuid'], correlation_uuid)

        # Check description HTML comment (backup 1)
        self.assertIn(f'<!-- [CB:{correlation_uuid}] -->', enhanced_data['description'])

        # Check title zero-width characters (backup 2)
        self.assertIn(f'\u200B{correlation_uuid}\u200B', enhanced_data['summary'])

    def test_extract_uuid_from_extended_properties(self):
        """Test UUID extraction from ExtendedProperties (primary method)"""
        correlation_uuid = str(uuid.uuid4())
        google_event = {
            'id': 'test_event',
            'summary': 'Test Event',
            'extendedProperties': {
                'private': {
                    'calendar_bridge_uuid': correlation_uuid
                }
            }
        }

        extracted_uuid = UUIDCorrelationUtils.extract_uuid_from_event(google_event)
        self.assertEqual(extracted_uuid, correlation_uuid)

    def test_extract_uuid_from_description_fallback(self):
        """Test UUID extraction from description (fallback method)"""
        correlation_uuid = str(uuid.uuid4())
        google_event = {
            'id': 'test_event',
            'summary': 'Test Event',
            'description': f'Event description\n<!-- [CB:{correlation_uuid}] -->'
        }

        extracted_uuid = UUIDCorrelationUtils.extract_uuid_from_event(google_event)
        self.assertEqual(extracted_uuid, correlation_uuid)

    def test_extract_uuid_from_title_fallback(self):
        """Test UUID extraction from title (second fallback)"""
        correlation_uuid = str(uuid.uuid4())
        google_event = {
            'id': 'test_event',
            'summary': f'Test Event\u200B{correlation_uuid}\u200B',
            'description': 'Event description'
        }

        extracted_uuid = UUIDCorrelationUtils.extract_uuid_from_event(google_event)
        self.assertEqual(extracted_uuid, correlation_uuid)

    def test_extract_uuid_no_correlation(self):
        """Test UUID extraction when no correlation exists"""
        google_event = {
            'id': 'test_event',
            'summary': 'Test Event',
            'description': 'Event description'
        }

        extracted_uuid = UUIDCorrelationUtils.extract_uuid_from_event(google_event)
        self.assertIsNone(extracted_uuid)

    @patch('apps.calendars.models.EventState.objects.by_uuid')
    def test_is_our_event_detection(self, mock_by_uuid):
        """Test event ownership detection"""
        correlation_uuid = str(uuid.uuid4())

        # Mock EventState lookup
        mock_event_state = Mock()
        mock_event_state.is_busy_block = True
        mock_by_uuid.return_value = mock_event_state

        google_event = {
            'extendedProperties': {
                'private': {
                    'calendar_bridge_uuid': correlation_uuid
                }
            }
        }

        is_ours, uuid_found = UUIDCorrelationUtils.is_our_event(google_event)

        self.assertTrue(is_ours)
        self.assertEqual(uuid_found, correlation_uuid)
        mock_by_uuid.assert_called_once_with(correlation_uuid)

    def test_clean_title_for_display(self):
        """Test removing invisible UUID markers from title"""
        correlation_uuid = str(uuid.uuid4())
        title_with_uuid = f'Meeting Title\u200B{correlation_uuid}\u200B'

        clean_title = UUIDCorrelationUtils.clean_title_for_display(title_with_uuid)

        self.assertEqual(clean_title, 'Meeting Title')
        self.assertNotIn(correlation_uuid, clean_title)

    def test_validate_event_integrity_consistent(self):
        """Test event integrity validation with consistent UUIDs"""
        correlation_uuid = str(uuid.uuid4())

        google_event = {
            'summary': f'Test Event\u200B{correlation_uuid}\u200B',
            'description': f'Description\n<!-- [CB:{correlation_uuid}] -->',
            'extendedProperties': {
                'private': {
                    'calendar_bridge_uuid': correlation_uuid
                }
            }
        }

        report = UUIDCorrelationUtils.validate_event_integrity(google_event)

        self.assertTrue(report['consistent'])
        self.assertEqual(report['primary_uuid'], correlation_uuid)
        self.assertEqual(report['backup1_uuid'], correlation_uuid)
        self.assertEqual(report['backup2_uuid'], correlation_uuid)
        self.assertEqual(len(report['issues']), 0)

    def test_validate_event_integrity_inconsistent(self):
        """Test event integrity validation with inconsistent UUIDs"""
        uuid1 = str(uuid.uuid4())
        uuid2 = str(uuid.uuid4())

        google_event = {
            'summary': f'Test Event\u200B{uuid1}\u200B',
            'description': f'Description\n<!-- [CB:{uuid2}] -->',
            'extendedProperties': {
                'private': {
                    'calendar_bridge_uuid': uuid1
                }
            }
        }

        report = UUIDCorrelationUtils.validate_event_integrity(google_event)

        self.assertFalse(report['consistent'])
        self.assertGreater(len(report['issues']), 0)


class TestLegacyDetectionUtils(TestCase):
    """Test legacy event detection for transition period"""

    def test_legacy_busy_block_detection_title(self):
        """Test legacy busy block detection via title"""
        google_event = {
            'summary': 'Busy - Important Meeting',
            'description': 'Meeting details'
        }

        is_legacy = LegacyDetectionUtils.is_legacy_busy_block(google_event)
        self.assertTrue(is_legacy)

    def test_legacy_busy_block_detection_emoji(self):
        """Test legacy busy block detection via emoji"""
        google_event = {
            'summary': '🔒 Busy - Important Meeting',
            'description': 'Meeting details'
        }

        is_legacy = LegacyDetectionUtils.is_legacy_busy_block(google_event)
        self.assertTrue(is_legacy)

    def test_legacy_busy_block_detection_description(self):
        """Test legacy busy block detection via description"""
        google_event = {
            'summary': 'Important Meeting',
            'description': 'CalSync [source:calendar_123:event_456]'
        }

        is_legacy = LegacyDetectionUtils.is_legacy_busy_block(google_event)
        self.assertTrue(is_legacy)

    def test_not_legacy_busy_block(self):
        """Test normal event is not detected as legacy busy block"""
        google_event = {
            'summary': 'Normal Meeting',
            'description': 'Regular meeting description'
        }

        is_legacy = LegacyDetectionUtils.is_legacy_busy_block(google_event)
        self.assertFalse(is_legacy)

    def test_upgrade_legacy_event(self):
        """Test upgrading legacy event to UUID correlation"""
        correlation_uuid = str(uuid.uuid4())

        legacy_event = {
            'summary': 'Busy - Important Meeting',
            'description': 'CalSync [source:calendar_123:event_456]'
        }

        upgraded_event = LegacyDetectionUtils.upgrade_legacy_event(
            google_event=legacy_event,
            correlation_uuid=correlation_uuid
        )

        # Should have UUID correlation embedded
        extracted_uuid = UUIDCorrelationUtils.extract_uuid_from_event(upgraded_event)
        self.assertEqual(extracted_uuid, correlation_uuid)

        # Should preserve original content
        self.assertEqual(upgraded_event['summary'][:4], 'Busy')  # Title preserved
        self.assertIn('CalSync [source:', upgraded_event['description'])  # Description preserved

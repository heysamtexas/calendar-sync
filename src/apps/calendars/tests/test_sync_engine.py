"""Tests for calendar sync engine"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.calendars.models import Calendar, CalendarAccount, Event, SyncLog
from apps.calendars.services.sync_engine import (
    SyncEngine,
    reset_calendar_busy_blocks,
    sync_all_calendars,
    sync_calendar,
)


@override_settings(
    GOOGLE_OAUTH_CLIENT_ID="test_client_id",
    GOOGLE_OAUTH_CLIENT_SECRET="test_client_secret",
)
class SyncEngineTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.profile = UserProfile.objects.create(user=self.user)
        self.account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="google123",
            email="test@gmail.com",
            access_token="",
            refresh_token="",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )
        self.account.set_access_token("test_token")
        self.account.set_refresh_token("test_refresh")
        self.account.save()

        self.calendar = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal123",
            name="Test Calendar",
            sync_enabled=True,
        )

    def test_sync_engine_initialization(self):
        """Test sync engine initialization"""
        engine = SyncEngine()

        expected_keys = [
            "calendars_processed",
            "events_created",
            "events_updated",
            "events_deleted",
            "busy_blocks_created",
            "busy_blocks_updated",
            "busy_blocks_deleted",
            "errors",
        ]

        for key in expected_keys:
            self.assertIn(key, engine.sync_results)
            if key == "errors":
                self.assertEqual(engine.sync_results[key], [])
            else:
                self.assertEqual(engine.sync_results[key], 0)

    @patch("apps.calendars.services.sync_engine.GoogleCalendarClient")
    def test_sync_all_calendars_no_calendars(self, mock_client_class):
        """Test sync when no active calendars exist"""
        # Make calendar inactive
        self.calendar.sync_enabled = False
        self.calendar.save()

        engine = SyncEngine()
        results = engine.sync_all_calendars()

        self.assertEqual(results["calendars_processed"], 0)
        self.assertEqual(len(results["errors"]), 0)

    @patch("apps.calendars.services.sync_engine.GoogleCalendarClient")
    def test_sync_all_calendars_success(self, mock_client_class):
        """Test successful sync of all calendars"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock Google Calendar events
        mock_events = [
            {
                "id": "event1",
                "summary": "Test Event",
                "description": "Test description",
                "start": {"dateTime": "2023-12-01T10:00:00Z"},
                "end": {"dateTime": "2023-12-01T11:00:00Z"},
                "status": "confirmed",
            }
        ]
        mock_client.list_events.return_value = mock_events
        mock_client.find_system_events.return_value = []

        engine = SyncEngine()
        results = engine.sync_all_calendars()

        self.assertEqual(results["calendars_processed"], 1)
        self.assertEqual(results["events_created"], 1)
        self.assertEqual(len(results["errors"]), 0)

        # Verify event was created
        self.assertTrue(Event.objects.filter(google_event_id="event1").exists())

        # Verify sync log was created
        self.assertTrue(SyncLog.objects.filter(calendar_account=self.account).exists())

    @patch("apps.calendars.services.sync_engine.GoogleCalendarClient")
    def test_sync_specific_calendar(self, mock_client_class):
        """Test syncing a specific calendar"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.list_events.return_value = []

        engine = SyncEngine()
        results = engine.sync_specific_calendar(self.calendar.id)

        self.assertEqual(results["calendars_processed"], 1)
        mock_client.list_events.assert_called_once()

    def test_sync_specific_calendar_not_found(self):
        """Test syncing non-existent calendar"""
        engine = SyncEngine()
        results = engine.sync_specific_calendar(9999)

        self.assertEqual(results["calendars_processed"], 0)
        self.assertEqual(len(results["errors"]), 1)
        self.assertIn("not found", results["errors"][0])

    @patch("apps.calendars.services.sync_engine.GoogleCalendarClient")
    def test_process_google_event_creation(self, mock_client_class):
        """Test processing a new Google Calendar event"""
        google_event = {
            "id": "new_event",
            "summary": "New Meeting",
            "description": "Meeting description",
            "start": {"dateTime": "2023-12-01T14:00:00Z"},
            "end": {"dateTime": "2023-12-01T15:00:00Z"},
            "status": "confirmed",
            "location": "Conference Room A",
        }

        engine = SyncEngine()
        engine._process_google_event(self.calendar, google_event)

        # Verify event was created
        event = Event.objects.get(google_event_id="new_event")
        self.assertEqual(event.title, "New Meeting")
        self.assertEqual(event.description, "Meeting description")

    @patch("apps.calendars.services.sync_engine.GoogleCalendarClient")
    def test_process_google_event_update(self, mock_client_class):
        """Test updating an existing event"""
        # Create existing event
        existing_event = Event.objects.create(
            calendar=self.calendar,
            google_event_id="existing_event",
            title="Old Title",
            description="Old description",
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
        )

        # Google event with updates
        google_event = {
            "id": "existing_event",
            "summary": "Updated Title",
            "description": "Updated description",
            "start": {"dateTime": "2023-12-01T14:00:00Z"},
            "end": {"dateTime": "2023-12-01T15:00:00Z"},
            "status": "confirmed",
        }

        engine = SyncEngine()
        engine._process_google_event(self.calendar, google_event)

        # Verify event was updated
        existing_event.refresh_from_db()
        self.assertEqual(existing_event.title, "Updated Title")
        self.assertEqual(existing_event.description, "Updated description")

    def test_process_google_event_skip_system_events(self):
        """Test that system-created events are skipped"""
        system_events = [
            {
                "id": "system1",
                "summary": "🔒 Busy - Meeting",
                "description": "",
                "start": {"dateTime": "2023-12-01T14:00:00Z"},
                "end": {"dateTime": "2023-12-01T15:00:00Z"},
            },
            {
                "id": "system2",
                "summary": "Regular Meeting",
                "description": "CalSync [source:cal1:event123]",
                "start": {"dateTime": "2023-12-01T16:00:00Z"},
                "end": {"dateTime": "2023-12-01T17:00:00Z"},
            },
        ]

        engine = SyncEngine()

        # Process system events - should be skipped
        for event in system_events:
            engine._process_google_event(self.calendar, event)

        # Verify no events were created
        self.assertEqual(Event.objects.count(), 0)

    def test_parse_event_time_datetime(self):
        """Test parsing datetime from Google Calendar format"""
        engine = SyncEngine()

        # Test with timezone
        time_data = {"dateTime": "2023-12-01T14:00:00Z"}
        parsed = engine._parse_event_time(time_data)
        self.assertEqual(parsed.year, 2023)
        self.assertEqual(parsed.month, 12)
        self.assertEqual(parsed.day, 1)
        self.assertEqual(parsed.hour, 14)

    def test_parse_event_time_date(self):
        """Test parsing all-day date from Google Calendar format"""
        engine = SyncEngine()

        time_data = {"date": "2023-12-01"}
        parsed = engine._parse_event_time(time_data)
        self.assertEqual(parsed.year, 2023)
        self.assertEqual(parsed.month, 12)
        self.assertEqual(parsed.day, 1)
        self.assertEqual(parsed.hour, 0)

    def test_event_needs_update(self):
        """Test event update detection"""
        event = Event.objects.create(
            calendar=self.calendar,
            google_event_id="test_event",
            title="Old Title",
            description="Old desc",
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
        )

        engine = SyncEngine()

        # Same data - no update needed
        same_data = {
            "title": "Old Title",
            "description": "Old desc",
            "start_time": event.start_time,
            "end_time": event.end_time,
            "is_all_day": False,
            "is_meeting_invite": False,
        }
        self.assertFalse(engine._event_needs_update(event, same_data))

        # Different title - update needed
        different_data = same_data.copy()
        different_data["title"] = "New Title"
        self.assertTrue(engine._event_needs_update(event, different_data))

    @patch("apps.calendars.services.sync_engine.GoogleCalendarClient")
    def test_cleanup_deleted_events(self, mock_client_class):
        """Test cleanup of events deleted from Google Calendar"""
        # Create events in our database
        Event.objects.create(
            calendar=self.calendar,
            google_event_id="event1",
            title="Event 1",
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            is_busy_block=False,
        )

        Event.objects.create(
            calendar=self.calendar,
            google_event_id="event2",
            title="Event 2",
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            is_busy_block=False,
        )

        # Google Calendar only has event1
        google_events = [{"id": "event1", "summary": "Event 1"}]

        engine = SyncEngine()
        engine._cleanup_deleted_events(self.calendar, google_events)

        # event1 should still exist, event2 should be deleted
        self.assertTrue(Event.objects.filter(google_event_id="event1").exists())
        self.assertFalse(Event.objects.filter(google_event_id="event2").exists())
        self.assertEqual(engine.sync_results["events_deleted"], 1)

    def test_utility_functions(self):
        """Test utility functions"""
        with patch(
            "apps.calendars.services.sync_engine.SyncEngine"
        ) as mock_engine_class:
            mock_engine = MagicMock()
            mock_engine_class.return_value = mock_engine
            mock_engine.sync_all_calendars.return_value = {"test": "result"}
            mock_engine.sync_specific_calendar.return_value = {"test": "result"}

            # Test sync_all_calendars function
            result = sync_all_calendars(verbose=True)
            self.assertEqual(result, {"test": "result"})
            mock_engine.sync_all_calendars.assert_called_with(verbose=True)

            # Test sync_calendar function
            result = sync_calendar(123)
            self.assertEqual(result, {"test": "result"})
            mock_engine.sync_specific_calendar.assert_called_with(123)

    @patch("apps.calendars.services.sync_engine.GoogleCalendarClient")
    def test_reset_calendar_busy_blocks(self, mock_client_class):
        """Test resetting calendar busy blocks"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock system events
        mock_system_events = [{"id": "busy1"}, {"id": "busy2"}]
        mock_client.find_system_events.return_value = mock_system_events
        mock_client.batch_delete_events.return_value = {"busy1": True, "busy2": True}

        # Create a source event first
        source_event = Event.objects.create(
            calendar=self.calendar,
            google_event_id="source1",
            title="Source Event",
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            is_busy_block=False,
        )

        # Create some system events in database
        Event.objects.create(
            calendar=self.calendar,
            google_event_id="busy1",
            title="🔒 Busy Block",
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
            is_busy_block=True,
            source_event=source_event,
        )

        result = reset_calendar_busy_blocks(self.calendar.id)

        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_count"], 2)
        self.assertEqual(result["calendar_name"], self.calendar.name)

        # Verify system events were deleted from database
        self.assertFalse(Event.objects.filter(is_busy_block=True).exists())

    def test_reset_calendar_not_found(self):
        """Test reset with non-existent calendar"""
        result = reset_calendar_busy_blocks(9999)

        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])

    @patch("apps.calendars.services.sync_engine.GoogleCalendarClient")
    def test_cross_calendar_busy_blocks(self, mock_client_class):
        """Test creation of cross-calendar busy blocks"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Create second calendar
        calendar2 = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal456",
            name="Second Calendar",
            sync_enabled=True,
        )

        # Create event in first calendar
        event = Event.objects.create(
            calendar=self.calendar,
            google_event_id="source_event",
            title="Source Meeting",
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=1),
            is_busy_block=False,
        )

        # Mock busy block creation
        mock_client.create_busy_block.return_value = {"id": "busy_block_id"}
        mock_client.find_system_events.return_value = []
        mock_client.batch_delete_events.return_value = {}

        engine = SyncEngine()
        engine._create_cross_calendar_busy_blocks()

        # Verify busy block creation was called
        mock_client.create_busy_block.assert_called()

        # Check the call arguments
        call_args = mock_client.create_busy_block.call_args
        self.assertEqual(
            call_args[0][0], calendar2.google_calendar_id
        )  # target calendar
        self.assertIn("🔒 Busy", call_args[0][1])  # title
        self.assertEqual(call_args[0][2], event.start_time)  # start time
        self.assertEqual(call_args[0][3], event.end_time)  # end time

    @patch("apps.calendars.services.sync_engine.GoogleCalendarClient")
    def test_busy_block_tag_length_limit(self, mock_client_class):
        """Test that busy block tags respect the 200 character database limit"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Create test accounts and calendars
        from apps.accounts.models import UserProfile
        
        profile, created = UserProfile.objects.get_or_create(
            user=self.user, defaults={'sync_enabled': True}
        )
        if not created:
            profile.sync_enabled = True
            profile.save()
        
        calendar1 = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="very-long-google-calendar-id-that-could-cause-issues@group.calendar.google.com",
            name="Source Calendar",
            sync_enabled=True,
        )
        
        calendar2 = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="another-very-long-google-calendar-id@group.calendar.google.com",
            name="Target Calendar", 
            sync_enabled=True,
        )

        # Create source event
        event = Event.objects.create(
            calendar=calendar1,
            google_event_id="extremely-long-google-event-id-that-would-normally-cause-busy-block-tag-to-exceed-database-limit-12345",
            title="GZ CMS & PME daily-ish standup",
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=1),
            is_busy_block=False,
        )

        # Mock busy block creation
        mock_client.create_busy_block.return_value = {"id": "busy_block_id"}
        mock_client.find_system_events.return_value = []
        mock_client.batch_delete_events.return_value = {}

        engine = SyncEngine()
        engine._create_cross_calendar_busy_blocks()

        # Verify busy blocks were created in database
        busy_blocks = Event.objects.filter(is_busy_block=True)
        self.assertGreaterEqual(busy_blocks.count(), 1, "At least one busy block should be created")
        
        # Verify all busy block tags are within the database limit
        for busy_block in busy_blocks:
            self.assertLessEqual(len(busy_block.busy_block_tag), 200, 
                               f"Busy block tag '{busy_block.busy_block_tag}' exceeds 200 character limit")
            
            # Verify the tag follows the expected format
            self.assertIn("CalSync [source:", busy_block.busy_block_tag)
            self.assertIn(":event", busy_block.busy_block_tag)
            self.assertIn("]", busy_block.busy_block_tag)

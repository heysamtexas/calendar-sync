"""
Tests for sync_calendars management command
"""

from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.calendars.models import Calendar, CalendarAccount


User = get_user_model()


class SyncCalendarsCommandTest(TestCase):
    """Test the sync_calendars management command"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create user profile
        self.profile = UserProfile.objects.create(
            user=self.user,
            sync_enabled=True,
        )

        # Create calendar account
        from datetime import timedelta

        from django.utils import timezone

        self.account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="test@example.com",
            email="test@example.com",
            access_token="encrypted_token",
            refresh_token="encrypted_refresh",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        # Create calendars
        self.calendar1 = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal1",
            name="Test Calendar 1",
            sync_enabled=True,
        )

        self.calendar2 = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal2",
            name="Test Calendar 2",
            sync_enabled=False,  # Disabled but not in cleanup
            cleanup_pending=False,  # Explicitly not in cleanup state
        )

        # Create another user's calendar
        self.user2 = User.objects.create_user(
            username="user2", email="user2@example.com", password="testpass123"
        )

        # Create user profile for user2
        self.profile2 = UserProfile.objects.create(
            user=self.user2,
            sync_enabled=True,
        )

        self.account2 = CalendarAccount.objects.create(
            user=self.user2,
            google_account_id="user2@example.com",
            email="user2@example.com",
            access_token="encrypted_token2",
            refresh_token="encrypted_refresh2",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )
        self.calendar3 = Calendar.objects.create(
            calendar_account=self.account2,
            google_calendar_id="cal3",
            name="User 2 Calendar",
            sync_enabled=True,
        )

        # Create a calendar in cleanup state (sync_enabled=True but cleanup_pending=True)
        self.calendar_in_cleanup = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal_cleanup",
            name="Calendar In Cleanup",
            sync_enabled=False,
            cleanup_pending=True,
        )

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_sync_all_calendars(self, mock_sync):
        """Test syncing all calendars"""
        mock_sync.return_value = {
            'user_events_found': 5,
            'busy_blocks_created': 3,
            'our_events_skipped': 2,
            'events_processed': 10,
            'errors': []
        }

        out = StringIO()
        call_command('sync_calendars', force=True, stdout=out)

        output = out.getvalue()

        # Should sync 2 calendars (calendar1 and calendar3, but not calendar2 which is disabled)
        self.assertIn('Will sync 2 calendars:', output)
        self.assertIn('Test Calendar 1', output)
        self.assertIn('User 2 Calendar', output)
        self.assertNotIn('Test Calendar 2', output)  # Disabled calendar

        # Should show success
        self.assertIn('Successfully synced: 2 calendars', output)
        self.assertIn('All calendars synced successfully!', output)

        # Verify sync was called for enabled calendars
        self.assertEqual(mock_sync.call_count, 2)

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_sync_specific_user(self, mock_sync):
        """Test syncing calendars for specific user"""
        mock_sync.return_value = {
            'user_events_found': 3,
            'busy_blocks_created': 1,
            'our_events_skipped': 0,
            'events_processed': 4,
            'errors': []
        }

        out = StringIO()
        call_command('sync_calendars', user_email='test@example.com', force=True, stdout=out)

        output = out.getvalue()

        # Should only sync user1's enabled calendar
        self.assertIn('Will sync 1 calendars:', output)
        self.assertIn('Test Calendar 1', output)
        self.assertNotIn('User 2 Calendar', output)

        # Verify sync was called once
        self.assertEqual(mock_sync.call_count, 1)
        mock_sync.assert_called_with(self.calendar1)

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_sync_specific_calendar(self, mock_sync):
        """Test syncing specific calendar by ID"""
        mock_sync.return_value = {
            'user_events_found': 2,
            'busy_blocks_created': 0,
            'our_events_skipped': 1,
            'events_processed': 3,
            'errors': []
        }

        out = StringIO()
        call_command('sync_calendars', calendar_id=self.calendar1.id, force=True, stdout=out)

        output = out.getvalue()

        # Should sync only the specified calendar
        self.assertIn('Will sync 1 calendars:', output)
        self.assertIn('Test Calendar 1', output)

        # Verify sync was called with correct calendar
        mock_sync.assert_called_once_with(self.calendar1)

    def test_dry_run(self):
        """Test dry run mode"""
        out = StringIO()
        call_command('sync_calendars', dry_run=True, stdout=out)

        output = out.getvalue()

        # Should show dry run info
        self.assertIn('DRY RUN - Will sync 2 calendars:', output)
        self.assertIn('Dry run complete. Use without --dry-run to execute.', output)

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_sync_with_errors(self, mock_sync):
        """Test handling sync errors"""
        mock_sync.side_effect = [
            {
                'user_events_found': 1,
                'busy_blocks_created': 0,
                'our_events_skipped': 0,
                'events_processed': 1,
                'errors': ['Some error occurred']
            },
            Exception("Sync failed")
        ]

        out = StringIO()
        call_command('sync_calendars', force=True, stdout=out)

        output = out.getvalue()

        # Should show partial success
        self.assertIn('Successfully synced: 1 calendars', output)
        self.assertIn('Failed to sync: 1 calendars', output)
        self.assertIn('Some error occurred', output)

    def test_invalid_user_email(self):
        """Test with invalid user email"""
        with self.assertRaises(SystemExit):
            call_command('sync_calendars', user_email='nonexistent@example.com')

    def test_invalid_calendar_id(self):
        """Test with invalid calendar ID"""
        with self.assertRaises(SystemExit):
            call_command('sync_calendars', calendar_id=99999)

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_force_sync_inactive_calendar(self, mock_sync):
        """Test force syncing inactive calendar"""
        # Deactivate account
        self.account.is_active = False
        self.account.save()

        mock_sync.return_value = {
            'user_events_found': 1,
            'busy_blocks_created': 0,
            'our_events_skipped': 0,
            'events_processed': 1,
            'errors': []
        }

        out = StringIO()
        call_command('sync_calendars', force=True, stdout=out)

        output = out.getvalue()

        # Should attempt sync even with inactive account when forced
        self.assertIn('Successfully synced:', output)

    def test_show_calendar_status_info(self):
        """Test that calendar status is shown in dry run"""
        # Make account token expired
        from datetime import timedelta

        from django.utils import timezone

        self.account.token_expires_at = timezone.now() - timedelta(hours=1)
        self.account.save()

        out = StringIO()
        call_command('sync_calendars', dry_run=True, stdout=out)

        output = out.getvalue()

        # Should show token status
        self.assertIn('[TOKEN EXPIRED]', output)


class SyncCalendarsCommandIntegrationTest(TestCase):
    """Integration tests for sync command with real sync engine"""

    def setUp(self):
        """Set up minimal test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create user profile
        self.profile = UserProfile.objects.create(
            user=self.user,
            sync_enabled=True,
        )

        from datetime import timedelta

        from django.utils import timezone

        self.account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="test@example.com",
            email="test@example.com",
            access_token="encrypted_token",
            refresh_token="encrypted_refresh",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient')
    def test_command_with_mocked_google_client(self, mock_client_class):
        """Test command with mocked Google Calendar client"""
        # Setup mock client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.list_events_with_uuid_extraction.return_value = []

        # Create calendar
        calendar = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="test_cal",
            name="Test Calendar",
            sync_enabled=True,
        )

        out = StringIO()
        call_command('sync_calendars', stdout=out, verbosity=0)

        # Should complete without errors
        output = out.getvalue()
        self.assertIn('Successfully synced: 1 calendars', output)

        # Verify Google client was called
        mock_client.list_events_with_uuid_extraction.assert_called_once_with('test_cal')

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_sync_excludes_cleanup_pending_calendars(self, mock_sync):
        """Test that calendars in cleanup state are excluded from sync"""
        mock_sync.return_value = {
            'user_events_found': 1,
            'busy_blocks_created': 0,
            'our_events_skipped': 0,
            'events_processed': 1,
            'errors': []
        }

        out = StringIO()
        call_command('sync_calendars', force=True, stdout=out)

        output = out.getvalue()

        # Should sync 2 calendars (calendar1 and calendar3, excluding disabled and cleanup calendars)
        self.assertIn('Will sync 2 calendars:', output)
        self.assertIn('Test Calendar 1', output)
        self.assertIn('User 2 Calendar', output)
        self.assertNotIn('Test Calendar 2', output)  # Disabled calendar
        self.assertNotIn('Calendar In Cleanup', output)  # Calendar in cleanup state

        # Verify sync was called for only enabled, non-cleanup calendars
        self.assertEqual(mock_sync.call_count, 2)

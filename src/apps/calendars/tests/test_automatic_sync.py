"""
Tests for automatic sync triggers when calendars are enabled
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.calendars.models import Calendar, CalendarAccount
from apps.calendars.services.calendar_service import CalendarService


User = get_user_model()


class AutomaticSyncTest(TestCase):
    """Test automatic sync triggers"""

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

        # Create calendar (initially disabled)
        self.calendar = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal1",
            name="Test Calendar",
            sync_enabled=False,
        )

        self.service = CalendarService(self.user)

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_toggle_calendar_sync_triggers_initial_sync(self, mock_sync):
        """Test that enabling calendar sync triggers initial sync"""
        mock_sync.return_value = {
            'user_events_found': 3,
            'busy_blocks_created': 2,
            'our_events_skipped': 1,
            'events_processed': 6,
            'errors': []
        }

        # Toggle calendar sync from disabled to enabled
        result_calendar = self.service.toggle_calendar_sync(self.calendar.id)

        # Verify calendar is now enabled
        self.assertTrue(result_calendar.sync_enabled)

        # Verify initial sync was triggered
        mock_sync.assert_called_once_with(self.calendar)

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_toggle_calendar_sync_no_sync_when_disabling(self, mock_sync):
        """Test that disabling calendar sync does not trigger sync"""
        # Start with enabled calendar
        self.calendar.sync_enabled = True
        self.calendar.save()

        # Toggle calendar sync from enabled to disabled
        result_calendar = self.service.toggle_calendar_sync(self.calendar.id)

        # Verify calendar is now disabled
        self.assertFalse(result_calendar.sync_enabled)

        # Verify no sync was triggered
        mock_sync.assert_not_called()

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_toggle_blocks_immediate_re_enable_during_cleanup(self, mock_sync):
        """Test that locked state pattern prevents immediate re-enable during cleanup"""
        from apps.calendars.services.base import BusinessLogicError

        # Start with enabled calendar
        self.calendar.sync_enabled = True
        self.calendar.save()

        # Disable sync (marks for cleanup)
        disabled_calendar = self.service.toggle_calendar_sync(self.calendar.id)
        self.assertFalse(disabled_calendar.sync_enabled)
        self.assertTrue(disabled_calendar.cleanup_pending)

        # Try to re-enable immediately (should fail with locked state protection)
        with self.assertRaises(BusinessLogicError) as context:
            self.service.toggle_calendar_sync(self.calendar.id)

        # Verify the error message mentions cleanup
        self.assertIn("cleanup is in progress", str(context.exception))

        # Verify sync was not called (calendar is locked)
        mock_sync.assert_not_called()

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_bulk_toggle_triggers_sync_for_newly_enabled(self, mock_sync):
        """Test that bulk enabling calendars triggers sync for newly enabled ones"""
        # Create another disabled calendar
        calendar2 = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal2",
            name="Test Calendar 2",
            sync_enabled=False,
        )

        # Create a third calendar that's already enabled
        calendar3 = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal3",
            name="Test Calendar 3",
            sync_enabled=True,
        )

        mock_sync.return_value = {
            'user_events_found': 1,
            'busy_blocks_created': 0,
            'our_events_skipped': 0,
            'events_processed': 1,
            'errors': []
        }

        # Bulk enable calendars
        calendar_ids = [self.calendar.id, calendar2.id, calendar3.id]
        updated_calendars = self.service.bulk_toggle_calendars(calendar_ids, enable=True)

        # Verify only the newly enabled calendars (not already enabled calendar3)
        self.assertEqual(len(updated_calendars), 2)  # calendar and calendar2

        # Verify sync was called for both newly enabled calendars
        self.assertEqual(mock_sync.call_count, 2)
        mock_sync.assert_any_call(self.calendar)
        mock_sync.assert_any_call(calendar2)

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_bulk_toggle_disable_no_sync(self, mock_sync):
        """Test that bulk disabling calendars doesn't trigger sync"""
        # Start with enabled calendars
        self.calendar.sync_enabled = True
        self.calendar.save()

        calendar2 = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal2",
            name="Test Calendar 2",
            sync_enabled=True,
        )

        # Bulk disable calendars
        calendar_ids = [self.calendar.id, calendar2.id]
        updated_calendars = self.service.bulk_toggle_calendars(calendar_ids, enable=False)

        # Verify calendars were updated
        self.assertEqual(len(updated_calendars), 2)

        # Verify no sync was triggered
        mock_sync.assert_not_called()

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_sync_fails_gracefully_on_error(self, mock_sync):
        """Test that sync errors are handled gracefully"""
        mock_sync.side_effect = Exception("Sync failed")

        # Toggle calendar sync - should not raise exception
        result_calendar = self.service.toggle_calendar_sync(self.calendar.id)

        # Calendar should still be enabled despite sync failure
        self.assertTrue(result_calendar.sync_enabled)

        # Verify sync was attempted
        mock_sync.assert_called_once_with(self.calendar)

    @patch('apps.calendars.services.calendar_service.CalendarService._log_operation')
    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_sync_success_is_logged(self, mock_sync, mock_log):
        """Test that successful sync is logged"""
        mock_sync.return_value = {
            'user_events_found': 2,
            'busy_blocks_created': 1,
            'our_events_skipped': 0,
            'events_processed': 3,
            'errors': []
        }

        # Toggle calendar sync
        self.service.toggle_calendar_sync(self.calendar.id)

        # Verify both status change and initial sync logging were called
        log_calls = [call[0][0] for call in mock_log.call_args_list]
        self.assertIn('calendar_sync_status_change', log_calls)
        self.assertIn('initial_sync_triggered', log_calls)

    @patch('apps.calendars.services.calendar_service.CalendarService._log_operation')
    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_sync_failure_is_logged(self, mock_sync, mock_log):
        """Test that sync failure is logged"""
        mock_sync.side_effect = Exception("Sync failed")

        # Toggle calendar sync
        self.service.toggle_calendar_sync(self.calendar.id)

        # Verify error logging was called
        log_calls = [call[0][0] for call in mock_log.call_args_list]
        self.assertIn('initial_sync_failed', log_calls)

    def test_inactive_account_no_sync_trigger(self):
        """Test that inactive accounts reject sync enablement"""
        from apps.calendars.services.base import BusinessLogicError

        # Deactivate account
        self.account.is_active = False
        self.account.save()

        with patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo') as mock_sync:
            # Toggle calendar sync should fail with inactive account
            with self.assertRaises(BusinessLogicError) as context:
                self.service.toggle_calendar_sync(self.calendar.id)

            # Verify the error message mentions inactive account
            self.assertIn("is inactive", str(context.exception))
            mock_sync.assert_not_called()

    def test_expired_token_no_sync_trigger(self):
        """Test that expired tokens reject sync enablement"""
        from datetime import timedelta

        from django.utils import timezone

        from apps.calendars.services.base import BusinessLogicError

        # Set expired token
        self.account.token_expires_at = timezone.now() - timedelta(hours=1)
        self.account.save()

        with patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo') as mock_sync:
            # Toggle calendar sync should fail with expired token
            with self.assertRaises(BusinessLogicError) as context:
                self.service.toggle_calendar_sync(self.calendar.id)

            # Verify the error message mentions token refresh failure
            self.assertIn("Unable to refresh expired token", str(context.exception))
            mock_sync.assert_not_called()


class CalendarSyncValidationTest(TestCase):
    """Test calendar sync validation logic"""

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

        # Create active account
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

        self.calendar = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal1",
            name="Test Calendar",
            sync_enabled=True,
        )

        self.service = CalendarService(self.user)

    def test_can_sync_validation_active_calendar(self):
        """Test sync validation for active calendar"""
        can_sync, reason = self.calendar.can_sync()
        self.assertTrue(can_sync)
        self.assertEqual(reason, "Calendar is ready for sync")

    def test_can_sync_validation_inactive_account(self):
        """Test sync validation for inactive account"""
        self.account.is_active = False
        self.account.save()

        can_sync, reason = self.calendar.can_sync()
        self.assertFalse(can_sync)
        self.assertEqual(reason, "Account is inactive")

    def test_can_sync_validation_expired_token(self):
        """Test sync validation for expired token"""
        from datetime import timedelta

        from django.utils import timezone

        self.account.token_expires_at = timezone.now() - timedelta(hours=1)
        self.account.save()

        can_sync, reason = self.calendar.can_sync()
        self.assertFalse(can_sync)
        self.assertEqual(reason, "Token has expired")

    def test_can_sync_validation_disabled_sync(self):
        """Test sync validation for disabled sync"""
        self.calendar.sync_enabled = False
        self.calendar.save()

        can_sync, reason = self.calendar.can_sync()
        self.assertFalse(can_sync)
        self.assertEqual(reason, "Sync is disabled for this calendar")

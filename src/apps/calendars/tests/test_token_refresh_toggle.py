"""
Tests for token refresh during calendar toggle operations
"""

from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from apps.calendars.models import Calendar, CalendarAccount
from apps.calendars.services.calendar_service import CalendarService
from apps.calendars.services.base import BusinessLogicError
from apps.accounts.models import UserProfile

User = get_user_model()


class TokenRefreshToggleTest(TestCase):
    """Test token refresh functionality during calendar toggle"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="tokentest",
            email="tokentest@example.com",
            password="testpass123"
        )
        
        # Create user profile
        self.profile = UserProfile.objects.create(
            user=self.user,
            sync_enabled=True,
        )
        
        # Create calendar account with expired token
        self.account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="tokentest@example.com",
            email="tokentest@example.com",
            access_token="encrypted_expired_token",
            refresh_token="encrypted_refresh_token",
            token_expires_at=timezone.now() - timedelta(hours=1),  # Expired
            is_active=True,
        )
        
        # Create calendar
        self.calendar = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="test_cal_token",
            name="Test Calendar",
            sync_enabled=False,  # Start disabled
        )

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    @patch('apps.calendars.services.token_manager.TokenManager')
    def test_toggle_on_with_successful_token_refresh(self, mock_token_manager_class, mock_sync):
        """Test toggling calendar ON with successful token refresh"""
        # Setup mocks
        mock_token_manager = MagicMock()
        mock_token_manager_class.return_value = mock_token_manager
        
        # Mock successful token refresh - this should update the token expiration
        mock_credentials = MagicMock()
        
        def mock_get_valid_credentials():
            # Simulate successful token refresh by updating the account's token expiration
            self.account.token_expires_at = timezone.now() + timedelta(hours=1)
            self.account.save()
            return mock_credentials
        
        mock_token_manager.get_valid_credentials.side_effect = mock_get_valid_credentials
        
        # Mock sync results
        mock_sync.return_value = {
            'user_events_found': 2,
            'busy_blocks_created': 1,
            'our_events_skipped': 0,
            'errors': []
        }
        
        # Verify initial state
        self.assertFalse(self.calendar.sync_enabled)
        self.assertTrue(self.account.is_token_expired)
        
        # Toggle calendar sync ON
        service = CalendarService(user=self.user)
        result = service.toggle_calendar_sync(self.calendar.id)
        
        # Verify calendar was enabled
        self.assertTrue(result.sync_enabled)
        
        # Verify token manager was called
        mock_token_manager_class.assert_called_once_with(self.account)
        mock_token_manager.get_valid_credentials.assert_called_once()
        
        # Verify sync was triggered
        mock_sync.assert_called_once_with(self.calendar)
        
        # Verify token is no longer expired
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_token_expired)

    @patch('apps.calendars.services.token_manager.TokenManager')
    def test_toggle_on_with_failed_token_refresh(self, mock_token_manager_class):
        """Test toggling calendar ON with failed token refresh"""
        # Setup mocks
        mock_token_manager = MagicMock()
        mock_token_manager_class.return_value = mock_token_manager
        
        # Mock failed token refresh
        mock_token_manager.get_valid_credentials.return_value = None
        
        # Verify initial state
        self.assertFalse(self.calendar.sync_enabled)
        self.assertTrue(self.account.is_token_expired)
        
        # Toggle calendar sync ON should fail
        service = CalendarService(user=self.user)
        
        with self.assertRaises(BusinessLogicError) as context:
            service.toggle_calendar_sync(self.calendar.id)
        
        # Verify error message mentions token refresh failure
        self.assertIn("Unable to refresh expired token", str(context.exception))
        
        # Verify calendar remains disabled after failed toggle
        self.calendar.refresh_from_db()
        self.assertFalse(self.calendar.sync_enabled)
        
        # Verify token manager was called
        mock_token_manager_class.assert_called_once_with(self.account)
        mock_token_manager.get_valid_credentials.assert_called_once()

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    def test_toggle_on_with_valid_token_no_refresh_needed(self, mock_sync):
        """Test toggling calendar ON when token is already valid"""
        # Update account to have valid token
        self.account.token_expires_at = timezone.now() + timedelta(hours=1)
        self.account.save()
        
        # Mock sync results
        mock_sync.return_value = {
            'user_events_found': 1,
            'busy_blocks_created': 0,
            'our_events_skipped': 0,
            'errors': []
        }
        
        # Verify token is not expired
        self.assertFalse(self.account.is_token_expired)
        
        # Toggle calendar sync ON
        service = CalendarService(user=self.user)
        result = service.toggle_calendar_sync(self.calendar.id)
        
        # Verify calendar was enabled
        self.assertTrue(result.sync_enabled)
        
        # Verify sync was triggered
        mock_sync.assert_called_once_with(self.calendar)

    def test_toggle_on_with_inactive_account(self):
        """Test toggling calendar ON with inactive account"""
        # Deactivate account
        self.account.is_active = False
        self.account.save()
        
        # Toggle calendar sync ON should fail
        service = CalendarService(user=self.user)
        
        with self.assertRaises(BusinessLogicError) as context:
            service.toggle_calendar_sync(self.calendar.id)
        
        # Verify error message mentions inactive account
        self.assertIn("Account", str(context.exception))
        self.assertIn("is inactive", str(context.exception))
        
        # Verify calendar remains disabled
        self.calendar.refresh_from_db()
        self.assertFalse(self.calendar.sync_enabled)

    @patch('apps.calendars.services.uuid_sync_engine.sync_calendar_yolo')
    @patch('apps.calendars.services.token_manager.TokenManager')
    def test_bulk_toggle_with_mixed_token_states(self, mock_token_manager_class, mock_sync):
        """Test bulk toggle with some calendars having expired tokens"""
        # Create second calendar with valid token
        account2 = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="valid@example.com",
            email="valid@example.com",
            access_token="encrypted_valid_token",
            refresh_token="encrypted_refresh_token2",
            token_expires_at=timezone.now() + timedelta(hours=1),  # Valid
            is_active=True,
        )
        
        calendar2 = Calendar.objects.create(
            calendar_account=account2,
            google_calendar_id="valid_cal",
            name="Valid Calendar",
            sync_enabled=False,
        )
        
        # Setup mocks
        mock_token_manager = MagicMock()
        mock_token_manager_class.return_value = mock_token_manager
        
        # Mock successful token refresh for expired account
        mock_credentials = MagicMock()
        
        def mock_get_valid_credentials():
            # Simulate successful token refresh by updating the account's token expiration
            self.account.token_expires_at = timezone.now() + timedelta(hours=1)
            self.account.save()
            return mock_credentials
        
        mock_token_manager.get_valid_credentials.side_effect = mock_get_valid_credentials
        
        mock_sync.return_value = {
            'user_events_found': 1,
            'busy_blocks_created': 0,
            'our_events_skipped': 0,
            'errors': []
        }
        
        # Bulk toggle both calendars ON
        service = CalendarService(user=self.user)
        result = service.bulk_toggle_calendars([self.calendar.id, calendar2.id], enable=True)
        
        # If no failures, result should be just the list of updated calendars
        if isinstance(result, list):
            self.assertEqual(len(result), 2)
        else:
            # If there were failures, check the structure
            self.assertIn("updated_calendars", result)
            self.assertIn("failed_calendars", result)
        
        # Verify sync was called for successfully enabled calendars
        self.assertGreater(mock_sync.call_count, 0)

    @patch('apps.calendars.services.calendar_service.CalendarService._enable_calendar_sync_with_validation')
    def test_validation_method_error_handling(self, mock_validation):
        """Test error handling in the validation method"""
        # Mock validation failure
        mock_validation.return_value = {
            "success": False,
            "error": "Test validation error",
            "error_type": "test_error"
        }
        
        # Toggle should fail and revert
        service = CalendarService(user=self.user)
        
        with self.assertRaises(BusinessLogicError) as context:
            service.toggle_calendar_sync(self.calendar.id)
        
        # Verify error message
        self.assertIn("Test validation error", str(context.exception))
        
        # Verify calendar remains disabled
        self.calendar.refresh_from_db()
        self.assertFalse(self.calendar.sync_enabled)
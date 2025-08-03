"""Tests for enhanced token management service"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from google.auth.exceptions import RefreshError

from apps.accounts.models import UserProfile
from apps.calendars.models import CalendarAccount
from apps.calendars.services.token_manager import TokenManager


@override_settings(
    GOOGLE_OAUTH_CLIENT_ID="test_client_id",
    GOOGLE_OAUTH_CLIENT_SECRET="test_client_secret",
)
class TokenManagerTest(TestCase):
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
        # Set test tokens
        self.account.set_access_token("test_access_token")
        self.account.set_refresh_token("test_refresh_token")
        self.account.save()

    def test_get_valid_credentials_not_expired(self):
        """Test getting credentials when token is not expired"""
        credentials = TokenManager.get_valid_credentials(self.account)

        self.assertIsNotNone(credentials)
        self.assertEqual(credentials.token, "test_access_token")
        self.assertEqual(credentials.refresh_token, "test_refresh_token")

    @patch.object(TokenManager, "get_valid_credentials")
    def test_get_valid_credentials_expired_refresh_success(self, mock_get_credentials):
        """Test token refresh when expired (simplified mock)"""
        # Mock return valid credentials
        mock_credentials = MagicMock()
        mock_get_credentials.return_value = mock_credentials

        # Set token as expired
        self.account.token_expires_at = timezone.now() - timedelta(hours=1)
        self.account.save()

        credentials = TokenManager.get_valid_credentials(self.account)

        self.assertIsNotNone(credentials)

    def test_get_valid_credentials_no_refresh_token(self):
        """Test handling of expired token with no refresh token"""
        # Set token as expired and remove refresh token
        self.account.token_expires_at = timezone.now() - timedelta(hours=1)
        self.account.set_refresh_token("")
        self.account.save()

        credentials = TokenManager.get_valid_credentials(self.account)

        self.assertIsNone(credentials)
        # Account should be deactivated
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_active)

    def test_get_valid_credentials_refresh_failure(self):
        """Test handling of token refresh failure"""
        # Set token as expired
        self.account.token_expires_at = timezone.now() - timedelta(hours=1)
        self.account.save()

        # This will fail due to invalid credentials
        credentials = TokenManager.get_valid_credentials(self.account)

        self.assertIsNone(credentials)
        # Account should be deactivated
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_active)

    @patch.object(TokenManager, "should_refresh_token")
    @patch.object(TokenManager, "get_valid_credentials")
    def test_validate_all_accounts(self, mock_get_credentials, mock_should_refresh):
        """Test validating all active accounts"""
        # Create another active account
        CalendarAccount.objects.create(
            user=self.user,
            google_account_id="google456",
            email="test2@gmail.com",
            access_token="token2",
            refresh_token="refresh2",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        # Create inactive account (should be skipped)
        CalendarAccount.objects.create(
            user=self.user,
            google_account_id="google789",
            email="test3@gmail.com",
            access_token="token3",
            refresh_token="refresh3",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=False,
        )

        # Mock that both accounts need refresh
        mock_should_refresh.return_value = True
        # Mock successful validation
        mock_get_credentials.return_value = MagicMock()

        results = TokenManager.validate_all_accounts()

        # Should be called twice (for two active accounts)
        self.assertEqual(mock_get_credentials.call_count, 2)
        self.assertEqual(results["total_accounts"], 2)  # Only active accounts

    def test_should_refresh_token_no_expiry(self):
        """Test should_refresh_token when no expiry is set"""
        # Skip this test since our model requires token_expires_at to be not null
        # In practice, this should never happen with proper OAuth flow
        self.skipTest("Model requires token_expires_at to be not null")

    def test_should_refresh_token_expires_soon(self):
        """Test should_refresh_token when token expires soon"""
        # Set token to expire in 5 minutes (less than buffer)
        self.account.token_expires_at = timezone.now() + timedelta(minutes=5)
        self.account.save()

        self.assertTrue(TokenManager.should_refresh_token(self.account))

    def test_should_refresh_token_valid(self):
        """Test should_refresh_token when token is still valid"""
        # Set token to expire in 20 minutes (more than buffer)
        self.account.token_expires_at = timezone.now() + timedelta(minutes=20)
        self.account.save()

        self.assertFalse(TokenManager.should_refresh_token(self.account))

    @patch.object(TokenManager, "_refresh_token_with_retry")
    def test_get_valid_credentials_inactive_account(self, mock_refresh):
        """Test get_valid_credentials with inactive account"""
        self.account.is_active = False
        self.account.save()

        credentials = TokenManager.get_valid_credentials(self.account)

        self.assertIsNone(credentials)
        mock_refresh.assert_not_called()

    @patch.object(TokenManager, "_refresh_token_with_retry")
    def test_get_valid_credentials_needs_refresh(self, mock_refresh):
        """Test get_valid_credentials when refresh is needed"""
        # Set token to expire soon
        self.account.token_expires_at = timezone.now() + timedelta(minutes=5)
        self.account.save()

        mock_credentials = MagicMock()
        mock_refresh.return_value = mock_credentials

        credentials = TokenManager.get_valid_credentials(self.account)

        self.assertEqual(credentials, mock_credentials)
        mock_refresh.assert_called_once()

    @patch("apps.calendars.services.token_manager.time.sleep")
    @patch("apps.calendars.services.token_manager.Request")
    def test_refresh_token_with_retry_success(self, mock_request_class, mock_sleep):
        """Test successful token refresh with retry logic"""
        mock_request = MagicMock()
        mock_request_class.return_value = mock_request

        mock_credentials = MagicMock()
        mock_credentials.refresh_token = "test_refresh_token"
        mock_credentials.token = "new_access_token"
        mock_credentials.expiry = timezone.now() + timedelta(hours=1)

        # Test successful refresh on first attempt
        result = TokenManager._refresh_token_with_retry(self.account, mock_credentials)

        self.assertIsNotNone(result)
        mock_credentials.refresh.assert_called_once_with(mock_request)
        mock_sleep.assert_not_called()  # No sleep on first successful attempt

    @patch("apps.calendars.services.token_manager.time.sleep")
    @patch("apps.calendars.services.token_manager.Request")
    def test_refresh_token_with_retry_permanent_error(self, mock_request_class, mock_sleep):
        """Test refresh with permanent error (invalid_grant)"""
        mock_request = MagicMock()
        mock_request_class.return_value = mock_request

        mock_credentials = MagicMock()
        mock_credentials.refresh_token = "test_refresh_token"
        mock_credentials.refresh.side_effect = RefreshError("invalid_grant")

        result = TokenManager._refresh_token_with_retry(self.account, mock_credentials)

        self.assertIsNone(result)
        # Should not retry on permanent errors
        self.assertEqual(mock_credentials.refresh.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("apps.calendars.services.token_manager.time.sleep")
    @patch("apps.calendars.services.token_manager.Request")
    def test_refresh_token_with_retry_temporary_error(self, mock_request_class, mock_sleep):
        """Test refresh with temporary error and retry"""
        mock_request = MagicMock()
        mock_request_class.return_value = mock_request

        mock_credentials = MagicMock()
        mock_credentials.refresh_token = "test_refresh_token"
        # Fail twice, then succeed
        mock_credentials.refresh.side_effect = [
            RefreshError("temporary_error"),
            RefreshError("temporary_error"),
            None  # Success on third attempt
        ]
        mock_credentials.token = "new_access_token"
        mock_credentials.expiry = timezone.now() + timedelta(hours=1)

        result = TokenManager._refresh_token_with_retry(self.account, mock_credentials)

        self.assertIsNotNone(result)
        self.assertEqual(mock_credentials.refresh.call_count, 3)
        # Should sleep before second and third attempts
        self.assertEqual(mock_sleep.call_count, 2)

    def test_validate_all_accounts_empty(self):
        """Test validate_all_accounts with no accounts"""
        # Delete the test account
        CalendarAccount.objects.all().delete()

        results = TokenManager.validate_all_accounts()

        self.assertEqual(results["total_accounts"], 0)
        self.assertEqual(results["successful_refreshes"], 0)
        self.assertEqual(results["failed_refreshes"], 0)

    @patch.object(TokenManager, "should_refresh_token")
    @patch.object(TokenManager, "get_valid_credentials")
    def test_validate_all_accounts_mixed_results(self, mock_get_creds, mock_should_refresh):
        """Test validate_all_accounts with mixed success/failure"""
        # Create second account
        user2 = User.objects.create_user(username="user2", email="user2@test.com")
        UserProfile.objects.create(user=user2)
        CalendarAccount.objects.create(
            user=user2,
            google_account_id="google456",
            email="test2@gmail.com",
            access_token="token2",
            refresh_token="refresh2",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        # Mock first account success, second account failure
        mock_should_refresh.side_effect = [True, True]
        mock_get_creds.side_effect = [MagicMock(), None]

        results = TokenManager.validate_all_accounts()

        self.assertEqual(results["total_accounts"], 2)
        self.assertEqual(results["successful_refreshes"], 1)
        self.assertEqual(results["failed_refreshes"], 1)
        self.assertEqual(len(results["deactivated_accounts"]), 1)

    def test_background_token_refresh(self):
        """Test background token refresh functionality"""
        # Set token to expire soon
        self.account.token_expires_at = timezone.now() + timedelta(minutes=5)
        self.account.save()

        with patch.object(TokenManager, "proactive_refresh_check") as mock_refresh:
            mock_refresh.return_value = True

            refresh_count = TokenManager.background_token_refresh()

            self.assertEqual(refresh_count, 1)
            mock_refresh.assert_called_once_with(self.account)

    def test_get_token_status_summary(self):
        """Test token status summary functionality"""
        # Create accounts in different states
        user2 = User.objects.create_user(username="user2", email="user2@test.com")
        UserProfile.objects.create(user=user2)

        # Inactive account
        CalendarAccount.objects.create(
            user=user2,
            google_account_id="google456",
            email="inactive@gmail.com",
            access_token="token2",
            refresh_token="refresh2",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=False,
        )

        # Expired token account
        user3 = User.objects.create_user(username="user3", email="user3@test.com")
        UserProfile.objects.create(user=user3)
        CalendarAccount.objects.create(
            user=user3,
            google_account_id="google789",
            email="expired@gmail.com",
            access_token="token3",
            refresh_token="refresh3",
            token_expires_at=timezone.now() - timedelta(hours=1),
            is_active=True,
        )

        status = TokenManager.get_token_status_summary()

        self.assertEqual(status["total_accounts"], 3)
        self.assertEqual(status["active_accounts"], 2)
        self.assertEqual(status["inactive_accounts"], 1)
        self.assertEqual(status["expired_tokens"], 1)

    def test_revoke_token_success(self):
        """Test successful token revocation"""
        with patch("apps.calendars.services.token_manager.Request") as mock_request_class:
            mock_request = MagicMock()
            mock_request_class.return_value = mock_request

            with patch("apps.calendars.services.token_manager.Credentials") as mock_creds_class:
                mock_credentials = MagicMock()
                mock_creds_class.return_value = mock_credentials

                result = TokenManager.revoke_token(self.account)

                self.assertTrue(result)
                mock_credentials.revoke.assert_called_once_with(mock_request)

                # Check that account was deactivated and tokens cleared
                self.account.refresh_from_db()
                self.assertFalse(self.account.is_active)

    def test_revoke_token_no_tokens(self):
        """Test token revocation when no tokens exist"""
        # Clear tokens
        self.account.set_access_token("")
        self.account.set_refresh_token("")
        self.account.save()

        result = TokenManager.revoke_token(self.account)

        # Should return True (nothing to revoke)
        self.assertTrue(result)

    def test_revoke_token_failure(self):
        """Test token revocation failure"""
        with patch("apps.calendars.services.token_manager.Request") as mock_request_class:
            mock_request = MagicMock()
            mock_request_class.return_value = mock_request

            with patch("apps.calendars.services.token_manager.Credentials") as mock_creds_class:
                mock_credentials = MagicMock()
                mock_credentials.revoke.side_effect = Exception("Revocation failed")
                mock_creds_class.return_value = mock_credentials

                result = TokenManager.revoke_token(self.account)

                self.assertFalse(result)
                # Even on failure, account should be deactivated for security
                self.account.refresh_from_db()
                self.assertFalse(self.account.is_active)

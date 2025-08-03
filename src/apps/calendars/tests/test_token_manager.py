"""Tests for simplified token management service"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from google.auth.exceptions import RefreshError

from apps.accounts.models import UserProfile
from apps.calendars.models import CalendarAccount
from apps.calendars.services.token_manager import (
    TokenManager,
    get_valid_credentials,
    revoke_token,
    validate_all_accounts,
)


@override_settings(
    GOOGLE_OAUTH_CLIENT_ID="test_client_id",
    GOOGLE_OAUTH_CLIENT_SECRET="test_client_secret",
)
class TokenManagerSimpleTest(TestCase):
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
        manager = TokenManager(self.account)
        credentials = manager.get_valid_credentials()

        self.assertIsNotNone(credentials)
        self.assertEqual(credentials.token, "test_access_token")
        self.assertEqual(credentials.refresh_token, "test_refresh_token")

    def test_get_valid_credentials_inactive_account(self):
        """Test get_valid_credentials with inactive account"""
        self.account.is_active = False
        self.account.save()

        manager = TokenManager(self.account)
        credentials = manager.get_valid_credentials()

        self.assertIsNone(credentials)

    def test_needs_refresh_expired_token(self):
        """Test needs refresh when token is expired"""
        # Set token to expire in 2 minutes (less than 5 minute buffer)
        self.account.token_expires_at = timezone.now() + timedelta(minutes=2)
        self.account.save()

        manager = TokenManager(self.account)
        self.assertTrue(manager._needs_refresh())

    def test_needs_refresh_valid_token(self):
        """Test needs refresh when token is still valid"""
        # Set token to expire in 10 minutes (more than 5 minute buffer)
        self.account.token_expires_at = timezone.now() + timedelta(minutes=10)
        self.account.save()

        manager = TokenManager(self.account)
        self.assertFalse(manager._needs_refresh())

    def test_get_valid_credentials_no_tokens(self):
        """Test handling when no tokens are stored"""
        # Clear tokens
        self.account.set_access_token("")
        self.account.set_refresh_token("")
        self.account.save()

        manager = TokenManager(self.account)
        credentials = manager.get_valid_credentials()

        self.assertIsNone(credentials)

    @patch("apps.calendars.services.token_manager.Request")
    def test_refresh_token_simple_success(self, mock_request_class):
        """Test successful simple token refresh"""
        mock_request = MagicMock()
        mock_request_class.return_value = mock_request

        # Set token to expire soon to trigger refresh
        self.account.token_expires_at = timezone.now() + timedelta(minutes=2)
        self.account.save()

        # Mock successful refresh
        with patch.object(self.account, "set_access_token") as mock_set_token:
            mock_credentials = MagicMock()
            mock_credentials.refresh_token = "test_refresh_token"
            mock_credentials.token = "new_access_token"
            mock_credentials.expiry = timezone.now() + timedelta(hours=1)

            manager = TokenManager(self.account)
            result = manager._refresh_token_simple(mock_credentials)

            self.assertTrue(result)
            mock_credentials.refresh.assert_called_once_with(mock_request)

    @patch("apps.calendars.services.token_manager.Request")
    def test_refresh_token_permanent_error(self, mock_request_class):
        """Test refresh with permanent error (invalid_grant)"""
        mock_request = MagicMock()
        mock_request_class.return_value = mock_request

        mock_credentials = MagicMock()
        mock_credentials.refresh_token = "test_refresh_token"
        mock_credentials.refresh.side_effect = RefreshError("invalid_grant")

        manager = TokenManager(self.account)
        result = manager._refresh_token_simple(mock_credentials)

        self.assertFalse(result)
        # Account should be deactivated
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_active)

    @patch("apps.calendars.services.token_manager.time.sleep")
    @patch("apps.calendars.services.token_manager.Request")
    def test_refresh_token_retry_then_success(self, mock_request_class, mock_sleep):
        """Test retry logic with eventual success"""
        mock_request = MagicMock()
        mock_request_class.return_value = mock_request

        mock_credentials = MagicMock()
        mock_credentials.refresh_token = "test_refresh_token"
        # Fail twice, then succeed
        mock_credentials.refresh.side_effect = [
            RefreshError("temporary_error"),
            RefreshError("temporary_error"),
            None,  # Success on third attempt
        ]
        mock_credentials.token = "new_access_token"
        mock_credentials.expiry = timezone.now() + timedelta(hours=1)

        manager = TokenManager(self.account)
        result = manager._refresh_token_simple(mock_credentials)

        self.assertTrue(result)
        self.assertEqual(mock_credentials.refresh.call_count, 3)
        # Should sleep twice (before second and third attempts)
        self.assertEqual(mock_sleep.call_count, 2)

    def test_revoke_token_success(self):
        """Test successful token clearing (simplified revoke)"""
        manager = TokenManager(self.account)
        result = manager.revoke_token()

        self.assertTrue(result)

        # Check that account was deactivated and tokens cleared
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_active)
        # Note: We can't easily test token clearing since get_access_token() returns empty on cleared tokens

    def test_revoke_token_no_credentials(self):
        """Test token revocation when no credentials exist"""
        # Clear tokens
        self.account.set_access_token("")
        self.account.set_refresh_token("")
        self.account.save()

        manager = TokenManager(self.account)
        result = manager.revoke_token()

        # Should still return True and deactivate account
        self.assertTrue(result)
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_active)

    def test_backward_compatibility_functions(self):
        """Test backward compatibility utility functions"""
        # Test get_valid_credentials function
        credentials = get_valid_credentials(self.account)
        self.assertIsNotNone(credentials)

        # Test revoke_token function
        result = revoke_token(self.account)
        self.assertTrue(result)

        # Test validate_all_accounts function
        results = validate_all_accounts()
        self.assertIn("total_accounts", results)
        self.assertIn("successful_refreshes", results)
        self.assertIn("failed_refreshes", results)
        self.assertIn("deactivated_accounts", results)
        self.assertIn("errors", results)

    def test_validate_all_accounts_mixed_results(self):
        """Test validate_all_accounts with mixed success/failure"""
        # Create second account
        user2 = User.objects.create_user(username="user2", email="user2@test.com")
        UserProfile.objects.create(user=user2)
        account2 = CalendarAccount.objects.create(
            user=user2,
            google_account_id="google456",
            email="test2@gmail.com",
            access_token="token2",
            refresh_token="refresh2",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        # Make second account have no tokens (will fail)
        account2.set_access_token("")
        account2.set_refresh_token("")
        account2.save()

        results = validate_all_accounts()

        self.assertEqual(results["total_accounts"], 2)
        # First account should succeed, second should fail
        self.assertEqual(results["successful_refreshes"], 1)
        self.assertEqual(results["failed_refreshes"], 1)
        self.assertEqual(len(results["deactivated_accounts"]), 1)

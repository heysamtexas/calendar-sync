"""Tests for global manual sync functionality"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.calendars.models import CalendarAccount


class GlobalSyncTest(TestCase):
    """Tests for global manual sync functionality"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.profile = UserProfile.objects.create(user=self.user)

        # Create test calendar account
        self.account = CalendarAccount.objects.create(
            user=self.user,
            email="test@gmail.com",
            google_account_id="test_account_id",
            is_active=True,
            token_expires_at=timezone.now() + timezone.timedelta(hours=1),
        )

    def test_global_sync_requires_login(self):
        """Test that global sync requires authentication"""
        response = self.client.post(reverse("dashboard:global_sync"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_global_sync_requires_post(self):
        """Test that global sync only accepts POST requests"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("dashboard:global_sync"))
        self.assertEqual(response.status_code, 405)

    @patch("apps.calendars.services.sync_engine.sync_all_calendars")
    def test_global_sync_success(self, mock_sync):
        """Test successful global sync"""
        self.client.login(username="testuser", password="testpass123")

        # Mock successful sync
        mock_sync.return_value = {
            "calendars_processed": 2,
            "events_created": 5,
            "events_updated": 3,
            "busy_blocks_created": 1,
            "errors": []
        }

        # Test POST to global sync
        response = self.client.post(reverse("dashboard:global_sync"))

        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))

        # Should have called sync_all_calendars with verbose=True
        mock_sync.assert_called_once_with(verbose=True)

    @patch("apps.calendars.services.sync_engine.sync_all_calendars")
    def test_global_sync_with_errors(self, mock_sync):
        """Test global sync with errors"""
        self.client.login(username="testuser", password="testpass123")

        # Mock sync with errors
        mock_sync.return_value = {
            "calendars_processed": 1,
            "events_created": 0,
            "events_updated": 0,
            "busy_blocks_created": 0,
            "errors": ["Some error occurred"]
        }

        # Test POST to global sync
        response = self.client.post(reverse("dashboard:global_sync"))

        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))

        # Should have called sync_all_calendars
        mock_sync.assert_called_once_with(verbose=True)

    @patch("apps.calendars.services.sync_engine.sync_all_calendars")
    def test_global_sync_exception_handling(self, mock_sync):
        """Test global sync handles exceptions gracefully"""
        self.client.login(username="testuser", password="testpass123")

        # Mock sync raising exception
        mock_sync.side_effect = Exception("Sync failed")

        # Test POST to global sync
        response = self.client.post(reverse("dashboard:global_sync"))

        # Should still redirect to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))

    def test_global_sync_button_appears_on_dashboard(self):
        """Test that global sync button appears on dashboard when accounts exist"""
        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(reverse("dashboard:index"))
        content = response.content.decode()

        # Should contain global sync button
        self.assertIn("Sync All Calendars", content)
        self.assertIn('action="/sync/"', content)
        self.assertIn("btn btn-success", content)

    def test_global_sync_button_not_shown_without_accounts(self):
        """Test that global sync button is hidden when no accounts exist"""
        # Remove the account
        self.account.delete()

        self.client.login(username="testuser", password="testpass123")

        response = self.client.get(reverse("dashboard:index"))
        content = response.content.decode()

        # Should not contain global sync button
        self.assertNotIn("Sync All Calendars", content)
        self.assertNotIn('action="/sync/"', content)

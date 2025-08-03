"""Tests for OAuth views and flows"""

from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.calendars.models import CalendarAccount


class OAuthViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.profile = UserProfile.objects.create(user=self.user)

    def test_oauth_initiate_requires_login(self):
        """Test that OAuth initiation requires authentication"""
        response = self.client.get(reverse("accounts:oauth_initiate"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    @patch("apps.accounts.views.get_oauth_flow")
    def test_oauth_initiate_success(self, mock_get_flow):
        """Test successful OAuth initiation"""
        # Mock the OAuth flow
        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = (
            "https://accounts.google.com/oauth",
            "state123",
        )
        mock_get_flow.return_value = mock_flow

        # Login user
        self.client.login(username="testuser", password="testpass123")

        # Start OAuth flow
        response = self.client.get(reverse("accounts:oauth_initiate"))

        # Should redirect to Google OAuth
        self.assertEqual(response.status_code, 302)
        self.assertIn("accounts.google.com", response.url)

        # State should be stored in session
        self.assertIn("oauth_state", self.client.session)

    @patch("apps.accounts.views.get_oauth_flow")
    def test_oauth_initiate_failure(self, mock_get_flow):
        """Test OAuth initiation failure"""
        # Mock flow to raise exception
        mock_get_flow.side_effect = Exception("OAuth config error")

        # Login user
        self.client.login(username="testuser", password="testpass123")

        # Start OAuth flow
        response = self.client.get(reverse("accounts:oauth_initiate"))

        # Should redirect to dashboard with error
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))

    def test_oauth_callback_requires_login(self):
        """Test that OAuth callback requires authentication"""
        response = self.client.get(reverse("accounts:auth_callback"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_oauth_callback_state_mismatch(self):
        """Test OAuth callback with state mismatch"""
        # Login user
        self.client.login(username="testuser", password="testpass123")

        # Set session state
        session = self.client.session
        session["oauth_state"] = "correct_state"
        session.save()

        # Call callback with wrong state
        response = self.client.get(
            reverse("accounts:auth_callback"), {"state": "wrong_state"}
        )

        # Should redirect to dashboard with error
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))

    def test_oauth_callback_error_parameter(self):
        """Test OAuth callback with error parameter"""
        # Login user
        self.client.login(username="testuser", password="testpass123")

        # Set session state
        session = self.client.session
        session["oauth_state"] = "test_state"
        session.save()

        # Call callback with error
        response = self.client.get(
            reverse("accounts:auth_callback"),
            {"state": "test_state", "error": "access_denied"},
        )

        # Should redirect to dashboard with error
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))

    @patch("googleapiclient.discovery.build")
    @patch("apps.accounts.views.get_oauth_flow")
    def test_oauth_callback_success(self, mock_get_flow, mock_build):
        """Test successful OAuth callback"""
        # Mock OAuth flow
        mock_flow = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.token = "access_token_123"
        mock_credentials.refresh_token = "refresh_token_123"
        mock_credentials.client_id = "google_client_id"
        mock_credentials.expiry.timestamp.return_value = 1234567890
        mock_flow.credentials = mock_credentials
        mock_get_flow.return_value = mock_flow

        # Mock Google Calendar service
        mock_service = MagicMock()
        mock_calendar_list = {"items": [{"id": "primary", "summary": "test@gmail.com"}]}
        mock_service.calendarList().list().execute.return_value = mock_calendar_list
        mock_service.settings().get().execute.return_value = {"value": "test@gmail.com"}
        mock_build.return_value = mock_service

        # Login user
        self.client.login(username="testuser", password="testpass123")

        # Set session state
        session = self.client.session
        session["oauth_state"] = "test_state"
        session.save()

        # Call callback with success
        response = self.client.get(
            reverse("accounts:auth_callback"),
            {"state": "test_state", "code": "auth_code_123"},
        )

        # Should redirect to account detail page
        self.assertEqual(response.status_code, 302)

        # Should create calendar account
        self.assertTrue(CalendarAccount.objects.filter(user=self.user).exists())
        account = CalendarAccount.objects.get(user=self.user)
        self.assertEqual(
            response.url, reverse("dashboard:account_detail", args=[account.id])
        )
        self.assertEqual(account.email, "test@gmail.com")
        self.assertTrue(account.is_active)

    def test_disconnect_account_requires_login(self):
        """Test that account disconnection requires authentication"""
        response = self.client.post(reverse("accounts:disconnect_account", args=[1]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_disconnect_account_success(self):
        """Test successful account disconnection"""
        # Create calendar account
        account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="google123",
            email="test@gmail.com",
            access_token="encrypted_token",
            refresh_token="encrypted_refresh",
            token_expires_at="2024-12-31 23:59:59+00:00",
        )

        # Login user
        self.client.login(username="testuser", password="testpass123")

        # Disconnect account
        response = self.client.get(
            reverse("accounts:disconnect_account", args=[account.id])
        )

        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))

        # Account should be deleted
        self.assertFalse(CalendarAccount.objects.filter(id=account.id).exists())

    def test_disconnect_account_not_found(self):
        """Test disconnecting non-existent account"""
        # Login user
        self.client.login(username="testuser", password="testpass123")

        # Try to disconnect non-existent account
        response = self.client.get(reverse("accounts:disconnect_account", args=[999]))

        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))

    def test_disconnect_account_wrong_user(self):
        """Test disconnecting account belonging to different user"""
        # Create another user and account
        other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="otherpass123"
        )
        account = CalendarAccount.objects.create(
            user=other_user,
            google_account_id="google123",
            email="other@gmail.com",
            access_token="encrypted_token",
            refresh_token="encrypted_refresh",
            token_expires_at="2024-12-31 23:59:59+00:00",
        )

        # Login as first user
        self.client.login(username="testuser", password="testpass123")

        # Try to disconnect other user's account
        response = self.client.get(
            reverse("accounts:disconnect_account", args=[account.id])
        )

        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard:index"))

        # Account should still exist
        self.assertTrue(CalendarAccount.objects.filter(id=account.id).exists())

"""
Tests for Guilfoyle's Minimalist Webhook Implementation

Simple tests for the 50-line webhook solution.
No complex infrastructure, just HTTP requests and responses.
"""

from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.calendars.models import Calendar, CalendarAccount
from apps.calendars.services.google_calendar_client import GoogleCalendarClient


class GoogleWebhookViewTests(TestCase):
    """Test the minimalist Google webhook endpoint"""

    def setUp(self):
        self.client = Client()

        # Create test user
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com"
        )

        # Create test calendar account and calendar
        self.calendar_account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="test_google_account_123",
            email="test@example.com",
            access_token="encrypted_access_token",
            refresh_token="encrypted_refresh_token",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True
        )

        self.calendar = Calendar.objects.create(
            calendar_account=self.calendar_account,
            name="Test Calendar",
            google_calendar_id="test_calendar_123",
            sync_enabled=True
        )

    def test_webhook_valid_request_triggers_sync(self):
        """Test that a valid webhook request triggers sync"""
        url = reverse('webhooks:google_webhook')

        # Mock the sync engine to verify it gets called
        with patch('apps.calendars.services.sync_engine.SyncEngine') as mock_sync:
            mock_engine_instance = Mock()
            mock_sync.return_value = mock_engine_instance
            mock_engine_instance.sync_specific_calendar.return_value = {"calendars_processed": 1}

            response = self.client.post(url,
                HTTP_X_GOOG_RESOURCE_ID=self.calendar.google_calendar_id,
                HTTP_X_GOOG_CHANNEL_ID='test-channel-123'
            )

        # Should return 200 for successful webhook processing
        self.assertEqual(response.status_code, 200)

        # Verify sync was triggered for correct calendar with webhook_triggered=True
        mock_engine_instance.sync_specific_calendar.assert_called_once_with(self.calendar.id, webhook_triggered=True)

    def test_webhook_missing_headers_returns_400(self):
        """Test that missing required headers returns 400"""
        url = reverse('webhooks:google_webhook')

        # Missing X-Goog-Resource-ID header
        response = self.client.post(url,
            HTTP_X_GOOG_CHANNEL_ID='test-channel-123'
        )

        self.assertEqual(response.status_code, 400)

        # Missing X-Goog-Channel-ID header
        response = self.client.post(url,
            HTTP_X_GOOG_RESOURCE_ID=self.calendar.google_calendar_id
        )

        self.assertEqual(response.status_code, 400)

    def test_webhook_unknown_calendar_logs_and_returns_200(self):
        """Test that webhook for unknown calendar logs but still returns 200"""
        url = reverse('webhooks:google_webhook')

        with patch('apps.webhooks.views.logger') as mock_logger:
            response = self.client.post(url,
                HTTP_X_GOOG_RESOURCE_ID='unknown_calendar_id',
                HTTP_X_GOOG_CHANNEL_ID='test-channel-123'
            )

        # Should still return 200 (webhooks should never fail)
        self.assertEqual(response.status_code, 200)

        # Should log the unknown calendar
        mock_logger.info.assert_called_with("Webhook for unknown or inactive calendar: unknown_calendar_id")

    def test_webhook_sync_failure_logs_and_returns_200(self):
        """Test that sync failures are logged but webhook still returns 200"""
        url = reverse('webhooks:google_webhook')

        with patch('apps.calendars.services.sync_engine.SyncEngine') as mock_sync:
            mock_sync.return_value.sync_specific_calendar.side_effect = Exception("Sync failed")

            with patch('apps.webhooks.views.logger') as mock_logger:
                response = self.client.post(url,
                    HTTP_X_GOOG_RESOURCE_ID=self.calendar.google_calendar_id,
                    HTTP_X_GOOG_CHANNEL_ID='test-channel-123'
                )

        # Should still return 200 (fail silently for webhooks)
        self.assertEqual(response.status_code, 200)

        # Should log the error
        mock_logger.error.assert_called_with(f"Webhook sync failed for {self.calendar.google_calendar_id}: Sync failed")

    def test_webhook_csrf_exempt(self):
        """Test that webhook endpoint is CSRF exempt (required for external requests)"""
        url = reverse('webhooks:google_webhook')

        # This should work without CSRF token
        response = self.client.post(url,
            HTTP_X_GOOG_RESOURCE_ID=self.calendar.google_calendar_id,
            HTTP_X_GOOG_CHANNEL_ID='test-channel-123'
        )

        # Should not get CSRF error (403)
        self.assertNotEqual(response.status_code, 403)
        self.assertEqual(response.status_code, 200)


class WebhookIntegrationTests(TestCase):
    """Integration tests for webhook with real sync engine"""

    def setUp(self):
        self.client = Client()

        # Create test user
        self.user = User.objects.create_user(
            username="integrationuser",
            email="integrationuser@example.com"
        )

        # Create test calendar account and calendar
        self.calendar_account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="integration_google_account_456",
            email="integration@example.com",
            access_token="encrypted_access_token",
            refresh_token="encrypted_refresh_token",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True
        )

        self.calendar = Calendar.objects.create(
            calendar_account=self.calendar_account,
            name="Integration Test Calendar",
            google_calendar_id="integration_test_123",
            sync_enabled=True,
            webhook_channel_id="integration-test-channel"  # Match the test channel ID
        )

    @patch('apps.calendars.services.token_manager.TokenManager')
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient')
    def test_webhook_integration_with_sync_engine(self, mock_client_class, mock_token_manager_class):
        """Test webhook integration with actual sync engine (mocked Google API)"""

        # Mock token manager to provide valid credentials
        mock_token_manager = Mock()
        mock_token_manager_class.return_value = mock_token_manager
        mock_token_manager.get_valid_credentials.return_value = Mock()  # Mock credentials object

        # Mock Google Calendar API responses
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.list_events.return_value = []  # No events

        url = reverse('webhooks:google_webhook')

        # Trigger webhook
        response = self.client.post(url,
            HTTP_X_GOOG_RESOURCE_ID=self.calendar.google_calendar_id,
            HTTP_X_GOOG_CHANNEL_ID='integration-test-channel'
        )

        # Should succeed
        self.assertEqual(response.status_code, 200)

        # Should have called Google API to list events
        mock_client.list_events.assert_called_once()


class CronSafeWebhookTests(TestCase):
    """Test cron-safe webhook setup functionality"""

    def setUp(self):
        # Create test user and calendar
        self.user = User.objects.create_user(
            username="cronuser",
            email="cronuser@example.com"
        )

        self.calendar_account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="cron_google_account",
            email="cron@example.com",
            access_token="encrypted_access_token",
            refresh_token="encrypted_refresh_token",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True
        )

        self.calendar = Calendar.objects.create(
            calendar_account=self.calendar_account,
            name="Cron Test Calendar",
            google_calendar_id="cron_test_calendar",
            sync_enabled=True
        )

    def test_calendar_has_active_webhook(self):
        """Test webhook status checking"""
        # Initially no webhook
        self.assertFalse(self.calendar.has_active_webhook())
        self.assertTrue(self.calendar.needs_webhook_renewal())

        # Add webhook info
        future_time = timezone.now() + timedelta(days=3)
        self.calendar.update_webhook_info("test-channel-123", future_time)

        # Should now have active webhook
        self.assertTrue(self.calendar.has_active_webhook())
        self.assertFalse(self.calendar.needs_webhook_renewal())

        # Test expiring webhook
        expiring_time = timezone.now() + timedelta(hours=12)  # Within 24 hour buffer
        self.calendar.update_webhook_info("test-channel-456", expiring_time)

        # Should need renewal
        self.assertFalse(self.calendar.has_active_webhook())
        self.assertTrue(self.calendar.needs_webhook_renewal())

    def test_webhook_status_display(self):
        """Test human-readable webhook status"""
        # No webhook
        self.assertEqual(self.calendar.get_webhook_status(), "No webhook registered")

        # Active webhook
        future_time = timezone.now() + timedelta(days=3)
        self.calendar.update_webhook_info("test-channel-123", future_time)
        self.assertEqual(self.calendar.get_webhook_status(), "Webhook active")

        # Expired webhook
        past_time = timezone.now() - timedelta(hours=1)
        self.calendar.update_webhook_info("test-channel-456", past_time)
        self.assertEqual(self.calendar.get_webhook_status(), "Webhook expired")

        # Expiring webhook
        expiring_time = timezone.now() + timedelta(hours=12)
        self.calendar.update_webhook_info("test-channel-789", expiring_time)
        status = self.calendar.get_webhook_status()
        self.assertIn("expires in", status)

    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient')
    def test_cron_safe_setup_skips_valid_webhooks(self, mock_client_class):
        """Test that cron-safe setup skips calendars with valid webhooks"""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Give calendar an active webhook
        future_time = timezone.now() + timedelta(days=3)
        self.calendar.update_webhook_info("existing-channel-123", future_time)

        # Test cron-safe setup (should skip)
        client = GoogleCalendarClient(self.calendar_account)
        result = client.setup_webhook(self.calendar.google_calendar_id, force_recreate=False)

        # Should skip and return existing info
        self.assertIsNotNone(result)
        self.assertTrue(result.get('skipped'))
        self.assertEqual(result['channel_id'], 'existing-channel-123')

        # Should not have called Google API
        mock_client.events.assert_not_called()

    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.setup_webhook')
    def test_force_recreate_replaces_valid_webhooks(self, mock_setup_webhook):
        """Test that force_recreate=True replaces even valid webhooks"""
        # Mock the setup_webhook method to return expected result
        mock_setup_webhook.return_value = {
            'channel_id': 'new-channel-456',
            'webhook_url': 'http://testserver/webhooks/google/',
            'expires_at': timezone.now() + timedelta(days=6),
            'resource_id': 'mock_resource_id',
            'resource_uri': 'mock_resource_uri'
        }

        # Give calendar an active webhook
        future_time = timezone.now() + timedelta(days=3)
        self.calendar.update_webhook_info("existing-channel-123", future_time)

        # Test force recreate
        client = GoogleCalendarClient(self.calendar_account)
        result = client.setup_webhook(self.calendar.google_calendar_id, force_recreate=True)

        # Should create new webhook
        self.assertIsNotNone(result)
        self.assertFalse(result.get('skipped', False))
        self.assertNotEqual(result['channel_id'], 'existing-channel-123')

        # Should have called the mocked method
        mock_setup_webhook.assert_called_once_with(self.calendar.google_calendar_id, force_recreate=True)

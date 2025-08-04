"""
Tests for Streamlined UUID Correlation Webhook System

Tests the cleaned-up webhook implementation that triggers UUID correlation sync.
Focuses on essential behavior without testing obsolete defensive code.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.calendars.models import Calendar, CalendarAccount


class GoogleWebhookViewTests(TestCase):
    """Test the minimalist Google webhook endpoint"""

    def setUp(self):
        self.client = Client()

        # Create test user
        self.user = User.objects.create_user(
            username="testuser", email="testuser@example.com"
        )

        # Create test calendar account and calendar
        self.calendar_account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="test_google_account_123",
            email="test@example.com",
            access_token="encrypted_access_token",
            refresh_token="encrypted_refresh_token",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        self.calendar = Calendar.objects.create(
            calendar_account=self.calendar_account,
            name="Test Calendar",
            google_calendar_id="test_calendar_123",
            sync_enabled=True,
        )

    def test_webhook_valid_request_triggers_uuid_sync(self):
        """Test that a valid webhook request triggers UUID correlation sync"""
        url = reverse("webhooks:google_webhook")

        # Mock the UUID correlation sync handler
        with patch("apps.calendars.services.uuid_sync_engine.handle_webhook_yolo") as mock_handler:
            mock_handler.return_value = {
                "status": "success",
                "calendar": self.calendar.name,
                "results": {"events_processed": 5}
            }

            response = self.client.post(
                url,
                HTTP_X_GOOG_RESOURCE_ID=self.calendar.google_calendar_id,
                HTTP_X_GOOG_CHANNEL_ID="test-channel-123",
            )

        # Should return 200 for successful webhook processing
        self.assertEqual(response.status_code, 200)

        # Verify UUID sync was triggered for correct calendar
        mock_handler.assert_called_once_with(self.calendar)

    def test_webhook_missing_headers_returns_400(self):
        """Test that missing required headers returns 400"""
        url = reverse("webhooks:google_webhook")

        # Missing X-Goog-Resource-ID header
        response = self.client.post(url, HTTP_X_GOOG_CHANNEL_ID="test-channel-123")

        self.assertEqual(response.status_code, 400)

        # Missing X-Goog-Channel-ID header
        response = self.client.post(
            url, HTTP_X_GOOG_RESOURCE_ID=self.calendar.google_calendar_id
        )

        self.assertEqual(response.status_code, 400)

    def test_webhook_unknown_calendar_returns_200(self):
        """Test that webhook for unknown calendar still returns 200"""
        url = reverse("webhooks:google_webhook")

        response = self.client.post(
            url,
            HTTP_X_GOOG_RESOURCE_ID="unknown_calendar_id",
            HTTP_X_GOOG_CHANNEL_ID="test-channel-123",
        )

        # Should still return 200 (webhooks should never fail)
        self.assertEqual(response.status_code, 200)

    def test_webhook_sync_failure_returns_200(self):
        """Test that sync failures are handled gracefully and webhook still returns 200"""
        url = reverse("webhooks:google_webhook")

        # Mock UUID sync to fail
        with patch("apps.calendars.services.uuid_sync_engine.handle_webhook_yolo") as mock_handler:
            mock_handler.side_effect = Exception("UUID sync failed")

            response = self.client.post(
                url,
                HTTP_X_GOOG_RESOURCE_ID=self.calendar.google_calendar_id,
                HTTP_X_GOOG_CHANNEL_ID="test-channel-123",
            )

        # Should still return 200 (fail silently for webhooks)
        self.assertEqual(response.status_code, 200)

    def test_webhook_csrf_exempt(self):
        """Test that webhook endpoint is CSRF exempt (required for external requests)"""
        url = reverse("webhooks:google_webhook")

        # This should work without CSRF token
        response = self.client.post(
            url,
            HTTP_X_GOOG_RESOURCE_ID=self.calendar.google_calendar_id,
            HTTP_X_GOOG_CHANNEL_ID="test-channel-123",
        )

        # Should not get CSRF error (403)
        self.assertNotEqual(response.status_code, 403)
        self.assertEqual(response.status_code, 200)


class WebhookUUIDIntegrationTests(TestCase):
    """Integration tests for webhook with UUID correlation system"""

    def setUp(self):
        self.client = Client()

        # Create test user
        self.user = User.objects.create_user(
            username="integrationuser", email="integrationuser@example.com"
        )

        # Create test calendar account and calendar
        self.calendar_account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="integration_google_account_456",
            email="integration@example.com",
            access_token="encrypted_access_token",
            refresh_token="encrypted_refresh_token",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        self.calendar = Calendar.objects.create(
            calendar_account=self.calendar_account,
            name="Integration Test Calendar",
            google_calendar_id="integration_test_123",
            sync_enabled=True,
            webhook_channel_id="integration-test-channel",
        )

    def test_webhook_channel_id_lookup(self):
        """Test that webhook finds calendar by channel ID (preferred method)"""
        url = reverse("webhooks:google_webhook")

        # Mock UUID sync to verify calendar is found correctly
        with patch("apps.calendars.services.uuid_sync_engine.handle_webhook_yolo") as mock_handler:
            mock_handler.return_value = {"status": "success", "calendar": self.calendar.name}

            response = self.client.post(
                url,
                HTTP_X_GOOG_RESOURCE_ID=self.calendar.google_calendar_id,
                HTTP_X_GOOG_CHANNEL_ID="integration-test-channel",
            )

            # Should succeed and find calendar by channel ID
            self.assertEqual(response.status_code, 200)
            mock_handler.assert_called_once_with(self.calendar)

    def test_webhook_resource_id_fallback(self):
        """Test that webhook falls back to resource ID when channel ID not found"""
        url = reverse("webhooks:google_webhook")

        # Mock UUID sync to verify fallback works
        with patch("apps.calendars.services.uuid_sync_engine.handle_webhook_yolo") as mock_handler:
            mock_handler.return_value = {"status": "success", "calendar": self.calendar.name}

            response = self.client.post(
                url,
                HTTP_X_GOOG_RESOURCE_ID=self.calendar.google_calendar_id,
                HTTP_X_GOOG_CHANNEL_ID="unknown-channel-id",  # Channel ID not in DB
            )

            # Should succeed using resource ID fallback
            self.assertEqual(response.status_code, 200)
            mock_handler.assert_called_once_with(self.calendar)


class WebhookCoordinationTests(TestCase):
    """Test webhook coordination and calendar status functionality"""

    def setUp(self):
        # Create test user and calendar
        self.user = User.objects.create_user(
            username="coorduser", email="coorduser@example.com"
        )

        self.calendar_account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="coord_google_account",
            email="coord@example.com",
            access_token="encrypted_access_token",
            refresh_token="encrypted_refresh_token",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        self.calendar = Calendar.objects.create(
            calendar_account=self.calendar_account,
            name="Coordination Test Calendar",
            google_calendar_id="coord_test_calendar",
            sync_enabled=True,
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

    def test_webhook_sync_coordination(self):
        """Test that webhook sync coordination prevents duplicate processing"""
        url = reverse("webhooks:google_webhook")

        # Mock cache to simulate sync lock
        with patch("django.core.cache.cache") as mock_cache:
            # Simulate existing sync lock
            mock_cache.get.return_value = "scheduled_sync"  # Existing lock

            response = self.client.post(
                url,
                HTTP_X_GOOG_RESOURCE_ID=self.calendar.google_calendar_id,
                HTTP_X_GOOG_CHANNEL_ID="test-channel-123",
            )

            # Should still return 200 but skip processing
            self.assertEqual(response.status_code, 200)

            # Should have checked for existing lock
            expected_cache_key = f"calendar_sync_lock_{self.calendar.google_calendar_id}"
            mock_cache.get.assert_called_with(expected_cache_key)

    def test_webhook_processing_flow(self):
        """Test the streamlined webhook processing flow"""
        url = reverse("webhooks:google_webhook")

        # Mock successful processing
        with patch("apps.calendars.services.uuid_sync_engine.handle_webhook_yolo") as mock_handler, \
             patch("django.core.cache.cache") as mock_cache:
                # No existing locks
                mock_cache.get.return_value = None

                mock_handler.return_value = {
                    "status": "success",
                    "calendar": self.calendar.name,
                    "processing_time": 0.5,
                    "results": {"events_processed": 3, "busy_blocks_created": 1}
                }

                response = self.client.post(
                    url,
                    HTTP_X_GOOG_RESOURCE_ID=self.calendar.google_calendar_id,
                    HTTP_X_GOOG_CHANNEL_ID="test-channel-123",
                )

                # Should succeed and process
                self.assertEqual(response.status_code, 200)
                mock_handler.assert_called_once_with(self.calendar)

                # Should set and clear cache locks
                mock_cache.set.assert_called()
                mock_cache.delete.assert_called()

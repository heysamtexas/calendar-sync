"""
Tests for Guilfoyle's Minimalist Webhook Implementation

Simple tests for the 50-line webhook solution.
No complex infrastructure, just HTTP requests and responses.
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, Mock

from apps.calendars.models import Calendar, CalendarAccount


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
        
        # Verify sync was triggered for correct calendar
        mock_engine_instance.sync_specific_calendar.assert_called_once_with(self.calendar.id)
    
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
            sync_enabled=True
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
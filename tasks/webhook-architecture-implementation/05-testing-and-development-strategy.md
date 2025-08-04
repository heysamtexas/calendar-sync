# Testing and Development Strategy - Webhook Implementation

## Webhook Architecture Terminology Reference

For consistent terminology across all documents, see [00-webhook-strategy-overview.md](00-webhook-strategy-overview.md#webhook-architecture-terminology).

## Objective

Establish a comprehensive testing and development strategy that enables 90% of webhook functionality to be developed and tested offline, with clear progression from local development to production deployment.

## Development Phases and Offline Capabilities

### Phase 1: Pure Offline Development (95% Coverage - 2 weeks)

#### Database and Model Testing
```python
# Complete offline testability - no external dependencies
def test_webhook_subscription_lifecycle():
    """Test subscription model creation, updates, and health checks"""
    
def test_webhook_notification_processing():
    """Test notification model state transitions and error handling"""
    
def test_calendar_webhook_integration():
    """Test Calendar model webhook-related fields and methods"""
```

#### Webhook Validation Testing  
```python
# apps/webhooks/tests/test_validation_offline.py
class OfflineWebhookValidationTests(TestCase):
    """Test webhook validation without external APIs"""
    
    def test_google_webhook_validation_with_mock_headers(self):
        """Test Google webhook validation using mock headers"""
        
        # Create mock request with Google webhook headers
        mock_request = Mock()
        mock_request.headers = {
            'X-Goog-Channel-ID': 'test-channel-123',
            'X-Goog-Resource-State': 'exists',
            'X-Goog-Message-Number': '456',
            'X-Goog-Resource-ID': 'test-resource-id'
        }
        mock_request.is_secure.return_value = True
        
        # Create test subscription
        subscription = WebhookSubscription.objects.create(
            calendar=self.test_calendar,
            provider='google',
            subscription_id='test-channel-123',
            webhook_url='https://test.com/webhook',
            resource_id='test-resource-id',
            expires_at=timezone.now() + timedelta(days=7)
        )
        
        # Test validation
        validator = GoogleWebhookValidator()
        result = validator.validate_request(mock_request, subscription)
        
        self.assertTrue(result)
    
    def test_microsoft_webhook_validation_with_mock_payload(self):
        """Test Microsoft webhook validation using mock payload"""
        
        mock_payload = {
            'value': [{
                'id': 'notification-123',
                'subscriptionId': 'subscription-456',
                'changeType': 'updated',
                'resource': 'calendars/test@example.com/events'
            }]
        }
        
        mock_request = Mock()
        mock_request.body = json.dumps(mock_payload).encode('utf-8')
        mock_request.headers = {'User-Agent': 'Microsoft-Graph-Webhooks/1.0'}
        mock_request.is_secure.return_value = True
        
        subscription = WebhookSubscription.objects.create(
            calendar=self.test_calendar,
            provider='microsoft',
            subscription_id='subscription-456',
            webhook_url='https://test.com/webhook',
            resource_id='calendars/test@example.com/events',
            expires_at=timezone.now() + timedelta(days=3)
        )
        
        validator = MicrosoftWebhookValidator()
        result = validator.validate_request(mock_request, subscription)
        
        self.assertTrue(result)
```

#### Sync Engine Integration Testing
```python
# apps/calendars/tests/test_webhook_sync_offline.py
class OfflineWebhookSyncTests(TestCase):
    """Test sync engine webhook integration offline"""
    
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.list_events')
    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient.create_busy_block')
    def test_webhook_triggered_sync_complete_flow(self, mock_create_busy_block, mock_list_events):
        """Test complete webhook sync flow with mocked Google API"""
        
        # Setup test data
        source_calendar = self.create_test_calendar()
        target_calendar = self.create_test_calendar(user=source_calendar.calendar_account.user)
        
        # Mock Google API responses
        mock_list_events.return_value = [
            {
                'id': 'new_event_123',
                'summary': 'New Meeting',
                'start': {'dateTime': '2024-02-01T10:00:00Z'},
                'end': {'dateTime': '2024-02-01T11:00:00Z'},
                'attendees': [{'email': 'test@example.com'}]
            }
        ]
        
        mock_create_busy_block.return_value = {'id': 'busy_block_456'}
        
        # Create webhook subscription
        WebhookSubscription.objects.create(
            calendar=source_calendar,
            provider='google',
            subscription_id='test-subscription',
            webhook_url='https://test.com/webhook',
            resource_id=source_calendar.google_calendar_id,
            expires_at=timezone.now() + timedelta(days=7),
            status='active'
        )
        
        # Test webhook sync
        sync_engine = WebhookAwareSyncEngine()
        result = sync_engine.sync_from_webhook(source_calendar.id)
        
        # Verify results
        self.assertIsNotNone(result)
        self.assertEqual(result['events_processed'], 1)
        
        # Verify event was created
        event = Event.objects.get(
            calendar=source_calendar,
            google_event_id='new_event_123'
        )
        self.assertEqual(event.title, 'New Meeting')
        self.assertTrue(event.is_meeting_invite)
        
        # Verify busy block was created in target calendar
        busy_block = Event.objects.get(
            calendar=target_calendar,
            is_busy_block=True,
            source_event=event
        )
        self.assertTrue(busy_block.title.startswith('🔒'))
        
        # Verify API was called correctly
        mock_list_events.assert_called_once()
        mock_create_busy_block.assert_called_once()
```

#### Subscription Management Testing
```python
# apps/webhooks/tests/test_subscription_management_offline.py
class OfflineSubscriptionManagementTests(TestCase):
    """Test subscription management with mocked APIs"""
    
    @patch('apps.webhooks.services.google_subscription_client.GoogleSubscriptionClient.create_subscription')
    def test_subscription_creation_flow(self, mock_create_subscription):
        """Test subscription creation with mocked Google API"""
        
        # Mock successful subscription creation
        mock_create_subscription.return_value = {
            'subscription_id': 'channel-123',
            'resource_id': 'resource-456',
            'expires_at': timezone.now() + timedelta(days=6),
            'metadata': {'resource_uri': 'test-uri'}
        }
        
        # Test subscription creation
        manager = SubscriptionManager()
        subscription = manager.create_subscription_for_calendar(self.test_calendar)
        
        # Verify subscription was created
        self.assertIsNotNone(subscription)
        self.assertEqual(subscription.subscription_id, 'channel-123')
        self.assertEqual(subscription.status, 'active')
        
        # Verify calendar was updated
        self.test_calendar.refresh_from_db()
        self.assertTrue(self.test_calendar.webhook_enabled)
    
    @patch('apps.webhooks.services.google_subscription_client.GoogleSubscriptionClient.renew_subscription')
    def test_subscription_renewal_flow(self, mock_renew_subscription):
        """Test subscription renewal with mocked Google API"""
        
        # Create expiring subscription
        subscription = WebhookSubscription.objects.create(
            calendar=self.test_calendar,
            provider='google',
            subscription_id='expiring-channel',
            webhook_url='https://test.com/webhook',
            resource_id='test-resource',
            expires_at=timezone.now() + timedelta(hours=2),  # Expires soon
            status='active'
        )
        
        # Mock successful renewal
        mock_renew_subscription.return_value = {
            'expires_at': timezone.now() + timedelta(days=6)
        }
        
        # Test renewal
        manager = SubscriptionManager()
        result = manager.renew_subscription(subscription)
        
        # Verify renewal succeeded
        self.assertTrue(result)
        
        # Verify subscription was updated
        subscription.refresh_from_db()
        self.assertTrue(subscription.expires_at > timezone.now() + timedelta(days=5))
```

## LLM Testing Execution Guide

### Phase 1: Offline Testing (COMPLETE BEFORE ANY EXTERNAL DEPENDENCIES)

**MANDATORY EXECUTION SEQUENCE** (AI agents: run these commands in order):
```bash
# STEP 1: Validate environment setup
cd /home/sheraz/src/calendar-bridge-clone
python --version  # Must be Python 3.11+
uv --version      # Must show uv version

# STEP 2: Install test dependencies
uv sync --all-extras

# STEP 3: Run offline webhook tests (NO external API calls allowed)
uv run python manage.py test apps.webhooks.tests.test_validation_offline --verbosity=2
uv run python manage.py test apps.webhooks.tests.test_subscription_management_offline --verbosity=2
uv run python manage.py test apps.calendars.tests.test_webhook_sync_offline --verbosity=2

# SUCCESS CRITERIA: ALL tests pass with 0 failures, 0 errors
# FAILURE RESPONSE: Fix ALL failures before proceeding to Phase 2
```

**Test Results Validation** (LLM: verify these metrics):
- **Coverage Requirement**: >90% for webhook-related code
- **Performance Requirement**: All tests complete in <30 seconds  
- **Mock Validation**: Zero external API calls during offline tests (check logs for HTTP requests)
- **Database Isolation**: Tests use Django's test database, not production data

### Phase 2: Local Development (REQUIRES NGROK)

**PREREQUISITES VALIDATION** (AI agents: check these before Phase 2):
```bash
# STEP 1: Verify ngrok installation
ngrok version  # Must show ngrok version

# STEP 2: Start webhook development server
uv run python manage.py runserver 8000 &
SERVER_PID=$!

# STEP 3: Start ngrok tunnel (in separate terminal)
ngrok http 8000 --region=us

# STEP 4: Extract ngrok URL (update this in tests)
curl -s http://localhost:4040/api/tunnels | grep -o 'https://[a-z0-9]*\.ngrok\.io'

# SUCCESS CRITERIA: Can access Django app through ngrok HTTPS URL
```

**Local Testing Commands** (AI agents: execute after ngrok setup):
```bash
# Test webhook endpoints are reachable via ngrok
curl -X GET https://YOUR_NGROK_URL.ngrok.io/webhooks/health/
# Expected: HTTP 200 with JSON health status

# Test webhook notification processing
curl -X POST https://YOUR_NGROK_URL.ngrok.io/webhooks/google/test-calendar/ \
  -H "X-Goog-Channel-ID: test-channel" \
  -H "X-Goog-Resource-State: exists" \
  -H "X-Goog-Message-Number: 123" \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: HTTP 200 or 404 (depending on test data)
```

### Phase 3: Production Testing Validation

**PRODUCTION READINESS CHECKLIST** (AI agents: verify ALL items):
- [ ] All Phase 1 offline tests pass: `uv run python manage.py test apps.webhooks --verbosity=2`
- [ ] All Phase 2 local tests pass with ngrok
- [ ] Webhook endpoints return correct HTTP status codes
- [ ] Database migrations applied: `uv run python manage.py migrate`
- [ ] Production webhook URLs accessible via HTTPS  
- [ ] Domain verification completed for Google Calendar
- [ ] SSL certificates valid and not expired

**Production Test Execution** (AI agents: run in production environment):
```bash
# Validate production webhook endpoints
curl -f https://your-production-domain.com/webhooks/health/ 
# Must return HTTP 200 - if fails, deployment is broken

# Test production webhook processing (use test subscription)
# NOTE: Only run this with valid test webhook subscription
curl -X POST https://your-production-domain.com/webhooks/google/test-calendar-id/ \
  -H "X-Goog-Channel-ID: valid-test-channel-id" \
  -H "X-Goog-Resource-State: exists" \
  -H "X-Goog-Message-Number: production-test-123" \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: HTTP 200 (successful processing) or 404 (no subscription - also OK for test)
```

### Phase 2: Local Development with ngrok (90% Coverage - 1 week)

#### Local Webhook Endpoint Testing
```python
# apps/webhooks/tests/test_local_endpoints.py
class LocalWebhookEndpointTests(TestCase):
    """Test webhook endpoints with actual HTTP requests (requires ngrok)"""
    
    def setUp(self):
        self.client = Client()
        self.ngrok_url = "https://abc123.ngrok.io"  # Replace with actual ngrok URL
    
    def test_google_webhook_endpoint_response(self):
        """Test Google webhook endpoint responds correctly"""
        
        calendar = self.create_test_calendar()
        
        # Create subscription with ngrok URL
        subscription = WebhookSubscription.objects.create(
            calendar=calendar,
            provider='google',
            subscription_id='local-test-channel',
            webhook_url=f"{self.ngrok_url}/webhooks/google/{calendar.google_calendar_id}/",
            resource_id=calendar.google_calendar_id,
            expires_at=timezone.now() + timedelta(days=7),
            status='active'
        )
        
        # Test webhook endpoint
        url = reverse('webhooks:google_webhook', args=[calendar.google_calendar_id])
        
        headers = {
            'HTTP_X_GOOG_CHANNEL_ID': subscription.subscription_id,
            'HTTP_X_GOOG_RESOURCE_STATE': 'exists',
            'HTTP_X_GOOG_MESSAGE_NUMBER': '123',
            'HTTP_CONTENT_TYPE': 'application/json'
        }
        
        with patch('apps.webhooks.services.notification_processor.NotificationProcessor.process_notification'):
            response = self.client.post(url, data='{}', **headers)
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        
        # Verify notification was stored
        notification = WebhookNotification.objects.get(notification_id='123')
        self.assertEqual(notification.subscription, subscription)
    
    def test_manual_webhook_simulation(self):
        """Test manual webhook simulation to local endpoint"""
        
        # This test would send actual HTTP requests to local ngrok URL
        # to simulate webhook delivery
        
        import requests
        
        webhook_url = f"{self.ngrok_url}/webhooks/google/test-calendar-id/"
        
        headers = {
            'X-Goog-Channel-ID': 'test-channel',
            'X-Goog-Resource-State': 'exists',
            'X-Goog-Message-Number': '789',
            'Content-Type': 'application/json'
        }
        
        # Send test webhook
        response = requests.post(webhook_url, json={}, headers=headers)
        
        # Verify webhook was received and processed
        self.assertEqual(response.status_code, 200)
```

#### Live Subscription Testing (ngrok required)
```python
# apps/webhooks/tests/test_live_subscriptions.py 
class LiveSubscriptionTests(TestCase):
    """Test subscription creation with real Google API (requires valid credentials)"""
    
    @patch('apps.webhooks.services.google_subscription_client.GoogleSubscriptionClient._get_access_token')
    def test_create_real_google_subscription(self, mock_get_token):
        """Test creating real Google Calendar subscription"""
        
        # Mock valid access token
        mock_get_token.return_value = 'valid-test-token'
        
        # Create test calendar with real Google Calendar ID
        calendar = Calendar.objects.create(
            calendar_account=self.test_account,
            google_calendar_id='test@gmail.com',  # Use real calendar ID
            name='Test Calendar'
        )
        
        # Generate ngrok webhook URL
        webhook_url = f"https://abc123.ngrok.io/webhooks/google/{calendar.google_calendar_id}/"
        
        # Test subscription creation (this will make real API call)
        google_client = GoogleSubscriptionClient()
        
        # Note: This test requires careful setup and cleanup
        # Should only run in controlled testing environment
        subscription_data = google_client.create_subscription(calendar, webhook_url)
        
        if subscription_data:
            # Verify subscription data
            self.assertIn('subscription_id', subscription_data)
            self.assertIn('expires_at', subscription_data)
            
            # Clean up - delete the subscription
            google_client.delete_subscription_by_id(subscription_data['subscription_id'])
```

### Phase 3: Development Environment Testing (Local Network - 1 week)

#### Integration Testing Framework
```python
# apps/webhooks/tests/test_integration_development.py
class DevelopmentIntegrationTests(TestCase):
    """Integration tests for development environment"""
    
    def setUp(self):
        # Set up test database with realistic data
        self.user = self.create_test_user()
        self.account1 = self.create_calendar_account(self.user, 'primary@gmail.com')
        self.account2 = self.create_calendar_account(self.user, 'work@gmail.com')
        
        self.calendar1 = self.create_calendar(self.account1, 'Primary Calendar')
        self.calendar2 = self.create_calendar(self.account1, 'Personal Calendar')
        self.calendar3 = self.create_calendar(self.account2, 'Work Calendar')
    
    def test_end_to_end_webhook_flow_development(self):
        """Test complete webhook flow in development environment"""
        
        # This test simulates the complete webhook flow:
        # 1. Subscription creation
        # 2. Webhook delivery simulation
        # 3. Event processing
        # 4. Cross-calendar propagation
        # 5. Database consistency validation
        
        with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient') as mock_client_class:
            # Set up mock client behavior
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            # Mock event fetching
            mock_client.list_events.return_value = [
                {
                    'id': 'integration_event_123',
                    'summary': 'Integration Test Meeting',
                    'start': {'dateTime': '2024-02-15T14:00:00Z'},
                    'end': {'dateTime': '2024-02-15T15:00:00Z'},
                    'attendees': [{'email': 'test@example.com'}]
                }
            ]
            
            # Mock busy block creation
            mock_client.create_busy_block.return_value = {'id': 'busy_block_integration'}
            
            # Create subscriptions
            manager = SubscriptionManager()
            
            with patch('apps.webhooks.services.google_subscription_client.GoogleSubscriptionClient.create_subscription') as mock_create:
                mock_create.return_value = {
                    'subscription_id': 'integration-channel-123',
                    'resource_id': self.calendar1.google_calendar_id,
                    'expires_at': timezone.now() + timedelta(days=6),
                    'metadata': {}
                }
                
                subscription = manager.create_subscription_for_calendar(self.calendar1)
            
            # Simulate webhook delivery
            notification = WebhookNotification.objects.create(
                subscription=subscription,
                notification_id='integration-notification-123',
                headers={
                    'X-Goog-Channel-ID': subscription.subscription_id,
                    'X-Goog-Resource-State': 'exists'
                },
                payload={}
            )
            
            # Process notification
            processor = NotificationProcessor()
            processor.process_notification(notification)
            
            # Verify event was created
            event = Event.objects.get(
                calendar=self.calendar1,
                google_event_id='integration_event_123'
            )
            self.assertEqual(event.title, 'Integration Test Meeting')
            
            # Verify busy blocks were created in other calendars
            busy_blocks = Event.objects.filter(
                is_busy_block=True,
                source_event=event
            )
            
            # Should have busy blocks in calendar2 and calendar3
            self.assertEqual(busy_blocks.count(), 2)
            
            # Verify notification was marked as completed
            notification.refresh_from_db()
            self.assertEqual(notification.processing_status, 'completed')
```

### Phase 4: Production Environment Testing (Live Server Required - 1 week)

#### Production Webhook Validation
```python
# apps/webhooks/tests/test_production_webhooks.py
@override_settings(DEBUG=False)  # Production-like settings
class ProductionWebhookTests(TestCase):
    """Test webhooks in production-like environment"""
    
    def test_production_webhook_security(self):
        """Verify webhook security measures work in production"""
        
        # Test HTTPS requirement
        with patch('django.http.HttpRequest.is_secure', return_value=False):
            validator = GoogleWebhookValidator()
            request = Mock()
            request.is_secure.return_value = False
            
            result = validator.validate_https(request)
            self.assertFalse(result)
    
    def test_production_rate_limiting(self):
        """Test rate limiting in production environment"""
        
        middleware = WebhookRateLimitMiddleware(lambda r: HttpResponse())
        
        # Simulate many requests from same IP
        for i in range(101):  # Over the limit
            request = Mock()
            request.path = '/webhooks/google/test/'
            request.META = {'REMOTE_ADDR': '192.168.1.100'}
            
            response = middleware(request)
            
            if i >= 100:  # Should be rate limited
                self.assertEqual(response.status_code, 429)
    
    def test_real_webhook_delivery_production(self):
        """Test real webhook delivery in production (manual test)"""
        
        # This test would verify that real webhooks are delivered
        # to production endpoints and processed correctly
        # Should be run manually with monitoring
        
        # 1. Create subscription with production webhook URL
        # 2. Make calendar change in Google Calendar
        # 3. Verify webhook is received within 2 minutes
        # 4. Verify processing completes successfully
        # 5. Verify cross-calendar updates occur
        
        # This is primarily a monitoring and validation test
        pass
```

## Test Data and Fixtures

### Comprehensive Test Data Factory
```python
# apps/webhooks/tests/factories.py
import factory
from django.utils import timezone
from datetime import timedelta

class WebhookSubscriptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WebhookSubscription
    
    calendar = factory.SubFactory('apps.calendars.tests.factories.CalendarFactory')
    provider = 'google'
    subscription_id = factory.Sequence(lambda n: f'test-subscription-{n}')
    webhook_url = factory.LazyAttribute(lambda obj: f'https://test.com/webhook/{obj.calendar.id}/')
    resource_id = factory.LazyAttribute(lambda obj: obj.calendar.google_calendar_id)
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=6))
    status = 'active'

class WebhookNotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WebhookNotification
    
    subscription = factory.SubFactory(WebhookSubscriptionFactory)
    notification_id = factory.Sequence(lambda n: f'notification-{n}')
    headers = factory.LazyFunction(lambda: {
        'X-Goog-Channel-ID': 'test-channel',
        'X-Goog-Resource-State': 'exists',
        'X-Goog-Message-Number': str(factory.Faker('random_int', min=1, max=1000))
    })
    payload = factory.Dict({})
    processing_status = 'pending'

# Sample webhook payloads for testing
GOOGLE_WEBHOOK_PAYLOADS = {
    'sync_message': {
        'headers': {
            'X-Goog-Channel-ID': 'test-channel-123',
            'X-Goog-Resource-State': 'sync',
            'X-Goog-Message-Number': '1'
        },
        'payload': {}
    },
    'change_notification': {
        'headers': {
            'X-Goog-Channel-ID': 'test-channel-123',
            'X-Goog-Resource-State': 'exists',
            'X-Goog-Message-Number': '2'
        },
        'payload': {}
    }
}

MICROSOFT_WEBHOOK_PAYLOADS = {
    'event_created': {
        'headers': {
            'User-Agent': 'Microsoft-Graph-Webhooks/1.0'
        },
        'payload': {
            'value': [{
                'id': 'notification-456',
                'subscriptionId': 'subscription-789',
                'changeType': 'created',
                'resource': 'calendars/test@example.com/events/event-123'
            }]
        }
    }
}
```

### Mock Service Factories
```python
# apps/webhooks/tests/mocks.py
class MockGoogleCalendarClient:
    """Mock Google Calendar client for testing"""
    
    def __init__(self, calendar_account):
        self.account = calendar_account
        self.events = []  # Store mock events
    
    def list_events(self, calendar_id, time_min=None, time_max=None, max_results=250):
        """Return mock events"""
        return self.events
    
    def create_busy_block(self, calendar_id, title, start_time, end_time, description=""):
        """Mock busy block creation"""
        return {
            'id': f'mock_busy_block_{len(self.events)}',
            'summary': title,
            'description': description
        }
    
    def delete_event(self, calendar_id, event_id):
        """Mock event deletion"""
        return True
    
    def find_system_events(self, calendar_id, tag_pattern):
        """Mock system event finding"""
        return [e for e in self.events if tag_pattern in e.get('description', '')]

class MockSubscriptionClient:
    """Mock subscription client for testing"""
    
    def create_subscription(self, calendar, webhook_url):
        """Mock subscription creation"""
        return {
            'subscription_id': f'mock-subscription-{calendar.id}',
            'resource_id': calendar.google_calendar_id,
            'expires_at': timezone.now() + timedelta(days=6),
            'metadata': {'test': True}
        }
    
    def renew_subscription(self, subscription):
        """Mock subscription renewal"""
        return {
            'expires_at': timezone.now() + timedelta(days=6)
        }
    
    def delete_subscription(self, subscription):
        """Mock subscription deletion"""
        pass
```

## Development Tools and Utilities

### Webhook Testing Utilities
```python
# apps/webhooks/tests/utils.py
import json
import requests
from django.test import Client
from django.urls import reverse

class WebhookTestHelper:
    """Helper utilities for webhook testing"""
    
    def __init__(self):
        self.client = Client()
    
    def send_test_webhook(self, calendar_uuid, provider='google', headers=None, payload=None):
        """Send test webhook to local endpoint"""
        
        url = reverse(f'webhooks:{provider}_webhook', args=[calendar_uuid])
        
        if headers is None:
            headers = self.get_default_headers(provider)
        
        if payload is None:
            payload = {}
        
        # Convert headers to Django test client format
        django_headers = {}
        for key, value in headers.items():
            django_key = f'HTTP_{key.upper().replace("-", "_")}'
            django_headers[django_key] = value
        
        django_headers['HTTP_CONTENT_TYPE'] = 'application/json'
        
        response = self.client.post(
            url, 
            data=json.dumps(payload),
            **django_headers
        )
        
        return response
    
    def get_default_headers(self, provider):
        """Get default headers for provider"""
        
        if provider == 'google':
            return {
                'X-Goog-Channel-ID': 'test-channel-123',
                'X-Goog-Resource-State': 'exists',
                'X-Goog-Message-Number': '456'
            }
        elif provider == 'microsoft':
            return {
                'User-Agent': 'Microsoft-Graph-Webhooks/1.0'
            }
        
        return {}
    
    def create_test_subscription(self, calendar, provider='google'):
        """Create test webhook subscription"""
        
        return WebhookSubscription.objects.create(
            calendar=calendar,
            provider=provider,
            subscription_id=f'test-{provider}-{calendar.id}',
            webhook_url=f'https://test.com/webhook/{provider}/{calendar.google_calendar_id}/',
            resource_id=calendar.google_calendar_id,
            expires_at=timezone.now() + timedelta(days=7),
            status='active'
        )
    
    def simulate_webhook_delivery(self, subscription, notification_id=None):
        """Simulate webhook delivery and processing"""
        
        if notification_id is None:
            notification_id = f'test-notification-{subscription.id}'
        
        # Create notification
        notification = WebhookNotification.objects.create(
            subscription=subscription,
            notification_id=notification_id,
            headers=self.get_default_headers(subscription.provider),
            payload={}
        )
        
        # Process notification
        processor = NotificationProcessor()
        processor.process_notification(notification)
        
        return notification

class NgrokTestHelper:
    """Helper for ngrok-based testing"""
    
    def __init__(self, ngrok_url):
        self.ngrok_url = ngrok_url
    
    def test_webhook_endpoint_reachability(self):
        """Test that webhook endpoints are reachable via ngrok"""
        
        endpoints = [
            '/webhooks/health/',
            '/webhooks/google/test-calendar/',
            '/webhooks/microsoft/test-calendar/'
        ]
        
        results = {}
        
        for endpoint in endpoints:
            try:
                response = requests.get(f"{self.ngrok_url}{endpoint}", timeout=10)
                results[endpoint] = {
                    'reachable': True,
                    'status_code': response.status_code
                }
            except Exception as e:
                results[endpoint] = {
                    'reachable': False,
                    'error': str(e)
                }
        
        return results
    
    def send_external_webhook(self, calendar_uuid, provider='google'):
        """Send webhook from external source to ngrok endpoint"""
        
        webhook_url = f"{self.ngrok_url}/webhooks/{provider}/{calendar_uuid}/"
        
        headers = {
            'X-Goog-Channel-ID': 'external-test-channel',
            'X-Goog-Resource-State': 'exists',
            'X-Goog-Message-Number': '999',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(webhook_url, json={}, headers=headers, timeout=10)
            return {
                'success': True,
                'status_code': response.status_code,
                'response_text': response.text
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
```

## Continuous Integration Testing

### CI/CD Pipeline Tests
```yaml
# .github/workflows/webhook_tests.yml
name: Webhook Implementation Tests

on: [push, pull_request]

jobs:
  offline-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.11
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      
      - name: Run offline webhook tests
        run: |
          python manage.py test apps.webhooks.tests.test_validation_offline
          python manage.py test apps.webhooks.tests.test_subscription_management_offline
          python manage.py test apps.calendars.tests.test_webhook_sync_offline
      
      - name: Check test coverage
        run: |
          coverage run manage.py test
          coverage report --fail-under=90
  
  integration-tests:
    runs-on: ubuntu-latest
    needs: offline-tests
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.11
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      
      - name: Run integration tests
        run: |
          python manage.py test apps.webhooks.tests.test_integration_development
```

## Success Criteria

### Development Efficiency
- **90% Offline Development**: Achieve 90% test coverage without external dependencies
- **<1 Hour Setup Time**: New developers can set up webhook testing environment in under 1 hour
- **Comprehensive Mocking**: All external APIs properly mocked for reliable testing

### Testing Coverage
- **95% Code Coverage**: Achieve >95% test coverage for webhook-related code
- **All Failure Scenarios**: Test all identified error conditions and edge cases
- **Performance Testing**: Validate webhook processing times and resource usage

### Development Workflow
- **Fast Feedback Loop**: Tests run in <30 seconds for rapid development iteration
- **Clear Progression Path**: Smooth transition from offline → local → development → production
- **Debugging Support**: Comprehensive logging and error reporting for troubleshooting

This testing and development strategy ensures reliable webhook implementation while maximizing development efficiency and minimizing dependencies on external services during the development phase.

## Related Documentation

**Prerequisites:**
- **Strategy**: Read [00-webhook-strategy-overview.md](00-webhook-strategy-overview.md) for testing approach context
- **Database**: Review [01-database-infrastructure.md](01-database-infrastructure.md) for models to test
- **Endpoints**: Test [02-webhook-endpoints-and-validation.md](02-webhook-endpoints-and-validation.md) implementation  
- **Subscriptions**: Validate [03-subscription-management.md](03-subscription-management.md) lifecycle management
- **Sync Engine**: Test [04-sync-engine-integration.md](04-sync-engine-integration.md) integration points

**Next Steps:**
- **Deployment**: Use [06-deployment-and-monitoring.md](06-deployment-and-monitoring.md) for production testing procedures
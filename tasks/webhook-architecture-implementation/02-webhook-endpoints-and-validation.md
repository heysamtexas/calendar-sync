# Webhook Endpoints and Validation - Implementation Guide

## Webhook Architecture Terminology Reference

For consistent terminology across all documents, see [00-webhook-strategy-overview.md](00-webhook-strategy-overview.md#webhook-architecture-terminology).

## Objective

Implement secure, reliable webhook endpoints for receiving calendar change notifications from Google Calendar and Microsoft Graph, with comprehensive request validation and authentication.

## Django App Structure

### New Webhooks App Architecture
```
apps/webhooks/
├── __init__.py
├── apps.py                    # Webhooks app configuration
├── models.py                  # WebhookSubscription, WebhookNotification
├── views.py                   # Webhook receiver endpoints
├── urls.py                    # URL routing for webhook endpoints
├── admin.py                   # Django admin integration
├── services/
│   ├── __init__.py
│   ├── webhook_validator.py   # Request validation and authentication
│   ├── google_handler.py      # Google Calendar webhook processing
│   ├── microsoft_handler.py   # Microsoft Graph webhook processing
│   ├── notification_processor.py  # Core notification processing
│   └── subscription_manager.py    # Subscription lifecycle management
├── management/
│   └── commands/
│       ├── __init__.py
│       ├── process_webhook_notifications.py  # Background processing
│       └── cleanup_webhook_data.py          # Data maintenance
└── tests/
    ├── __init__.py
    ├── test_webhook_endpoints.py    # Endpoint testing
    ├── test_validation.py           # Validation testing
    ├── test_google_handler.py       # Google-specific testing
    ├── test_microsoft_handler.py    # Microsoft-specific testing
    └── fixtures/
        ├── google_webhooks.json     # Sample Google payloads
        └── microsoft_webhooks.json  # Sample Microsoft payloads
```

### URL Configuration

#### Main URLs Integration
```python
# src/calendar_sync/urls.py
urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.dashboard.urls")),
    path("", include("apps.accounts.urls")),
    path("webhooks/", include("apps.webhooks.urls")),  # Add webhook routes
    # ... existing auth URLs
]
```

#### Webhook App URLs
```python
# apps/webhooks/urls.py
from django.urls import path
from . import views

app_name = 'webhooks'

urlpatterns = [
    # Google Calendar webhook endpoints
    path(
        'google/<str:calendar_uuid>/', 
        views.GoogleWebhookView.as_view(), 
        name='google_webhook'
    ),
    
    # Microsoft Graph webhook endpoints
    path(
        'microsoft/<str:calendar_uuid>/', 
        views.MicrosoftWebhookView.as_view(), 
        name='microsoft_webhook'
    ),
    
    # Health check endpoint
    path('health/', views.WebhookHealthView.as_view(), name='webhook_health'),
    
    # Admin endpoints for debugging (protected)
    path('admin/subscriptions/', views.SubscriptionListView.as_view(), name='subscription_list'),
    path('admin/notifications/', views.NotificationListView.as_view(), name='notification_list'),
]
```

## Webhook Endpoint Implementation

### Base Webhook View
```python
# apps/webhooks/views.py
import json
import logging
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from django.db import transaction

from .models import WebhookSubscription, WebhookNotification
from .services.webhook_validator import WebhookValidator
from .services.notification_processor import NotificationProcessor

logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name='dispatch')
class BaseWebhookView(View):
    """Base class for webhook endpoints with common functionality"""
    
    provider = None  # Override in subclasses
    validator_class = None  # Override in subclasses
    
    def post(self, request, calendar_uuid):
        """Handle incoming webhook notifications"""
        
        # Extract notification ID for deduplication
        notification_id = self.get_notification_id(request)
        if not notification_id:
            logger.warning(f"Missing notification ID in {self.provider} webhook")
            return HttpResponse(status=400)
        
        try:
            # Find subscription by calendar UUID
            subscription = self.get_subscription(calendar_uuid)
            if not subscription:
                logger.warning(f"No active subscription found for calendar {calendar_uuid}")
                return HttpResponse(status=404)
            
            # Check for duplicate notification
            if self.is_duplicate_notification(subscription, notification_id):
                logger.info(f"Ignoring duplicate notification {notification_id}")
                return HttpResponse(status=200)  # Already processed
            
            # Validate webhook authenticity
            if not self.validate_webhook(request, subscription):
                logger.error(f"Invalid {self.provider} webhook signature for {calendar_uuid}")
                return HttpResponse(status=403)
            
            # Store notification for processing
            notification = self.store_notification(request, subscription, notification_id)
            
            # Process notification asynchronously (or immediately for simple cases)
            self.process_notification(notification)
            
            # Update subscription health
            subscription.mark_notification_received()
            
            logger.info(f"Successfully processed {self.provider} webhook for {calendar_uuid}")
            return HttpResponse(status=200)
            
        except Exception as e:
            logger.error(f"Error processing {self.provider} webhook: {e}")
            return HttpResponse(status=500)
    
    def get_subscription(self, calendar_uuid):
        """Get active webhook subscription for calendar"""
        try:
            return WebhookSubscription.objects.get(
                calendar__google_calendar_id=calendar_uuid,  # Using google_calendar_id as UUID
                provider=self.provider,
                status='active'
            )
        except WebhookSubscription.DoesNotExist:
            return None
    
    def is_duplicate_notification(self, subscription, notification_id):
        """Check if notification has already been processed"""
        return WebhookNotification.objects.filter(
            subscription=subscription,
            notification_id=notification_id
        ).exists()
    
    def store_notification(self, request, subscription, notification_id):
        """Store webhook notification for processing"""
        
        # Parse request body safely
        try:
            if request.content_type == 'application/json':
                payload = json.loads(request.body.decode('utf-8'))
            else:
                payload = {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        
        # Store notification
        notification = WebhookNotification.objects.create(
            subscription=subscription,
            notification_id=notification_id,
            headers=dict(request.headers),
            payload=payload,
            processing_status='pending'
        )
        
        return notification
    
    def process_notification(self, notification):
        """Process the webhook notification"""
        processor = NotificationProcessor()
        processor.process_notification(notification)
    
    # Abstract methods for subclasses
    def get_notification_id(self, request):
        """Extract unique notification ID from request headers"""
        raise NotImplementedError
    
    def validate_webhook(self, request, subscription):
        """Validate webhook authenticity"""
        raise NotImplementedError
```

## LLM Webhook Processing Protocol

### Mandatory Processing Steps (Execute in Order)
**CRITICAL: AI agents must follow these steps exactly to ensure reliable webhook notification processing.**

#### 1. Extract Notification ID (FAIL FAST if missing)
- **Google**: Use `X-Goog-Message-Number` header
- **Microsoft**: Parse from JSON payload `value[0].id`
- **Action on Missing**: Return HTTP 400 immediately, log error

```python
# Example validation
def get_notification_id(self, request):
    notification_id = request.headers.get('X-Goog-Message-Number')
    if not notification_id:
        logger.error("Missing X-Goog-Message-Number header")
        return None  # Triggers 400 response
    return notification_id
```

#### 2. Find Webhook Subscription (FAIL FAST if not found)
- **Query**: `WebhookSubscription.objects.get(calendar__google_calendar_id=calendar_uuid, status='active')`
- **Action on Missing**: Return HTTP 404 immediately, log warning

```python
# Example lookup
def get_subscription(self, calendar_uuid):
    try:
        return WebhookSubscription.objects.get(
            calendar__google_calendar_id=calendar_uuid,
            provider=self.provider,
            status='active'
        )
    except WebhookSubscription.DoesNotExist:
        logger.warning(f"No active subscription for calendar {calendar_uuid}")
        return None  # Triggers 404 response
```

#### 3. Check for Duplicate Notifications (EARLY RETURN if duplicate)
- **Query**: `WebhookNotification.objects.filter(subscription=sub, notification_id=id).exists()`
- **Action if Duplicate**: Return HTTP 200 immediately (already processed successfully)

#### 4. Validate Webhook Authenticity (FAIL FAST if invalid)
- **Google**: Validate required headers and channel ID match
- **Microsoft**: Validate User-Agent and subscription ID match
- **Action on Invalid**: Return HTTP 403 immediately, log security warning

#### 5. Store and Process Notification
- **Store**: Create `WebhookNotification` record with status='pending'
- **Process**: Call `NotificationProcessor.process_notification()`
- **Action on Success**: Return HTTP 200
- **Action on Error**: Return HTTP 500, log error details

### HTTP Response Requirements (LLM: Use Exact Status Codes)
- **200**: Success - webhook processed or already processed (duplicate)
- **400**: Bad Request - missing required headers/payload data
- **403**: Forbidden - invalid webhook signature/authentication  
- **404**: Not Found - no active subscription found for calendar
- **429**: Too Many Requests - rate limit exceeded
- **500**: Internal Server Error - processing failure (retry-able)

### Error Recovery Decision Matrix
| Error Type | HTTP Status | Retry? | Action |
|------------|-------------|--------|--------|
| Missing headers | 400 | No | Log error, return immediately |
| Invalid signature | 403 | No | Log security warning, return immediately |
| No subscription | 404 | No | Log warning, return immediately |
| Duplicate notification | 200 | No | Return success (already processed) |
| Processing failure | 500 | Yes | Log error, increment failure_count |

### Google Calendar Webhook View
```python
class GoogleWebhookView(BaseWebhookView):
    """Handle Google Calendar webhook notifications"""
    
    provider = 'google'
    
    def get_notification_id(self, request):
        """Extract Google notification ID from headers"""
        # Google sends X-Goog-Message-Number for deduplication
        return request.headers.get('X-Goog-Message-Number')
    
    def validate_webhook(self, request, subscription):
        """Validate Google webhook authenticity"""
        from .services.webhook_validator import GoogleWebhookValidator
        
        validator = GoogleWebhookValidator()
        return validator.validate_request(request, subscription)
    
    def get_resource_state(self, request):
        """Extract resource state from Google webhook headers"""
        return request.headers.get('X-Goog-Resource-State', 'exists')
    
    def process_notification(self, notification):
        """Process Google Calendar notification"""
        from .services.google_handler import GoogleWebhookHandler
        
        handler = GoogleWebhookHandler()
        handler.process_notification(notification)
```

### Microsoft Graph Webhook View
```python  
class MicrosoftWebhookView(BaseWebhookView):
    """Handle Microsoft Graph webhook notifications"""
    
    provider = 'microsoft'
    
    def get_notification_id(self, request):
        """Extract Microsoft notification ID from payload"""
        try:
            payload = json.loads(request.body.decode('utf-8'))
            # Microsoft sends notifications in an array
            if 'value' in payload and payload['value']:
                return payload['value'][0].get('id')
            return payload.get('id')
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
            return None
    
    def validate_webhook(self, request, subscription):
        """Validate Microsoft webhook authenticity"""
        from .services.webhook_validator import MicrosoftWebhookValidator
        
        validator = MicrosoftWebhookValidator()
        return validator.validate_request(request, subscription)
    
    def handle_validation_token(self, request):
        """Handle Microsoft webhook validation challenge"""
        validation_token = request.GET.get('validationToken')
        if validation_token:
            return HttpResponse(validation_token, content_type='text/plain')
        return None
    
    def get(self, request, calendar_uuid):
        """Handle Microsoft webhook validation challenge"""
        # Microsoft sends GET request with validationToken for initial setup
        validation_response = self.handle_validation_token(request)
        if validation_response:
            return validation_response
        
        return HttpResponse(status=404)
    
    def process_notification(self, notification):
        """Process Microsoft Graph notification"""
        from .services.microsoft_handler import MicrosoftWebhookHandler
        
        handler = MicrosoftWebhookHandler()
        handler.process_notification(notification)
```

## Webhook Validation Services

### Base Webhook Validator
```python
# apps/webhooks/services/webhook_validator.py
import hmac
import hashlib
import base64
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseWebhookValidator(ABC):
    """Base class for webhook request validation"""
    
    @abstractmethod
    def validate_request(self, request, subscription):
        """Validate webhook request authenticity"""
        pass
    
    def validate_https(self, request):
        """Ensure request is over HTTPS in production"""
        if not settings.DEBUG and not request.is_secure():
            logger.error("Webhook request not over HTTPS")
            return False
        return True
    
    def validate_user_agent(self, request, expected_patterns=None):
        """Validate User-Agent header against expected patterns"""
        if not expected_patterns:
            return True
        
        user_agent = request.headers.get('User-Agent', '')
        for pattern in expected_patterns:
            if pattern in user_agent:
                return True
        
        logger.warning(f"Unexpected User-Agent: {user_agent}")
        return False
```

### Google Webhook Validator
```python
class GoogleWebhookValidator(BaseWebhookValidator):
    """Validate Google Calendar webhook requests"""
    
    def validate_request(self, request, subscription):
        """Validate Google webhook request"""
        
        # Basic HTTPS validation
        if not self.validate_https(request):
            return False
        
        # Validate required headers
        if not self.validate_google_headers(request):
            return False
        
        # Validate channel ID matches subscription
        if not self.validate_channel_id(request, subscription):
            return False
        
        # Validate resource ID matches calendar
        if not self.validate_resource_id(request, subscription):
            return False
        
        return True
    
    def validate_google_headers(self, request):
        """Validate required Google webhook headers"""
        required_headers = [
            'X-Goog-Channel-ID',
            'X-Goog-Resource-State',
            'X-Goog-Message-Number'
        ]
        
        for header in required_headers:
            if header not in request.headers:
                logger.error(f"Missing required Google header: {header}")
                return False
        
        return True
    
    def validate_channel_id(self, request, subscription):
        """Validate channel ID matches subscription"""
        channel_id = request.headers.get('X-Goog-Channel-ID')
        expected_channel_id = subscription.subscription_id
        
        if channel_id != expected_channel_id:
            logger.error(f"Channel ID mismatch: {channel_id} != {expected_channel_id}")
            return False
        
        return True
    
    def validate_resource_id(self, request, subscription):
        """Validate resource ID matches subscribed calendar"""
        resource_id = request.headers.get('X-Goog-Resource-ID')
        if not resource_id:
            return True  # Resource ID is optional
        
        # Resource ID should match calendar's Google Calendar ID
        expected_resource_id = subscription.calendar.google_calendar_id
        
        if resource_id != expected_resource_id:
            logger.warning(f"Resource ID mismatch: {resource_id} != {expected_resource_id}")
            # Don't fail validation - Google's resource IDs can be complex
        
        return True
```

### Microsoft Webhook Validator
```python
class MicrosoftWebhookValidator(BaseWebhookValidator):
    """Validate Microsoft Graph webhook requests"""
    
    def validate_request(self, request, subscription):
        """Validate Microsoft webhook request"""
        
        # Basic HTTPS validation
        if not self.validate_https(request):
            return False
        
        # Validate User-Agent
        if not self.validate_user_agent(request, ['Microsoft-Graph-Webhooks']):
            return False
        
        # Validate subscription ID if present in payload
        if not self.validate_subscription_id(request, subscription):
            return False
        
        # TODO: Implement signature validation when Microsoft provides signing keys
        # Currently Microsoft Graph webhooks don't include HMAC signatures
        
        return True
    
    def validate_subscription_id(self, request, subscription):
        """Validate subscription ID in payload matches our subscription"""
        try:
            import json
            payload = json.loads(request.body.decode('utf-8'))
            
            # Microsoft sends notifications in 'value' array
            if 'value' in payload and payload['value']:
                notification = payload['value'][0]
                subscription_id = notification.get('subscriptionId')
                
                if subscription_id and subscription_id != subscription.subscription_id:
                    logger.error(f"Subscription ID mismatch: {subscription_id} != {subscription.subscription_id}")
                    return False
            
            return True
            
        except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
            logger.warning("Could not validate Microsoft subscription ID - invalid payload")
            return True  # Don't fail on payload parsing errors
```

## Security and Authentication

### Rate Limiting and DDoS Protection
```python
# apps/webhooks/middleware.py
from django.core.cache import cache
from django.http import HttpResponse
import time

class WebhookRateLimitMiddleware:
    """Rate limiting middleware for webhook endpoints"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.path.startswith('/webhooks/'):
            if not self.check_rate_limit(request):
                return HttpResponse(status=429)  # Too Many Requests
        
        response = self.get_response(request)
        return response
    
    def check_rate_limit(self, request, max_requests=100, window_seconds=60):
        """Check if request exceeds rate limit"""
        
        # Use IP address for rate limiting key
        client_ip = self.get_client_ip(request)
        cache_key = f"webhook_rate_limit:{client_ip}"
        
        # Get current request count
        current_requests = cache.get(cache_key, 0)
        
        if current_requests >= max_requests:
            return False
        
        # Increment counter
        cache.set(cache_key, current_requests + 1, window_seconds)
        return True
    
    def get_client_ip(self, request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
```

### CSRF and Security Headers
```python
# apps/webhooks/decorators.py
from functools import wraps
from django.http import HttpResponse
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def webhook_security(view_func):
    """Security decorator for webhook endpoints"""
    
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        
        # Validate Content-Type for POST requests
        if request.method == 'POST':
            content_type = request.content_type
            if content_type not in ['application/json', 'application/x-www-form-urlencoded']:
                logger.warning(f"Invalid Content-Type for webhook: {content_type}")
                return HttpResponse(status=400)
        
        # Validate request size
        if len(request.body) > 10 * 1024:  # 10KB limit
            logger.warning(f"Webhook payload too large: {len(request.body)} bytes")
            return HttpResponse(status=413)  # Payload Too Large
        
        # Add security headers to response
        response = view_func(request, *args, **kwargs)
        
        if hasattr(response, '__setitem__'):
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options'] = 'DENY'
            response['X-XSS-Protection'] = '1; mode=block'
        
        return response
    
    return _wrapped_view
```

## Health Check and Monitoring

### Webhook Health Endpoint
```python
class WebhookHealthView(View):
    """Health check endpoint for webhook infrastructure"""
    
    def get(self, request):
        """Return webhook system health status"""
        from django.db import connection
        from .models import WebhookSubscription, WebhookNotification
        
        health_data = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'checks': {}
        }
        
        try:
            # Database connectivity
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            health_data['checks']['database'] = 'ok'
            
            # Active subscriptions count
            active_subscriptions = WebhookSubscription.objects.filter(status='active').count()
            health_data['checks']['active_subscriptions'] = active_subscriptions
            
            # Recent notification processing
            recent_notifications = WebhookNotification.objects.filter(
                received_at__gte=timezone.now() - timedelta(hours=1)
            ).count()
            health_data['checks']['recent_notifications'] = recent_notifications
            
            # Processing success rate (last 24 hours)
            day_ago = timezone.now() - timedelta(hours=24)
            total_notifications = WebhookNotification.objects.filter(received_at__gte=day_ago).count()
            
            if total_notifications > 0:
                successful_notifications = WebhookNotification.objects.filter(
                    received_at__gte=day_ago,
                    processing_status='completed'
                ).count()
                success_rate = (successful_notifications / total_notifications) * 100
                health_data['checks']['success_rate_24h'] = f"{success_rate:.1f}%"
            else:
                health_data['checks']['success_rate_24h'] = 'no_data'
            
        except Exception as e:
            health_data['status'] = 'unhealthy'
            health_data['error'] = str(e)
            return JsonResponse(health_data, status=503)
        
        return JsonResponse(health_data)
```

## Error Handling and Recovery

### Webhook Processing Error Handling
```python
# apps/webhooks/services/notification_processor.py
import logging
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

class NotificationProcessor:
    """Process webhook notifications with error handling and recovery"""
    
    def process_notification(self, notification):
        """Process a webhook notification with comprehensive error handling"""
        
        try:
            notification.start_processing()
            
            with transaction.atomic():
                if notification.subscription.provider == 'google':
                    self._process_google_notification(notification)
                elif notification.subscription.provider == 'microsoft':
                    self._process_microsoft_notification(notification)
                else:
                    raise ValueError(f"Unsupported provider: {notification.subscription.provider}")
            
            # Mark as completed
            notification.complete_processing(
                calendars_synced=1,
                events_processed=getattr(self, '_events_processed', 0),
                busy_blocks_updated=getattr(self, '_busy_blocks_updated', 0)
            )
            
            # Update subscription health
            notification.subscription.mark_notification_received()
            
        except Exception as e:
            error_message = f"Failed to process notification {notification.id}: {e}"
            logger.error(error_message)
            
            # Determine if we should retry
            should_retry = self._should_retry_notification(notification, e)
            notification.fail_processing(error_message, should_retry)
            
            # Update subscription failure count
            notification.subscription.increment_failure_count()
            
            # If too many failures, consider disabling subscription
            if notification.subscription.failure_count >= 10:
                self._handle_persistent_failures(notification.subscription)
    
    def _should_retry_notification(self, notification, error):
        """Determine if notification should be retried"""
        
        # Don't retry validation errors
        if isinstance(error, (ValueError, KeyError)):
            return False
        
        # Don't retry if already retried too many times
        if notification.retry_count >= 3:
            return False
        
        # Retry database and network errors
        return True
    
    def _handle_persistent_failures(self, subscription):
        """Handle subscriptions with persistent failures"""
        logger.error(f"Subscription {subscription.id} has {subscription.failure_count} consecutive failures")
        
        # Enable polling fallback
        calendar = subscription.calendar
        calendar.fallback_polling_enabled = True
        calendar.save(update_fields=['fallback_polling_enabled'])
        
        # TODO: Send alert to administrators
        # TODO: Consider temporarily suspending subscription
    
    def _process_google_notification(self, notification):
        """Process Google Calendar notification"""
        from .google_handler import GoogleWebhookHandler
        
        handler = GoogleWebhookHandler()
        self._events_processed, self._busy_blocks_updated = handler.process_notification(notification)
    
    def _process_microsoft_notification(self, notification):
        """Process Microsoft Graph notification"""
        from .microsoft_handler import MicrosoftWebhookHandler
        
        handler = MicrosoftWebhookHandler()
        self._events_processed, self._busy_blocks_updated = handler.process_notification(notification)
```

## Testing Framework

### Webhook Endpoint Testing
```python
# apps/webhooks/tests/test_webhook_endpoints.py
import json
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, Mock

from apps.calendars.models import Calendar, CalendarAccount
from apps.webhooks.models import WebhookSubscription, WebhookNotification

class WebhookEndpointTests(TestCase):
    """Test webhook endpoint functionality"""
    
    def setUp(self):
        self.client = Client()
        
        # Create test calendar and subscription
        self.calendar = self.create_test_calendar()
        self.subscription = WebhookSubscription.objects.create(
            calendar=self.calendar,
            provider='google',
            subscription_id='test-subscription-123',
            webhook_url='https://example.com/webhooks/google/test/',
            resource_id=self.calendar.google_calendar_id,
            expires_at=timezone.now() + timedelta(days=7),
            status='active'
        )
    
    def test_google_webhook_valid_request(self):
        """Test valid Google webhook request processing"""
        url = reverse('webhooks:google_webhook', args=[self.calendar.google_calendar_id])
        
        headers = {
            'HTTP_X_GOOG_CHANNEL_ID': self.subscription.subscription_id,
            'HTTP_X_GOOG_RESOURCE_STATE': 'exists',
            'HTTP_X_GOOG_MESSAGE_NUMBER': '123',
            'HTTP_CONTENT_TYPE': 'application/json'
        }
        
        with patch('apps.webhooks.services.notification_processor.NotificationProcessor.process_notification'):
            response = self.client.post(url, data='{}', **headers)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify notification was stored
        notification = WebhookNotification.objects.get(notification_id='123')
        self.assertEqual(notification.subscription, self.subscription)
    
    def test_google_webhook_missing_headers(self):
        """Test Google webhook with missing required headers"""
        url = reverse('webhooks:google_webhook', args=[self.calendar.google_calendar_id])
        
        # Missing X-Goog-Channel-ID header
        headers = {
            'HTTP_X_GOOG_RESOURCE_STATE': 'exists',
            'HTTP_X_GOOG_MESSAGE_NUMBER': '124',
        }
        
        response = self.client.post(url, data='{}', **headers)
        self.assertEqual(response.status_code, 403)  # Validation failed
    
    def test_duplicate_notification_handling(self):
        """Test that duplicate notifications are handled properly"""
        
        # Create existing notification
        WebhookNotification.objects.create(
            subscription=self.subscription,
            notification_id='123',
            headers={},
            payload={}
        )
        
        url = reverse('webhooks:google_webhook', args=[self.calendar.google_calendar_id])
        headers = {
            'HTTP_X_GOOG_CHANNEL_ID': self.subscription.subscription_id,
            'HTTP_X_GOOG_RESOURCE_STATE': 'exists',
            'HTTP_X_GOOG_MESSAGE_NUMBER': '123',  # Same as existing
        }
        
        response = self.client.post(url, data='{}', **headers)
        self.assertEqual(response.status_code, 200)  # Should accept but not reprocess
        
        # Should still only have one notification
        self.assertEqual(WebhookNotification.objects.filter(notification_id='123').count(), 1)
    
    def test_microsoft_webhook_validation_challenge(self):
        """Test Microsoft webhook validation challenge response"""
        url = reverse('webhooks:microsoft_webhook', args=[self.calendar.google_calendar_id])
        
        # Microsoft sends GET request with validationToken
        response = self.client.get(url, {'validationToken': 'test-token-456'})
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'test-token-456')
        self.assertEqual(response['Content-Type'], 'text/plain')
    
    def test_webhook_health_endpoint(self):
        """Test webhook health check endpoint"""
        url = reverse('webhooks:webhook_health')
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        health_data = json.loads(response.content)
        self.assertEqual(health_data['status'], 'healthy')
        self.assertIn('checks', health_data)
        self.assertIn('database', health_data['checks'])
```

## Success Criteria

### Security and Validation
- **100% Request Validation**: All webhook requests properly validated for authenticity
- **Zero Unauthorized Access**: No webhook processing without proper validation
- **Rate Limiting Effective**: Protection against DDoS and abuse

### Reliability and Performance
- **<100ms Response Time**: Webhook endpoints respond within 100ms
- **99.9% Uptime**: Webhook endpoints available and functional
- **Zero Duplicate Processing**: Duplicate notifications properly deduplicated

### Error Handling
- **Graceful Failure Recovery**: Failed notifications retried with exponential backoff
- **Comprehensive Logging**: All webhook activity logged for debugging
- **Automatic Fallback**: Persistent webhook failures trigger polling fallback

This webhook endpoint and validation system provides a secure, reliable foundation for receiving and processing calendar change notifications from Google Calendar and Microsoft Graph APIs.

## Related Documentation

**Prerequisites:**
- **Strategy**: Read [00-webhook-strategy-overview.md](00-webhook-strategy-overview.md) for architectural overview
- **Database**: Implement [01-database-infrastructure.md](01-database-infrastructure.md) for required models

**Next Implementation Steps:**
- **Subscription Lifecycle**: Setup [03-subscription-management.md](03-subscription-management.md) to create and manage webhook subscriptions
- **Sync Integration**: Connect [04-sync-engine-integration.md](04-sync-engine-integration.md) for processing received notifications

**Development & Operations:**
- **Testing**: Follow [05-testing-and-development-strategy.md](05-testing-and-development-strategy.md) for endpoint testing strategies
- **Deployment**: Reference [06-deployment-and-monitoring.md](06-deployment-and-monitoring.md) for production webhook endpoint setup
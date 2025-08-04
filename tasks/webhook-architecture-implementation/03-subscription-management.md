# Subscription Management - Webhook Implementation

## Webhook Architecture Terminology Reference

For consistent terminology across all documents, see [00-webhook-strategy-overview.md](00-webhook-strategy-overview.md#webhook-architecture-terminology).

## Objective

Implement comprehensive webhook subscription lifecycle management for Google Calendar and Microsoft Graph APIs, including creation, renewal, monitoring, and failure recovery.

## Subscription Lifecycle Overview

### Subscription States and Transitions
```
[Calendar Created] → [Create Subscription] → [Active]
                                               ↓
[Active] → [Needs Renewal] → [Renew] → [Active]
    ↓           ↓                         ↑
[Failed] → [Retry/Fallback]               ↑
    ↓                                     ↑
[Suspended] → [Manual Recovery] → [Active]
    ↓
[Expired] → [Cleanup]
```

### Subscription Management Services

#### Core Subscription Manager
```python
# apps/webhooks/services/subscription_manager.py
import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from ..models import WebhookSubscription
from .google_subscription_client import GoogleSubscriptionClient
from .microsoft_subscription_client import MicrosoftSubscriptionClient

logger = logging.getLogger(__name__)

class SubscriptionManager:
    """Manages webhook subscription lifecycle across all providers"""
    
    def __init__(self):
        self.google_client = GoogleSubscriptionClient()
        self.microsoft_client = MicrosoftSubscriptionClient()
        self.provider_clients = {
            'google': self.google_client,
            'microsoft': self.microsoft_client,
        }
    
    def create_subscription_for_calendar(self, calendar):
        """Create webhook subscriptions for a calendar based on provider"""
        
        # Determine provider from calendar account
        provider = self._get_provider_for_calendar(calendar)
        if not provider:
            logger.error(f"Cannot determine provider for calendar {calendar.id}")
            return None
        
        try:
            with transaction.atomic():
                # Deactivate any existing subscriptions
                self._deactivate_existing_subscriptions(calendar, provider)
                
                # Create new subscription
                subscription = self._create_provider_subscription(calendar, provider)
                
                if subscription:
                    # Update calendar webhook settings
                    calendar.webhook_enabled = True
                    calendar.save(update_fields=['webhook_enabled'])
                    
                    logger.info(f"Created webhook subscription {subscription.id} for calendar {calendar.name}")
                
                return subscription
                
        except Exception as e:
            logger.error(f"Failed to create subscription for calendar {calendar.id}: {e}")
            return None
    
    def renew_expiring_subscriptions(self, buffer_hours=24):
        """Renew subscriptions that will expire soon"""
        
        expiring_subscriptions = WebhookSubscription.objects.needing_renewal(buffer_hours)
        
        renewal_results = {
            'attempted': 0,
            'successful': 0,
            'failed': 0,
            'errors': []
        }
        
        for subscription in expiring_subscriptions:
            renewal_results['attempted'] += 1
            
            try:
                success = self.renew_subscription(subscription)
                if success:
                    renewal_results['successful'] += 1
                else:
                    renewal_results['failed'] += 1
                    
            except Exception as e:
                error_msg = f"Failed to renew subscription {subscription.id}: {e}"
                logger.error(error_msg)
                renewal_results['failed'] += 1
                renewal_results['errors'].append(error_msg)
        
        logger.info(f"Subscription renewal: {renewal_results}")
        return renewal_results
    
    def renew_subscription(self, subscription):
        """Renew a specific subscription"""
        
        provider_client = self.provider_clients.get(subscription.provider)
        if not provider_client:
            logger.error(f"No client for provider {subscription.provider}")
            return False
        
        try:
            # Get new expiration time from provider
            new_subscription_data = provider_client.renew_subscription(subscription)
            
            if new_subscription_data:
                # Update subscription in database
                subscription.renew_subscription(new_subscription_data['expires_at'])
                
                # Reset calendar failure streak
                calendar = subscription.calendar
                if calendar.webhook_failure_streak > 0:
                    calendar.webhook_failure_streak = 0
                    calendar.save(update_fields=['webhook_failure_streak'])
                
                logger.info(f"Successfully renewed subscription {subscription.id}")
                return True
            else:
                logger.error(f"Provider returned no data for subscription renewal {subscription.id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to renew subscription {subscription.id}: {e}")
            return False
    
    def cleanup_failed_subscriptions(self, failure_threshold=10, days_failed=7):
        """Clean up subscriptions that have been failing for too long"""
        
        cleanup_cutoff = timezone.now() - timedelta(days=days_failed)
        
        failed_subscriptions = WebhookSubscription.objects.filter(
            failure_count__gte=failure_threshold,
            last_notification_at__lt=cleanup_cutoff,
            status='active'
        )
        
        cleanup_results = {
            'subscriptions_suspended': 0,
            'polling_enabled': 0,
        }
        
        for subscription in failed_subscriptions:
            try:
                with transaction.atomic():
                    # Suspend the subscription
                    subscription.status = 'suspended'
                    subscription.save(update_fields=['status'])
                    
                    # Enable polling fallback
                    calendar = subscription.calendar
                    calendar.fallback_polling_enabled = True
                    calendar.save(update_fields=['fallback_polling_enabled'])
                    
                    cleanup_results['subscriptions_suspended'] += 1
                    cleanup_results['polling_enabled'] += 1
                    
                    logger.info(f"Suspended failing subscription {subscription.id}, enabled polling for calendar {calendar.id}")
                    
            except Exception as e:
                logger.error(f"Failed to cleanup subscription {subscription.id}: {e}")
        
        return cleanup_results
    
    def delete_subscription(self, subscription, reason="Manual deletion"):
        """Delete a webhook subscription"""
        
        provider_client = self.provider_clients.get(subscription.provider)
        if provider_client:
            try:
                # Delete from provider first
                provider_client.delete_subscription(subscription)
                logger.info(f"Deleted subscription {subscription.id} from {subscription.provider}")
            except Exception as e:
                logger.error(f"Failed to delete subscription from provider: {e}")
                # Continue with database deletion even if provider deletion fails
        
        # Delete from database
        subscription.delete()
        logger.info(f"Deleted subscription {subscription.id}: {reason}")
    
    def _get_provider_for_calendar(self, calendar):
        """Determine webhook provider based on calendar account type"""
        
        # For now, assume Google Calendar based on existing codebase
        # This would be enhanced to support Microsoft Graph
        return 'google'
    
    def _deactivate_existing_subscriptions(self, calendar, provider):
        """Deactivate existing subscriptions for calendar/provider"""
        
        existing_subscriptions = WebhookSubscription.objects.filter(
            calendar=calendar,
            provider=provider,
            status='active'
        )
        
        for subscription in existing_subscriptions:
            try:
                self.delete_subscription(subscription, "Replacing with new subscription")
            except Exception as e:
                logger.error(f"Failed to deactivate existing subscription {subscription.id}: {e}")
    
    def _create_provider_subscription(self, calendar, provider):
        """Create subscription with specific provider"""
        
        provider_client = self.provider_clients.get(provider)
        if not provider_client:
            raise ValueError(f"Unsupported provider: {provider}")
        
        # Generate webhook URL
        webhook_url = self._generate_webhook_url(calendar, provider)
        
        # Create subscription with provider
        subscription_data = provider_client.create_subscription(calendar, webhook_url)
        
        if not subscription_data:
            return None
        
        # Store subscription in database
        subscription = WebhookSubscription.objects.create(
            calendar=calendar,
            provider=provider,
            subscription_id=subscription_data['subscription_id'],
            webhook_url=webhook_url,
            resource_id=subscription_data.get('resource_id', calendar.google_calendar_id),
            expires_at=subscription_data['expires_at'],
            status='active',
            provider_metadata=subscription_data.get('metadata', {})
        )
        
        return subscription
    
    def _generate_webhook_url(self, calendar, provider):
        """Generate webhook URL for calendar and provider"""
        
        base_url = settings.WEBHOOK_BASE_URL
        calendar_uuid = calendar.google_calendar_id  # Using as unique identifier
        
        return f"{base_url}/webhooks/{provider}/{calendar_uuid}/"
```

## LLM Operational Procedures

### When to Create Webhook Subscriptions
**TRIGGER CONDITIONS** (AI agents must check these):
1. **New calendar created** with `sync_enabled=True`
2. **Existing calendar enabled** for sync (`sync_enabled` changed to True)
3. **Calendar account reconnected** after OAuth token refresh
4. **Existing subscription expired** or failed beyond repair (failure_count >= 10)

### Subscription Creation Validation Steps
**MANDATORY CHECKS** (execute before creation):
```python
def validate_before_subscription_creation(calendar):
    # 1. Verify calendar has valid OAuth tokens
    if not calendar.calendar_account.is_token_valid():
        logger.error(f"Invalid OAuth tokens for calendar {calendar.id}")
        return False
    
    # 2. Check calendar provider supports webhooks
    if calendar.calendar_account.provider != 'google':
        logger.info(f"Provider {calendar.calendar_account.provider} doesn't support webhooks")
        return False
    
    # 3. Ensure webhook URL is accessible
    webhook_url = generate_webhook_url(calendar)
    if not test_webhook_endpoint_accessibility(webhook_url):
        logger.error(f"Webhook URL {webhook_url} not accessible")
        return False
    
    # 4. Confirm no existing active subscription
    existing = WebhookSubscription.objects.filter(
        calendar=calendar, 
        provider='google', 
        status='active'
    ).exists()
    if existing:
        logger.warning(f"Active subscription already exists for calendar {calendar.id}")
        return False
    
    return True
```

### Subscription Failure Recovery Protocol
**AUTOMATIC RECOVERY** (AI agents must implement):
```python
def handle_subscription_failure(subscription):
    if subscription.failure_count >= 10:
        # Permanent failure - suspend and enable polling
        subscription.status = 'suspended'
        subscription.save(update_fields=['status'])
        
        # Enable polling fallback
        calendar = subscription.calendar
        calendar.fallback_polling_enabled = True
        calendar.save(update_fields=['fallback_polling_enabled'])
        
        logger.error(f"Subscription {subscription.id} permanently failed - enabled polling fallback")
        
    elif subscription.failure_count >= 5:
        # Attempt subscription renewal as recovery
        manager = SubscriptionManager()
        success = manager.renew_subscription(subscription)
        
        if success:
            logger.info(f"Successfully renewed failing subscription {subscription.id}")
        else:
            logger.error(f"Failed to renew subscription {subscription.id}")
```

### Subscription Renewal Decision Logic
**WHEN to renew subscriptions** (AI agents: execute this logic):
```python
def should_renew_subscription(subscription, buffer_hours=24):
    # Check if subscription expires within buffer time
    buffer_time = timezone.now() + timedelta(hours=buffer_hours)
    expires_soon = subscription.expires_at <= buffer_time
    
    # Check if subscription is healthy enough to renew
    is_healthy = subscription.failure_count < 5
    
    # Check if subscription is active
    is_active = subscription.status == 'active'
    
    # Renew if expires soon AND healthy AND active
    return expires_soon and is_healthy and is_active
```

### Error Recovery Decision Matrix
**AUTOMATIC ACTIONS** (AI agents: implement these responses):

| Failure Count | Action | Fallback | Monitoring |
|---------------|--------|-----------|------------|
| 1-4 | Retry subscription operation | None | Log warning |
| 5-9 | Attempt subscription renewal | Enable polling fallback | Send alert |
| 10+ | Suspend subscription permanently | Full polling mode | Page administrator |

### Google Calendar Subscription Client
```python
# apps/webhooks/services/google_subscription_client.py
import logging
from datetime import timedelta
from django.utils import timezone
from googleapiclient.errors import HttpError

from apps.calendars.services.google_calendar_client import GoogleCalendarClient

logger = logging.getLogger(__name__)

class GoogleSubscriptionClient:
    """Manages Google Calendar webhook subscriptions"""
    
    def create_subscription(self, calendar, webhook_url):
        """Create Google Calendar webhook subscription"""
        
        try:
            # Get Google Calendar client for this calendar's account
            google_client = GoogleCalendarClient(calendar.calendar_account)
            service = google_client._get_service()
            
            # Generate unique channel ID
            channel_id = self._generate_channel_id(calendar)
            
            # Set expiration time (Google allows max 7 days for calendar events)
            expiration_time = timezone.now() + timedelta(days=6)  # 6 days for safety buffer
            expiration_timestamp = int(expiration_time.timestamp() * 1000)  # Milliseconds
            
            # Create watch request
            watch_request = {
                'id': channel_id,
                'type': 'web_hook',
                'address': webhook_url,
                'expiration': expiration_timestamp
            }
            
            # Create the subscription
            response = service.events().watch(
                calendarId=calendar.google_calendar_id,
                body=watch_request
            ).execute()
            
            logger.info(f"Created Google webhook subscription for calendar {calendar.id}")
            
            return {
                'subscription_id': channel_id,
                'resource_id': response.get('resourceId'),
                'expires_at': expiration_time,
                'metadata': {
                    'resource_uri': response.get('resourceUri'),
                    'kind': response.get('kind')
                }
            }
            
        except HttpError as e:
            logger.error(f"Google API error creating subscription: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creating Google subscription: {e}")
            return None
    
    def renew_subscription(self, subscription):
        """Renew Google Calendar webhook subscription"""
        
        try:
            # Google doesn't support renewal - must delete and recreate
            calendar = subscription.calendar
            
            # Delete existing subscription
            self.delete_subscription(subscription)
            
            # Create new subscription
            return self.create_subscription(calendar, subscription.webhook_url)
            
        except Exception as e:
            logger.error(f"Failed to renew Google subscription {subscription.id}: {e}")
            return None
    
    def delete_subscription(self, subscription):
        """Delete Google Calendar webhook subscription"""
        
        try:
            # Get Google Calendar client
            google_client = GoogleCalendarClient(subscription.calendar.calendar_account)
            service = google_client._get_service()
            
            # Stop the channel
            stop_request = {
                'id': subscription.subscription_id,
                'resourceId': subscription.provider_metadata.get('resource_id', '')
            }
            
            service.channels().stop(body=stop_request).execute()
            
            logger.info(f"Deleted Google webhook subscription {subscription.subscription_id}")
            
        except HttpError as e:
            if e.resp.status == 404:
                # Subscription already deleted
                logger.info(f"Google subscription {subscription.subscription_id} already deleted")
            else:
                logger.error(f"Google API error deleting subscription: {e}")
                raise
        except Exception as e:
            logger.error(f"Error deleting Google subscription: {e}")
            raise
    
    def _generate_channel_id(self, calendar):
        """Generate unique channel ID for subscription"""
        import uuid
        return f"calendar-sync-{calendar.id}-{uuid.uuid4().hex[:8]}"
```

### Microsoft Graph Subscription Client
```python
# apps/webhooks/services/microsoft_subscription_client.py
import logging
import requests
from datetime import timedelta
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)

class MicrosoftSubscriptionClient:
    """Manages Microsoft Graph webhook subscriptions"""
    
    def __init__(self):
        self.graph_api_base = "https://graph.microsoft.com/v1.0"
    
    def create_subscription(self, calendar, webhook_url):
        """Create Microsoft Graph webhook subscription"""
        
        try:
            # Get access token for calendar account
            access_token = self._get_access_token(calendar.calendar_account)
            if not access_token:
                logger.error(f"No access token for Microsoft calendar {calendar.id}")
                return None
            
            # Set expiration time (Microsoft allows max 4230 minutes ~ 3 days)
            expiration_time = timezone.now() + timedelta(days=2, hours=23)  # Safety margin
            
            # Create subscription request
            subscription_data = {
                "changeType": "created,updated,deleted",
                "notificationUrl": webhook_url,
                "resource": f"/me/calendars/{calendar.google_calendar_id}/events",  # Reusing field
                "expirationDateTime": expiration_time.isoformat(),
                "clientState": self._generate_client_state(calendar)  # For validation
            }
            
            # Make API request
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                f"{self.graph_api_base}/subscriptions",
                json=subscription_data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 201:
                subscription_response = response.json()
                
                logger.info(f"Created Microsoft webhook subscription for calendar {calendar.id}")
                
                return {
                    'subscription_id': subscription_response['id'],
                    'resource_id': subscription_response['resource'],
                    'expires_at': expiration_time,
                    'metadata': {
                        'client_state': subscription_data['clientState'],
                        'change_type': subscription_response['changeType']
                    }
                }
            else:
                logger.error(f"Microsoft API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating Microsoft subscription: {e}")
            return None
    
    def renew_subscription(self, subscription):
        """Renew Microsoft Graph webhook subscription"""
        
        try:
            # Get access token
            access_token = self._get_access_token(subscription.calendar.calendar_account)
            if not access_token:
                return None
            
            # Set new expiration time
            new_expiration = timezone.now() + timedelta(days=2, hours=23)
            
            # Update subscription
            update_data = {
                "expirationDateTime": new_expiration.isoformat()
            }
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.patch(
                f"{self.graph_api_base}/subscriptions/{subscription.subscription_id}",
                json=update_data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Renewed Microsoft subscription {subscription.subscription_id}")
                return {
                    'expires_at': new_expiration
                }
            else:
                logger.error(f"Microsoft renewal error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error renewing Microsoft subscription: {e}")
            return None
    
    def delete_subscription(self, subscription):
        """Delete Microsoft Graph webhook subscription"""
        
        try:
            # Get access token
            access_token = self._get_access_token(subscription.calendar.calendar_account)
            if not access_token:
                logger.warning(f"No access token to delete Microsoft subscription {subscription.subscription_id}")
                return
            
            headers = {
                'Authorization': f'Bearer {access_token}'
            }
            
            response = requests.delete(
                f"{self.graph_api_base}/subscriptions/{subscription.subscription_id}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code in [204, 404]:
                logger.info(f"Deleted Microsoft subscription {subscription.subscription_id}")
            else:
                logger.error(f"Microsoft deletion error: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Error deleting Microsoft subscription: {e}")
            raise
    
    def _get_access_token(self, calendar_account):
        """Get valid access token for Microsoft Graph API"""
        # This would integrate with your existing token management
        # For now, return None since we're focusing on Google Calendar
        return None
    
    def _generate_client_state(self, calendar):
        """Generate client state for validation"""
        import hashlib
        return hashlib.md5(f"calendar-sync-{calendar.id}".encode()).hexdigest()[:16]
```

## Subscription Monitoring and Health Checks

### Subscription Health Monitor
```python
# apps/webhooks/services/subscription_monitor.py
import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q, Count

from ..models import WebhookSubscription, WebhookNotification

logger = logging.getLogger(__name__)

class SubscriptionHealthMonitor:
    """Monitor webhook subscription health and performance"""
    
    def check_subscription_health(self):
        """Perform comprehensive health check on all subscriptions"""
        
        health_report = {
            'timestamp': timezone.now(),
            'total_subscriptions': 0,
            'healthy_subscriptions': 0,
            'unhealthy_subscriptions': 0,
            'expiring_soon': 0,
            'failed_subscriptions': 0,
            'issues': []
        }
        
        # Get all active subscriptions
        subscriptions = WebhookSubscription.objects.filter(status='active')
        health_report['total_subscriptions'] = subscriptions.count()
        
        for subscription in subscriptions:
            issues = self._check_single_subscription_health(subscription)
            
            if issues:
                health_report['unhealthy_subscriptions'] += 1
                health_report['issues'].extend(issues)
            else:
                health_report['healthy_subscriptions'] += 1
        
        # Check for subscriptions expiring soon
        expiring_soon = subscriptions.filter(
            expires_at__lte=timezone.now() + timedelta(hours=24)
        ).count()
        health_report['expiring_soon'] = expiring_soon
        
        # Check for high-failure subscriptions
        failed_subscriptions = subscriptions.filter(failure_count__gte=5).count()
        health_report['failed_subscriptions'] = failed_subscriptions
        
        logger.info(f"Subscription health check: {health_report}")
        return health_report
    
    def _check_single_subscription_health(self, subscription):
        """Check health of individual subscription"""
        
        issues = []
        
        # Check if subscription is expired
        if subscription.is_expired:
            issues.append({
                'subscription_id': subscription.id,
                'type': 'expired',
                'message': f"Subscription {subscription.id} has expired"
            })
        
        # Check if subscription needs renewal soon
        if subscription.needs_renewal(buffer_hours=24):
            issues.append({
                'subscription_id': subscription.id,
                'type': 'expiring_soon',
                'message': f"Subscription {subscription.id} expires within 24 hours"
            })
        
        # Check if subscription is receiving notifications
        if not subscription.is_healthy(max_silence_hours=6):
            issues.append({
                'subscription_id': subscription.id,
                'type': 'no_notifications',
                'message': f"Subscription {subscription.id} hasn't received notifications in >6 hours"
            })
        
        # Check for high failure rate
        if subscription.failure_count >= 5:
            issues.append({
                'subscription_id': subscription.id,
                'type': 'high_failure_rate',
                'message': f"Subscription {subscription.id} has {subscription.failure_count} consecutive failures"
            })
        
        return issues
    
    def get_subscription_metrics(self, hours=24):
        """Get subscription performance metrics"""
        
        since = timezone.now() - timedelta(hours=hours)
        
        # Notification processing metrics
        notification_metrics = WebhookNotification.objects.filter(
            received_at__gte=since
        ).aggregate(
            total_notifications=Count('id'),
            completed_notifications=Count('id', filter=Q(processing_status='completed')),
            failed_notifications=Count('id', filter=Q(processing_status='failed')),
        )
        
        # Calculate success rate
        total = notification_metrics['total_notifications'] or 1  # Avoid division by zero
        success_rate = (notification_metrics['completed_notifications'] / total) * 100
        
        # Subscription status distribution
        subscription_metrics = WebhookSubscription.objects.aggregate(
            total_subscriptions=Count('id'),
            active_subscriptions=Count('id', filter=Q(status='active')),
            failed_subscriptions=Count('id', filter=Q(status='failed')),
            expired_subscriptions=Count('id', filter=Q(status='expired')),
        )
        
        return {
            'time_period_hours': hours,
            'notifications': notification_metrics,
            'success_rate_percent': round(success_rate, 2),
            'subscriptions': subscription_metrics,
            'generated_at': timezone.now()
        }
```

## Management Commands

### Subscription Management Commands
```python
# apps/webhooks/management/commands/manage_subscriptions.py
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.calendars.models import Calendar
from apps.webhooks.services.subscription_manager import SubscriptionManager
from apps.webhooks.services.subscription_monitor import SubscriptionHealthMonitor

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Manage webhook subscriptions'
    
    def add_arguments(self, parser):
        parser.add_argument('action', choices=['create', 'renew', 'cleanup', 'health', 'metrics'])
        parser.add_argument('--calendar-id', type=int, help='Specific calendar ID for create action')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
        parser.add_argument('--hours', type=int, default=24, help='Time period for metrics')
    
    def handle(self, *args, **options):
        manager = SubscriptionManager()
        monitor = SubscriptionHealthMonitor()
        
        if options['action'] == 'create':
            self.handle_create(manager, options)
        elif options['action'] == 'renew':
            self.handle_renew(manager, options)
        elif options['action'] == 'cleanup':
            self.handle_cleanup(manager, options)
        elif options['action'] == 'health':
            self.handle_health_check(monitor)
        elif options['action'] == 'metrics':
            self.handle_metrics(monitor, options)
    
    def handle_create(self, manager, options):
        """Create subscriptions for calendars"""
        
        if options['calendar_id']:
            # Create for specific calendar
            try:
                calendar = Calendar.objects.get(id=options['calendar_id'])
                if options['dry_run']:
                    self.stdout.write(f"Would create subscription for calendar {calendar.name}")
                else:
                    subscription = manager.create_subscription_for_calendar(calendar)
                    if subscription:
                        self.stdout.write(f"Created subscription {subscription.id} for calendar {calendar.name}")
                    else:
                        self.stdout.write(f"Failed to create subscription for calendar {calendar.name}")
            except Calendar.DoesNotExist:
                self.stdout.write(f"Calendar {options['calendar_id']} not found")
        else:
            # Create for all calendars without subscriptions
            calendars = Calendar.objects.filter(
                sync_enabled=True,
                webhook_enabled=True,
                webhook_subscriptions__isnull=True
            )
            
            for calendar in calendars:
                if options['dry_run']:
                    self.stdout.write(f"Would create subscription for calendar {calendar.name}")
                else:
                    subscription = manager.create_subscription_for_calendar(calendar)
                    if subscription:
                        self.stdout.write(f"Created subscription {subscription.id} for calendar {calendar.name}")
    
    def handle_renew(self, manager, options):
        """Renew expiring subscriptions"""
        
        if options['dry_run']:
            from apps.webhooks.models import WebhookSubscription
            expiring = WebhookSubscription.objects.needing_renewal()
            self.stdout.write(f"Would renew {expiring.count()} expiring subscriptions")
        else:
            results = manager.renew_expiring_subscriptions()
            self.stdout.write(f"Renewal results: {results}")
    
    def handle_cleanup(self, manager, options):
        """Cleanup failed subscriptions"""
        
        if options['dry_run']:
            from apps.webhooks.models import WebhookSubscription
            failed = WebhookSubscription.objects.filter(failure_count__gte=10)
            self.stdout.write(f"Would clean up {failed.count()} failed subscriptions")
        else:
            results = manager.cleanup_failed_subscriptions()
            self.stdout.write(f"Cleanup results: {results}")
    
    def handle_health_check(self, monitor):
        """Run subscription health check"""
        
        health_report = monitor.check_subscription_health()
        
        self.stdout.write("=== Subscription Health Report ===")
        self.stdout.write(f"Total subscriptions: {health_report['total_subscriptions']}")
        self.stdout.write(f"Healthy: {health_report['healthy_subscriptions']}")
        self.stdout.write(f"Unhealthy: {health_report['unhealthy_subscriptions']}")
        self.stdout.write(f"Expiring soon: {health_report['expiring_soon']}")
        self.stdout.write(f"High failure rate: {health_report['failed_subscriptions']}")
        
        if health_report['issues']:
            self.stdout.write("\n=== Issues Found ===")
            for issue in health_report['issues']:
                self.stdout.write(f"- {issue['type']}: {issue['message']}")
    
    def handle_metrics(self, monitor, options):
        """Show subscription metrics"""
        
        metrics = monitor.get_subscription_metrics(hours=options['hours'])
        
        self.stdout.write(f"=== Metrics (last {options['hours']} hours) ===")
        self.stdout.write(f"Total notifications: {metrics['notifications']['total_notifications']}")
        self.stdout.write(f"Completed: {metrics['notifications']['completed_notifications']}")
        self.stdout.write(f"Failed: {metrics['notifications']['failed_notifications']}")  
        self.stdout.write(f"Success rate: {metrics['success_rate_percent']}%")
        
        self.stdout.write(f"\nSubscription status:")
        self.stdout.write(f"Active: {metrics['subscriptions']['active_subscriptions']}")
        self.stdout.write(f"Failed: {metrics['subscriptions']['failed_subscriptions']}")
        self.stdout.write(f"Expired: {metrics['subscriptions']['expired_subscriptions']}")
```

### Automated Subscription Maintenance
```python
# apps/webhooks/management/commands/subscription_maintenance.py
from django.core.management.base import BaseCommand
from apps.webhooks.services.subscription_manager import SubscriptionManager

class Command(BaseCommand):
    help = 'Automated subscription maintenance (run via cron)'
    
    def handle(self, *args, **options):
        manager = SubscriptionManager()
        
        # Renew expiring subscriptions
        renewal_results = manager.renew_expiring_subscriptions()
        
        # Cleanup persistently failed subscriptions
        cleanup_results = manager.cleanup_failed_subscriptions()
        
        # Log results
        self.stdout.write(f"Renewed {renewal_results['successful']} subscriptions")
        self.stdout.write(f"Suspended {cleanup_results['subscriptions_suspended']} failed subscriptions")
        
        if renewal_results['failed'] > 0 or cleanup_results['subscriptions_suspended'] > 0:
            # Alert administrators if there are issues
            self.stdout.write("WARNING: Subscription maintenance issues detected")
```

## Integration with Calendar Management

### Calendar Lifecycle Integration
```python
# apps/calendars/signals.py (addition)
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from apps.webhooks.services.subscription_manager import SubscriptionManager
from .models import Calendar

@receiver(post_save, sender=Calendar)
def handle_calendar_saved(sender, instance, created, **kwargs):
    """Handle calendar creation and updates"""
    
    manager = SubscriptionManager()
    
    if created and instance.webhook_enabled:
        # Create webhook subscription for new calendar
        subscription = manager.create_subscription_for_calendar(instance)
        if subscription:
            logger.info(f"Created webhook subscription for new calendar {instance.id}")
        else:
            logger.error(f"Failed to create webhook subscription for calendar {instance.id}")
    
    elif not created:
        # Handle calendar updates
        if instance.webhook_enabled and not instance.get_active_webhook_subscription():
            # Webhook was enabled but no active subscription exists
            manager.create_subscription_for_calendar(instance)
        elif not instance.webhook_enabled and instance.get_active_webhook_subscription():
            # Webhook was disabled - clean up subscription
            subscription = instance.get_active_webhook_subscription()
            if subscription:
                manager.delete_subscription(subscription, "Webhook disabled for calendar")

@receiver(post_delete, sender=Calendar)
def handle_calendar_deleted(sender, instance, **kwargs):
    """Clean up webhook subscriptions when calendar is deleted"""
    
    manager = SubscriptionManager()
    
    # Delete all subscriptions for the calendar
    for subscription in instance.webhook_subscriptions.all():
        try:
            manager.delete_subscription(subscription, "Calendar deleted")
        except Exception as e:
            logger.error(f"Failed to cleanup subscription {subscription.id} for deleted calendar: {e}")
```

## Success Criteria

### Subscription Reliability
- **99.5% Subscription Uptime**: Active subscriptions maintain connectivity
- **<1 Hour Renewal Latency**: Expiring subscriptions renewed before expiration
- **Zero Subscription Gaps**: No periods without active subscriptions for enabled calendars

### Health Monitoring
- **Real-time Health Tracking**: Subscription health monitored continuously
- **Proactive Issue Detection**: Problems identified before they cause failures
- **Automated Recovery**: Failed subscriptions automatically repaired or replaced

### Operational Efficiency
- **Automated Lifecycle Management**: Minimal manual intervention required
- **Comprehensive Logging**: All subscription operations logged for debugging
- **Performance Metrics**: Clear visibility into subscription performance

This subscription management system ensures reliable webhook delivery while providing comprehensive monitoring and automated maintenance capabilities.

## Related Documentation

**Prerequisites:**
- **Strategy**: Read [00-webhook-strategy-overview.md](00-webhook-strategy-overview.md) for architectural context
- **Database**: Implement [01-database-infrastructure.md](01-database-infrastructure.md) for WebhookSubscription models
- **Endpoints**: Setup [02-webhook-endpoints-and-validation.md](02-webhook-endpoints-and-validation.md) for webhook receivers

**Next Implementation Steps:**
- **Sync Processing**: Connect [04-sync-engine-integration.md](04-sync-engine-integration.md) to process webhook notifications
- **Testing**: Follow [05-testing-and-development-strategy.md](05-testing-and-development-strategy.md) for subscription testing

**Operations:**
- **Deployment**: Reference [06-deployment-and-monitoring.md](06-deployment-and-monitoring.md) for subscription monitoring setup
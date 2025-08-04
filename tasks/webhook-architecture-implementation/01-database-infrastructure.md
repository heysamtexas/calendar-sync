# Database Infrastructure - Webhook Implementation

## 🤖 AI AGENT QUICK START

> **Hey AI Agent!** 👋 You're about to implement webhook database models.
> 
> **Your Mission**: Create database infrastructure for webhook subscriptions and notifications
> **Key Models**: `WebhookSubscription` (tracks webhook channels) + `WebhookNotification` (logs incoming webhooks)
> **Success Criteria**: Models support subscription lifecycle + health monitoring + notification processing
> **Critical Fields**: See [🔧 AI Agent Essential Fields](#🔧-ai-agent-essential-fields) below
> 
> **Next Action**: Jump to [🤖 AI Agent Database Protocol](#🤖-ai-agent-database-protocol)

## 🤖 AI AGENT DATABASE PROTOCOL

> **Hey AI Agent!** 👋 These are YOUR database implementation instructions.

### 🔧 AI AGENT ESSENTIAL FIELDS

**AI Agent, these fields are MANDATORY for WebhookSubscription model:**

#### 🚨 Core Required Fields (AI Agent: Include These)
- `calendar`: ForeignKey to Calendar (MANDATORY - links subscription to specific calendar)
- `provider`: Choice field ('google'|'microsoft') (MANDATORY - determines webhook provider)  
- `subscription_id`: Unique provider identifier (MANDATORY - provider's webhook channel ID)
- `expires_at`: Subscription expiration time (MANDATORY - when subscription becomes invalid)
- `status`: Current subscription state (MANDATORY - 'active'|'expired'|'failed'|'suspended')

#### 📊 Health Monitoring Fields (AI Agent: Update During Processing)
- `last_notification_at`: Timestamp of last webhook received (update on each webhook)
- `failure_count`: Consecutive processing failures (auto-increment on failure, reset on success)
- `last_renewal_at`: When subscription was last renewed (update during renewal)

### 🔧 AI AGENT PROCESSING COMMANDS

**AI Agent, use these exact method calls:**

```python
# AI Agent: When webhook notification arrives
subscription.mark_notification_received()  # Updates last_notification_at

# AI Agent: When webhook processing fails  
subscription.increment_failure_count()     # Tracks consecutive failures

# AI Agent: When renewing subscription
subscription.renew_subscription(new_expiry_datetime)  # Resets health metrics
```

### ✅ AI AGENT VALIDATION PROTOCOL

**AI Agent, execute this validation BEFORE processing any webhook:**

```python
# AI Agent: Subscription health check sequence
def validate_subscription_health(subscription):
    # Check 1: Subscription not expired
    if subscription.is_expired:
        logger.warning("Subscription expired - cannot process")
        return False
        
    # Check 2: Subscription not failing too much  
    if subscription.failure_count >= 5:
        logger.warning("Subscription unhealthy - enabling polling fallback")
        enable_polling_fallback(subscription.calendar)
        return False

    # Check 3: Subscription is active
    if subscription.status != 'active':
        logger.warning("Subscription not active - cannot process")
        return False
    
    return True  # Safe to process webhook
```

### 🤖 AI AGENT SUCCESS VALIDATION

**AI Agent, verify these conditions after database setup:**
- [ ] WebhookSubscription model created with all mandatory fields
- [ ] WebhookNotification model created for logging incoming webhooks
- [ ] Database migrations applied successfully: `python manage.py migrate`
- [ ] Models can be imported: `from apps.webhooks.models import WebhookSubscription`
- [ ] Foreign key relationships work: `subscription.calendar` returns Calendar instance

## Webhook Architecture Terminology Reference

For consistent terminology across all documents, see [00-webhook-strategy-overview.md](00-webhook-strategy-overview.md#webhook-architecture-terminology).

## Objective

Design and implement database models and infrastructure to support webhook-driven calendar synchronization, including subscription management, webhook notification logging, and integration with existing calendar models.

## Database Schema Design

### New Models for Webhook Support

#### WebhookSubscription Model
```python
# apps/webhooks/models.py
class WebhookSubscription(models.Model):
    """Manages webhook subscriptions for calendar providers"""
    
    PROVIDER_CHOICES = [
        ('google', 'Google Calendar'),
        ('microsoft', 'Microsoft Graph'),
        ('apple', 'Apple iCloud'),  # Future support
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('failed', 'Failed'),
        ('suspended', 'Suspended'),
    ]
    
    # Core subscription data
    calendar = models.ForeignKey(
        'calendars.Calendar', 
        on_delete=models.CASCADE, 
        related_name='webhook_subscriptions'
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    subscription_id = models.CharField(
        max_length=255, 
        unique=True, 
        help_text="Provider's unique subscription identifier"
    )
    
    # Webhook configuration
    webhook_url = models.URLField(
        help_text="HTTPS endpoint for receiving webhook notifications"
    )
    resource_id = models.CharField(
        max_length=255,
        help_text="Resource identifier from provider (e.g., calendar ID)"
    )
    
    # Subscription lifecycle
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="When this subscription expires"
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='active'
    )
    
    # Health monitoring
    last_notification_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When we last received a webhook notification"
    )
    last_renewal_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When subscription was last renewed"
    )
    failure_count = models.PositiveIntegerField(
        default=0,
        help_text="Consecutive webhook processing failures"
    )
    
    # Provider-specific metadata
    provider_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Provider-specific subscription data"
    )
    
    class Meta:
        unique_together = ['calendar', 'provider']
        indexes = [
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['last_notification_at']),
        ]
    
    def __str__(self):
        return f"{self.calendar.name} - {self.provider} webhook"
    
    @property
    def is_expired(self):
        """Check if subscription has expired"""
        return timezone.now() >= self.expires_at
    
    @property
    def needs_renewal(self, buffer_hours=24):
        """Check if subscription needs renewal soon"""
        buffer_time = timezone.now() + timedelta(hours=buffer_hours)
        return buffer_time >= self.expires_at
    
    @property 
    def is_healthy(self, max_silence_hours=6):
        """Check if subscription is receiving notifications regularly"""
        if not self.last_notification_at:
            return False
        
        silence_threshold = timezone.now() - timedelta(hours=max_silence_hours)
        return self.last_notification_at >= silence_threshold
    
    def mark_notification_received(self):
        """Update last notification timestamp"""
        self.last_notification_at = timezone.now()
        self.failure_count = 0  # Reset failure count on success
        self.save(update_fields=['last_notification_at', 'failure_count'])
    
    def increment_failure_count(self):
        """Increment failure count for monitoring"""
        self.failure_count = models.F('failure_count') + 1
        self.save(update_fields=['failure_count'])
    
    def renew_subscription(self, new_expiry):
        """Update subscription renewal information"""
        self.expires_at = new_expiry
        self.last_renewal_at = timezone.now()
        self.status = 'active'
        self.failure_count = 0
        self.save(update_fields=['expires_at', 'last_renewal_at', 'status', 'failure_count'])
```


#### WebhookNotification Model
```python
class WebhookNotification(models.Model):
    """Logs all webhook notifications received"""
    
    PROCESSING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
    ]
    
    # Core notification data
    subscription = models.ForeignKey(
        WebhookSubscription, 
        on_delete=models.CASCADE, 
        related_name='notifications'
    )
    notification_id = models.CharField(
        max_length=255,
        help_text="Unique notification ID from headers"
    )
    
    # Request details
    received_at = models.DateTimeField(auto_now_add=True)
    headers = models.JSONField(
        help_text="HTTP headers from webhook request"
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Request body/payload data"
    )
    
    # Processing tracking
    processing_status = models.CharField(
        max_length=20,
        choices=PROCESSING_STATUS_CHOICES,
        default='pending'
    )
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_completed_at = models.DateTimeField(null=True, blank=True)
    processing_time_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Processing time in milliseconds"
    )
    
    # Error handling
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    
    # Sync results
    calendars_synced = models.PositiveIntegerField(default=0)
    events_processed = models.PositiveIntegerField(default=0)
    busy_blocks_updated = models.PositiveIntegerField(default=0)
    
    class Meta:
        indexes = [
            models.Index(fields=['received_at']),
            models.Index(fields=['processing_status']),
            models.Index(fields=['subscription', 'received_at']),
        ]
        # Prevent duplicate processing of same notification
        unique_together = ['subscription', 'notification_id']
    
    def __str__(self):
        return f"Webhook notification {self.notification_id} - {self.processing_status}"
    
    def start_processing(self):
        """Mark notification as being processed"""
        self.processing_status = 'processing'
        self.processing_started_at = timezone.now()
        self.save(update_fields=['processing_status', 'processing_started_at'])
    
    def complete_processing(self, calendars_synced=0, events_processed=0, busy_blocks_updated=0):
        """Mark notification processing as completed"""
        self.processing_status = 'completed'
        self.processing_completed_at = timezone.now()
        
        # Calculate processing time
        if self.processing_started_at:
            delta = self.processing_completed_at - self.processing_started_at
            self.processing_time_ms = int(delta.total_seconds() * 1000)
        
        # Update sync results
        self.calendars_synced = calendars_synced
        self.events_processed = events_processed
        self.busy_blocks_updated = busy_blocks_updated
        
        self.save(update_fields=[
            'processing_status', 'processing_completed_at', 'processing_time_ms',
            'calendars_synced', 'events_processed', 'busy_blocks_updated'
        ])
    
    def fail_processing(self, error_message, should_retry=True):
        """Mark notification processing as failed"""
        self.processing_status = 'failed'
        self.processing_completed_at = timezone.now()
        self.error_message = error_message
        
        if should_retry and self.retry_count < 3:
            self.processing_status = 'retrying'
            self.retry_count += 1
            # Exponential backoff: 1min, 5min, 15min
            retry_delays = [1, 5, 15]
            delay_minutes = retry_delays[min(self.retry_count - 1, len(retry_delays) - 1)]
            self.next_retry_at = timezone.now() + timedelta(minutes=delay_minutes)
        
        self.save(update_fields=[
            'processing_status', 'processing_completed_at', 'error_message',
            'retry_count', 'next_retry_at'
        ])
```

### Enhanced Calendar Model Integration

#### Calendar Model Extensions
```python
# Extensions to existing apps/calendars/models.py Calendar model
class Calendar(models.Model):
    # ... existing fields ...
    
    # Webhook integration fields
    webhook_enabled = models.BooleanField(
        default=True,
        help_text="Enable webhook notifications for this calendar"
    )
    webhook_last_activity = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last webhook notification received"
    )
    fallback_polling_enabled = models.BooleanField(
        default=True,
        help_text="Enable polling fallback when webhooks fail"
    )
    last_polling_sync = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time polling sync was performed"
    )
    
    # Webhook health metrics
    webhook_failure_streak = models.PositiveIntegerField(
        default=0,
        help_text="Consecutive webhook processing failures"
    )
    last_webhook_failure = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When last webhook failure occurred"
    )
    
    def get_active_webhook_subscription(self, provider=None):
        """Get active webhook subscription for this calendar"""
        query = self.webhook_subscriptions.filter(status='active')
        
        if provider:
            query = query.filter(provider=provider)
        
        return query.first()
    
    def has_healthy_webhook(self, max_silence_hours=6):
        """Check if calendar has healthy webhook subscription"""
        subscription = self.get_active_webhook_subscription()
        return subscription and subscription.is_healthy(max_silence_hours)
    
    def needs_polling_fallback(self):
        """Determine if calendar needs polling fallback"""
        if not self.fallback_polling_enabled:
            return False
        
        # No webhook subscription
        if not self.get_active_webhook_subscription():
            return True
        
        # Webhook subscription is unhealthy
        if not self.has_healthy_webhook():
            return True
        
        # High failure rate
        if self.webhook_failure_streak >= 3:
            return True
        
        return False
    
    def update_webhook_activity(self):
        """Update webhook activity timestamp"""
        self.webhook_last_activity = timezone.now()
        self.webhook_failure_streak = 0
        self.save(update_fields=['webhook_last_activity', 'webhook_failure_streak'])
    
    def increment_webhook_failures(self):
        """Increment webhook failure counter"""
        self.webhook_failure_streak = models.F('webhook_failure_streak') + 1
        self.last_webhook_failure = timezone.now()
        self.save(update_fields=['webhook_failure_streak', 'last_webhook_failure'])
```

### Database Migration Strategy

#### Migration 001: Create Webhook Models
```python
# apps/webhooks/migrations/0001_initial.py
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    
    dependencies = [
        ('calendars', '0003_add_meeting_invite_field'),
    ]
    
    operations = [
        migrations.CreateModel(
            name='WebhookSubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('provider', models.CharField(choices=[('google', 'Google Calendar'), ('microsoft', 'Microsoft Graph'), ('apple', 'Apple iCloud')], max_length=20)),
                ('subscription_id', models.CharField(help_text="Provider's unique subscription identifier", max_length=255, unique=True)),
                ('webhook_url', models.URLField(help_text='HTTPS endpoint for receiving webhook notifications')),
                ('resource_id', models.CharField(help_text='Resource identifier from provider (e.g., calendar ID)', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(help_text='When this subscription expires')),
                ('status', models.CharField(choices=[('active', 'Active'), ('expired', 'Expired'), ('failed', 'Failed'), ('suspended', 'Suspended')], default='active', max_length=20)),
                ('last_notification_at', models.DateTimeField(blank=True, help_text='When we last received a webhook notification', null=True)),
                ('last_renewal_at', models.DateTimeField(blank=True, help_text='When subscription was last renewed', null=True)),
                ('failure_count', models.PositiveIntegerField(default=0, help_text='Consecutive webhook processing failures')),
                ('provider_metadata', models.JSONField(blank=True, default=dict, help_text='Provider-specific subscription data')),
                ('calendar', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='webhook_subscriptions', to='calendars.calendar')),
            ],
            options={
                'unique_together': {('calendar', 'provider')},
            },
        ),
        
        migrations.CreateModel(
            name='WebhookNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('notification_id', models.CharField(help_text='Unique notification ID from headers', max_length=255)),
                ('received_at', models.DateTimeField(auto_now_add=True)),
                ('headers', models.JSONField(help_text='HTTP headers from webhook request')),
                ('payload', models.JSONField(blank=True, default=dict, help_text='Request body/payload data')),
                ('processing_status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed'), ('retrying', 'Retrying')], default='pending', max_length=20)),
                ('processing_started_at', models.DateTimeField(blank=True, null=True)),
                ('processing_completed_at', models.DateTimeField(blank=True, null=True)),
                ('processing_time_ms', models.PositiveIntegerField(blank=True, help_text='Processing time in milliseconds', null=True)),
                ('error_message', models.TextField(blank=True)),
                ('retry_count', models.PositiveIntegerField(default=0)),
                ('next_retry_at', models.DateTimeField(blank=True, null=True)),
                ('calendars_synced', models.PositiveIntegerField(default=0)),
                ('events_processed', models.PositiveIntegerField(default=0)),
                ('busy_blocks_updated', models.PositiveIntegerField(default=0)),
                ('subscription', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='webhooks.webhooksubscription')),
            ],
            options={
                'unique_together': {('subscription', 'notification_id')},
            },
        ),
        
        # Create indexes
        migrations.AddIndex(
            model_name='webhooksubscription',
            index=models.Index(fields=['provider', 'status'], name='webhooks_webhooksubscription_provider_status_idx'),
        ),
        migrations.AddIndex(
            model_name='webhooksubscription',
            index=models.Index(fields=['expires_at'], name='webhooks_webhooksubscription_expires_at_idx'),
        ),
        migrations.AddIndex(
            model_name='webhooksubscription',
            index=models.Index(fields=['last_notification_at'], name='webhooks_webhooksubscription_last_notification_at_idx'),
        ),
        migrations.AddIndex(
            model_name='webhooknotification',
            index=models.Index(fields=['received_at'], name='webhooks_webhooknotification_received_at_idx'),
        ),
        migrations.AddIndex(
            model_name='webhooknotification',
            index=models.Index(fields=['processing_status'], name='webhooks_webhooknotification_processing_status_idx'),
        ),
        migrations.AddIndex(
            model_name='webhooknotification',
            index=models.Index(fields=['subscription', 'received_at'], name='webhooks_webhooknotification_subscription_received_at_idx'),
        ),
    ]
```

#### Migration 002: Extend Calendar Model
```python
# apps/calendars/migrations/0004_add_webhook_fields.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('calendars', '0003_add_meeting_invite_field'),
        ('webhooks', '0001_initial'),
    ]
    
    operations = [
        migrations.AddField(
            model_name='calendar',
            name='webhook_enabled',
            field=models.BooleanField(default=True, help_text='Enable webhook notifications for this calendar'),
        ),
        migrations.AddField(
            model_name='calendar',
            name='webhook_last_activity',
            field=models.DateTimeField(blank=True, help_text='Last webhook notification received', null=True),
        ),
        migrations.AddField(
            model_name='calendar',
            name='fallback_polling_enabled',
            field=models.BooleanField(default=True, help_text='Enable polling fallback when webhooks fail'),
        ),
        migrations.AddField(
            model_name='calendar',
            name='last_polling_sync',
            field=models.DateTimeField(blank=True, help_text='Last time polling sync was performed', null=True),
        ),
        migrations.AddField(
            model_name='calendar',
            name='webhook_failure_streak',
            field=models.PositiveIntegerField(default=0, help_text='Consecutive webhook processing failures'),
        ),
        migrations.AddField(
            model_name='calendar',
            name='last_webhook_failure',
            field=models.DateTimeField(blank=True, help_text='When last webhook failure occurred', null=True),
        ),
    ]
```

## Database Query Optimization

### Efficient Query Patterns

#### Subscription Health Monitoring
```python
# apps/webhooks/managers.py
class WebhookSubscriptionManager(models.Manager):
    
    def needing_renewal(self, buffer_hours=24):
        """Get subscriptions that need renewal soon"""
        buffer_time = timezone.now() + timedelta(hours=buffer_hours)
        return self.filter(
            status='active',
            expires_at__lte=buffer_time
        ).select_related('calendar', 'calendar__calendar_account')
    
    def unhealthy_subscriptions(self, max_silence_hours=6):
        """Get subscriptions that haven't received notifications recently"""
        silence_threshold = timezone.now() - timedelta(hours=max_silence_hours)
        return self.filter(
            status='active',
            provider__in=['google', 'microsoft'],  # Only providers that should send webhooks
            last_notification_at__lt=silence_threshold
        ).select_related('calendar')
    
    def expired_subscriptions(self):
        """Get expired subscriptions for cleanup"""
        return self.filter(
            expires_at__lt=timezone.now(),
            status='active'
        )
    
    def high_failure_subscriptions(self, failure_threshold=5):
        """Get subscriptions with high failure rates"""
        return self.filter(
            failure_count__gte=failure_threshold,
            status='active'
        ).select_related('calendar')

class WebhookNotificationManager(models.Manager):
    
    def pending_processing(self):
        """Get notifications waiting to be processed"""
        return self.filter(processing_status='pending').order_by('received_at')
    
    def failed_retryable(self):
        """Get failed notifications that should be retried"""
        return self.filter(
            processing_status='retrying',
            next_retry_at__lte=timezone.now(),
            retry_count__lt=3
        ).order_by('received_at')
    
    def processing_metrics(self, hours=24):
        """Get processing metrics for monitoring"""
        since = timezone.now() - timedelta(hours=hours)
        
        return self.filter(received_at__gte=since).aggregate(
            total_notifications=models.Count('id'),
            completed_notifications=models.Count('id', filter=models.Q(processing_status='completed')),
            failed_notifications=models.Count('id', filter=models.Q(processing_status='failed')),
            avg_processing_time=models.Avg('processing_time_ms'),
            total_calendars_synced=models.Sum('calendars_synced'),
            total_events_processed=models.Sum('events_processed'),
        )
```

### Database Performance Considerations

#### Index Strategy
```sql
-- Critical indexes for webhook performance
CREATE INDEX CONCURRENTLY webhook_subscription_health_idx 
ON webhooks_webhooksubscription (provider, status, last_notification_at);

CREATE INDEX CONCURRENTLY webhook_notification_processing_idx 
ON webhooks_webhooknotification (processing_status, received_at);

CREATE INDEX CONCURRENTLY webhook_notification_retry_idx 
ON webhooks_webhooknotification (processing_status, next_retry_at) 
WHERE processing_status = 'retrying';

CREATE INDEX CONCURRENTLY calendar_webhook_health_idx 
ON calendars_calendar (webhook_enabled, webhook_last_activity);
```

#### Query Performance Guidelines
1. **Always use select_related()** for subscription queries that need calendar data
2. **Filter by status first** before other conditions for optimal index usage
3. **Use bulk operations** for subscription renewals and notification processing
4. **Implement query result caching** for health monitoring dashboards
5. **Archive old notifications** to maintain query performance

## Data Integrity and Consistency

### Webhook Subscription Lifecycle
```python
# apps/webhooks/services/subscription_lifecycle.py
class SubscriptionLifecycleManager:
    
    def create_subscription(self, calendar, provider, subscription_data):
        """Create new webhook subscription with proper validation"""
        with transaction.atomic():
            # Deactivate any existing subscriptions for this calendar/provider
            existing = WebhookSubscription.objects.filter(
                calendar=calendar,
                provider=provider,
                status='active'
            )
            existing.update(status='suspended')
            
            # Create new subscription
            subscription = WebhookSubscription.objects.create(
                calendar=calendar,
                provider=provider,
                **subscription_data
            )
            
            # Update calendar webhook settings
            calendar.webhook_enabled = True
            calendar.save(update_fields=['webhook_enabled'])
            
            return subscription
    
    def renew_subscription(self, subscription, new_expiry_data):
        """Renew existing subscription with atomic update"""
        with transaction.atomic():
            subscription.renew_subscription(new_expiry_data['expires_at'])
            
            # Reset any failure streaks on successful renewal
            if subscription.calendar.webhook_failure_streak > 0:
                subscription.calendar.webhook_failure_streak = 0
                subscription.calendar.save(update_fields=['webhook_failure_streak'])
    
    def deactivate_subscription(self, subscription, reason="Manual deactivation"):
        """Safely deactivate subscription"""
        with transaction.atomic():
            subscription.status = 'suspended'
            subscription.save(update_fields=['status'])
            
            # Log deactivation
            logger.info(f"Deactivated webhook subscription {subscription.id}: {reason}")
            
            # Enable polling fallback
            calendar = subscription.calendar
            calendar.fallback_polling_enabled = True
            calendar.save(update_fields=['fallback_polling_enabled'])
```

### Data Cleanup Strategy
```python
# apps/webhooks/management/commands/cleanup_webhook_data.py
class Command(BaseCommand):
    help = 'Clean up old webhook notifications and expired subscriptions'
    
    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30, help='Keep notifications newer than N days')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted')
    
    def handle(self, *args, **options):
        cutoff_date = timezone.now() - timedelta(days=options['days'])
        
        # Clean up old completed notifications
        old_notifications = WebhookNotification.objects.filter(
            processing_status='completed',
            processing_completed_at__lt=cutoff_date
        )
        
        if options['dry_run']:
            self.stdout.write(f"Would delete {old_notifications.count()} old notifications")
        else:
            deleted_count = old_notifications.delete()[0]
            self.stdout.write(f"Deleted {deleted_count} old notifications")
        
        # Clean up expired subscriptions
        expired_subscriptions = WebhookSubscription.objects.filter(
            status='expired',
            expires_at__lt=cutoff_date
        )
        
        if options['dry_run']:
            self.stdout.write(f"Would delete {expired_subscriptions.count()} expired subscriptions")
        else:
            deleted_count = expired_subscriptions.delete()[0]
            self.stdout.write(f"Deleted {deleted_count} expired subscriptions")
```

## Success Criteria

### Database Performance
- **Query Response Time**: <100ms for webhook subscription lookups
- **Notification Processing**: <500ms for webhook notification database operations
- **Health Monitoring**: <1s for subscription health checks across all calendars

### Data Integrity
- **Zero Orphaned Subscriptions**: All subscriptions linked to active calendars
- **Consistent State Tracking**: Webhook activity timestamps always updated
- **Reliable Cleanup**: Old data cleaned without affecting active subscriptions

### Scalability
- **Support 10x Growth**: Database design handles 10x more subscriptions efficiently
- **Index Performance**: All queries use appropriate indexes
- **Storage Efficiency**: Notification data archived/cleaned regularly

This database infrastructure provides the foundation for reliable webhook-driven calendar synchronization while maintaining data integrity and performance at scale.

## Related Documentation

**Prerequisites:**
- **Strategy**: Read [00-webhook-strategy-overview.md](00-webhook-strategy-overview.md) for architectural context

**Next Implementation Steps:**  
- **Endpoints**: Implement [02-webhook-endpoints-and-validation.md](02-webhook-endpoints-and-validation.md) for webhook receivers
- **Lifecycle**: Setup [03-subscription-management.md](03-subscription-management.md) for subscription management
- **Integration**: Connect [04-sync-engine-integration.md](04-sync-engine-integration.md) for sync processing

**Development & Operations:**
- **Testing**: Follow [05-testing-and-development-strategy.md](05-testing-and-development-strategy.md) for testing these models
- **Deployment**: Reference [06-deployment-and-monitoring.md](06-deployment-and-monitoring.md) for production database setup
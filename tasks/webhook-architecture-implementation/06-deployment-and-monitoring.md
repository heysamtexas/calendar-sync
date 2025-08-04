# Deployment and Monitoring - Webhook Implementation

## Webhook Architecture Terminology Reference

For consistent terminology across all documents, see [00-webhook-strategy-overview.md](00-webhook-strategy-overview.md#webhook-architecture-terminology).

## Objective

Establish comprehensive deployment procedures and monitoring systems for webhook-driven calendar synchronization, ensuring reliable operation, proactive issue detection, and seamless production deployment.

## Deployment Prerequisites

### Infrastructure Requirements

#### HTTPS and Domain Configuration
```bash
# Production domain requirements
# Required: Valid SSL certificate for webhook endpoints
# Required: Domain verification with Google/Microsoft

# Example nginx configuration for webhook endpoints
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /path/to/ssl/certificate.crt;
    ssl_certificate_key /path/to/ssl/private.key;
    
    # Webhook-specific location
    location /webhooks/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Webhook-specific settings
        proxy_read_timeout 30s;
        proxy_connect_timeout 10s;
        client_max_body_size 10k;  # Limit webhook payload size
        
        # Rate limiting for webhook endpoints
        limit_req zone=webhook_limit burst=100 nodelay;
    }
}

# Rate limiting configuration
http {
    limit_req_zone $remote_addr zone=webhook_limit:10m rate=100r/m;
}
```

#### Environment Configuration
```python
# settings/production.py
import os
from .base import *

# Webhook-specific settings
WEBHOOK_BASE_URL = os.environ.get('WEBHOOK_BASE_URL', 'https://your-domain.com')
WEBHOOK_RATE_LIMIT_ENABLED = True
WEBHOOK_RATE_LIMIT_MAX_REQUESTS = 100
WEBHOOK_RATE_LIMIT_WINDOW_SECONDS = 60

# Security settings for webhooks
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_TLS = True

# Database settings optimized for webhook performance
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'OPTIONS': {
            'sslmode': 'require',
        },
        'CONN_MAX_AGE': 600,  # Connection pooling for webhook performance
    }
}

# Cache configuration for webhook rate limiting
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'calendar_sync',
        'TIMEOUT': 300,
    }
}

# Logging configuration for webhook monitoring
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'webhook': {
            'format': '[{asctime}] {levelname} webhook.{name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'webhook_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/calendar_sync/webhooks.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'webhook',
        },
        'webhook_errors': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/calendar_sync/webhook_errors.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'webhook',
        },
    },
    'loggers': {
        'apps.webhooks': {
            'handlers': ['webhook_file', 'webhook_errors'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.calendars.services.sync_engine': {
            'handlers': ['webhook_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

### Domain Verification

#### Google Calendar Domain Verification
```python
# apps/webhooks/management/commands/verify_google_domain.py
from django.core.management.base import BaseCommand
from django.conf import settings
import requests

class Command(BaseCommand):
    help = 'Verify domain ownership with Google for webhook subscriptions'
    
    def add_arguments(self, parser):
        parser.add_argument('--domain', required=True, help='Domain to verify')
        parser.add_argument('--verification-file', help='Path to verification file')
    
    def handle(self, *args, **options):
        domain = options['domain']
        
        # Step 1: Download verification file from Google Search Console
        verification_url = f"https://www.google.com/webmasters/verification/{domain}"
        
        self.stdout.write("Domain verification steps:")
        self.stdout.write(f"1. Visit: {verification_url}")
        self.stdout.write("2. Download the HTML verification file")
        self.stdout.write(f"3. Place it at: https://{domain}/google[verification-code].html")
        self.stdout.write("4. Verify ownership in Google Search Console")
        self.stdout.write("5. Test webhook URL accessibility")
        
        # Test webhook endpoint accessibility
        webhook_test_url = f"https://{domain}/webhooks/health/"
        
        try:
            response = requests.get(webhook_test_url, timeout=10)
            if response.status_code == 200:
                self.stdout.write(f"✅ Webhook endpoint accessible: {webhook_test_url}")
            else:
                self.stdout.write(f"❌ Webhook endpoint error: {response.status_code}")
        except Exception as e:
            self.stdout.write(f"❌ Webhook endpoint unreachable: {e}")
```

## Deployment Strategy

### Phase 1: Infrastructure Deployment

#### Docker Configuration
```dockerfile
# Dockerfile for webhook-enabled application
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    redis-tools \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create log directory for webhooks
RUN mkdir -p /var/log/calendar_sync

# Expose webhook port
EXPOSE 8000

# Health check for webhook endpoints
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/webhooks/health/ || exit 1

# Start application with webhook support
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "2", "calendar_sync.wsgi:application"]
```

#### Docker Compose for Development
```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DEBUG=False
      - WEBHOOK_BASE_URL=https://your-domain.com
      - DB_HOST=db
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    volumes:
      - ./logs:/var/log/calendar_sync
    restart: unless-stopped
  
  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=calendar_sync
      - POSTGRES_USER=calendar_sync
      - POSTGRES_PASSWORD=secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
  
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    restart: unless-stopped
  
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - app
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

### Phase 2: Gradual Webhook Rollout

#### Feature Flag Implementation
```python
# apps/webhooks/utils.py
from django.conf import settings
from django.core.cache import cache

class WebhookFeatureFlags:
    """Feature flags for gradual webhook rollout"""
    
    @staticmethod
    def is_webhook_enabled_for_calendar(calendar):
        """Check if webhooks are enabled for specific calendar"""
        
        # Global webhook disable
        if not getattr(settings, 'WEBHOOKS_ENABLED', True):
            return False
        
        # Per-calendar rollout based on calendar ID
        rollout_percentage = getattr(settings, 'WEBHOOK_ROLLOUT_PERCENTAGE', 100)
        
        if rollout_percentage >= 100:
            return True
        
        # Use calendar ID for consistent rollout
        calendar_hash = hash(str(calendar.id)) % 100
        return calendar_hash < rollout_percentage
    
    @staticmethod
    def is_webhook_enabled_for_user(user):
        """Check if webhooks are enabled for specific user"""
        
        # Opt-in list for early adopters
        early_adopters = getattr(settings, 'WEBHOOK_EARLY_ADOPTERS', [])
        if user.email in early_adopters:
            return True
        
        # Gradual rollout by user ID
        rollout_percentage = getattr(settings, 'WEBHOOK_USER_ROLLOUT_PERCENTAGE', 0)
        user_hash = hash(str(user.id)) % 100
        return user_hash < rollout_percentage

# Enhanced subscription manager with feature flags
class FeatureFlaggedSubscriptionManager(SubscriptionManager):
    """Subscription manager with feature flag support"""
    
    def create_subscription_for_calendar(self, calendar):
        """Create subscription only if feature flag allows"""
        
        if not WebhookFeatureFlags.is_webhook_enabled_for_calendar(calendar):
            logger.info(f"Webhooks disabled for calendar {calendar.id} by feature flag")
            return None
        
        if not WebhookFeatureFlags.is_webhook_enabled_for_user(calendar.calendar_account.user):
            logger.info(f"Webhooks disabled for user {calendar.calendar_account.user.id} by feature flag")
            return None
        
        return super().create_subscription_for_calendar(calendar)
```

#### Deployment Configuration
```python
# settings/deployment_phases.py

# Phase 1: Webhook infrastructure deployed, but disabled
PHASE_1_SETTINGS = {
    'WEBHOOKS_ENABLED': False,
    'WEBHOOK_ROLLOUT_PERCENTAGE': 0,
    'WEBHOOK_USER_ROLLOUT_PERCENTAGE': 0,
}

# Phase 2: Enable for early adopters
PHASE_2_SETTINGS = {
    'WEBHOOKS_ENABLED': True,
    'WEBHOOK_ROLLOUT_PERCENTAGE': 0,
    'WEBHOOK_USER_ROLLOUT_PERCENTAGE': 0,
    'WEBHOOK_EARLY_ADOPTERS': [
        'admin@yourdomain.com',
        'developer@yourdomain.com',
    ],
}

# Phase 3: Gradual rollout (10% of users)
PHASE_3_SETTINGS = {
    'WEBHOOKS_ENABLED': True,
    'WEBHOOK_ROLLOUT_PERCENTAGE': 10,
    'WEBHOOK_USER_ROLLOUT_PERCENTAGE': 10,
}

# Phase 4: Majority rollout (75% of users)
PHASE_4_SETTINGS = {
    'WEBHOOKS_ENABLED': True,
    'WEBHOOK_ROLLOUT_PERCENTAGE': 75,
    'WEBHOOK_USER_ROLLOUT_PERCENTAGE': 75,
}

# Phase 5: Full rollout (100% of users)
PHASE_5_SETTINGS = {
    'WEBHOOKS_ENABLED': True,
    'WEBHOOK_ROLLOUT_PERCENTAGE': 100,
    'WEBHOOK_USER_ROLLOUT_PERCENTAGE': 100,
}
```

## Monitoring and Alerting

### Webhook Health Monitoring

#### Comprehensive Health Check System
```python
# apps/webhooks/services/health_monitor.py
import logging
from datetime import timedelta
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Count, Avg

from ..models import WebhookSubscription, WebhookNotification

logger = logging.getLogger(__name__)

class WebhookHealthMonitor:
    """Comprehensive webhook health monitoring system"""
    
    def __init__(self):
        self.health_metrics = {}
    
    def get_system_health(self):
        """Get overall webhook system health"""
        
        health_data = {
            'timestamp': timezone.now(),
            'status': 'healthy',  # healthy/degraded/critical
            'metrics': {},
            'alerts': [],
            'recommendations': []
        }
        
        # Check subscription health
        subscription_health = self._check_subscription_health()
        health_data['metrics']['subscriptions'] = subscription_health
        
        # Check notification processing health
        notification_health = self._check_notification_processing_health()
        health_data['metrics']['notifications'] = notification_health
        
        # Check API performance
        api_health = self._check_api_performance()
        health_data['metrics']['api_performance'] = api_health
        
        # Check infrastructure health
        infrastructure_health = self._check_infrastructure_health()
        health_data['metrics']['infrastructure'] = infrastructure_health
        
        # Determine overall status and generate alerts
        health_data['status'] = self._determine_overall_status(health_data['metrics'])
        health_data['alerts'] = self._generate_alerts(health_data['metrics'])
        health_data['recommendations'] = self._generate_recommendations(health_data['metrics'])
        
        return health_data
    
    def _check_subscription_health(self):
        """Check webhook subscription health metrics"""
        
        now = timezone.now()
        
        # Total subscription counts
        total_subscriptions = WebhookSubscription.objects.count()
        active_subscriptions = WebhookSubscription.objects.filter(status='active').count()
        
        # Expiring subscriptions
        expiring_soon = WebhookSubscription.objects.filter(
            status='active',
            expires_at__lte=now + timedelta(hours=24)
        ).count()
        
        # Failed subscriptions
        failed_subscriptions = WebhookSubscription.objects.filter(
            failure_count__gte=5
        ).count()
        
        # Inactive subscriptions (no recent notifications)
        inactive_subscriptions = WebhookSubscription.objects.filter(
            status='active',
            last_notification_at__lt=now - timedelta(hours=6)
        ).count()
        
        return {
            'total_subscriptions': total_subscriptions,
            'active_subscriptions': active_subscriptions,
            'expiring_soon': expiring_soon,
            'failed_subscriptions': failed_subscriptions,
            'inactive_subscriptions': inactive_subscriptions,
            'health_percentage': self._calculate_subscription_health_percentage(
                active_subscriptions, failed_subscriptions, inactive_subscriptions, total_subscriptions
            )
        }
    
    def _check_notification_processing_health(self):
        """Check webhook notification processing health"""
        
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        
        # Notification counts by status
        notification_stats = WebhookNotification.objects.filter(
            received_at__gte=last_24h
        ).aggregate(
            total_notifications=Count('id'),
            completed_notifications=Count('id', filter=models.Q(processing_status='completed')),
            failed_notifications=Count('id', filter=models.Q(processing_status='failed')),
            pending_notifications=Count('id', filter=models.Q(processing_status='pending')),
            average_processing_time=Avg('processing_time_ms')
        )
        
        # Calculate success rate
        total = notification_stats['total_notifications'] or 1
        success_rate = (notification_stats['completed_notifications'] / total) * 100
        
        # Check for processing backlogs
        old_pending = WebhookNotification.objects.filter(
            processing_status='pending',
            received_at__lt=now - timedelta(minutes=5)
        ).count()
        
        return {
            'total_notifications_24h': notification_stats['total_notifications'],
            'success_rate_percentage': round(success_rate, 2),
            'failed_notifications_24h': notification_stats['failed_notifications'],
            'pending_notifications': notification_stats['pending_notifications'],
            'old_pending_notifications': old_pending,
            'average_processing_time_ms': notification_stats['average_processing_time'] or 0,
        }
    
    def _check_api_performance(self):
        """Check Google Calendar API performance metrics"""
        
        # This would integrate with your existing API monitoring
        # For now, return basic metrics
        
        return {
            'api_calls_last_hour': self._get_api_calls_count(hours=1),
            'api_errors_last_hour': self._get_api_errors_count(hours=1),
            'average_api_response_time_ms': self._get_average_api_response_time(),
            'api_quota_usage_percentage': self._get_api_quota_usage(),
        }
    
    def _check_infrastructure_health(self):
        """Check infrastructure health (database, cache, etc.)"""
        
        health = {
            'database_healthy': True,
            'cache_healthy': True,
            'disk_space_ok': True,
            'memory_usage_ok': True
        }
        
        # Database connectivity test
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            health['database_healthy'] = True
        except Exception as e:
            health['database_healthy'] = False
            logger.error(f"Database health check failed: {e}")
        
        # Cache connectivity test
        try:
            cache.set('health_check', '1', timeout=10)
            result = cache.get('health_check')
            health['cache_healthy'] = result == '1'
        except Exception as e:
            health['cache_healthy'] = False
            logger.error(f"Cache health check failed: {e}")
        
        return health
    
    def _determine_overall_status(self, metrics):
        """Determine overall system status based on metrics"""
        
        # Critical conditions
        if not metrics['infrastructure']['database_healthy']:
            return 'critical'
        
        if metrics['notifications']['success_rate_percentage'] < 80:
            return 'critical'
        
        if metrics['subscriptions']['failed_subscriptions'] > 10:
            return 'critical'
        
        # Degraded conditions
        if metrics['subscriptions']['health_percentage'] < 90:
            return 'degraded'
        
        if metrics['notifications']['success_rate_percentage'] < 95:
            return 'degraded'
        
        if metrics['notifications']['old_pending_notifications'] > 5:
            return 'degraded'
        
        return 'healthy'
    
    def _generate_alerts(self, metrics):
        """Generate alerts based on health metrics"""
        
        alerts = []
        
        # Subscription alerts
        if metrics['subscriptions']['expiring_soon'] > 5:
            alerts.append({
                'level': 'warning',
                'type': 'subscription_expiring',
                'message': f"{metrics['subscriptions']['expiring_soon']} subscriptions expiring within 24 hours",
                'action': 'Run subscription renewal process'
            })
        
        if metrics['subscriptions']['failed_subscriptions'] > 5:
            alerts.append({
                'level': 'error',
                'type': 'subscription_failures',
                'message': f"{metrics['subscriptions']['failed_subscriptions']} subscriptions have high failure rates",
                'action': 'Review and repair failed subscriptions'
            })
        
        # Notification processing alerts
        if metrics['notifications']['success_rate_percentage'] < 95:
            alerts.append({
                'level': 'warning',
                'type': 'low_success_rate',
                'message': f"Notification success rate is {metrics['notifications']['success_rate_percentage']}%",
                'action': 'Investigate notification processing errors'
            })
        
        if metrics['notifications']['old_pending_notifications'] > 0:
            alerts.append({
                'level': 'warning',
                'type': 'processing_backlog',
                'message': f"{metrics['notifications']['old_pending_notifications']} notifications pending >5 minutes",
                'action': 'Check notification processing system'
            })
        
        # Infrastructure alerts
        if not metrics['infrastructure']['database_healthy']:
            alerts.append({
                'level': 'critical',
                'type': 'database_down',
                'message': 'Database connectivity issues detected',
                'action': 'Check database server status immediately'
            })
        
        return alerts
    
    def _generate_recommendations(self, metrics):
        """Generate optimization recommendations"""
        
        recommendations = []
        
        # Performance recommendations
        if metrics['notifications']['average_processing_time_ms'] > 5000:
            recommendations.append({
                'type': 'performance',
                'message': 'Notification processing time is high',
                'suggestion': 'Consider optimizing sync queries or increasing worker processes'
            })
        
        # Subscription management recommendations
        if metrics['subscriptions']['inactive_subscriptions'] > 0:
            recommendations.append({
                'type': 'maintenance',
                'message': f"{metrics['subscriptions']['inactive_subscriptions']} subscriptions appear inactive",
                'suggestion': 'Review webhook subscription health and consider recreation'
            })
        
        return recommendations
    
    # Helper methods for metrics calculation
    def _calculate_subscription_health_percentage(self, active, failed, inactive, total):
        """Calculate overall subscription health percentage"""
        
        if total == 0:
            return 100
        
        healthy = active - failed - inactive
        return max(0, (healthy / total) * 100)
    
    def _get_api_calls_count(self, hours=1):
        """Get API calls count from logs or metrics"""
        # Implementation would depend on your API monitoring setup
        return 0
    
    def _get_api_errors_count(self, hours=1):
        """Get API errors count from logs or metrics"""
        # Implementation would depend on your API monitoring setup
        return 0
    
    def _get_average_api_response_time(self):
        """Get average API response time"""
        # Implementation would depend on your API monitoring setup
        return 500
    
    def _get_api_quota_usage(self):
        """Get API quota usage percentage"""
        # Implementation would depend on your API monitoring setup
        return 25
```

## LLM Monitoring Thresholds

### Health Status Determination (AI Agents: Use These Exact Rules)

#### HEALTHY Status Requirements (ALL conditions must be true)
- **Database connectivity**: ✅ (connection test passes)
- **Subscription success rate**: ≥95% (active subscriptions working properly)
- **Notification processing success rate**: ≥95% (webhooks processed successfully)
- **Pending notifications <5 minutes old**: ≤5 (no significant processing backlog)
- **Failed subscriptions**: ≤5 (low failure rate)

#### DEGRADED Status Triggers (ANY condition can trigger)
- **Subscription success rate**: 80-94% (some subscriptions failing)
- **Notification processing success rate**: 90-94% (some webhook processing issues)
- **Pending notifications >5 minutes**: 5-20 (moderate processing backlog)
- **Failed subscriptions**: 5-10 (moderate failure rate)
- **Cache connectivity**: ❌ (Redis/cache issues - not critical but degraded)

#### CRITICAL Status Triggers (ANY condition triggers immediate alert)
- **Database connectivity**: ❌ (cannot connect to database)
- **Subscription success rate**: <80% (major subscription failures)
- **Notification processing success rate**: <90% (major processing failures)
- **Pending notifications >5 minutes**: >20 (severe processing backlog)
- **Failed subscriptions**: >10 (high failure rate)

### Alert Response Actions (LLM: Execute These Automatically)

#### CRITICAL Status Response
```python
def handle_critical_status(status, metrics):
    # IMMEDIATE ACTIONS (execute within 30 seconds):
    
    # 1. Send alert to all configured channels
    alert_manager.send_critical_alert(
        message=f"Webhook system CRITICAL: {status}",
        metrics=metrics
    )
    
    # 2. Enable polling fallback for ALL calendars
    Calendar.objects.filter(sync_enabled=True).update(
        fallback_polling_enabled=True
    )
    
    # 3. Suspend problematic webhook subscriptions
    WebhookSubscription.objects.filter(
        failure_count__gte=10
    ).update(status='suspended')
    
    # 4. Page on-call engineer (if configured)
    send_page_alert("Webhook system critical failure")
    
    logger.critical(f"CRITICAL webhook system status: {metrics}")
```

#### DEGRADED Status Response  
```python
def handle_degraded_status(status, metrics):
    # AUTOMATIC MAINTENANCE ACTIONS:
    
    # 1. Run subscription maintenance immediately
    call_command('subscription_maintenance')
    
    # 2. Increase health check frequency
    settings.WEBHOOK_HEALTH_CHECK_INTERVAL = 120  # Every 2 minutes
    
    # 3. Send warning alert
    alert_manager.send_warning_alert(
        message=f"Webhook system degraded: {status}",
        metrics=metrics
    )
    
    # 4. Enable temporary polling fallback for failing calendars
    failing_subscriptions = WebhookSubscription.objects.filter(
        failure_count__gte=5
    )
    for subscription in failing_subscriptions:
        subscription.calendar.fallback_polling_enabled = True
        subscription.calendar.save()
    
    logger.warning(f"DEGRADED webhook system status: {metrics}")
```

#### HEALTHY Status Response
```python
def handle_healthy_status(status, metrics):
    # MAINTENANCE ACTIONS:
    
    # 1. Reset health check frequency to normal
    settings.WEBHOOK_HEALTH_CHECK_INTERVAL = 300  # Every 5 minutes
    
    # 2. Disable unnecessary polling fallbacks (if webhook subscriptions are healthy)
    healthy_calendars = Calendar.objects.filter(
        webhook_subscriptions__status='active',
        webhook_subscriptions__failure_count__lt=3
    )
    healthy_calendars.update(fallback_polling_enabled=False)
    
    # 3. Log healthy status (for trending)
    logger.info(f"Webhook system healthy: {metrics}")
```

### Monitoring Validation Steps (LLM: Run These Checks)

#### Before Deployment
```python
# MANDATORY PRE-DEPLOYMENT CHECKS
def validate_monitoring_setup():
    # 1. Health check endpoint accessible
    response = requests.get('https://your-domain.com/webhooks/health/')
    assert response.status_code == 200, "Health endpoint not accessible"
    
    # 2. Database connectivity working
    monitor = WebhookHealthMonitor()
    health = monitor.get_system_health()
    assert health['status'] != 'critical', "System unhealthy before deployment"
    
    # 3. Alert channels configured
    assert hasattr(settings, 'WEBHOOK_ALERT_CHANNELS'), "Alert channels not configured"
    assert len(settings.WEBHOOK_ALERT_CHANNELS) > 0, "No alert channels configured"
    
    return True
```

#### Post-Deployment
```python  
# MANDATORY POST-DEPLOYMENT VALIDATION
def validate_deployment_success():
    # 1. Wait for system to stabilize
    time.sleep(60)
    
    # 2. Check system health
    monitor = WebhookHealthMonitor()
    health = monitor.get_system_health()
    
    # 3. Validate healthy state
    assert health['status'] in ['healthy', 'degraded'], f"Deployment failed: {health['status']}"
    assert health['metrics']['infrastructure']['database_healthy'], "Database issues after deployment"
    
    # 4. Test webhook endpoint processing
    test_response = test_webhook_endpoint()
    assert test_response.status_code in [200, 404], "Webhook endpoints not responding"
    
    return True
```

### Monitoring Dashboard

#### Webhook Metrics Dashboard
```python
# apps/webhooks/views.py (monitoring endpoints)
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator
from django.views import View

@method_decorator(staff_member_required, name='dispatch')
class WebhookMonitoringDashboardView(View):
    """Dashboard view for webhook monitoring"""
    
    def get(self, request):
        """Return webhook monitoring dashboard data"""
        
        monitor = WebhookHealthMonitor()
        health_data = monitor.get_system_health()
        
        # Add additional dashboard-specific data
        dashboard_data = {
            'health': health_data,
            'recent_activity': self._get_recent_activity(),
            'performance_trends': self._get_performance_trends(),
            'subscription_distribution': self._get_subscription_distribution(),
        }
        
        return JsonResponse(dashboard_data)
    
    def _get_recent_activity(self):
        """Get recent webhook activity for dashboard"""
        
        recent_notifications = WebhookNotification.objects.filter(
            received_at__gte=timezone.now() - timedelta(hours=1)
        ).order_by('-received_at')[:10]
        
        return [{
            'id': notification.id,
            'calendar': notification.subscription.calendar.name,
            'provider': notification.subscription.provider,
            'status': notification.processing_status,
            'received_at': notification.received_at.isoformat(),
            'processing_time_ms': notification.processing_time_ms,
        } for notification in recent_notifications]
    
    def _get_performance_trends(self):
        """Get performance trends for dashboard charts"""
        
        # This would generate data for charts showing:
        # - Success rate over time
        # - Processing time trends
        # - Subscription health trends
        
        return {
            'success_rate_24h': [],  # Time series data
            'processing_time_24h': [],  # Time series data
            'subscription_count_24h': [],  # Time series data
        }
    
    def _get_subscription_distribution(self):
        """Get subscription distribution by provider, status, etc."""
        
        from django.db.models import Count
        
        by_provider = WebhookSubscription.objects.values('provider').annotate(
            count=Count('id')
        )
        
        by_status = WebhookSubscription.objects.values('status').annotate(
            count=Count('id')
        )
        
        return {
            'by_provider': list(by_provider),
            'by_status': list(by_status),
        }

# URL configuration for monitoring
# apps/webhooks/urls.py (addition)
urlpatterns = [
    # ... existing patterns ...
    path('monitoring/dashboard/', WebhookMonitoringDashboardView.as_view(), name='monitoring_dashboard'),
    path('monitoring/health/', WebhookSystemHealthView.as_view(), name='system_health'),
]
```

### Alerting Integration

#### Alert Management System
```python
# apps/webhooks/services/alerting.py
import logging
import requests
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

class WebhookAlertManager:
    """Manages webhook-related alerts and notifications"""
    
    def __init__(self):
        self.alert_channels = {
            'email': self._send_email_alert,
            'slack': self._send_slack_alert,
            'webhook': self._send_webhook_alert,
        }
    
    def send_alert(self, alert):
        """Send alert through configured channels"""
        
        enabled_channels = getattr(settings, 'WEBHOOK_ALERT_CHANNELS', ['email'])
        
        for channel in enabled_channels:
            try:
                if channel in self.alert_channels:
                    self.alert_channels[channel](alert)
                    logger.info(f"Alert sent via {channel}: {alert['type']}")
            except Exception as e:
                logger.error(f"Failed to send alert via {channel}: {e}")
    
    def _send_email_alert(self, alert):
        """Send alert via email"""
        
        recipients = getattr(settings, 'WEBHOOK_ALERT_EMAIL_RECIPIENTS', [])
        if not recipients:
            return
        
        subject = f"[Calendar Sync] {alert['level'].upper()}: {alert['type']}"
        message = self._format_email_alert(alert)
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False
        )
    
    def _send_slack_alert(self, alert):
        """Send alert via Slack webhook"""
        
        slack_webhook_url = getattr(settings, 'SLACK_WEBHOOK_URL', None)
        if not slack_webhook_url:
            return
        
        color_map = {
            'critical': '#ff0000',
            'error': '#ff6600',
            'warning': '#ffcc00',
            'info': '#0066cc'
        }
        
        payload = {
            'attachments': [{
                'color': color_map.get(alert['level'], '#0066cc'),
                'title': f"Calendar Sync Alert: {alert['type']}",
                'text': alert['message'],
                'fields': [
                    {
                        'title': 'Level',
                        'value': alert['level'].upper(),
                        'short': True
                    },
                    {
                        'title': 'Action Required',
                        'value': alert.get('action', 'None'),
                        'short': True
                    }
                ],
                'timestamp': int(timezone.now().timestamp())
            }]
        }
        
        response = requests.post(slack_webhook_url, json=payload, timeout=10)
        response.raise_for_status()
    
    def _send_webhook_alert(self, alert):
        """Send alert via webhook to external monitoring system"""
        
        webhook_url = getattr(settings, 'EXTERNAL_ALERT_WEBHOOK_URL', None)
        if not webhook_url:
            return
        
        payload = {
            'source': 'calendar_sync_webhooks',
            'alert': alert,
            'timestamp': timezone.now().isoformat(),
        }
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
    
    def _format_email_alert(self, alert):
        """Format alert for email"""
        
        return f"""
Calendar Sync Webhook Alert

Level: {alert['level'].upper()}
Type: {alert['type']}
Message: {alert['message']}

Action Required: {alert.get('action', 'None')}

Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

This is an automated alert from the Calendar Sync webhook monitoring system.
        """.strip()

# Integration with health monitor
class AlertingHealthMonitor(WebhookHealthMonitor):
    """Health monitor with alerting integration"""
    
    def __init__(self):
        super().__init__()
        self.alert_manager = WebhookAlertManager()
    
    def get_system_health(self):
        """Get system health and send alerts if needed"""
        
        health_data = super().get_system_health()
        
        # Send alerts for critical and error level issues
        for alert in health_data['alerts']:
            if alert['level'] in ['critical', 'error']:
                self.alert_manager.send_alert(alert)
        
        return health_data
```

### Automated Monitoring Tasks

#### Monitoring Management Commands  
```python
# apps/webhooks/management/commands/webhook_health_check.py
from django.core.management.base import BaseCommand
from apps.webhooks.services.health_monitor import AlertingHealthMonitor

class Command(BaseCommand):
    help = 'Run webhook health check and send alerts if needed'
    
    def add_arguments(self, parser):
        parser.add_argument('--send-alerts', action='store_true', help='Send alerts for issues')
    
    def handle(self, *args, **options):
        monitor = AlertingHealthMonitor()
        health_data = monitor.get_system_health()
        
        # Display health summary
        self.stdout.write(f"System Status: {health_data['status']}")
        self.stdout.write(f"Active Subscriptions: {health_data['metrics']['subscriptions']['active_subscriptions']}")
        self.stdout.write(f"Success Rate (24h): {health_data['metrics']['notifications']['success_rate_percentage']}%")
        
        # Display alerts
        if health_data['alerts']:
            self.stdout.write("\nAlerts:")
            for alert in health_data['alerts']:
                self.stdout.write(f"  - {alert['level'].upper()}: {alert['message']}")
        
        # Display recommendations
        if health_data['recommendations']:
            self.stdout.write("\nRecommendations:")
            for rec in health_data['recommendations']:
                self.stdout.write(f"  - {rec['message']}: {rec['suggestion']}")
```

#### Cron Configuration
```bash
# /etc/crontab additions for webhook monitoring

# Run health check every 5 minutes
*/5 * * * * cd /path/to/app && python manage.py webhook_health_check

# Run subscription maintenance every 30 minutes  
*/30 * * * * cd /path/to/app && python manage.py subscription_maintenance

# Run comprehensive monitoring report daily
0 8 * * * cd /path/to/app && python manage.py webhook_health_check --send-alerts

# Clean up old webhook data weekly
0 2 * * 0 cd /path/to/app && python manage.py cleanup_webhook_data --days=7
```

## Success Criteria

### Deployment Success
- **Zero-Downtime Deployment**: Webhook infrastructure deployed without service interruption
- **Gradual Rollout**: Successful phased rollout from 0% to 100% of users
- **Feature Flag Control**: Ability to instantly disable webhooks if issues arise

### Monitoring Success
- **Proactive Issue Detection**: Critical issues detected and alerted within 5 minutes
- **Comprehensive Visibility**: Full visibility into webhook performance and health
- **Automated Recovery**: Failed subscriptions automatically renewed or repaired

### Operational Success
- **99.9% Webhook Uptime**: Webhook endpoints available and responsive
- **<5 Minute Alert Response**: Critical alerts trigger response within 5 minutes
- **Automated Maintenance**: Routine maintenance tasks run automatically without manual intervention

This deployment and monitoring strategy ensures reliable webhook operation with comprehensive observability and proactive issue management.

## Related Documentation

**Prerequisites (Read Before Deployment):**
- **Strategy**: Review [00-webhook-strategy-overview.md](00-webhook-strategy-overview.md) for deployment context
- **Database**: Ensure [01-database-infrastructure.md](01-database-infrastructure.md) models are migrated
- **Endpoints**: Validate [02-webhook-endpoints-and-validation.md](02-webhook-endpoints-and-validation.md) security setup
- **Subscriptions**: Configure [03-subscription-management.md](03-subscription-management.md) lifecycle management
- **Sync Engine**: Test [04-sync-engine-integration.md](04-sync-engine-integration.md) integration
- **Testing**: Complete [05-testing-and-development-strategy.md](05-testing-and-development-strategy.md) validation

**This is the final implementation document** - deploy only after all prerequisites are complete and tested.
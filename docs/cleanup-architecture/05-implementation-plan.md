# Account Disconnection: Implementation Plan

## Overview

This document provides the detailed technical implementation plan for the Guilfoyle-approved account disconnection architecture. The plan prioritizes immediate user experience improvements while building robust background cleanup.

## Implementation Phases

### Phase 1: Database Schema Changes (High Priority)

#### 1.1 Add Account Status Field

**Target**: Replace boolean `is_active` with status enum

**Migration**: `src/apps/calendars/migrations/XXXX_add_account_status.py`
```python
class Migration(migrations.Migration):
    dependencies = [
        ('calendars', 'XXXX_previous_migration'),
    ]

    operations = [
        migrations.AddField(
            model_name='calendaraccount',
            name='status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('ACTIVE', 'Active'),
                    ('DISCONNECTING', 'Disconnecting'),
                    ('CLEANUP_FAILED', 'Cleanup Failed'),
                    ('DISCONNECTED', 'Disconnected'),
                ],
                default='ACTIVE'
            ),
        ),
        migrations.AddField(
            model_name='calendaraccount', 
            name='cleanup_retry_count',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='calendaraccount',
            name='cleanup_last_error', 
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='calendaraccount',
            name='disconnect_requested_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        # Data migration: Set status='ACTIVE' for existing is_active=True accounts
        migrations.RunSQL(
            "UPDATE calendars_calendaraccount SET status='ACTIVE' WHERE is_active=true;",
            reverse_sql="UPDATE calendars_calendaraccount SET is_active=true WHERE status='ACTIVE';"
        ),
        # Remove old field after data migration
        migrations.RemoveField(
            model_name='calendaraccount',
            name='is_active',
        ),
    ]
```

#### 1.2 Update CalendarAccount Model

**File**: `src/apps/calendars/models.py`
```python
class CalendarAccount(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('DISCONNECTING', 'Disconnecting'),
        ('CLEANUP_FAILED', 'Cleanup Failed'),
        ('DISCONNECTED', 'Disconnected'),
    ]
    
    # ... existing fields ...
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='ACTIVE',
        help_text="Current account lifecycle status"
    )
    cleanup_retry_count = models.IntegerField(
        default=0,
        help_text="Number of cleanup attempts for this account"
    )
    cleanup_last_error = models.TextField(
        blank=True,
        help_text="Last error encountered during cleanup"
    )
    disconnect_requested_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When disconnection was requested by user"
    )
    
    @property
    def is_active(self):
        """Backward compatibility property"""
        return self.status == 'ACTIVE'
    
    @property  
    def cleanup_age_hours(self):
        """Hours since disconnection requested"""
        if not self.disconnect_requested_at:
            return 0
        return (timezone.now() - self.disconnect_requested_at).total_seconds() / 3600
    
    def can_attempt_cleanup(self):
        """Check if account is eligible for cleanup retry"""
        return (self.status == 'DISCONNECTING' and 
                self.cleanup_retry_count < settings.MAX_CLEANUP_RETRIES and
                self.cleanup_age_hours < settings.CLEANUP_BANKRUPTCY_HOURS)
```

### Phase 2: Immediate User Feedback (High Priority)

#### 2.1 Modify Disconnect Endpoint

**File**: `src/apps/accounts/services/oauth_service.py`
```python
def disconnect_account(self, account_id):
    """Immediate user feedback with background cleanup"""
    try:
        account = CalendarAccount.objects.get(id=account_id, user=self.user)
        
        with transaction.atomic():
            # Immediate status change - never fails
            account.status = 'DISCONNECTING'
            account.disconnect_requested_at = timezone.now()
            account.save(update_fields=['status', 'disconnect_requested_at'])
            
            # Queue background cleanup - don't wait
            from .tasks import cleanup_account_background
            cleanup_account_background.delay(account_id)
        
        self._log_operation(
            "account_disconnect_initiated",
            account_id=account_id,
            email=account.email,
        )
        
        return {
            "success": True,
            "message": f"Account {account.email} disconnected successfully. Cleanup in progress.",
            "status": "disconnecting"
        }
        
    except CalendarAccount.DoesNotExist:
        raise ResourceNotFoundError(f"Account {account_id} not found")
    except Exception as e:
        self._handle_error(e, "account_disconnect", account_id=account_id)
        raise ExternalServiceError(f"Failed to disconnect account: {e!s}")
```

#### 2.2 Update View Response

**File**: `src/apps/accounts/views.py`  
```python
def disconnect_account(request: HttpRequest, account_id: int) -> HttpResponse:
    """Handle account disconnection with immediate feedback"""
    try:
        oauth_service = OAuthService(request.user)
        result = oauth_service.disconnect_account(account_id)
        
        if result["success"]:
            messages.success(request, result["message"])
        else:
            messages.error(request, result.get("message", "Failed to disconnect account"))
            
        return redirect("dashboard:index")
        
    except ResourceNotFoundError:
        messages.error(request, "Account not found or already disconnected.")
        return redirect("dashboard:index")
    except Exception as e:
        logger.error(f"Account disconnect failed: {e}")
        messages.error(request, "Disconnection failed. Please try again.")
        return redirect("dashboard:index")
```

### Phase 3: Background Cleanup Job (High Priority)

#### 3.1 Create Background Task

**File**: `src/apps/accounts/tasks.py` (new file)
```python
from celery import shared_task
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=None)
def cleanup_account_background(self, account_id):
    """Background account cleanup with retry and bankruptcy logic"""
    from apps.calendars.models import CalendarAccount
    from apps.calendars.services.calendar_service import CalendarService
    
    try:
        account = CalendarAccount.objects.get(id=account_id)
        
        # Check bankruptcy conditions
        if not account.can_attempt_cleanup():
            logger.warning(f"Account {account_id} bankruptcy triggered")
            declare_cleanup_bankruptcy(account)
            return f"Account {account_id} cleanup bankruptcy declared"
        
        # Attempt cleanup
        calendar_service = CalendarService()
        cleanup_result = calendar_service.cleanup_account_google_events(account)
        
        if cleanup_result['success']:
            # Complete success - delete account
            logger.info(f"Account {account_id} cleanup completed successfully")
            account.status = 'DISCONNECTED'
            account.save()
            account.delete()  # CASCADE removes all related data
            return f"Account {account_id} cleanup completed and deleted"
            
        else:
            # Partial failure - retry with backoff
            account.cleanup_retry_count += 1
            account.cleanup_last_error = cleanup_result.get('error', 'Unknown cleanup error')
            account.save()
            
            # Exponential backoff: 1min, 2min, 4min, 8min, ... up to 1 hour
            retry_delay = min(3600, 60 * (2 ** account.cleanup_retry_count))
            
            logger.info(f"Account {account_id} cleanup failed, retrying in {retry_delay}s (attempt {account.cleanup_retry_count})")
            raise self.retry(countdown=retry_delay)
            
    except CalendarAccount.DoesNotExist:
        logger.error(f"Account {account_id} not found for cleanup")
        return f"Account {account_id} not found"
        
    except Exception as exc:
        logger.error(f"Account {account_id} cleanup error: {exc}")
        # Update error state but don't fail the task permanently
        try:
            account = CalendarAccount.objects.get(id=account_id) 
            account.cleanup_retry_count += 1
            account.cleanup_last_error = str(exc)
            account.save()
        except:
            pass
        
        # Retry with exponential backoff
        raise self.retry(countdown=min(3600, 60 * (2 ** (account.cleanup_retry_count or 0))), exc=exc)

def declare_cleanup_bankruptcy(account):
    """Handle cleanup bankruptcy - delete locally and alert"""
    from django.core.mail import mail_admins
    
    logger.error(f"BANKRUPTCY: Account {account.id} ({account.email}) cleanup failed permanently")
    
    # Update status
    account.status = 'CLEANUP_FAILED'
    account.save()
    
    # Send operational alert
    alert_message = f"""
    Account cleanup bankruptcy declared:
    
    Account: {account.email} (ID: {account.id})
    Retry attempts: {account.cleanup_retry_count}
    Last error: {account.cleanup_last_error}
    Disconnect requested: {account.disconnect_requested_at}
    
    Local database records will be deleted, but Google Calendar events may remain orphaned.
    """
    
    mail_admins(
        subject=f"Calendar Bridge: Account Cleanup Bankruptcy ({account.email})", 
        message=alert_message
    )
    
    # Delete account locally (accept orphaned Google events)
    account.delete()
```

#### 3.2 Enhance Calendar Service

**File**: `src/apps/calendars/services/calendar_service.py`
```python
def cleanup_account_google_events(self, account):
    """Cleanup all Google Calendar events for an account"""
    results = {
        'success': True,
        'calendars_cleaned': 0,
        'events_deleted': 0,
        'errors': []
    }
    
    try:
        # Get all calendars for the account
        calendars = account.calendars.all()
        
        for calendar in calendars:
            try:
                # Use existing calendar cleanup logic
                calendar_result = self._execute_gone_gone_cleanup(calendar)
                results['calendars_cleaned'] += 1
                results['events_deleted'] += calendar_result.get('events_deleted', 0)
                
            except Exception as e:
                error_msg = f"Calendar {calendar.name} cleanup failed: {e}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
                results['success'] = False
        
        if results['errors']:
            results['error'] = '; '.join(results['errors'])
            
        return results
        
    except Exception as e:
        logger.error(f"Account {account.id} cleanup failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'calendars_cleaned': 0,
            'events_deleted': 0
        }
```

### Phase 4: UI Updates (Medium Priority)

#### 4.1 Update Template Tags

**File**: `src/apps/dashboard/templatetags/account_tags.py`
```python
@register.inclusion_tag('dashboard/partials/account_status_badge.html')
def account_status_badge(account):
    """Render account status badge with cleanup progress"""
    status_config = {
        'ACTIVE': {
            'badge_class': 'bg-success',
            'text': 'Active',
            'description': None,
        },
        'DISCONNECTING': {
            'badge_class': 'bg-warning',
            'text': 'Disconnecting',
            'description': f'Cleanup in progress (attempt {account.cleanup_retry_count + 1})',
        },
        'CLEANUP_FAILED': {
            'badge_class': 'bg-danger', 
            'text': 'Cleanup Failed',
            'description': 'Manual intervention required',
        },
        'DISCONNECTED': {
            'badge_class': 'bg-secondary',
            'text': 'Disconnected',
            'description': None,
        }
    }
    
    config = status_config.get(account.status, status_config['ACTIVE'])
    return {
        'status': account.status,
        **config
    }
```

#### 4.2 Update Account Detail Template

**File**: `src/templates/dashboard/account_detail.html`
```html
<!-- Status section -->
<tr>
    <td><strong>Status:</strong></td>
    <td>{% account_status_badge account %}</td>
</tr>

<!-- Action buttons -->
<div class="d-flex flex-wrap gap-2">
    {% if account.status == 'ACTIVE' %}
        <a href="{% url 'dashboard:refresh_calendars' account.id %}" class="btn btn-outline-primary">
            Refresh Calendars
        </a>
        <a href="{% url 'accounts:disconnect_account' account.id %}" class="btn btn-danger disconnect-account-btn" 
           data-confirm-message="Are you sure you want to disconnect this account? Busy blocks will be cleaned up automatically.">
            Disconnect Account
        </a>
    {% elif account.status == 'DISCONNECTING' %}
        <div class="alert alert-info" role="alert">
            <strong>Disconnection in Progress</strong><br>
            Your account is being disconnected and busy blocks are being cleaned up. 
            This process typically completes within 15-30 minutes.
            {% if account.cleanup_retry_count > 0 %}
                <br><small class="text-muted">Cleanup attempt {{ account.cleanup_retry_count }} in progress.</small>
            {% endif %}
        </div>
    {% elif account.status == 'CLEANUP_FAILED' %}
        <div class="alert alert-danger" role="alert">
            <strong>Cleanup Failed</strong><br>
            Account disconnection encountered persistent issues. Support has been notified.
            Some calendar events may remain in your Google Calendar.
            <br><small class="text-muted">Last error: {{ account.cleanup_last_error|truncatechars:100 }}</small>
        </div>
    {% endif %}
</div>
```

### Phase 5: Legacy Cleanup Command Updates (Medium Priority)

#### 5.1 Modify Management Command

**File**: `src/apps/calendars/management/commands/cleanup_disabled_calendars.py`

Remove account deletion logic since it's now handled by background tasks:
```python
def handle(self, *args, **options):
    # ... existing calendar cleanup logic ...
    
    # Remove the account deletion section - now handled by background tasks
    # Just process individual calendar cleanups
    
    # Add monitoring for stuck background cleanups
    if not options['dry_run']:
        self._report_stuck_account_cleanups()

def _report_stuck_account_cleanups(self):
    """Report accounts stuck in DISCONNECTING status"""
    from django.utils import timezone
    from datetime import timedelta
    
    stuck_threshold = timezone.now() - timedelta(hours=2)
    stuck_accounts = CalendarAccount.objects.filter(
        status='DISCONNECTING',
        disconnect_requested_at__lt=stuck_threshold
    )
    
    if stuck_accounts.exists():
        self.stdout.write(
            self.style.WARNING(
                f"Found {stuck_accounts.count()} accounts stuck in DISCONNECTING status"
            )
        )
        for account in stuck_accounts:
            self.stdout.write(
                f"  🚨 {account.email}: {account.cleanup_retry_count} attempts, "
                f"last error: {account.cleanup_last_error[:50]}..."
            )
```

### Phase 6: Settings and Configuration (Low Priority)

#### 6.1 Add Settings

**File**: `src/config/settings/base.py`
```python
# Account cleanup configuration
MAX_CLEANUP_RETRIES = 20  # Maximum retry attempts before bankruptcy
CLEANUP_BANKRUPTCY_HOURS = 48  # Hours before declaring bankruptcy
CLEANUP_EXPONENTIAL_BACKOFF_MAX = 3600  # Max retry delay in seconds
```

#### 6.2 Update Celery Configuration

**File**: `src/config/celery.py` (if not exists, create)
```python
from celery import Celery
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')

app = Celery('calendar_bridge')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# For development - run with: celery -A config worker -l INFO
```

### Phase 7: Testing Strategy (High Priority)

#### 7.1 Unit Tests

**File**: `src/apps/accounts/tests/test_disconnect_flow.py`
```python
class TestAccountDisconnectFlow(TestCase):
    def test_immediate_disconnect_response(self):
        """Test that disconnect returns immediately with success"""
        # Test immediate status change and task queuing
        
    def test_background_cleanup_success(self):
        """Test successful background cleanup and account deletion"""
        
    def test_background_cleanup_retry(self):  
        """Test retry logic for failed cleanup attempts"""
        
    def test_cleanup_bankruptcy(self):
        """Test bankruptcy timeout handling"""
        
    def test_ui_status_display(self):
        """Test UI shows correct status during cleanup phases"""
```

#### 7.2 Integration Tests

**File**: `src/apps/accounts/tests/test_disconnect_integration.py`
```python 
class TestDisconnectIntegration(TestCase):
    def test_full_disconnect_flow_success(self):
        """End-to-end test of successful disconnection"""
        
    def test_disconnect_with_google_api_failures(self):
        """Test disconnection when Google Calendar API fails"""
        
    def test_disconnect_with_rate_limiting(self):
        """Test disconnection with Google API rate limiting"""
```

## Implementation Timeline

### Week 1: Foundation
- [ ] Database migration and model changes
- [ ] Basic disconnect endpoint modification
- [ ] Template updates for new status

### Week 2: Background Processing  
- [ ] Background task implementation
- [ ] Celery configuration
- [ ] Error handling and bankruptcy logic

### Week 3: Integration & Testing
- [ ] End-to-end testing
- [ ] UI polish and user messaging
- [ ] Monitoring and alerting setup

### Week 4: Deployment & Validation
- [ ] Production deployment
- [ ] Real-world testing with actual disconnections
- [ ] Performance monitoring and tuning

## Success Criteria

1. **User Experience**: Account disconnection always appears successful immediately
2. **Data Integrity**: No more orphaned busy blocks in Google Calendar
3. **System Reliability**: Background cleanup handles failures gracefully
4. **Operational Visibility**: Clear monitoring of cleanup success/failure rates
5. **Performance**: No blocking operations in user-facing endpoints

## Risk Mitigation

### Risk: Background Task Failures
**Mitigation**: Comprehensive retry logic with bankruptcy timeout

### Risk: Celery Queue Issues  
**Mitigation**: Add monitoring for stuck tasks, manual cleanup scripts

### Risk: User Confusion During Cleanup
**Mitigation**: Clear UI messaging about cleanup progress and timeframes

---

This implementation plan provides the complete technical roadmap for implementing the Guilfoyle-approved account disconnection architecture.
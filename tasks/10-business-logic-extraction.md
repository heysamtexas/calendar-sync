# TASK-10: Business Logic Extraction

## Priority: HIGH
## Estimated Time: 5-6 hours
## Dependencies: TASK-09 (View Layer Optimization)

## Problem Statement

Guilfoyle identified a fundamental architectural flaw where business logic is scattered throughout views, violating Django best practices and creating maintenance nightmares:

### Business Logic Issues Found:
1. **Fat Views Anti-Pattern**
   - Calendar operations mixed with HTTP handling
   - OAuth logic embedded directly in views
   - Complex business rules scattered across view functions

2. **Missing Service Layer**
   - No abstraction for calendar operations
   - No centralized business logic
   - Direct model manipulation in views

3. **Model Anemia**
   - Models lack business methods
   - No domain-specific operations
   - Missing model managers for complex queries

4. **Code Duplication**
   - Similar calendar operations repeated
   - OAuth handling duplicated
   - Validation logic scattered

## Acceptance Criteria

- [ ] All business logic extracted from views
- [ ] Service layer created for major operations (Calendar, OAuth, Dashboard)
- [ ] Model methods added for domain operations
- [ ] Custom model managers for complex queries
- [ ] Views handle only HTTP concerns (request/response)
- [ ] No code duplication in business operations
- [ ] Proper error handling in business layer
- [ ] All existing functionality preserved
- [ ] Comprehensive tests for business logic
- [ ] Clean separation of concerns achieved

## Implementation Steps

### Step 1: Create Service Layer Architecture (2 hours)

1. **Design Service Layer Structure**
   - CalendarService for calendar operations
   - OAuthService for authentication flows
   - SyncService for synchronization logic
   - DashboardService for dashboard data

2. **Implement Base Service Class**
   - Common error handling patterns
   - Logging standardization
   - Transaction management helpers

3. **Create Service Interfaces**
   - Define clear method signatures
   - Document expected inputs/outputs
   - Establish error handling patterns

### Step 2: Extract Calendar Operations (2 hours)

1. **Calendar Management Service**
   - Move toggle operations to CalendarService
   - Extract calendar discovery logic
   - Centralize calendar validation

2. **Calendar CRUD Operations**
   - Create, update, delete operations
   - Bulk operations for multiple calendars
   - Calendar synchronization state management

3. **Calendar Query Service**
   - Complex calendar filtering
   - Dashboard statistics
   - User calendar management

### Step 3: Extract OAuth Logic (1.5 hours)

1. **OAuth Flow Service**
   - Extract OAuth initiation logic
   - Centralize callback handling
   - Token management operations

2. **Account Management Service**
   - Account creation and updates
   - Token refresh operations
   - Account deactivation logic

3. **Integration with Calendar Discovery**
   - Safe calendar discovery
   - Transaction-wrapped operations
   - Error recovery mechanisms

### Step 4: Enhance Model Layer (1.5 hours)

1. **Add Model Methods**
   - Business operations on models
   - Validation methods
   - State management methods

2. **Create Custom Managers**
   - Complex query operations
   - User-specific filtering
   - Performance-optimized queries

3. **Add Model Properties**
   - Computed properties
   - Status indicators
   - Helper methods

## Files to Create/Modify

### Service Layer (New Files)
- `apps/calendars/services/__init__.py` - Service layer exports
- `apps/calendars/services/base.py` - Base service class
- `apps/calendars/services/calendar_service.py` - Calendar operations
- `apps/calendars/services/sync_service.py` - Sync operations
- `apps/accounts/services/__init__.py` - Account services exports
- `apps/accounts/services/oauth_service.py` - OAuth operations
- `apps/dashboard/services/__init__.py` - Dashboard services
- `apps/dashboard/services/dashboard_service.py` - Dashboard data

### Model Enhancements
- `apps/calendars/models.py` - Add methods and managers
- `apps/accounts/models.py` - Add account-specific methods

### View Refactoring
- `apps/dashboard/views.py` - Remove business logic, use services
- `apps/accounts/views.py` - Extract OAuth logic to services

### Testing
- `apps/calendars/tests/test_services.py` - Service layer tests
- `apps/accounts/tests/test_services.py` - OAuth service tests
- `apps/dashboard/tests/test_services.py` - Dashboard service tests

## Code Examples

### Base Service Class
```python
# apps/calendars/services/base.py
import logging
from django.db import transaction
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

class BaseService:
    """Base class for all business services"""
    
    def __init__(self, user=None):
        self.user = user
        self.logger = logger.getChild(self.__class__.__name__)
    
    def _validate_user_permission(self, obj, user_field='user'):
        """Validate user has permission for operation"""
        if not self.user:
            raise PermissionError("User required for this operation")
        
        obj_user = getattr(obj, user_field)
        if obj_user != self.user:
            raise PermissionError(f"User {self.user.username} cannot access this resource")
    
    def _log_operation(self, operation, **kwargs):
        """Standardized operation logging"""
        self.logger.info(
            f"Operation: {operation}",
            extra={
                'user_id': self.user.id if self.user else None,
                'user_name': self.user.username if self.user else None,
                **kwargs
            }
        )
    
    def _handle_error(self, error, operation, **context):
        """Standardized error handling"""
        self.logger.error(
            f"Error in {operation}: {str(error)}",
            extra={
                'error_type': type(error).__name__,
                'user_id': self.user.id if self.user else None,
                **context
            },
            exc_info=True
        )
        raise
```

### Calendar Service
```python
# apps/calendars/services/calendar_service.py
from django.db import transaction
from django.core.exceptions import ValidationError
from .base import BaseService
from ..models import Calendar, CalendarAccount

class CalendarNotFoundError(Exception):
    pass

class CalendarService(BaseService):
    """Service for calendar business operations"""
    
    def toggle_calendar_sync(self, calendar_id):
        """Toggle sync status for a calendar"""
        try:
            calendar = Calendar.objects.select_related('calendar_account').get(
                id=calendar_id
            )
            
            # Validate user permission
            self._validate_user_permission(calendar, 'calendar_account__user')
            
            # Perform toggle operation
            old_status = calendar.sync_enabled
            calendar.sync_enabled = not calendar.sync_enabled
            calendar.save(update_fields=['sync_enabled'])
            
            # Log operation
            self._log_operation(
                'calendar_sync_toggle',
                calendar_id=calendar.id,
                calendar_name=calendar.name,
                old_status=old_status,
                new_status=calendar.sync_enabled
            )
            
            return calendar
            
        except Calendar.DoesNotExist:
            raise CalendarNotFoundError(f"Calendar {calendar_id} not found")
    
    def bulk_toggle_calendars(self, calendar_ids, enable=True):
        """Toggle multiple calendars efficiently"""
        calendars = Calendar.objects.filter(
            id__in=calendar_ids,
            calendar_account__user=self.user
        ).select_related('calendar_account')
        
        if not calendars.exists():
            raise CalendarNotFoundError("No accessible calendars found")
        
        with transaction.atomic():
            updated_calendars = []
            for calendar in calendars:
                if calendar.sync_enabled != enable:
                    calendar.sync_enabled = enable
                    calendar.save(update_fields=['sync_enabled'])
                    updated_calendars.append(calendar)
            
            self._log_operation(
                'bulk_calendar_toggle',
                calendar_count=len(updated_calendars),
                enabled=enable
            )
            
            return updated_calendars
    
    def get_user_calendar_stats(self):
        """Get calendar statistics for user"""
        from django.db.models import Count, Q
        
        stats = CalendarAccount.objects.filter(
            user=self.user
        ).aggregate(
            total_accounts=Count('id'),
            active_accounts=Count('id', filter=Q(is_active=True)),
            total_calendars=Count('calendars'),
            sync_enabled_calendars=Count('calendars', filter=Q(calendars__sync_enabled=True))
        )
        
        return stats
    
    def refresh_calendar_list(self, account_id):
        """Refresh calendar list for an account"""
        try:
            account = CalendarAccount.objects.get(id=account_id, user=self.user)
            
            if not account.is_active:
                raise ValidationError("Cannot refresh calendars for inactive account")
            
            # Use existing GoogleCalendarClient
            from ..services.google_calendar_client import GoogleCalendarClient
            client = GoogleCalendarClient(account)
            
            calendars_data = client.list_calendars()
            
            with transaction.atomic():
                calendars_created = 0
                calendars_updated = 0
                
                for cal_item in calendars_data:
                    calendar, created = Calendar.objects.update_or_create(
                        calendar_account=account,
                        google_calendar_id=cal_item["id"],
                        defaults={
                            "name": cal_item.get("summary", "Unnamed Calendar"),
                            "is_primary": cal_item.get("primary", False),
                            "description": cal_item.get("description", ""),
                            "color": cal_item.get("backgroundColor", ""),
                        },
                    )
                    
                    if created:
                        calendar.sync_enabled = False  # Safe default
                        calendar.save(update_fields=['sync_enabled'])
                        calendars_created += 1
                    else:
                        calendars_updated += 1
                
                self._log_operation(
                    'calendar_refresh',
                    account_id=account.id,
                    calendars_found=len(calendars_data),
                    calendars_created=calendars_created,
                    calendars_updated=calendars_updated
                )
                
                return {
                    'calendars_found': len(calendars_data),
                    'calendars_created': calendars_created,
                    'calendars_updated': calendars_updated
                }
                
        except CalendarAccount.DoesNotExist:
            raise CalendarNotFoundError(f"Account {account_id} not found")
        except Exception as e:
            self._handle_error(e, 'calendar_refresh', account_id=account_id)
            raise
```

### OAuth Service
```python
# apps/accounts/services/oauth_service.py
from django.db import transaction
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from .base import BaseService
from ..models import CalendarAccount
from apps.calendars.services.calendar_service import CalendarService

class OAuthError(Exception):
    pass

class OAuthService(BaseService):
    """Service for OAuth business operations"""
    
    def process_oauth_callback(self, request, credentials, user_info):
        """Process OAuth callback with transaction safety"""
        try:
            with transaction.atomic():
                # Extract account information safely
                google_account_id = credentials.client_id
                email = self._extract_email_safely(user_info)
                expires_at = self._calculate_token_expiry(credentials)
                
                # Create or update account
                account, created = CalendarAccount.objects.update_or_create(
                    user=self.user,
                    google_account_id=google_account_id,
                    defaults={
                        "email": email,
                        "token_expires_at": expires_at,
                        "is_active": True,
                    },
                )
                
                # Set encrypted tokens
                account.set_access_token(credentials.token)
                if credentials.refresh_token:
                    account.set_refresh_token(credentials.refresh_token)
                account.save()
                
                # Discover calendars safely
                calendar_stats = self._discover_calendars_safely(account, credentials)
                
                # Log successful operation
                self._log_operation(
                    'oauth_callback_success',
                    account_id=account.id,
                    email=email,
                    created=created,
                    **calendar_stats
                )
                
                # Prepare user message
                action = "connected" if created else "updated"
                if calendar_stats['calendars_created'] > 0:
                    message = (
                        f"Successfully {action} {email} and discovered "
                        f"{calendar_stats['calendars_created']} calendars. "
                        "Sync is disabled by default - enable it for calendars you want to sync."
                    )
                else:
                    message = f"Successfully {action} {email}. No calendars found."
                
                return {
                    'success': True,
                    'account': account,
                    'message': message,
                    'created': created,
                    **calendar_stats
                }
                
        except Exception as e:
            self._handle_error(e, 'oauth_callback', email=email)
            return {
                'success': False,
                'error': str(e),
                'message': "Failed to connect Google Calendar account. Please try again."
            }
    
    def _extract_email_safely(self, user_info):
        """Extract email from user info with fallbacks"""
        if isinstance(user_info, dict):
            return user_info.get('email', 'Unknown Email')
        # Handle other user info formats
        return getattr(user_info, 'email', 'Unknown Email')
    
    def _calculate_token_expiry(self, credentials):
        """Calculate token expiry with timezone handling"""
        if credentials.expiry:
            if credentials.expiry.tzinfo is None:
                # Convert naive UTC to timezone-aware
                from zoneinfo import ZoneInfo
                expiry_aware = timezone.make_aware(credentials.expiry, ZoneInfo('UTC'))
            else:
                expiry_aware = credentials.expiry
            return expiry_aware
        
        # Default to 1 hour from now
        return timezone.now() + timedelta(hours=1)
    
    def _discover_calendars_safely(self, account, credentials):
        """Discover calendars with safe defaults and error handling"""
        try:
            from googleapiclient.discovery import build
            service = build("calendar", "v3", credentials=credentials)
            
            all_calendars_result = service.calendarList().list().execute()
            all_calendars = all_calendars_result.get("items", [])
            
            # Use CalendarService for calendar creation
            calendar_service = CalendarService(self.user)
            
            calendars_created = 0
            for cal_item in all_calendars:
                from apps.calendars.models import Calendar
                
                calendar, cal_created = Calendar.objects.update_or_create(
                    calendar_account=account,
                    google_calendar_id=cal_item["id"],
                    defaults={
                        "name": cal_item.get("summary", "Unnamed Calendar"),
                        "is_primary": cal_item.get("primary", False),
                        "description": cal_item.get("description", ""),
                        "color": cal_item.get("backgroundColor", ""),
                        "sync_enabled": False,  # SAFE DEFAULT - require explicit opt-in
                    },
                )
                if cal_created:
                    calendars_created += 1
            
            return {
                'calendars_found': len(all_calendars),
                'calendars_created': calendars_created
            }
            
        except Exception as e:
            self.logger.error(f"Calendar discovery failed for {account.email}: {e}")
            return {
                'calendars_found': 0,
                'calendars_created': 0,
                'discovery_error': str(e)
            }
    
    def disconnect_account(self, account_id):
        """Safely disconnect an OAuth account"""
        try:
            account = CalendarAccount.objects.get(id=account_id, user=self.user)
            
            email = account.email
            calendar_count = account.calendars.count()
            
            with transaction.atomic():
                # Deactivate first, then delete
                account.is_active = False
                account.save()
                account.delete()
            
            self._log_operation(
                'account_disconnect',
                account_id=account_id,
                email=email,
                calendar_count=calendar_count
            )
            
            return {
                'success': True,
                'message': f"Disconnected {email} and removed {calendar_count} calendars."
            }
            
        except CalendarAccount.DoesNotExist:
            raise OAuthError(f"Account {account_id} not found")
        except Exception as e:
            self._handle_error(e, 'account_disconnect', account_id=account_id)
            raise
```

### Enhanced Models
```python
# apps/calendars/models.py - Add to Calendar model

class Calendar(models.Model):
    # ... existing fields ...
    
    def toggle_sync(self):
        """Toggle sync status - business logic in model"""
        self.sync_enabled = not self.sync_enabled
        self.save(update_fields=['sync_enabled'])
        return self.sync_enabled
    
    def can_sync(self):
        """Check if calendar can be synced"""
        return (
            self.sync_enabled and 
            self.calendar_account.is_active and
            not self.calendar_account.is_token_expired()
        )
    
    def get_sync_status_display(self):
        """Human-readable sync status"""
        if not self.calendar_account.is_active:
            return "Account Inactive"
        elif self.calendar_account.is_token_expired():
            return "Token Expired"
        elif not self.sync_enabled:
            return "Sync Disabled"
        else:
            return "Sync Enabled"
    
    def get_last_sync_time(self):
        """Get last successful sync time"""
        last_sync = self.calendar_account.sync_logs.filter(
            success=True
        ).order_by('-completed_at').first()
        
        return last_sync.completed_at if last_sync else None

# Add to CalendarAccount model
class CalendarAccount(models.Model):
    # ... existing fields ...
    
    def is_token_expired(self):
        """Check if token is expired"""
        if not self.token_expires_at:
            return True
        return timezone.now() >= self.token_expires_at
    
    def needs_token_refresh(self, buffer_minutes=5):
        """Check if token needs refresh"""
        if not self.token_expires_at:
            return True
        buffer_time = timedelta(minutes=buffer_minutes)
        return timezone.now() + buffer_time >= self.token_expires_at
    
    def get_calendar_stats(self):
        """Get statistics for this account's calendars"""
        return {
            'total_calendars': self.calendars.count(),
            'sync_enabled_calendars': self.calendars.filter(sync_enabled=True).count(),
            'last_sync': self.sync_logs.filter(success=True).order_by('-completed_at').first()
        }
```

### Refactored Views
```python
# apps/dashboard/views.py - After business logic extraction

@login_required  
@require_POST
@csrf_protect
def toggle_calendar_sync(request: HttpRequest, calendar_id: int) -> HttpResponse:
    """Toggle sync status - thin view using service layer"""
    try:
        # Use service for business logic
        calendar_service = CalendarService(request.user)
        calendar = calendar_service.toggle_calendar_sync(calendar_id)
        
        # Return updated partial template
        return render(request, "dashboard/partials/calendar_sync_status.html", {
            "calendar": calendar
        })
        
    except CalendarNotFoundError:
        return HttpResponse("Calendar not found", status=404)
    except PermissionError:
        return HttpResponse("Access denied", status=403)
    except Exception as e:
        logger.error(f"Toggle failed for calendar {calendar_id}: {e}")
        return HttpResponse("Internal error", status=500)

def refresh_calendars(request: HttpRequest, account_id: int) -> HttpResponse:
    """Refresh calendars - thin view using service layer"""
    try:
        # Use service for business logic
        calendar_service = CalendarService(request.user)
        result = calendar_service.refresh_calendar_list(account_id)
        
        # Add user message
        if result['calendars_created'] > 0:
            messages.success(
                request,
                f"Refreshed calendars: found {result['calendars_found']}, "
                f"added {result['calendars_created']} new calendars."
            )
        else:
            messages.success(
                request,
                f"Refreshed calendars: {result['calendars_found']} calendars found, all up to date."
            )
            
        return redirect("dashboard:account_detail", account_id=account_id)
        
    except CalendarNotFoundError:
        messages.error(request, "Account not found.")
        return redirect("dashboard:index")
    except ValidationError as e:
        messages.error(request, str(e))
        return redirect("dashboard:account_detail", account_id=account_id)
    except Exception as e:
        logger.error(f"Calendar refresh failed for account {account_id}: {e}")
        messages.error(request, "Failed to refresh calendars. Please try again.")
        return redirect("dashboard:account_detail", account_id=account_id)
```

## Testing Requirements

### Service Layer Tests
- Test all service methods with various inputs
- Test error conditions and exception handling
- Test transaction safety and rollback scenarios
- Test user permission validation

### Integration Tests
- Test service layer integration with models
- Test view integration with services
- Test error propagation from services to views

### Business Logic Tests
- Test all business rules and validations
- Test edge cases and boundary conditions
- Test concurrent operations and race conditions

## Definition of Done

- [ ] All business logic extracted from views to services
- [ ] Service layer provides clean APIs for all operations
- [ ] Views handle only HTTP concerns (thin views)
- [ ] Model methods added for domain operations
- [ ] Custom managers created for complex queries
- [ ] No code duplication in business operations
- [ ] Comprehensive error handling in business layer
- [ ] All existing functionality preserved
- [ ] Service layer tests achieve 95%+ coverage
- [ ] Views are thin and focused
- [ ] Clean separation of concerns achieved

## Success Metrics

- Views contain ≤20 lines of business logic
- Service methods are reusable across different contexts
- Business logic is unit testable independent of HTTP
- Error handling is consistent across all operations
- Code duplication eliminated in business operations
- New features can be added by extending services only

This refactoring creates a maintainable architecture where business logic is centralized, testable, and reusable while keeping views focused on their HTTP responsibilities.
# TASK-09: View Layer Optimization

## Priority: HIGH
## Estimated Time: 4-5 hours  
## Dependencies: TASK-07 (Critical Security Fixes)

## Problem Statement

Guilfoyle identified significant performance and architectural issues in the dashboard views that violate Django best practices and create maintainability problems:

### View Layer Issues Found:
1. **N+1 Query Problems**
   - Dashboard views loading related data inefficiently
   - Missing `select_related` and `prefetch_related` optimization
   - Unnecessary database hits in template rendering

2. **Fat Views Anti-Pattern**
   - Business logic mixed with presentation logic
   - Complex operations directly in view functions
   - Violation of single responsibility principle

3. **Poor Error Handling**
   - Generic error responses without context
   - No structured error logging
   - Missing user-friendly error messages

4. **Database Query Inefficiency**
   - Repeated queries for the same data
   - No query optimization for list views
   - Missing database indexes usage

## Acceptance Criteria

- [ ] All dashboard views optimized with proper prefetch/select_related
- [ ] N+1 queries eliminated (verified with Django Debug Toolbar)
- [ ] Views converted to class-based where appropriate
- [ ] Business logic extracted to service layer or model methods
- [ ] Comprehensive error handling implemented
- [ ] Structured logging added throughout
- [ ] Database queries optimized and measured
- [ ] All existing functionality preserved
- [ ] Performance tests show measurable improvement
- [ ] All tests pass after refactoring

## Implementation Steps

### Step 1: Database Query Optimization (2 hours)

1. **Audit Current Query Patterns**
   - Install Django Debug Toolbar for development
   - Identify N+1 query problems
   - Measure baseline query counts

2. **Optimize Dashboard Views**
   - Add `select_related` for foreign keys
   - Add `prefetch_related` for many-to-many and reverse foreign keys
   - Use `only()` and `defer()` where appropriate

3. **Optimize Account Detail Views**
   - Prefetch calendars and sync logs
   - Optimize related data loading
   - Reduce database round trips

### Step 2: Convert to Class-Based Views (1.5 hours)

1. **Convert Dashboard Views**
   - Replace function-based views with class-based
   - Use appropriate generic views (ListView, DetailView)
   - Maintain existing URL patterns

2. **Add Proper Mixins**
   - Use LoginRequiredMixin consistently
   - Add custom mixins for common functionality
   - Implement proper permission checking

3. **Optimize Context Data**
   - Override get_context_data efficiently
   - Avoid duplicate queries
   - Cache expensive operations

### Step 3: Extract Business Logic (1.5 hours)

1. **Create Service Layer**
   - Extract calendar operations to CalendarService
   - Move dashboard stats calculation to DashboardService
   - Create proper abstraction layers

2. **Add Model Methods**
   - Move calendar-specific logic to Calendar model
   - Add convenience methods for common operations
   - Use model managers for complex queries

3. **Simplify View Logic**
   - Views should only handle HTTP concerns
   - Delegate business logic to services
   - Keep views thin and focused

## Files to Modify

### View Optimization
- `apps/dashboard/views.py` - Complete refactor to class-based views
- New: `apps/dashboard/services.py` - Business logic extraction
- New: `apps/dashboard/mixins.py` - Custom mixins for common functionality

### Model Enhancements  
- `apps/calendars/models.py` - Add model methods and managers
- `apps/accounts/models.py` - Add user-related query optimizations

### Configuration
- `calendar_sync/settings.py` - Add Django Debug Toolbar for development
- `requirements.txt` - Add performance monitoring dependencies

### Testing
- `apps/dashboard/tests.py` - Update for class-based views
- New: `apps/dashboard/test_performance.py` - Performance tests

## Code Examples

### Optimized Dashboard View
```python
# apps/dashboard/views.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, DetailView
from django.db.models import Count, Q, Prefetch
from .services import DashboardService

class DashboardView(LoginRequiredMixin, TemplateView):
    """Optimized dashboard with proper query optimization"""
    template_name = 'dashboard/index.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Use service for business logic
        dashboard_service = DashboardService(self.request.user)
        context.update(dashboard_service.get_dashboard_context())
        
        return context

class AccountDetailView(LoginRequiredMixin, DetailView):
    """Optimized account detail with prefetch optimization"""
    model = CalendarAccount
    template_name = 'dashboard/account_detail.html'
    context_object_name = 'account'
    
    def get_queryset(self):
        """Optimize queries with proper prefetch"""
        return CalendarAccount.objects.filter(
            user=self.request.user
        ).select_related(
            'user'
        ).prefetch_related(
            Prefetch(
                'calendars',
                queryset=Calendar.objects.select_related().order_by('name')
            ),
            Prefetch(
                'sync_logs',
                queryset=SyncLog.objects.select_related().order_by('-started_at')[:20]
            )
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add additional context efficiently
        account = self.object
        context['calendars'] = account.calendars.all()  # Already prefetched
        context['recent_syncs'] = account.sync_logs.all()[:10]  # Already prefetched
        
        return context
```

### Dashboard Service Layer
```python
# apps/dashboard/services.py
from django.db.models import Count, Q, Max
from django.utils import timezone
from datetime import timedelta
from apps.calendars.models import Calendar, CalendarAccount, SyncLog

class DashboardService:
    """Service layer for dashboard business logic"""
    
    def __init__(self, user):
        self.user = user
    
    def get_dashboard_context(self):
        """Get all dashboard data in optimized queries"""
        # Single query for accounts with annotations
        accounts_data = self._get_accounts_with_stats()
        
        # Single query for recent sync logs
        recent_syncs = self._get_recent_sync_logs()
        
        # Calculate aggregate statistics
        stats = self._calculate_dashboard_stats(accounts_data)
        
        return {
            'calendar_accounts': accounts_data,
            'recent_syncs': recent_syncs,
            **stats
        }
    
    def _get_accounts_with_stats(self):
        """Get accounts with calendar counts in single query"""
        return CalendarAccount.objects.filter(
            user=self.user
        ).select_related(
            'user'
        ).prefetch_related(
            'calendars'
        ).annotate(
            calendar_count=Count('calendars'),
            active_calendar_count=Count('calendars', filter=Q(calendars__sync_enabled=True)),
            last_sync=Max('sync_logs__completed_at')
        ).order_by('email')
    
    def _get_recent_sync_logs(self):
        """Get recent sync logs optimized"""
        return SyncLog.objects.filter(
            calendar_account__user=self.user
        ).select_related(
            'calendar_account'
        ).order_by('-started_at')[:10]
    
    def _calculate_dashboard_stats(self, accounts_data):
        """Calculate dashboard statistics efficiently"""
        total_calendars = sum(account.calendar_count for account in accounts_data)
        active_accounts = sum(1 for account in accounts_data if account.is_active)
        
        # Get user profile with sync status
        profile = self.user.userprofile if hasattr(self.user, 'userprofile') else None
        sync_enabled = profile.sync_enabled if profile else False
        
        return {
            'total_calendars': total_calendars,
            'active_accounts': active_accounts,
            'sync_enabled': sync_enabled,
        }

class CalendarService:
    """Service layer for calendar operations"""
    
    @staticmethod
    def toggle_sync(calendar, user):
        """Toggle calendar sync with proper validation and logging"""
        if calendar.calendar_account.user != user:
            raise PermissionError("User does not own this calendar")
        
        old_status = calendar.sync_enabled
        calendar.sync_enabled = not calendar.sync_enabled
        calendar.save(update_fields=['sync_enabled'])
        
        action = "enabled" if calendar.sync_enabled else "disabled"
        logger.info(
            f"Calendar sync {action}",
            extra={
                'user_id': user.id,
                'calendar_id': calendar.id,
                'calendar_name': calendar.name,
                'old_status': old_status,
                'new_status': calendar.sync_enabled
            }
        )
        
        return calendar
    
    @staticmethod
    def get_user_calendars_optimized(user):
        """Get user's calendars with optimization"""
        return Calendar.objects.filter(
            calendar_account__user=user
        ).select_related(
            'calendar_account'
        ).order_by('calendar_account__email', 'name')
```

### Enhanced Model Methods
```python
# apps/calendars/models.py - Add to Calendar model

class CalendarQuerySet(models.QuerySet):
    """Custom queryset for Calendar model"""
    
    def for_user(self, user):
        """Filter calendars for specific user"""
        return self.filter(calendar_account__user=user)
    
    def sync_enabled(self):
        """Filter only sync-enabled calendars"""
        return self.filter(sync_enabled=True)
    
    def with_account_data(self):
        """Prefetch account data efficiently"""
        return self.select_related('calendar_account__user')

class CalendarManager(models.Manager):
    """Custom manager for Calendar model"""
    
    def get_queryset(self):
        return CalendarQuerySet(self.model, using=self._db)
    
    def for_user(self, user):
        return self.get_queryset().for_user(user)
    
    def sync_enabled(self):
        return self.get_queryset().sync_enabled()

class Calendar(models.Model):
    # ... existing fields ...
    
    objects = CalendarManager()
    
    def toggle_sync(self):
        """Toggle sync status for this calendar"""
        self.sync_enabled = not self.sync_enabled
        self.save(update_fields=['sync_enabled'])
        return self.sync_enabled
    
    def can_be_synced(self):
        """Check if calendar can be synced"""
        return (
            self.sync_enabled and 
            self.calendar_account.is_active and
            self.calendar_account.user.is_active
        )
    
    @property
    def sync_status_display(self):
        """Human-readable sync status"""
        if not self.calendar_account.is_active:
            return "Account Inactive"
        elif not self.sync_enabled:
            return "Sync Disabled"
        else:
            return "Sync Enabled"
```

### Performance Testing
```python
# apps/dashboard/test_performance.py
from django.test import TestCase, override_settings
from django.test.utils import override_settings
from django.db import connection
from django.contrib.auth.models import User
from apps.calendars.models import Calendar, CalendarAccount

class ViewPerformanceTest(TestCase):
    """Test view performance and query optimization"""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@example.com', 'pass')
        
        # Create test data
        for i in range(5):
            account = CalendarAccount.objects.create(
                user=self.user,
                email=f'test{i}@gmail.com',
                google_account_id=f'account{i}',
                is_active=True,
                token_expires_at=timezone.now() + timedelta(hours=1)
            )
            
            # Create calendars for each account
            for j in range(3):
                Calendar.objects.create(
                    calendar_account=account,
                    google_calendar_id=f'cal{i}_{j}',
                    name=f'Calendar {i}_{j}',
                    sync_enabled=j % 2 == 0  # Alternate enabled/disabled
                )
    
    def test_dashboard_query_count(self):
        """Test dashboard view query efficiency"""
        self.client.login(username='testuser', password='pass')
        
        with self.assertNumQueries(3):  # Should be 3 or fewer queries
            response = self.client.get('/dashboard/')
        
        self.assertEqual(response.status_code, 200)
    
    def test_account_detail_query_count(self):
        """Test account detail view query efficiency"""
        account = CalendarAccount.objects.filter(user=self.user).first()
        self.client.login(username='testuser', password='pass')
        
        with self.assertNumQueries(2):  # Should be 2 or fewer queries
            response = self.client.get(f'/account/{account.id}/')
        
        self.assertEqual(response.status_code, 200)
    
    def test_calendar_service_performance(self):
        """Test service layer query efficiency"""
        from apps.dashboard.services import DashboardService
        
        service = DashboardService(self.user)
        
        with self.assertNumQueries(3):  # Should be efficient
            context = service.get_dashboard_context()
        
        self.assertIn('calendar_accounts', context)
        self.assertIn('total_calendars', context)
```

## Testing Requirements

### Performance Tests
- Query count assertions for all views
- Database query optimization verification
- Load testing with multiple users and data

### Functionality Tests  
- All existing view functionality preserved
- Class-based view behavior matches original
- Service layer operations work correctly

### Integration Tests
- Dashboard statistics calculated correctly
- Account detail shows all required data
- Error handling works across all views

## Definition of Done

- [ ] All dashboard views use optimized queries (≤3 queries per page)
- [ ] Class-based views implemented with proper mixins
- [ ] Business logic extracted to service layer
- [ ] Model methods added for common operations
- [ ] Error handling implemented throughout
- [ ] Performance tests passing with query limits
- [ ] All existing functionality preserved
- [ ] Django Debug Toolbar shows optimized queries
- [ ] Code review completed
- [ ] Documentation updated

## Success Metrics

- Dashboard page loads in ≤200ms with test data
- Account detail page uses ≤2 database queries
- No N+1 query patterns detected
- Service layer provides clean API for business operations
- Views are thin and focused on HTTP concerns only
- Error handling provides useful feedback to users

This optimization will make the dashboard significantly faster and more maintainable while following Django best practices.
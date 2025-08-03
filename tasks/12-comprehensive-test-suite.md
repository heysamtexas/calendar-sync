# TASK-12: Comprehensive Test Suite

## Priority: HIGH
## Estimated Time: 4-5 hours
## Dependencies: TASK-11 (OAuth Callback Hardening)

## Problem Statement

Guilfoyle identified significant gaps in test coverage and quality that compromise the reliability and maintainability of the codebase:

### Testing Issues Found:
1. **Inadequate Test Coverage**
   - Critical business logic lacks proper test coverage
   - Security features not adequately tested
   - Edge cases and error conditions untested
   - Integration between components not verified

2. **Poor Test Organization**
   - Tests scattered across different patterns
   - No consistent testing strategy
   - Missing test utilities and fixtures
   - No performance or load testing

3. **Security Testing Gaps**
   - CSRF protection not tested
   - OAuth security not validated
   - Input validation not comprehensive
   - No penetration testing framework

4. **Missing Test Types**
   - No integration tests for critical workflows
   - No API endpoint testing
   - No template security testing
   - No database transaction testing

## Acceptance Criteria

- [ ] Achieve ≥90% test coverage across all modules
- [ ] Comprehensive unit tests for all business logic
- [ ] Integration tests for critical user workflows
- [ ] Security tests for all attack vectors
- [ ] Performance tests for key operations
- [ ] Template tests for security and accessibility
- [ ] API endpoint tests with proper authentication
- [ ] Database transaction and rollback tests
- [ ] Test utilities and fixtures for maintainability
- [ ] CI/CD integration with quality gates

## Implementation Steps

### Step 1: Test Infrastructure Setup (1 hour)

1. **Test Configuration Enhancement**
   - Configure Django test settings
   - Set up test database configuration
   - Configure coverage reporting
   - Add performance testing framework

2. **Test Utilities and Fixtures**
   - Create reusable test fixtures
   - Build test data factories
   - Add authentication test helpers
   - Create API testing utilities

3. **Coverage Tools Integration**
   - Configure coverage.py with exclusions
   - Set up HTML coverage reports
   - Add coverage quality gates
   - Configure CI/CD coverage reporting

### Step 2: Core Business Logic Tests (2 hours)

1. **Model Testing**
   - Test all model methods and properties
   - Test model validation and constraints
   - Test custom managers and querysets
   - Test model relationships and cascades

2. **Service Layer Testing**
   - Test all service methods with various inputs
   - Test business logic edge cases
   - Test error handling and exceptions
   - Test transaction safety and rollbacks

3. **Utility Function Testing**
   - Test token encryption/decryption
   - Test calendar sync utilities
   - Test date/time handling functions
   - Test security validation functions

### Step 3: Security and Integration Tests (1.5 hours)

1. **Security Testing Framework**
   - Test CSRF protection on all endpoints
   - Test OAuth security implementation
   - Test input validation and sanitization
   - Test authorization and permissions

2. **Integration Testing**
   - Test complete OAuth flow
   - Test calendar sync workflow
   - Test user management operations
   - Test error handling across boundaries

3. **API Endpoint Testing**
   - Test all view endpoints
   - Test HTMX partial rendering
   - Test authentication requirements
   - Test error response handling

### Step 4: Performance and Load Testing (30 minutes)

1. **Performance Benchmarks**
   - Test database query performance
   - Test view response times
   - Test sync operation performance
   - Test concurrent user scenarios

2. **Load Testing**
   - Test OAuth endpoint under load
   - Test sync operations with large datasets
   - Test database connection pooling
   - Test memory usage patterns

## Files to Create/Modify

### Test Infrastructure
- `src/calendar_sync/test_settings.py` - Test-specific Django settings
- `tests/conftest.py` - Pytest configuration and fixtures
- `tests/factories.py` - Test data factories using factory_boy
- `tests/utils.py` - Common test utilities and helpers

### Comprehensive Test Files
- `apps/calendars/tests/test_models_comprehensive.py` - Complete model testing
- `apps/calendars/tests/test_services_comprehensive.py` - Service layer testing
- `apps/accounts/tests/test_oauth_comprehensive.py` - Complete OAuth testing
- `apps/dashboard/tests/test_views_comprehensive.py` - Complete view testing

### Security Testing
- `tests/security/test_csrf_protection.py` - CSRF testing
- `tests/security/test_oauth_security.py` - OAuth security testing
- `tests/security/test_input_validation.py` - Input validation testing
- `tests/security/test_authorization.py` - Authorization testing

### Integration Testing
- `tests/integration/test_oauth_flow.py` - Complete OAuth workflow
- `tests/integration/test_sync_workflow.py` - Calendar sync workflow
- `tests/integration/test_user_workflows.py` - End-to-end user scenarios

### Performance Testing
- `tests/performance/test_database_queries.py` - Query performance
- `tests/performance/test_view_performance.py` - View response times
- `tests/performance/test_sync_performance.py` - Sync operation benchmarks

## Code Examples

### Test Infrastructure Setup
```python
# tests/conftest.py
import pytest
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from unittest.mock import Mock, patch
from apps.calendars.models import Calendar, CalendarAccount
from apps.accounts.models import UserProfile

@pytest.fixture
def test_user():
    """Create a test user"""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )

@pytest.fixture
def test_calendar_account(test_user):
    """Create a test calendar account"""
    return CalendarAccount.objects.create(
        user=test_user,
        email='test@gmail.com',
        google_account_id='test_account_123',
        is_active=True,
        token_expires_at=timezone.now() + timedelta(hours=1)
    )

@pytest.fixture
def test_calendar(test_calendar_account):
    """Create a test calendar"""
    return Calendar.objects.create(
        calendar_account=test_calendar_account,
        google_calendar_id='test_cal_123',
        name='Test Calendar',
        sync_enabled=True
    )

@pytest.fixture
def mock_google_service():
    """Mock Google Calendar service"""
    with patch('googleapiclient.discovery.build') as mock_build:
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        # Configure common mock responses
        mock_service.calendarList().list().execute.return_value = {
            'items': [
                {
                    'id': 'test_cal_123',
                    'summary': 'Test Calendar',
                    'primary': True,
                    'backgroundColor': '#1f4788'
                }
            ]
        }
        
        mock_service.events().list().execute.return_value = {
            'items': [],
            'nextSyncToken': 'sync_token_123'
        }
        
        yield mock_service

class BaseTestCase(TestCase):
    """Base test case with common setup"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
    
    def create_calendar_account(self, user=None, **kwargs):
        """Helper to create calendar account"""
        defaults = {
            'email': 'test@gmail.com',
            'google_account_id': 'test_account_123',
            'is_active': True,
            'token_expires_at': timezone.now() + timedelta(hours=1)
        }
        defaults.update(kwargs)
        
        return CalendarAccount.objects.create(
            user=user or self.user,
            **defaults
        )
    
    def create_calendar(self, account=None, **kwargs):
        """Helper to create calendar"""
        if account is None:
            account = self.create_calendar_account()
        
        defaults = {
            'google_calendar_id': 'test_cal_123',
            'name': 'Test Calendar',
            'sync_enabled': False
        }
        defaults.update(kwargs)
        
        return Calendar.objects.create(
            calendar_account=account,
            **defaults
        )
```

### Comprehensive Model Tests
```python
# apps/calendars/tests/test_models_comprehensive.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, Mock
from apps.calendars.models import Calendar, CalendarAccount, Event, SyncLog
from apps.accounts.models import UserProfile
from tests.conftest import BaseTestCase

class CalendarModelTest(BaseTestCase):
    """Comprehensive tests for Calendar model"""
    
    def test_calendar_creation_with_all_fields(self):
        """Test calendar creation with all optional fields"""
        account = self.create_calendar_account()
        
        calendar = Calendar.objects.create(
            calendar_account=account,
            google_calendar_id='cal_123',
            name='Work Calendar',
            description='My work calendar',
            color='#1f4788',
            is_primary=True,
            sync_enabled=True
        )
        
        self.assertEqual(calendar.name, 'Work Calendar')
        self.assertEqual(calendar.description, 'My work calendar')
        self.assertEqual(calendar.color, '#1f4788')
        self.assertTrue(calendar.is_primary)
        self.assertTrue(calendar.sync_enabled)
    
    def test_calendar_str_representation(self):
        """Test calendar string representation"""
        calendar = self.create_calendar(name='Test Calendar')
        self.assertEqual(str(calendar), 'Test Calendar')
    
    def test_toggle_sync_method(self):
        """Test calendar sync toggle functionality"""
        calendar = self.create_calendar(sync_enabled=False)
        
        # Test enable sync
        result = calendar.toggle_sync()
        self.assertTrue(result)
        self.assertTrue(calendar.sync_enabled)
        
        # Test disable sync
        result = calendar.toggle_sync()
        self.assertFalse(result)
        self.assertFalse(calendar.sync_enabled)
    
    def test_can_sync_property(self):
        """Test can_sync property logic"""
        account = self.create_calendar_account(is_active=True)
        calendar = self.create_calendar(account=account, sync_enabled=True)
        
        # Should be able to sync when all conditions met
        self.assertTrue(calendar.can_sync())
        
        # Should not sync when sync disabled
        calendar.sync_enabled = False
        calendar.save()
        self.assertFalse(calendar.can_sync())
        
        # Should not sync when account inactive
        calendar.sync_enabled = True
        account.is_active = False
        account.save()
        self.assertFalse(calendar.can_sync())
    
    def test_sync_status_display(self):
        """Test sync status display logic"""
        account = self.create_calendar_account(is_active=True)
        calendar = self.create_calendar(account=account, sync_enabled=True)
        
        # Active and enabled
        self.assertEqual(calendar.get_sync_status_display(), 'Sync Enabled')
        
        # Disabled
        calendar.sync_enabled = False
        calendar.save()
        self.assertEqual(calendar.get_sync_status_display(), 'Sync Disabled')
        
        # Account inactive
        account.is_active = False
        account.save()
        self.assertEqual(calendar.get_sync_status_display(), 'Account Inactive')
        
        # Token expired
        account.is_active = True
        account.token_expires_at = timezone.now() - timedelta(hours=1)
        account.save()
        self.assertEqual(calendar.get_sync_status_display(), 'Token Expired')
    
    def test_calendar_validation(self):
        """Test calendar field validation"""
        account = self.create_calendar_account()
        
        # Test name length validation
        with self.assertRaises(ValidationError):
            calendar = Calendar(
                calendar_account=account,
                google_calendar_id='cal_123',
                name='x' * 256  # Exceeds max_length
            )
            calendar.full_clean()
        
        # Test Google calendar ID uniqueness per account
        Calendar.objects.create(
            calendar_account=account,
            google_calendar_id='cal_123',
            name='First Calendar'
        )
        
        # Should allow same google_calendar_id for different accounts
        other_account = self.create_calendar_account(
            google_account_id='other_account',
            email='other@gmail.com'
        )
        
        calendar2 = Calendar.objects.create(
            calendar_account=other_account,
            google_calendar_id='cal_123',  # Same ID, different account
            name='Second Calendar'
        )
        
        self.assertEqual(Calendar.objects.filter(google_calendar_id='cal_123').count(), 2)
    
    def test_calendar_manager_methods(self):
        """Test custom Calendar manager methods"""
        account = self.create_calendar_account()
        
        # Create test calendars
        enabled_cal = self.create_calendar(
            account=account,
            name='Enabled Calendar',
            sync_enabled=True
        )
        disabled_cal = self.create_calendar(
            account=account,
            name='Disabled Calendar',
            sync_enabled=False
        )
        
        # Test for_user method
        user_calendars = Calendar.objects.for_user(self.user)
        self.assertEqual(user_calendars.count(), 2)
        
        # Test sync_enabled method
        enabled_calendars = Calendar.objects.sync_enabled()
        self.assertEqual(enabled_calendars.count(), 1)
        self.assertEqual(enabled_calendars.first(), enabled_cal)
        
        # Test method chaining
        user_enabled = Calendar.objects.for_user(self.user).sync_enabled()
        self.assertEqual(user_enabled.count(), 1)

class CalendarAccountModelTest(BaseTestCase):
    """Comprehensive tests for CalendarAccount model"""
    
    def test_token_expiry_methods(self):
        """Test token expiry checking methods"""
        # Create account with future expiry
        account = CalendarAccount.objects.create(
            user=self.user,
            email='test@gmail.com',
            google_account_id='account_123',
            token_expires_at=timezone.now() + timedelta(hours=1)
        )
        
        # Should not be expired
        self.assertFalse(account.is_token_expired())
        self.assertFalse(account.needs_token_refresh())
        
        # Should need refresh within buffer
        self.assertTrue(account.needs_token_refresh(buffer_minutes=70))
        
        # Set to expired
        account.token_expires_at = timezone.now() - timedelta(hours=1)
        account.save()
        
        self.assertTrue(account.is_token_expired())
        self.assertTrue(account.needs_token_refresh())
    
    def test_calendar_stats_method(self):
        """Test calendar statistics calculation"""
        account = self.create_calendar_account()
        
        # Create test calendars
        self.create_calendar(account=account, sync_enabled=True)
        self.create_calendar(account=account, sync_enabled=False)
        self.create_calendar(account=account, sync_enabled=True)
        
        stats = account.get_calendar_stats()
        
        self.assertEqual(stats['total_calendars'], 3)
        self.assertEqual(stats['sync_enabled_calendars'], 2)
    
    @patch('apps.accounts.models.encrypt_token')
    @patch('apps.accounts.models.decrypt_token')
    def test_token_encryption_methods(self, mock_decrypt, mock_encrypt):
        """Test token encryption and decryption"""
        mock_encrypt.return_value = 'encrypted_token'
        mock_decrypt.return_value = 'decrypted_token'
        
        account = self.create_calendar_account()
        
        # Test setting access token
        account.set_access_token('access_token')
        mock_encrypt.assert_called_with('access_token')
        self.assertEqual(account.encrypted_access_token, 'encrypted_token')
        
        # Test getting access token
        result = account.get_access_token()
        mock_decrypt.assert_called_with('encrypted_token')
        self.assertEqual(result, 'decrypted_token')
```

### Security Test Suite
```python
# tests/security/test_csrf_protection.py
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from apps.calendars.models import Calendar, CalendarAccount
from tests.conftest import BaseTestCase

class CSRFProtectionTest(BaseTestCase):
    """Test CSRF protection on all endpoints"""
    
    def test_toggle_calendar_sync_requires_csrf(self):
        """Test calendar toggle requires CSRF token"""
        calendar = self.create_calendar()
        url = reverse('dashboard:toggle_calendar_sync', args=[calendar.id])
        
        # Test without CSRF token fails
        client = Client(enforce_csrf_checks=True)
        client.login(username='testuser', password='testpass123')
        
        response = client.post(url)
        self.assertEqual(response.status_code, 403)  # CSRF failure
        
        # Test with CSRF token succeeds
        response = client.get(reverse('dashboard:index'))  # Get CSRF token
        csrf_token = get_token(client.session)
        
        response = client.post(url, {'csrfmiddlewaretoken': csrf_token})
        self.assertEqual(response.status_code, 200)
    
    def test_htmx_requests_include_csrf(self):
        """Test HTMX requests properly include CSRF tokens"""
        calendar = self.create_calendar()
        url = reverse('dashboard:toggle_calendar_sync', args=[calendar.id])
        
        # Simulate HTMX request with CSRF header
        client = Client(enforce_csrf_checks=True)
        client.login(username='testuser', password='testpass123')
        
        # Get CSRF token
        response = client.get(reverse('dashboard:index'))
        csrf_token = get_token(client.session)
        
        # Test HTMX request with X-CSRFToken header
        response = client.post(
            url,
            HTTP_X_CSRFTOKEN=csrf_token,
            HTTP_HX_REQUEST='true'
        )
        self.assertEqual(response.status_code, 200)
    
    def test_oauth_callback_csrf_exempt(self):
        """Test OAuth callback is CSRF exempt (as required)"""
        url = reverse('accounts:oauth_callback')
        
        client = Client(enforce_csrf_checks=True)
        client.login(username='testuser', password='testpass123')
        
        # OAuth callback should work without CSRF token
        response = client.get(url + '?error=access_denied')
        self.assertEqual(response.status_code, 302)  # Redirect, not 403

class InputValidationTest(BaseTestCase):
    """Test input validation and sanitization"""
    
    def test_calendar_name_validation(self):
        """Test calendar name input validation"""
        account = self.create_calendar_account()
        
        # Test XSS attempt in calendar name
        malicious_name = '<script>alert("xss")</script>'
        
        calendar = Calendar.objects.create(
            calendar_account=account,
            google_calendar_id='cal_123',
            name=malicious_name
        )
        
        # Name should be stored as-is (Django templates will escape)
        self.assertEqual(calendar.name, malicious_name)
        
        # Test SQL injection attempt
        sql_name = "'; DROP TABLE calendars; --"
        
        calendar2 = Calendar.objects.create(
            calendar_account=account,
            google_calendar_id='cal_456',
            name=sql_name
        )
        
        # Should be stored safely
        self.assertEqual(calendar2.name, sql_name)
        
        # Verify original calendar still exists
        self.assertTrue(Calendar.objects.filter(id=calendar.id).exists())
```

### Performance Test Suite
```python
# tests/performance/test_database_queries.py
from django.test import TestCase, TransactionTestCase
from django.test.utils import override_settings
from django.db import connection
from django.contrib.auth.models import User
from apps.dashboard.services import DashboardService
from apps.calendars.models import Calendar, CalendarAccount
from tests.conftest import BaseTestCase
import time

class DatabaseQueryPerformanceTest(BaseTestCase):
    """Test database query performance and N+1 issues"""
    
    def setUp(self):
        super().setUp()
        
        # Create test data
        for i in range(5):
            account = CalendarAccount.objects.create(
                user=self.user,
                email=f'test{i}@gmail.com',
                google_account_id=f'account_{i}',
                is_active=True,
                token_expires_at=timezone.now() + timedelta(hours=1)
            )
            
            # Create calendars for each account
            for j in range(3):
                Calendar.objects.create(
                    calendar_account=account,
                    google_calendar_id=f'cal_{i}_{j}',
                    name=f'Calendar {i}_{j}',
                    sync_enabled=j % 2 == 0
                )
    
    def test_dashboard_service_query_count(self):
        """Test dashboard service uses efficient queries"""
        service = DashboardService(self.user)
        
        # Reset query count
        connection.queries.clear()
        
        # Get dashboard context
        context = service.get_dashboard_context()
        
        # Should use ≤3 queries regardless of data size
        query_count = len(connection.queries)
        self.assertLessEqual(
            query_count, 3,
            f"Dashboard service used {query_count} queries, should be ≤3"
        )
        
        # Verify data is correct
        self.assertEqual(len(context['calendar_accounts']), 5)
        self.assertEqual(context['total_calendars'], 15)
    
    def test_calendar_list_performance(self):
        """Test calendar list view performance"""
        url = reverse('dashboard:index')
        
        connection.queries.clear()
        
        # Time the request
        start_time = time.time()
        response = self.client.get(url)
        end_time = time.time()
        
        # Should complete quickly
        response_time = end_time - start_time
        self.assertLess(response_time, 0.5, f"Dashboard took {response_time:.3f}s")
        
        # Should use reasonable number of queries
        query_count = len(connection.queries)
        self.assertLessEqual(query_count, 5)
        
        self.assertEqual(response.status_code, 200)
    
    def test_bulk_calendar_operations(self):
        """Test bulk calendar operations performance"""
        calendars = Calendar.objects.for_user(self.user)[:10]
        calendar_ids = list(calendars.values_list('id', flat=True))
        
        from apps.calendars.services.calendar_service import CalendarService
        service = CalendarService(self.user)
        
        connection.queries.clear()
        start_time = time.time()
        
        # Bulk toggle operation
        result = service.bulk_toggle_calendars(calendar_ids, enable=True)
        
        end_time = time.time()
        
        # Should be efficient
        response_time = end_time - start_time
        self.assertLess(response_time, 1.0)
        
        # Should use minimal queries
        query_count = len(connection.queries)
        self.assertLessEqual(query_count, 3)  # 1 for select, 1 for bulk update, 1 for logging
```

## Testing Requirements

### Coverage Targets
- **Overall Coverage**: ≥90% statement coverage
- **Critical Business Logic**: ≥95% coverage
- **Security Features**: 100% coverage
- **Model Methods**: 100% coverage

### Test Categories
- **Unit Tests**: All models, services, utilities
- **Integration Tests**: Complete user workflows
- **Security Tests**: All attack vectors and protections
- **Performance Tests**: Key operations and bottlenecks

### Quality Gates
- All tests must pass before merge
- Coverage must not decrease
- Performance benchmarks must be met
- Security tests must show no vulnerabilities

## Definition of Done

- [ ] ≥90% test coverage achieved across all modules
- [ ] All business logic covered by unit tests
- [ ] Critical workflows covered by integration tests
- [ ] Security features comprehensively tested
- [ ] Performance benchmarks established and met
- [ ] Test utilities and fixtures created for maintainability
- [ ] CI/CD integration with quality gates configured
- [ ] Test documentation complete
- [ ] Code review completed
- [ ] All existing functionality preserved

## Success Metrics

- Test coverage ≥90% with no critical gaps
- All security tests pass with zero vulnerabilities
- Performance tests show acceptable response times
- Integration tests validate complete user workflows
- Test suite runs in <2 minutes for fast feedback
- Zero flaky or intermittent test failures

This comprehensive test suite ensures code quality, security, and reliability while providing a solid foundation for continued development.
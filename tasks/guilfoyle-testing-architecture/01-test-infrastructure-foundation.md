# TASK GT-01: Test Infrastructure Foundation
## *"Proper foundations prevent architectural disasters"*

### Priority: HIGH - FOUNDATION
### Estimated Time: 2-3 hours
### Dependencies: 00-GUILFOYLE-TESTING-MANIFESTO.md
### Status: Ready for Implementation

---

## Problem Statement

Our current testing infrastructure violates every principle in the Guilfoyle Testing Manifesto:
- No consistent fixtures for real objects
- Mock setup scattered across files with different strategies
- No boundary-only mocking utilities
- Complex test configurations that hide actual test logic
- No shared patterns for the "mock external APIs only" approach

**Result**: Every new test becomes a unique snowflake of mock configuration.

---

## Acceptance Criteria

- [ ] Create `tests/conftest.py` with Guilfoyle-approved fixtures
- [ ] Establish boundary-only mocking utilities
- [ ] Provide real object factories for all core models
- [ ] Configure pytest with Django integration
- [ ] Set up test database configuration optimized for speed
- [ ] Create utilities for common testing scenarios
- [ ] Eliminate all existing `setUp()` methods with mock novels
- [ ] Validate fixtures work with both unit and integration tests

---

## Implementation Steps

### Step 1: Create Core Test Infrastructure (45 minutes)

#### A. Main Test Configuration
Create `tests/conftest.py` as the single source of truth for all test fixtures:

```python
"""
Guilfoyle-Approved Test Infrastructure
Mock at boundaries only. Test business outcomes.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings

from apps.calendars.models import CalendarAccount, Calendar, Event
from apps.accounts.models import UserProfile

# ============================================================================
# CORE FIXTURES - Real Objects, Minimal Mocking
# ============================================================================

@pytest.fixture
def test_user():
    """Create a real Django user - no mocking"""
    return User.objects.create_user(
        username='testuser',
        email='testuser@example.com',
        password='testpass123'
    )

@pytest.fixture
def authenticated_client(test_user):
    """Django test client with authenticated user"""
    client = Client()
    client.force_login(test_user)
    return client

@pytest.fixture
def calendar_account(test_user):
    """Real CalendarAccount with valid tokens"""
    return CalendarAccount.objects.create(
        user=test_user,
        google_account_id='test_google_account_123',
        email='testuser@gmail.com',
        access_token='valid_access_token_encrypted',
        refresh_token='valid_refresh_token_encrypted',
        token_expires_at=timezone.now() + timedelta(hours=1),
        is_active=True
    )

@pytest.fixture
def calendar(calendar_account):
    """Real Calendar object for testing"""
    return Calendar.objects.create(
        calendar_account=calendar_account,
        google_calendar_id='test_calendar_123',
        name='Test Calendar',
        description='Test calendar for integration tests',
        color='#1f4788',
        is_primary=False,
        sync_enabled=True
    )

@pytest.fixture
def inactive_calendar_account(test_user):
    """CalendarAccount that's inactive for testing edge cases"""
    return CalendarAccount.objects.create(
        user=test_user,
        google_account_id='inactive_account_456',
        email='inactive@gmail.com',
        access_token='expired_token',
        refresh_token='expired_refresh',
        token_expires_at=timezone.now() - timedelta(hours=1),
        is_active=False
    )

# ============================================================================
# BOUNDARY MOCKING - External APIs Only
# ============================================================================

@pytest.fixture
def mock_google_calendar_api():
    """
    Mock Google Calendar API at the boundary - THIS IS THE ONLY EXTERNAL MOCK
    
    Usage: Tests that need to mock Google API responses use this fixture.
    Tests that don't interact with Google don't need any mocking.
    """
    with patch('googleapiclient.discovery.build') as mock_build:
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        # Default successful responses - tests can override
        mock_service.calendarList().list().execute.return_value = {
            'items': [
                {
                    'id': 'test_calendar_123',
                    'summary': 'Test Calendar',
                    'description': 'Test calendar description',
                    'primary': False,
                    'backgroundColor': '#1f4788'
                }
            ]
        }
        
        mock_service.events().list().execute.return_value = {
            'items': [],
            'nextSyncToken': 'sync_token_abc123'
        }
        
        mock_service.events().insert().execute.return_value = {
            'id': 'created_event_123',
            'summary': 'Created Event',
            'status': 'confirmed'
        }
        
        mock_service.events().watch().execute.return_value = {
            'id': 'webhook_channel_123',
            'resourceId': 'resource_456',
            'expiration': str(int((timezone.now() + timedelta(days=7)).timestamp() * 1000))
        }
        
        yield mock_service

@pytest.fixture
def mock_google_oauth_api():
    """
    Mock Google OAuth API for authentication flows
    """
    with patch('google.auth.transport.requests.Request'), \
         patch('google_auth_oauthlib.flow.Flow') as mock_flow_class:
        
        # Mock OAuth flow
        mock_flow = Mock()
        mock_flow_class.from_client_config.return_value = mock_flow
        
        # Mock credentials
        mock_credentials = Mock()
        mock_credentials.token = 'mock_access_token'
        mock_credentials.refresh_token = 'mock_refresh_token'
        mock_credentials.expiry = timezone.now() + timedelta(hours=1)
        mock_flow.credentials = mock_credentials
        
        # Mock user info
        with patch('googleapiclient.discovery.build') as mock_build:
            mock_oauth_service = Mock()
            mock_build.return_value = mock_oauth_service
            mock_oauth_service.userinfo().get().execute.return_value = {
                'id': 'google_user_123',
                'email': 'testuser@gmail.com',
                'name': 'Test User',
                'picture': 'https://example.com/photo.jpg'
            }
            
            yield {
                'flow': mock_flow,
                'credentials': mock_credentials,
                'oauth_service': mock_oauth_service
            }

# ============================================================================
# TEST UTILITIES - Common Patterns
# ============================================================================

class BaseTestCase(TestCase):
    """
    Base test case following Guilfoyle principles
    
    - Provides real objects by default
    - Minimal setup, maximum clarity
    - Helper methods for common patterns
    """
    
    def setUp(self):
        """Minimal setup - only what every test needs"""
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='testpass123'
        )
        self.client.force_login(self.user)
    
    def create_calendar_account(self, **kwargs):
        """Factory method for calendar accounts"""
        defaults = {
            'user': self.user,
            'google_account_id': f'account_{id(self)}',
            'email': f'test{id(self)}@gmail.com',
            'access_token': 'valid_encrypted_token',
            'refresh_token': 'valid_refresh_token',
            'token_expires_at': timezone.now() + timedelta(hours=1),
            'is_active': True
        }
        defaults.update(kwargs)
        return CalendarAccount.objects.create(**defaults)
    
    def create_calendar(self, account=None, **kwargs):
        """Factory method for calendars"""
        if account is None:
            account = self.create_calendar_account()
        
        defaults = {
            'calendar_account': account,
            'google_calendar_id': f'calendar_{id(self)}',
            'name': f'Test Calendar {id(self)}',
            'sync_enabled': True
        }
        defaults.update(kwargs)
        return Calendar.objects.create(**defaults)
    
    def create_event(self, calendar=None, **kwargs):
        """Factory method for calendar events"""
        if calendar is None:
            calendar = self.create_calendar()
        
        defaults = {
            'calendar': calendar,
            'google_event_id': f'event_{id(self)}',
            'title': f'Test Event {id(self)}',
            'start_time': timezone.now(),
            'end_time': timezone.now() + timedelta(hours=1),
            'is_busy_block': False
        }
        defaults.update(kwargs)
        return Event.objects.create(**defaults)

# ============================================================================
# TESTING UTILITIES - Boundary Verification
# ============================================================================

def assert_no_external_calls_made():
    """
    Utility to verify tests don't make unexpected external API calls
    Use in tests that shouldn't touch external services
    """
    # This can be expanded to check for network calls, API usage, etc
    pass

def create_google_event_data(**kwargs):
    """
    Factory for Google Calendar event data structures
    Returns data in Google's expected format
    """
    defaults = {
        'id': 'google_event_123',
        'summary': 'Google Event',
        'description': 'Event from Google Calendar',
        'start': {
            'dateTime': timezone.now().isoformat(),
            'timeZone': 'UTC'
        },
        'end': {
            'dateTime': (timezone.now() + timedelta(hours=1)).isoformat(),
            'timeZone': 'UTC'
        },
        'status': 'confirmed',
        'visibility': 'default'
    }
    defaults.update(kwargs)
    return defaults

def create_webhook_headers(resource_id='test_resource', channel_id='test_channel'):
    """
    Factory for Google webhook headers
    """
    return {
        'HTTP_X_GOOG_RESOURCE_ID': resource_id,
        'HTTP_X_GOOG_CHANNEL_ID': channel_id,
        'HTTP_X_GOOG_RESOURCE_STATE': 'sync',
        'HTTP_X_GOOG_MESSAGE_NUMBER': '1'
    }
```

#### B. Pytest Configuration
Create `pytest.ini` in project root:

```ini
[tool:pytest]
DJANGO_SETTINGS_MODULE = calendar_sync.test_settings
python_files = tests.py test_*.py *_tests.py
python_classes = Test* *Tests
python_functions = test_*
addopts = 
    --verbose
    --strict-markers
    --strict-config
    --disable-socket
    --allow-unix-socket
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (slower, multiple components)
    external: Tests that require external API mocking
```

#### C. Test-Specific Django Settings
Create `src/calendar_sync/test_settings.py`:

```python
"""
Test-specific Django settings
Optimized for speed and isolation
"""

from .settings import *

# Use in-memory SQLite for speed
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
        'OPTIONS': {
            'timeout': 20,
        }
    }
}

# Disable migrations for speed
class DisableMigrations:
    def __contains__(self, item):
        return True
    
    def __getitem__(self, item):
        return None

MIGRATION_MODULES = DisableMigrations()

# Disable logging during tests unless explicitly enabled
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
        'apps': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
    },
}

# Speed up password hashing
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Disable caching
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Fast email backend
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Disable debug toolbar
DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': lambda request: False,
}

# Test-specific settings
SECRET_KEY = 'test-secret-key-not-for-production'
DEBUG = False  # Test as close to production as possible
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']

# Disable external API calls by default
GOOGLE_OAUTH_CLIENT_ID = 'test_client_id'
GOOGLE_OAUTH_CLIENT_SECRET = 'test_client_secret'
WEBHOOK_BASE_URL = 'http://testserver'
```

### Step 2: Create Test Organization Structure (30 minutes)

Create the following directory structure:
```
tests/
├── conftest.py                    # Main fixtures (created above)
├── __init__.py
├── unit/                          # Fast, isolated tests
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_services.py
│   └── test_utilities.py
├── integration/                   # Multi-component tests
│   ├── __init__.py
│   ├── test_oauth_flow.py
│   ├── test_calendar_sync.py
│   └── test_webhook_processing.py
└── utilities/                     # Test helper modules
    ├── __init__.py
    ├── factories.py               # Advanced object factories
    └── assertions.py              # Custom assertion helpers
```

#### Create `tests/utilities/factories.py`:
```python
"""
Advanced object factories for complex test scenarios
"""

import factory
from django.contrib.auth.models import User
from datetime import datetime, timedelta
from django.utils import timezone

from apps.calendars.models import CalendarAccount, Calendar, Event

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f'user{n}')
    email = factory.LazyAttribute(lambda obj: f'{obj.username}@example.com')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')

class CalendarAccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CalendarAccount
    
    user = factory.SubFactory(UserFactory)
    google_account_id = factory.Faker('uuid4')
    email = factory.LazyAttribute(lambda obj: f'{obj.user.username}@gmail.com')
    access_token = 'encrypted_access_token'
    refresh_token = 'encrypted_refresh_token'
    token_expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(hours=1))
    is_active = True

class CalendarFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Calendar
    
    calendar_account = factory.SubFactory(CalendarAccountFactory)
    google_calendar_id = factory.Faker('uuid4')
    name = factory.Faker('sentence', nb_words=3)
    description = factory.Faker('text', max_nb_chars=200)
    color = '#1f4788'
    sync_enabled = True

class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Event
    
    calendar = factory.SubFactory(CalendarFactory)
    google_event_id = factory.Faker('uuid4')
    title = factory.Faker('sentence', nb_words=4)
    description = factory.Faker('text', max_nb_chars=500)
    start_time = factory.LazyFunction(timezone.now)
    end_time = factory.LazyAttribute(lambda obj: obj.start_time + timedelta(hours=1))
    is_busy_block = False
```

#### Create `tests/utilities/assertions.py`:
```python
"""
Custom assertion helpers for common testing patterns
"""

def assert_calendar_synced(calendar, expected_events_count=None):
    """Assert calendar is properly synced"""
    assert calendar.sync_enabled
    assert calendar.calendar_account.is_active
    
    if expected_events_count is not None:
        assert calendar.events.count() == expected_events_count

def assert_webhook_processed(webhook_request):
    """Assert webhook was processed successfully"""
    assert webhook_request.processed_at is not None
    assert webhook_request.status == 'success'

def assert_oauth_flow_completed(user, google_account_id):
    """Assert OAuth flow created proper account"""
    account = user.calendar_accounts.get(google_account_id=google_account_id)
    assert account.is_active
    assert account.access_token
    assert account.refresh_token
    assert account.token_expires_at > timezone.now()
```

### Step 3: Validation and Testing (30 minutes)

Create a simple validation test to ensure the infrastructure works:

```python
# tests/test_infrastructure.py
"""
Test the test infrastructure itself
"""

import pytest
from django.test import TestCase
from tests.conftest import BaseTestCase
from tests.utilities.factories import CalendarAccountFactory, CalendarFactory

class TestInfrastructureTest(BaseTestCase):
    """Test that our testing infrastructure works correctly"""
    
    def test_base_test_case_setup(self):
        """Test BaseTestCase provides proper setup"""
        # Should have authenticated user
        self.assertIsNotNone(self.user)
        self.assertEqual(self.user.username, 'testuser')
        
        # Should have authenticated client
        response = self.client.get('/dashboard/')  # Assuming this requires auth
        self.assertNotEqual(response.status_code, 302)  # Not redirected to login
    
    def test_factory_methods(self):
        """Test factory methods create valid objects"""
        account = self.create_calendar_account()
        self.assertTrue(account.is_active)
        self.assertEqual(account.user, self.user)
        
        calendar = self.create_calendar(account=account)
        self.assertTrue(calendar.sync_enabled)
        self.assertEqual(calendar.calendar_account, account)

@pytest.mark.django_db
def test_fixtures_work(test_user, calendar_account, calendar):
    """Test that pytest fixtures work correctly"""
    assert test_user.username == 'testuser'
    assert calendar_account.user == test_user
    assert calendar.calendar_account == calendar_account
    assert calendar.sync_enabled

@pytest.mark.django_db
def test_google_api_mocking(mock_google_calendar_api, calendar):
    """Test that Google API mocking works"""
    # This would be a real test that uses the Google API client
    # The mock should provide predictable responses
    from apps.calendars.services.google_calendar_client import GoogleCalendarClient
    
    client = GoogleCalendarClient(calendar.calendar_account)
    calendars = client.list_calendars()
    
    # Should get mocked response
    assert len(calendars) == 1
    assert calendars[0]['id'] == 'test_calendar_123'
    
    # Verify mock was called
    mock_google_calendar_api.calendarList().list().execute.assert_called_once()

def test_factory_boy_integration():
    """Test that factory_boy factories work"""
    account = CalendarAccountFactory()
    assert account.user is not None
    assert account.is_active
    
    calendar = CalendarFactory(calendar_account=account)
    assert calendar.calendar_account == account
    assert calendar.sync_enabled
```

---

## Files to Create/Modify

### New Files:
- `tests/conftest.py` - Core fixtures and utilities
- `src/calendar_sync/test_settings.py` - Test-optimized Django settings  
- `pytest.ini` - Pytest configuration
- `tests/utilities/factories.py` - Advanced object factories
- `tests/utilities/assertions.py` - Custom assertion helpers
- `tests/test_infrastructure.py` - Infrastructure validation tests

### Directory Structure:
```
tests/
├── conftest.py
├── unit/
├── integration/
└── utilities/
```

---

## Validation Steps

1. **Run Infrastructure Tests**:
   ```bash
   cd src
   pytest tests/test_infrastructure.py -v
   ```

2. **Verify Fixture Loading**:
   ```bash
   pytest --fixtures-per-test
   ```

3. **Check Test Discovery**:
   ```bash
   pytest --collect-only
   ```

4. **Validate Mock Isolation**:
   ```bash
   pytest tests/test_infrastructure.py::test_google_api_mocking -v
   ```

---

## Success Criteria

- [ ] All infrastructure tests pass
- [ ] Fixtures provide real objects with minimal mocking
- [ ] Google API mocking works at boundary only
- [ ] Test database is fast (in-memory SQLite)
- [ ] Factory methods create valid objects
- [ ] No existing mock patterns are used
- [ ] Tests can use either pytest fixtures or BaseTestCase
- [ ] Clear separation between unit and integration test structure

---

## Definition of Done

- [ ] Test infrastructure follows all Guilfoyle principles from manifesto
- [ ] Boundary-only mocking utilities are functional
- [ ] Real object factories work for all core models
- [ ] Test configuration is optimized for speed
- [ ] Infrastructure tests validate the setup works
- [ ] Documentation explains how to use new patterns
- [ ] No existing mock patterns are referenced or used

This foundation enables all subsequent testing tasks to follow the Guilfoyle principles without requiring repeated infrastructure setup.
# TASK-13: Code Quality Improvements

## Priority: MEDIUM
## Estimated Time: 3-4 hours
## Dependencies: TASK-12 (Comprehensive Test Suite)

## Problem Statement

Guilfoyle identified several code quality issues that, while not critical, reduce maintainability, readability, and long-term stability of the codebase:

### Code Quality Issues Found:
1. **Complexity and Maintainability**
   - Some functions exceed complexity thresholds
   - Repetitive code patterns not extracted
   - Inconsistent error handling patterns
   - Missing documentation for complex logic

2. **Type Safety and Validation**
   - Missing type hints throughout codebase
   - Insufficient input validation in some areas
   - No static type checking integration
   - Inconsistent parameter validation

3. **Code Organization**
   - Some modules lack clear separation of concerns
   - Constants scattered throughout files
   - No centralized configuration management
   - Missing utility functions for common operations

4. **Development Experience**
   - No pre-commit hooks for code quality
   - Inconsistent coding standards
   - Missing developer documentation
   - No automated code formatting enforcement

## Acceptance Criteria

- [ ] All functions have cyclomatic complexity ≤8
- [ ] Type hints added to all public functions and methods
- [ ] Consistent error handling patterns throughout
- [ ] Code duplication eliminated via extraction
- [ ] Pre-commit hooks configured for quality enforcement
- [ ] Static type checking integrated
- [ ] Developer documentation updated
- [ ] All ruff quality rules passing
- [ ] Performance optimizations where identified
- [ ] Code review standards documented

## Implementation Steps

### Step 1: Complexity Reduction and Refactoring (2 hours)

1. **Identify Complex Functions**
   - Run complexity analysis with ruff
   - Identify functions exceeding complexity threshold
   - Document refactoring plan for each

2. **Extract Common Patterns**
   - Identify repeated code patterns
   - Extract utility functions and decorators
   - Create reusable components

3. **Refactor Complex Functions**
   - Break down complex functions into smaller methods
   - Use early returns and guard clauses
   - Extract business logic into named methods

### Step 2: Type Safety Implementation (1 hour)

1. **Add Type Hints**
   - Add type hints to all public functions
   - Add return type annotations
   - Use Union types for optional parameters

2. **Static Type Checking**
   - Configure mypy for Django
   - Add mypy to pre-commit hooks
   - Fix initial type checking errors

3. **Enhanced Validation**
   - Add runtime type validation where needed
   - Improve parameter validation
   - Add input sanitization

### Step 3: Code Organization and Standards (1 hour)

1. **Constants and Configuration**
   - Extract magic numbers to named constants
   - Centralize configuration values
   - Create settings validation

2. **Developer Tooling**
   - Configure pre-commit hooks
   - Add code formatting automation
   - Set up development documentation

3. **Code Standards Documentation**
   - Document coding standards
   - Create code review checklist
   - Add contribution guidelines

## Files to Create/Modify

### Code Quality Infrastructure
- `.pre-commit-config.yaml` - Pre-commit hooks configuration
- `pyproject.toml` - Enhanced linting and type checking rules
- `mypy.ini` - MyPy configuration for Django
- `src/calendar_sync/constants.py` - Centralized constants

### Refactored Modules
- `apps/calendars/services/calendar_service.py` - Reduce complexity
- `apps/accounts/services/oauth_service.py` - Type hints and refactoring
- `apps/dashboard/services/dashboard_service.py` - Performance optimizations
- `apps/calendars/utils.py` - Extracted utility functions

### Documentation
- `docs/DEVELOPMENT.md` - Developer guidelines
- `docs/CODE_STANDARDS.md` - Coding standards
- `docs/CONTRIBUTING.md` - Contribution guidelines

### Testing
- `tests/test_code_quality.py` - Code quality validation tests
- `tests/test_type_hints.py` - Type hint validation

## Code Examples

### Complexity Reduction Example
```python
# apps/calendars/services/calendar_service.py - BEFORE (Complex)
def sync_calendar_events(self, calendar_id, force_full_sync=False):
    """Sync events for a calendar - COMPLEX VERSION"""
    calendar = Calendar.objects.get(id=calendar_id)
    if not calendar.sync_enabled:
        return False
    
    if not calendar.calendar_account.is_active:
        logger.error(f"Account {calendar.calendar_account.email} is inactive")
        return False
    
    if calendar.calendar_account.is_token_expired():
        try:
            self._refresh_token(calendar.calendar_account)
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return False
    
    try:
        service = self._get_google_service(calendar.calendar_account)
        if force_full_sync:
            sync_token = None
        else:
            sync_token = calendar.last_sync_token
        
        events_result = service.events().list(
            calendarId=calendar.google_calendar_id,
            syncToken=sync_token,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        next_sync_token = events_result.get('nextSyncToken')
        
        for event in events:
            if event.get('status') == 'cancelled':
                self._handle_cancelled_event(calendar, event)
            else:
                self._sync_event(calendar, event)
        
        calendar.last_sync_token = next_sync_token
        calendar.last_sync_time = timezone.now()
        calendar.save()
        
        return True
        
    except Exception as e:
        logger.error(f"Sync failed for calendar {calendar.name}: {e}")
        return False

# AFTER (Refactored for clarity and lower complexity)
def sync_calendar_events(self, calendar_id: int, force_full_sync: bool = False) -> bool:
    """Sync events for a calendar - REFACTORED VERSION"""
    try:
        calendar = self._get_calendar_for_sync(calendar_id)
        if not self._can_sync_calendar(calendar):
            return False
        
        service = self._prepare_google_service(calendar.calendar_account)
        sync_token = None if force_full_sync else calendar.last_sync_token
        
        events_data = self._fetch_calendar_events(service, calendar, sync_token)
        self._process_event_changes(calendar, events_data['events'])
        self._update_calendar_sync_state(calendar, events_data['next_sync_token'])
        
        return True
        
    except CalendarSyncError as e:
        self._handle_sync_error(calendar_id, e)
        return False

def _get_calendar_for_sync(self, calendar_id: int) -> Calendar:
    """Get and validate calendar for sync operation"""
    try:
        return Calendar.objects.select_related('calendar_account').get(id=calendar_id)
    except Calendar.DoesNotExist:
        raise CalendarSyncError(f"Calendar {calendar_id} not found")

def _can_sync_calendar(self, calendar: Calendar) -> bool:
    """Check if calendar can be synced"""
    if not calendar.sync_enabled:
        self.logger.info(f"Sync disabled for calendar {calendar.name}")
        return False
    
    if not calendar.calendar_account.is_active:
        self.logger.warning(f"Account {calendar.calendar_account.email} is inactive")
        return False
    
    return True

def _prepare_google_service(self, account: CalendarAccount):
    """Prepare Google Calendar service with valid token"""
    if account.is_token_expired():
        self._refresh_account_token(account)
    
    return self._get_google_service(account)

def _fetch_calendar_events(self, service, calendar: Calendar, sync_token: str = None) -> dict:
    """Fetch events from Google Calendar"""
    try:
        events_result = service.events().list(
            calendarId=calendar.google_calendar_id,
            syncToken=sync_token,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        return {
            'events': events_result.get('items', []),
            'next_sync_token': events_result.get('nextSyncToken')
        }
        
    except Exception as e:
        raise CalendarSyncError(f"Failed to fetch events: {e}")

def _process_event_changes(self, calendar: Calendar, events: list) -> None:
    """Process event changes from Google Calendar"""
    for event in events:
        if event.get('status') == 'cancelled':
            self._handle_cancelled_event(calendar, event)
        else:
            self._sync_event(calendar, event)

def _update_calendar_sync_state(self, calendar: Calendar, next_sync_token: str) -> None:
    """Update calendar sync state after successful sync"""
    calendar.last_sync_token = next_sync_token
    calendar.last_sync_time = timezone.now()
    calendar.save(update_fields=['last_sync_token', 'last_sync_time'])
```

### Type Hints Implementation
```python
# apps/calendars/services/calendar_service.py - With comprehensive type hints
from typing import Dict, List, Optional, Union, Any
from django.contrib.auth.models import User
from django.db.models import QuerySet
from apps.calendars.models import Calendar, CalendarAccount

class CalendarService:
    """Service for calendar business operations with type safety"""
    
    def __init__(self, user: User) -> None:
        self.user = user
        self.logger = logger.getChild(self.__class__.__name__)
    
    def toggle_calendar_sync(self, calendar_id: int) -> Calendar:
        """Toggle sync status for a calendar"""
        calendar = self._get_user_calendar(calendar_id)
        
        old_status = calendar.sync_enabled
        calendar.sync_enabled = not calendar.sync_enabled
        calendar.save(update_fields=['sync_enabled'])
        
        self._log_sync_toggle(calendar, old_status)
        return calendar
    
    def bulk_toggle_calendars(
        self, 
        calendar_ids: List[int], 
        enable: bool = True
    ) -> List[Calendar]:
        """Toggle multiple calendars efficiently"""
        calendars = self._get_user_calendars(calendar_ids)
        updated_calendars: List[Calendar] = []
        
        with transaction.atomic():
            for calendar in calendars:
                if calendar.sync_enabled != enable:
                    calendar.sync_enabled = enable
                    calendar.save(update_fields=['sync_enabled'])
                    updated_calendars.append(calendar)
        
        self._log_bulk_toggle(updated_calendars, enable)
        return updated_calendars
    
    def get_user_calendar_stats(self) -> Dict[str, Union[int, str]]:
        """Get calendar statistics for user"""
        stats = CalendarAccount.objects.filter(
            user=self.user
        ).aggregate(
            total_accounts=Count('id'),
            active_accounts=Count('id', filter=Q(is_active=True)),
            total_calendars=Count('calendars'),
            sync_enabled_calendars=Count('calendars', filter=Q(calendars__sync_enabled=True))
        )
        
        return {
            'total_accounts': stats['total_accounts'] or 0,
            'active_accounts': stats['active_accounts'] or 0,
            'total_calendars': stats['total_calendars'] or 0,
            'sync_enabled_calendars': stats['sync_enabled_calendars'] or 0,
        }
    
    def _get_user_calendar(self, calendar_id: int) -> Calendar:
        """Get calendar owned by current user"""
        try:
            return Calendar.objects.select_related('calendar_account').get(
                id=calendar_id,
                calendar_account__user=self.user
            )
        except Calendar.DoesNotExist:
            raise CalendarNotFoundError(f"Calendar {calendar_id} not found")
    
    def _get_user_calendars(self, calendar_ids: List[int]) -> QuerySet[Calendar]:
        """Get calendars owned by current user"""
        return Calendar.objects.filter(
            id__in=calendar_ids,
            calendar_account__user=self.user
        ).select_related('calendar_account')
    
    def _log_sync_toggle(self, calendar: Calendar, old_status: bool) -> None:
        """Log sync toggle operation"""
        self.logger.info(
            'Calendar sync toggled',
            extra={
                'user_id': self.user.id,
                'calendar_id': calendar.id,
                'calendar_name': calendar.name,
                'old_status': old_status,
                'new_status': calendar.sync_enabled
            }
        )
    
    def _log_bulk_toggle(self, calendars: List[Calendar], enabled: bool) -> None:
        """Log bulk toggle operation"""
        self.logger.info(
            'Bulk calendar toggle completed',
            extra={
                'user_id': self.user.id,
                'calendar_count': len(calendars),
                'enabled': enabled,
                'calendar_ids': [cal.id for cal in calendars]
            }
        )
```

### Constants Extraction
```python
# src/calendar_sync/constants.py
"""Centralized constants for the application"""

# OAuth Configuration
OAUTH_SCOPES = [
    'https://www.googleapis.com/auth/calendar'
]
OAUTH_STATE_EXPIRY_MINUTES = 5
OAUTH_RATE_LIMIT_REQUESTS = 10
OAUTH_RATE_LIMIT_WINDOW_SECONDS = 300

# Calendar Sync Configuration
SYNC_TOKEN_EXPIRY_DAYS = 30
MAX_EVENTS_PER_SYNC = 1000
SYNC_RETRY_DELAY_SECONDS = 60
MAX_SYNC_RETRIES = 3

# Database Configuration
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

# Security Configuration
TOKEN_ENCRYPTION_ALGORITHM = 'AES-256-GCM'
SESSION_TIMEOUT_MINUTES = 60
PASSWORD_MIN_LENGTH = 12

# Google API Configuration
GOOGLE_API_REQUEST_TIMEOUT = 30
GOOGLE_API_MAX_RETRIES = 3
GOOGLE_API_DEFAULT_PAGE_SIZE = 250

# Busy Block Configuration
BUSY_BLOCK_TAG_PREFIX = "🔒 Busy - CalSync"
BUSY_BLOCK_DESCRIPTION_MAX_LENGTH = 200

# Error Messages
ERROR_MESSAGES = {
    'CALENDAR_NOT_FOUND': 'Calendar not found or access denied',
    'ACCOUNT_INACTIVE': 'Google Calendar account is inactive',
    'TOKEN_EXPIRED': 'Authentication token has expired',
    'SYNC_DISABLED': 'Calendar sync is disabled',
    'RATE_LIMIT_EXCEEDED': 'Too many requests, please try again later',
    'OAUTH_STATE_INVALID': 'Authentication request validation failed',
    'PERMISSION_DENIED': 'Insufficient permissions for this operation',
}

# Success Messages
SUCCESS_MESSAGES = {
    'CALENDAR_SYNC_ENABLED': 'Calendar sync enabled successfully',
    'CALENDAR_SYNC_DISABLED': 'Calendar sync disabled successfully',
    'ACCOUNT_CONNECTED': 'Google Calendar account connected successfully',
    'ACCOUNT_DISCONNECTED': 'Google Calendar account disconnected successfully',
    'SYNC_COMPLETED': 'Calendar synchronization completed successfully',
}

# Validation Rules
VALIDATION_RULES = {
    'CALENDAR_NAME_MAX_LENGTH': 200,
    'ACCOUNT_EMAIL_MAX_LENGTH': 254,
    'GOOGLE_CALENDAR_ID_MAX_LENGTH': 100,
    'SYNC_TOKEN_MAX_LENGTH': 500,
    'EVENT_TITLE_MAX_LENGTH': 300,
}

# Time Constants
TIME_CONSTANTS = {
    'SECONDS_PER_MINUTE': 60,
    'MINUTES_PER_HOUR': 60,
    'HOURS_PER_DAY': 24,
    'DAYS_PER_WEEK': 7,
}
```

### Pre-commit Configuration
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: debug-statements

  - repo: https://github.com/charliermarsh/ruff-pre-commit
    rev: v0.1.6
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.1
    hooks:
      - id: mypy
        additional_dependencies:
          - django-stubs
          - types-requests
        args: [--config-file=mypy.ini]

  - repo: https://github.com/adamchainz/django-upgrade
    rev: 1.15.0
    hooks:
      - id: django-upgrade
        args: [--target-version, "4.2"]

  - repo: https://github.com/pycqa/bandit
    rev: 1.7.5
    hooks:
      - id: bandit
        args: [-c, pyproject.toml]
        additional_dependencies: ["bandit[toml]"]

  - repo: local
    hooks:
      - id: django-tests
        name: Run Django tests
        entry: uv run python manage.py test
        language: system
        pass_filenames: false
        stages: [pre-push]

      - id: coverage-check
        name: Check test coverage
        entry: uv run coverage run manage.py test && uv run coverage report --fail-under=85
        language: system
        pass_filenames: false
        stages: [pre-push]
```

### Enhanced MyPy Configuration
```ini
# mypy.ini
[mypy]
python_version = 3.11
check_untyped_defs = true
ignore_missing_imports = true
show_error_codes = true
warn_unused_ignores = true
warn_redundant_casts = true
warn_unused_configs = true

# Django-specific settings
plugins = mypy_django_plugin.main

[mypy.plugins.django-stubs]
django_settings_module = "calendar_sync.settings"

# Strict checking for our apps
[mypy-apps.calendars.*]
disallow_untyped_defs = true
disallow_any_generics = true
disallow_untyped_calls = true

[mypy-apps.accounts.*]
disallow_untyped_defs = true
disallow_any_generics = true
disallow_untyped_calls = true

[mypy-apps.dashboard.*]
disallow_untyped_defs = true
disallow_any_generics = true
disallow_untyped_calls = true

# Third-party modules
[mypy-google.*]
ignore_missing_imports = true

[mypy-googleapiclient.*]
ignore_missing_imports = true
```

## Testing Requirements

### Code Quality Validation
- All ruff rules must pass
- MyPy type checking must pass with no errors
- Complexity analysis must show all functions ≤8
- No code duplication detected by tools

### Performance Testing
- Refactored functions maintain or improve performance
- Type checking overhead acceptable
- Pre-commit hooks complete in <30 seconds

### Documentation Testing
- All public APIs documented
- Code examples in documentation work
- Development setup instructions validated

## Definition of Done

- [ ] All functions have cyclomatic complexity ≤8
- [ ] Type hints added to all public functions and methods
- [ ] Code duplication eliminated through extraction
- [ ] Pre-commit hooks configured and passing
- [ ] MyPy type checking integrated and passing
- [ ] Constants extracted to centralized location
- [ ] Developer documentation updated
- [ ] All ruff quality rules passing
- [ ] Performance maintained or improved
- [ ] Code review completed

## Success Metrics

- Cyclomatic complexity average ≤5 across codebase
- Type coverage ≥95% for application code
- Zero code duplication violations
- Pre-commit hooks prevent quality regressions
- Developer onboarding time reduced
- Code review feedback focused on business logic, not style

This task establishes high code quality standards and tooling to maintain them throughout the project lifecycle.
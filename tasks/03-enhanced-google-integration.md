# Enhanced Google Calendar Integration Tasks

## Overview
Implement production-grade Google Calendar API integration with comprehensive rate limiting, circuit breaker patterns, and resilience mechanisms.

## Priority: HIGH (Core sync functionality with production reliability)

**Total Enhanced Time: 24 hours** (vs 11 hours original)

---

## TASK-011: Rate Limiting & Circuit Breaker Implementation
**Status:** Not Started  
**Estimated Time:** 120 minutes (2 hours)  
**Dependencies:** TASK-010 (Enhanced Security)  
**Complexity Level:** Medium

### Description
Implement production-grade rate limiting and circuit breaker patterns for Google Calendar API calls.

### Enhanced Acceptance Criteria
- [ ] `calendars/services/rate_limiter.py` created
- [ ] RateLimiter class with methods:
  - [ ] `can_make_request(api_endpoint)` - Check if request allowed
  - [ ] `record_request(api_endpoint, success)` - Track request outcomes
  - [ ] `get_backoff_delay(failure_count)` - Exponential backoff calculation
  - [ ] `is_circuit_open(api_endpoint)` - Circuit breaker status
- [ ] Simple circuit breaker (3 failures = 5-minute pause)
- [ ] Exponential backoff with jitter for retry logic
- [ ] Per-endpoint rate limiting (different limits for read vs write)
- [ ] Request queuing for burst handling
- [ ] Comprehensive logging for rate limit analysis

### LLM Prerequisites Section
**MANDATORY validation before starting:**
```bash
# Verify enhanced authentication is working
python manage.py test accounts.tests.test_token_manager --verbosity=0

# Verify basic Google API connectivity
python manage.py shell -c "
from google.oauth2.credentials import Credentials
print('Google OAuth libraries available')
"

# Check Redis/cache backend (if using for rate limiting)
python manage.py shell -c "
from django.core.cache import cache
cache.set('test', 'working', 10)
assert cache.get('test') == 'working', 'Cache backend not working'
print('Cache backend validated')
"
```

### LLM Success Criteria Section
**CONCRETE success indicators:**
- [ ] File exists: `/path/to/src/calendars/services/rate_limiter.py`
- [ ] Rate limiter blocks requests when limit exceeded
- [ ] Circuit breaker opens after 3 consecutive failures
- [ ] Exponential backoff increases delay properly
- [ ] Jitter prevents thundering herd problems
- [ ] Rate limiting works across multiple API endpoints

### LLM Failure Detection Section
**STOP immediately if ANY of these occur:**
- Rate limiter allows unlimited requests (no limiting effect)
- Circuit breaker never opens despite failures
- Exponential backoff produces infinite delays
- Memory usage grows unbounded during rate limiting
- Cache backend errors prevent rate limiting functionality

### LLM Recovery Procedures Section
**If task fails:**
1. **Rate Limiting Not Working**:
   - Check cache backend is properly configured
   - Verify rate limiting algorithms with simple test cases
   - Test with known API quota limits
2. **Circuit Breaker Issues**:
   - Validate failure detection logic with mock failures
   - Check timeout calculations are reasonable
   - Test circuit breaker reset after timeout period
3. **Performance Issues**:
   - Profile memory usage during high-volume scenarios
   - Optimize data structures for rate limiting storage
   - Consider using Redis for production rate limiting

### Enhanced Implementation Pattern
```python
import time
import random
import threading
from dataclasses import dataclass
from typing import Dict, Optional
from django.core.cache import cache

@dataclass
class CircuitBreakerState:
    failure_count: int = 0
    last_failure_time: Optional[float] = None
    is_open: bool = False

class SimpleRateLimiter:
    """Production-ready rate limiter with circuit breaker"""
    
    def __init__(self):
        self.circuit_states: Dict[str, CircuitBreakerState] = {}
        self.lock = threading.Lock()
        
        # Rate limits per endpoint (requests per minute)
        self.rate_limits = {
            'calendar_list': 100,      # Read operations
            'calendar_get': 100,
            'event_list': 100,
            'event_get': 100,
            'event_create': 60,        # Write operations (more limited)
            'event_update': 60,
            'event_delete': 60,
        }
    
    def can_make_request(self, endpoint: str) -> tuple[bool, float]:
        """
        Check if request can be made now.
        Returns: (can_make_request, delay_seconds)
        """
        # Check circuit breaker first
        if self.is_circuit_open(endpoint):
            return False, self.get_circuit_delay(endpoint)
        
        # Check rate limit
        rate_key = f"rate_limit:{endpoint}"
        current_requests = cache.get(rate_key, 0)
        limit = self.rate_limits.get(endpoint, 100)
        
        if current_requests >= limit:
            # Calculate backoff delay
            delay = self.get_backoff_delay(current_requests - limit)
            return False, delay
        
        return True, 0.0
    
    def record_request(self, endpoint: str, success: bool, response_time: float = None):
        """Record request outcome for rate limiting and circuit breaker"""
        # Update rate limiting counter
        rate_key = f"rate_limit:{endpoint}"
        cache.set(rate_key, cache.get(rate_key, 0) + 1, 60)  # 1-minute window
        
        # Update circuit breaker state
        with self.lock:
            if endpoint not in self.circuit_states:
                self.circuit_states[endpoint] = CircuitBreakerState()
            
            state = self.circuit_states[endpoint]
            
            if success:
                # Reset failure count on success
                state.failure_count = 0
                state.is_open = False
            else:
                # Increment failure count
                state.failure_count += 1
                state.last_failure_time = time.time()
                
                # Open circuit after 3 failures
                if state.failure_count >= 3:
                    state.is_open = True
    
    def is_circuit_open(self, endpoint: str) -> bool:
        """Check if circuit breaker is open for endpoint"""
        if endpoint not in self.circuit_states:
            return False
        
        state = self.circuit_states[endpoint]
        
        if not state.is_open:
            return False
        
        # Check if circuit should be reset (5-minute timeout)
        if state.last_failure_time and (time.time() - state.last_failure_time) > 300:
            with self.lock:
                state.is_open = False
                state.failure_count = 0
            return False
        
        return True
    
    def get_backoff_delay(self, failure_count: int) -> float:
        """Calculate exponential backoff delay with jitter"""
        base_delay = min(2 ** failure_count, 300)  # Max 5 minutes
        jitter = random.uniform(0.1, 0.3) * base_delay
        return base_delay + jitter
    
    def get_circuit_delay(self, endpoint: str) -> float:
        """Get delay until circuit breaker resets"""
        state = self.circuit_states.get(endpoint)
        if not state or not state.last_failure_time:
            return 0.0
        
        elapsed = time.time() - state.last_failure_time
        remaining = max(0, 300 - elapsed)  # 5-minute circuit breaker
        return remaining
```

### LLM Validation Commands Section
**Run these EXACT commands to verify success:**
```bash
# Test 1: Verify rate limiter can be imported and instantiated
python manage.py shell -c "
from calendars.services.rate_limiter import SimpleRateLimiter
limiter = SimpleRateLimiter()
print('Rate limiter created successfully')
"

# Test 2: Test rate limiting behavior
python manage.py test calendars.tests.test_rate_limiter.TestRateLimiter.test_rate_limiting

# Test 3: Test circuit breaker behavior
python manage.py test calendars.tests.test_rate_limiter.TestRateLimiter.test_circuit_breaker

# Test 4: Test exponential backoff
python manage.py test calendars.tests.test_rate_limiter.TestRateLimiter.test_exponential_backoff
```

---

## TASK-012: Enhanced Google Calendar Client
**Status:** Not Started  
**Estimated Time:** 180 minutes (3 hours)  
**Dependencies:** TASK-011  
**Complexity Level:** High

### Description
Create production-grade Google Calendar API client with integrated rate limiting, error recovery, and comprehensive resilience.

### Enhanced Acceptance Criteria
- [ ] `calendars/services/google_calendar_client.py` created
- [ ] GoogleCalendarClient class with methods:
  - [ ] `__init__(calendar_account, rate_limiter)` - Initialize with rate limiting
  - [ ] `execute_with_resilience(operation, *args)` - Resilient API execution
  - [ ] `handle_api_error(error, context)` - Comprehensive error handling
  - [ ] `build_service_with_retry()` - Service creation with retries
  - [ ] `refresh_token_if_needed()` - Token management integration
- [ ] Integration with rate limiter and circuit breaker
- [ ] Automatic retry with exponential backoff
- [ ] Comprehensive error classification and handling
- [ ] Request/response logging for debugging
- [ ] Timeout configuration for all API calls
- [ ] Connection pooling for better performance

### LLM Prerequisites Section
**MANDATORY validation before starting:**
```bash
# Verify rate limiter is working
python manage.py test calendars.tests.test_rate_limiter --verbosity=0

# Verify Google API dependencies
python -c "
import googleapiclient.discovery
import googleapiclient.errors
import google.auth.exceptions
print('Google API libraries validated')
"

# Verify token manager integration
python manage.py test accounts.tests.test_token_manager --verbosity=0
```

### Enhanced Implementation Pattern
```python
import logging
import time
from typing import Any, Callable, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError
from accounts.services.token_manager import TokenManager
from .rate_limiter import SimpleRateLimiter

logger = logging.getLogger(__name__)

class GoogleCalendarClient:
    """Production-grade Google Calendar API client with resilience"""
    
    def __init__(self, calendar_account, rate_limiter: SimpleRateLimiter = None):
        self.account = calendar_account
        self.rate_limiter = rate_limiter or SimpleRateLimiter()
        self.token_manager = TokenManager()
        self._service = None
        
        # Timeout configurations
        self.default_timeout = 30  # seconds
        self.retry_timeout = 60   # seconds
    
    def execute_with_resilience(self, operation: Callable, endpoint: str, *args, **kwargs) -> Any:
        """
        Execute Google API operation with rate limiting, retries, and error handling.
        
        Args:
            operation: The API operation function to execute
            endpoint: API endpoint name for rate limiting
            *args, **kwargs: Arguments for the operation
            
        Returns:
            API response data
            
        Raises:
            GoogleAPIError: When operation fails after all retries
        """
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Check rate limiting and circuit breaker
                can_proceed, delay = self.rate_limiter.can_make_request(endpoint)
                if not can_proceed:
                    if delay > 0:
                        logger.info(f"Rate limited for {endpoint}, waiting {delay:.2f}s")
                        time.sleep(delay)
                        continue
                    else:
                        raise RateLimitError(f"Circuit breaker open for {endpoint}")
                
                # Ensure valid token before API call
                self.token_manager.ensure_valid_token(self.account)
                
                # Execute the operation
                start_time = time.time()
                result = operation(*args, **kwargs)
                response_time = time.time() - start_time
                
                # Record successful request
                self.rate_limiter.record_request(endpoint, True, response_time)
                
                logger.debug(f"API call {endpoint} succeeded in {response_time:.2f}s")
                return result
                
            except HttpError as e:
                response_time = time.time() - start_time if 'start_time' in locals() else 0
                last_error = e
                
                # Record failed request
                self.rate_limiter.record_request(endpoint, False, response_time)
                
                # Handle specific HTTP errors
                if e.resp.status == 429:  # Rate limited
                    retry_after = int(e.resp.get('retry-after', 60))
                    logger.warning(f"Rate limited by Google API, waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue
                    
                elif e.resp.status in [401, 403]:  # Auth errors
                    logger.warning(f"Authentication error for {endpoint}: {e}")
                    try:
                        self.token_manager.force_token_refresh(self.account)
                        continue  # Retry with refreshed token
                    except RefreshError:
                        raise AuthenticationError(f"Failed to refresh token: {e}")
                        
                elif e.resp.status >= 500:  # Server errors
                    if attempt < max_retries - 1:
                        delay = self.rate_limiter.get_backoff_delay(attempt)
                        logger.warning(f"Server error for {endpoint}, retrying in {delay:.2f}s")
                        time.sleep(delay)
                        continue
                
                # For other errors, don't retry
                break
                
            except Exception as e:
                last_error = e
                self.rate_limiter.record_request(endpoint, False)
                
                if attempt < max_retries - 1:
                    delay = self.rate_limiter.get_backoff_delay(attempt)
                    logger.warning(f"Unexpected error for {endpoint}, retrying in {delay:.2f}s: {e}")
                    time.sleep(delay)
                    continue
                break
        
        # All retries exhausted
        raise GoogleAPIError(f"Operation {endpoint} failed after {max_retries} attempts: {last_error}")
    
    def list_calendars(self):
        """List accessible calendars with resilience"""
        def _list_calendars():
            service = self.get_service()
            return service.calendarList().list().execute()
        
        return self.execute_with_resilience(_list_calendars, 'calendar_list')
    
    def list_events(self, calendar_id: str, time_min: str = None, time_max: str = None):
        """List events with resilience"""
        def _list_events():
            service = self.get_service()
            request = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            )
            return request.execute()
        
        return self.execute_with_resilience(_list_events, 'event_list')
    
    def create_event(self, calendar_id: str, event_data: dict):
        """Create event with resilience"""
        def _create_event():
            service = self.get_service()
            return service.events().insert(
                calendarId=calendar_id,
                body=event_data
            ).execute()
        
        return self.execute_with_resilience(_create_event, 'event_create')
    
    def get_service(self):
        """Get or create Google Calendar service"""
        if self._service is None:
            credentials = self.token_manager.get_credentials(self.account)
            self._service = build('calendar', 'v3', credentials=credentials)
        return self._service

# Custom exceptions for better error handling
class GoogleAPIError(Exception):
    """Base exception for Google API errors"""
    pass

class RateLimitError(GoogleAPIError):
    """Raised when rate limiting prevents operation"""
    pass

class AuthenticationError(GoogleAPIError):
    """Raised when authentication fails"""
    pass
```

### LLM Validation Commands Section
```bash
# Test 1: Verify client can be created and service built
python manage.py shell -c "
from calendars.services.google_calendar_client import GoogleCalendarClient
from accounts.models import CalendarAccount
# Note: This requires a real account for full testing
print('GoogleCalendarClient imported successfully')
"

# Test 2: Test rate limiting integration
python manage.py test calendars.tests.test_google_client.TestGoogleClient.test_rate_limiting_integration

# Test 3: Test error handling
python manage.py test calendars.tests.test_google_client.TestGoogleClient.test_error_handling

# Test 4: Test resilience patterns
python manage.py test calendars.tests.test_google_client.TestGoogleClient.test_resilience_patterns
```

---

## TASK-013: Time Zone Core Handling
**Status:** Not Started  
**Estimated Time:** 90 minutes (1.5 hours)  
**Dependencies:** TASK-012  
**Complexity Level:** Medium

### Description
Implement essential time zone handling for calendar events without falling into edge case rabbit holes.

### Enhanced Acceptance Criteria
- [ ] `calendars/services/timezone_handler.py` created
- [ ] TimezoneHandler class with methods:
  - [ ] `normalize_event_time(event_data, calendar_timezone)` - Convert to UTC
  - [ ] `localize_event_time(event_data, target_timezone)` - Convert from UTC
  - [ ] `handle_all_day_events(event_data)` - All-day event timezone logic
  - [ ] `detect_dst_transition(date, timezone)` - Basic DST handling
- [ ] UTC storage with timezone-aware display conversion
- [ ] Handle user's primary timezone per calendar
- [ ] Basic DST transition support (avoid complex edge cases)
- [ ] All-day event handling (no timezone conversion)
- [ ] Validation for timezone consistency

### LLM Prerequisites Section
**MANDATORY validation before starting:**
```bash
# Verify Google Calendar client is working
python manage.py test calendars.tests.test_google_client --verbosity=0

# Verify timezone libraries
python -c "
import pytz
import datetime
from django.utils import timezone
print('Timezone libraries validated')
"

# Check Calendar model has timezone field
python manage.py shell -c "
from calendars.models import Calendar
print('Calendar model available for timezone handling')
"
```

### Essential Time Zone Implementation (MVP Focus)
```python
import pytz
from datetime import datetime
from typing import Optional, Dict, Any
from django.utils import timezone as django_timezone

class TimezoneHandler:
    """Essential timezone handling for calendar sync (MVP scope)"""
    
    def __init__(self):
        # Common timezones - avoid complex timezone database queries
        self.common_timezones = {
            'UTC': pytz.UTC,
            'US/Eastern': pytz.timezone('US/Eastern'),
            'US/Central': pytz.timezone('US/Central'),
            'US/Mountain': pytz.timezone('US/Mountain'),
            'US/Pacific': pytz.timezone('US/Pacific'),
            'Europe/London': pytz.timezone('Europe/London'),
            'Europe/Paris': pytz.timezone('Europe/Paris'),
            # Add more as needed, but keep it simple
        }
    
    def normalize_event_time(self, event_data: Dict[str, Any], source_calendar_tz: str) -> Dict[str, Any]:
        """
        Convert event times to UTC for storage.
        
        Args:
            event_data: Google Calendar event data
            source_calendar_tz: Source calendar's timezone
            
        Returns:
            Event data with UTC times
        """
        normalized = event_data.copy()
        
        # Handle start time
        if 'start' in event_data:
            normalized['start'] = self._normalize_datetime(
                event_data['start'], source_calendar_tz
            )
        
        # Handle end time
        if 'end' in event_data:
            normalized['end'] = self._normalize_datetime(
                event_data['end'], source_calendar_tz
            )
        
        return normalized
    
    def localize_event_time(self, event_data: Dict[str, Any], target_timezone: str) -> Dict[str, Any]:
        """
        Convert UTC times to target timezone for display.
        
        Args:
            event_data: Event data with UTC times
            target_timezone: Target timezone name
            
        Returns:
            Event data with localized times
        """
        localized = event_data.copy()
        target_tz = self._get_timezone(target_timezone)
        
        # Handle start time
        if 'start' in event_data and 'dateTime' in event_data['start']:
            utc_time = self._parse_utc_datetime(event_data['start']['dateTime'])
            localized_time = utc_time.astimezone(target_tz)
            localized['start'] = {
                'dateTime': localized_time.isoformat(),
                'timeZone': target_timezone
            }
        
        # Handle end time
        if 'end' in event_data and 'dateTime' in event_data['end']:
            utc_time = self._parse_utc_datetime(event_data['end']['dateTime'])
            localized_time = utc_time.astimezone(target_tz)
            localized['end'] = {
                'dateTime': localized_time.isoformat(),
                'timeZone': target_timezone
            }
        
        return localized
    
    def handle_all_day_events(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle all-day events (no timezone conversion needed).
        
        All-day events use 'date' instead of 'dateTime' and don't need timezone conversion.
        """
        # All-day events are stored as-is with date only
        if self._is_all_day_event(event_data):
            # No timezone conversion for all-day events
            return event_data
        
        return event_data
    
    def _normalize_datetime(self, time_data: Dict[str, Any], source_tz: str) -> Dict[str, Any]:
        """Convert datetime to UTC"""
        if 'date' in time_data:
            # All-day event, no conversion needed
            return time_data
        
        if 'dateTime' in time_data:
            # Parse the datetime string
            dt_str = time_data['dateTime']
            
            # If it already has timezone info, use it
            if 'timeZone' in time_data:
                tz = self._get_timezone(time_data['timeZone'])
            else:
                # Use source calendar timezone
                tz = self._get_timezone(source_tz)
            
            # Parse and convert to UTC
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = tz.localize(dt)
            
            utc_dt = dt.astimezone(pytz.UTC)
            
            return {
                'dateTime': utc_dt.isoformat(),
                'timeZone': 'UTC'
            }
        
        return time_data
    
    def _get_timezone(self, tz_name: str) -> pytz.BaseTzInfo:
        """Get timezone object, fallback to common timezones"""
        if tz_name in self.common_timezones:
            return self.common_timezones[tz_name]
        
        try:
            return pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            # Fallback to UTC for unknown timezones
            return pytz.UTC
    
    def _parse_utc_datetime(self, dt_str: str) -> datetime:
        """Parse UTC datetime string"""
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        return dt
    
    def _is_all_day_event(self, event_data: Dict[str, Any]) -> bool:
        """Check if event is all-day (uses 'date' instead of 'dateTime')"""
        return (
            'start' in event_data and 'date' in event_data['start'] and
            'end' in event_data and 'date' in event_data['end']
        )
```

### What We're NOT Handling (Avoiding Rabbit Holes)
- Historical timezone data edge cases
- Complex recurring event timezone calculations  
- Cross-timezone recurring event exceptions
- Timezone database version conflicts
- Leap second handling
- Ancient/obsolete timezone definitions
- Custom timezone definitions

### LLM Validation Commands Section
```bash
# Test timezone normalization
python manage.py test calendars.tests.test_timezone.TestTimezoneHandler.test_normalize_event_time

# Test timezone localization
python manage.py test calendars.tests.test_timezone.TestTimezoneHandler.test_localize_event_time

# Test all-day event handling
python manage.py test calendars.tests.test_timezone.TestTimezoneHandler.test_all_day_events

# Test basic DST handling
python manage.py test calendars.tests.test_timezone.TestTimezoneHandler.test_dst_transitions
```

---

## Summary: Enhanced Google Integration

**Total Enhanced Time: 24 hours** (vs 11 hours original)

### Key Enhancements
1. **Rate Limiting & Circuit Breaker**: Production-grade API resilience (+2 hours)
2. **Enhanced Google Client**: Comprehensive error handling and retries (+3 hours)
3. **Time Zone Core Handling**: Essential timezone logic without rabbit holes (+1.5 hours)
4. **Performance Optimization**: Realistic volume handling (+2 hours)
5. **Enhanced Testing**: Better mocking and edge case coverage (+4 hours)

### Production Reliability Features
- **Simple Circuit Breaker**: 3 failures = 5-minute pause (not complex distributed systems)
- **Exponential Backoff with Jitter**: Prevents thundering herd problems
- **Operation-aware Token Refresh**: Handles token expiration during API calls
- **Essential Timezone Handling**: Core use cases without edge case complexity
- **Comprehensive Error Classification**: Different handling for different error types

### AI Agent Safety Features
- **Clear Prerequisites**: Concrete validation steps for each task
- **Failure Detection**: Explicit conditions that indicate task failure
- **Recovery Procedures**: Step-by-step recovery for common failure modes
- **Validation Commands**: Exact commands to verify task completion
- **Complexity Limits**: Avoid over-engineering while ensuring production readiness

This enhanced Google integration provides the reliability and resilience needed for production use while maintaining focus on essential functionality rather than edge cases.
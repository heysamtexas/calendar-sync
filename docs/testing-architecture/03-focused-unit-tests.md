# TASK GT-03: Focused Unit Tests
## *"Unit tests only for complex business logic that needs isolation"*

### Priority: MEDIUM - SELECTIVE TESTING
### Estimated Time: 2-3 hours
### Dependencies: GT-01 (Test Infrastructure), GT-02 (Integration Tests First)
### Status: Ready for Implementation

---

## Problem Statement

Traditional testing approaches write unit tests for everything, leading to:
- Thousands of tests that mock internal services
- Brittle tests that break when implementation changes
- False confidence from testing mocks instead of business logic
- Maintenance nightmare when refactoring

**Guilfoyle's Approach**: Unit tests only for complex business logic that genuinely needs isolation. Most business logic should be tested through integration tests.

---

## Unit Test Criteria (The Guilfoyle Filter)

**Write unit tests ONLY when ALL of these are true:**
1. **Complex Algorithm**: Non-trivial business logic with multiple edge cases
2. **Pure Function**: Doesn't depend on external services or database state
3. **High Value**: Critical business logic that must be bulletproof
4. **Hard to Test in Integration**: Would require complex integration test setup

**Examples of GOOD unit test candidates:**
- Token encryption/decryption logic
- Rate limiting retry algorithms
- Date/time calculation utilities
- Data transformation functions
- Validation rules with complex edge cases

**Examples of BAD unit test candidates (use integration tests instead):**
- Model save() methods (test through actual saves)
- Service methods that call other services (test the complete flow)
- View logic (test through HTTP requests)
- Database queries (test through actual database operations)

---

## Acceptance Criteria

- [ ] Unit tests only for isolated business logic following Guilfoyle criteria
- [ ] Rate limiting algorithm tests with various error scenarios
- [ ] Token encryption/decryption tests with edge cases
- [ ] Calendar sync token handling unit tests
- [ ] Date/time utility function tests
- [ ] Input validation and sanitization tests
- [ ] No unit tests for database operations, HTTP requests, or service orchestration
- [ ] All unit tests run in <1 second total

---

## Implementation Steps

### Step 1: Rate Limiting Algorithm Unit Tests (45 minutes)

Create `tests/unit/test_rate_limiting.py`:

```python
"""
Unit tests for rate limiting algorithms
These are isolated functions with complex retry logic - perfect for unit testing
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
import time

from apps.calendars.services.google_calendar_client import GoogleCalendarClient
from googleapiclient.errors import HttpError


class TestRateLimitingAlgorithm:
    """Test the rate limiting retry algorithm in isolation"""
    
    def test_execute_with_rate_limiting_succeeds_immediately(self):
        """Test successful API call on first attempt"""
        # Create mock request that succeeds
        mock_request = Mock()
        mock_request.execute.return_value = {'success': True}
        
        # Test the rate limiting method directly
        client = GoogleCalendarClient(Mock())
        result = client._execute_with_rate_limiting(mock_request, "test_operation")
        
        # Should return result without retries
        assert result == {'success': True}
        assert mock_request.execute.call_count == 1
    
    def test_execute_with_rate_limiting_retries_on_429(self):
        """Test exponential backoff on rate limit errors"""
        # Create mock request that fails then succeeds
        mock_request = Mock()
        mock_response = Mock()
        mock_response.status = 403
        
        rate_limit_error = HttpError(
            resp=mock_response, 
            content=b'{"error": {"message": "rateLimitExceeded"}}'
        )
        
        mock_request.execute.side_effect = [
            rate_limit_error,  # First call fails
            rate_limit_error,  # Second call fails  
            {'success': True}  # Third call succeeds
        ]
        
        # Mock time.sleep to verify backoff timing
        with patch('time.sleep') as mock_sleep:
            client = GoogleCalendarClient(Mock())
            result = client._execute_with_rate_limiting(mock_request, "test_operation")
        
        # Should eventually succeed
        assert result == {'success': True}
        assert mock_request.execute.call_count == 3
        
        # Should use exponential backoff: 3s, 6s
        expected_sleep_calls = [((3,),), ((6,),)]
        assert mock_sleep.call_args_list == expected_sleep_calls
    
    def test_execute_with_rate_limiting_gives_up_after_max_retries(self):
        """Test that algorithm gives up after max retries"""
        mock_request = Mock()
        mock_response = Mock()
        mock_response.status = 403
        
        rate_limit_error = HttpError(
            resp=mock_response,
            content=b'{"error": {"message": "quotaExceeded"}}'
        )
        
        # Always fail
        mock_request.execute.side_effect = rate_limit_error
        
        # Should raise after max retries
        client = GoogleCalendarClient(Mock())
        with pytest.raises(HttpError):
            client._execute_with_rate_limiting(mock_request, "test_operation", max_retries=2)
        
        # Should have tried max_retries + 1 times (initial + 2 retries)
        assert mock_request.execute.call_count == 3
    
    def test_execute_with_rate_limiting_handles_non_rate_limit_errors(self):
        """Test that non-rate-limit errors are raised immediately"""
        mock_request = Mock()
        mock_response = Mock()
        mock_response.status = 404
        
        not_found_error = HttpError(
            resp=mock_response,
            content=b'{"error": {"message": "Not found"}}'
        )
        
        mock_request.execute.side_effect = not_found_error
        
        # Should raise immediately without retries
        client = GoogleCalendarClient(Mock())
        with pytest.raises(HttpError):
            client._execute_with_rate_limiting(mock_request, "test_operation")
        
        # Should only try once
        assert mock_request.execute.call_count == 1
    
    def test_rate_limiting_backoff_calculation(self):
        """Test exponential backoff calculation logic"""
        client = GoogleCalendarClient(Mock())
        base_delay = 3
        
        # Test backoff calculation for different attempts
        # This tests the pure calculation logic: base_delay * (2 ** attempt)
        
        def calculate_delay(attempt):
            return base_delay * (2 ** attempt)
        
        assert calculate_delay(0) == 3   # First retry: 3s
        assert calculate_delay(1) == 6   # Second retry: 6s  
        assert calculate_delay(2) == 12  # Third retry: 12s
        assert calculate_delay(3) == 24  # Fourth retry: 24s
    
    def test_rate_limit_error_detection(self):
        """Test detection of different rate limit error types"""
        client = GoogleCalendarClient(Mock())
        
        # Test rate limit error detection logic
        def is_rate_limit_error(http_error):
            if http_error.resp.status == 403:
                error_content = str(http_error)
                return ('rateLimitExceeded' in error_content or 
                       'quotaExceeded' in error_content)
            return False
        
        # Test rate limit exceeded
        mock_response = Mock()
        mock_response.status = 403
        rate_limit_error = HttpError(
            resp=mock_response,
            content=b'rateLimitExceeded'
        )
        assert is_rate_limit_error(rate_limit_error)
        
        # Test quota exceeded  
        quota_error = HttpError(
            resp=mock_response,
            content=b'quotaExceeded'
        )
        assert is_rate_limit_error(quota_error)
        
        # Test non-rate-limit 403
        mock_response.status = 403
        permission_error = HttpError(
            resp=mock_response,
            content=b'insufficient permissions'
        )
        assert not is_rate_limit_error(permission_error)
        
        # Test non-403 error
        mock_response.status = 404
        not_found_error = HttpError(
            resp=mock_response,
            content=b'not found'
        )
        assert not is_rate_limit_error(not_found_error)
```

### Step 2: Token Encryption/Decryption Unit Tests (45 minutes)

Create `tests/unit/test_token_encryption.py`:

```python
"""
Unit tests for token encryption/decryption
These are pure cryptographic functions - perfect for unit testing
"""

import pytest
from django.test import TestCase
from django.conf import settings
from django.core.exceptions import ValidationError
from unittest.mock import patch

from apps.accounts.utils import encrypt_token, decrypt_token, TokenEncryptionError


class TestTokenEncryption:
    """Test token encryption/decryption algorithms"""
    
    def test_encrypt_decrypt_roundtrip(self):
        """Test that encrypt → decrypt returns original value"""
        original_token = "test_access_token_123"
        
        # Encrypt the token
        encrypted = encrypt_token(original_token)
        
        # Should be different from original
        assert encrypted != original_token
        assert len(encrypted) > len(original_token)  # Includes IV and padding
        
        # Decrypt should return original
        decrypted = decrypt_token(encrypted)
        assert decrypted == original_token
    
    def test_encrypt_produces_different_output_each_time(self):
        """Test that encryption produces different ciphertext each time (due to random IV)"""
        token = "same_token_value"
        
        encrypted1 = encrypt_token(token)
        encrypted2 = encrypt_token(token)
        
        # Should produce different encrypted values (different IVs)
        assert encrypted1 != encrypted2
        
        # But both should decrypt to same value
        assert decrypt_token(encrypted1) == token
        assert decrypt_token(encrypted2) == token
    
    def test_decrypt_invalid_token_raises_error(self):
        """Test that invalid encrypted data raises appropriate error"""
        with pytest.raises(TokenEncryptionError):
            decrypt_token("invalid_encrypted_data")
        
        with pytest.raises(TokenEncryptionError):
            decrypt_token("")
        
        with pytest.raises(TokenEncryptionError):
            decrypt_token(None)
    
    def test_encrypt_empty_token_handling(self):
        """Test encryption behavior with edge case inputs"""
        # Empty string
        encrypted_empty = encrypt_token("")
        decrypted_empty = decrypt_token(encrypted_empty)
        assert decrypted_empty == ""
        
        # Very long token
        long_token = "x" * 1000
        encrypted_long = encrypt_token(long_token)
        decrypted_long = decrypt_token(encrypted_long)
        assert decrypted_long == long_token
        
        # Unicode characters
        unicode_token = "token_with_unicode_🔐_characters"
        encrypted_unicode = encrypt_token(unicode_token)
        decrypted_unicode = decrypt_token(encrypted_unicode)
        assert decrypted_unicode == unicode_token
    
    def test_encryption_key_rotation_compatibility(self):
        """Test behavior when encryption key changes"""
        original_token = "test_token_for_key_rotation"
        
        # Encrypt with current key
        encrypted_with_key1 = encrypt_token(original_token)
        
        # Simulate key rotation by changing SECRET_KEY
        with patch.object(settings, 'SECRET_KEY', 'different_secret_key'):
            # Should raise error when trying to decrypt with wrong key
            with pytest.raises(TokenEncryptionError, match="decryption failed"):
                decrypt_token(encrypted_with_key1)
            
            # Should be able to encrypt with new key
            encrypted_with_key2 = encrypt_token(original_token)
            decrypted_with_key2 = decrypt_token(encrypted_with_key2)
            assert decrypted_with_key2 == original_token
    
    def test_token_encryption_performance(self):
        """Test that encryption/decryption is reasonably fast"""
        import time
        
        token = "performance_test_token_1234567890"
        
        # Test encryption performance
        start_time = time.time()
        for _ in range(100):
            encrypt_token(token)
        encryption_time = time.time() - start_time
        
        # Should encrypt 100 tokens in less than 1 second
        assert encryption_time < 1.0
        
        # Test decryption performance
        encrypted = encrypt_token(token)
        start_time = time.time()
        for _ in range(100):
            decrypt_token(encrypted)
        decryption_time = time.time() - start_time
        
        # Should decrypt 100 tokens in less than 1 second
        assert decryption_time < 1.0


class TestTokenValidation:
    """Test token validation utilities"""
    
    def test_is_token_expired(self):
        """Test token expiration check logic"""
        from datetime import datetime, timedelta
        from django.utils import timezone
        from apps.accounts.utils import is_token_expired
        
        # Token expires in 1 hour - not expired
        future_expiry = timezone.now() + timedelta(hours=1)
        assert not is_token_expired(future_expiry)
        
        # Token expired 1 hour ago - expired
        past_expiry = timezone.now() - timedelta(hours=1)
        assert is_token_expired(past_expiry)
        
        # Token expires in 5 minutes - not expired normally
        near_expiry = timezone.now() + timedelta(minutes=5)
        assert not is_token_expired(near_expiry)
        
        # Token expires in 5 minutes but with 10 minute buffer - expired
        assert is_token_expired(near_expiry, buffer_minutes=10)
    
    def test_token_format_validation(self):
        """Test validation of token format"""
        from apps.accounts.utils import validate_token_format
        
        # Valid token formats
        assert validate_token_format("ya29.a0AWY7CknfZ...")  # Google access token
        assert validate_token_format("1//04xxxxxxxxxxx")     # Google refresh token
        
        # Invalid token formats
        assert not validate_token_format("")
        assert not validate_token_format(None)
        assert not validate_token_format("obviously_fake_token")
        assert not validate_token_format("too_short")
```

### Step 3: Date/Time Utility Unit Tests (30 minutes)

Create `tests/unit/test_datetime_utils.py`:

```python
"""
Unit tests for date/time utilities
These are pure calculation functions - perfect for unit testing
"""

import pytest
from datetime import datetime, timedelta
from django.utils import timezone
from unittest.mock import patch

from apps.calendars.utils import (
    parse_google_datetime, 
    format_datetime_for_google,
    calculate_busy_block_overlap,
    get_sync_time_range,
    is_within_business_hours
)


class TestDateTimeUtilities:
    """Test date/time calculation utilities"""
    
    def test_parse_google_datetime_formats(self):
        """Test parsing various Google Calendar datetime formats"""
        # ISO format with timezone
        iso_with_tz = "2023-06-01T10:00:00-07:00"
        parsed = parse_google_datetime(iso_with_tz)
        assert parsed.hour == 10
        assert parsed.tzinfo is not None
        
        # ISO format UTC
        iso_utc = "2023-06-01T10:00:00Z"
        parsed_utc = parse_google_datetime(iso_utc)
        assert parsed_utc.hour == 10
        assert parsed_utc.tzinfo.utcoffset(None) == timedelta(0)
        
        # Date-only format (all-day event)
        date_only = "2023-06-01"
        parsed_date = parse_google_datetime(date_only)
        assert parsed_date.hour == 0
        assert parsed_date.minute == 0
        
        # Invalid format
        with pytest.raises(ValueError):
            parse_google_datetime("invalid_date_format")
    
    def test_format_datetime_for_google(self):
        """Test formatting datetime for Google Calendar API"""
        # Test with timezone-aware datetime
        dt = timezone.make_aware(
            datetime(2023, 6, 1, 10, 30, 0),
            timezone.get_current_timezone()
        )
        
        formatted = format_datetime_for_google(dt)
        assert "2023-06-01T10:30:00" in formatted
        assert formatted.endswith("Z") or "+" in formatted or "-" in formatted
        
        # Test with UTC datetime
        utc_dt = datetime(2023, 6, 1, 10, 30, 0, tzinfo=timezone.utc)
        formatted_utc = format_datetime_for_google(utc_dt)
        assert formatted_utc == "2023-06-01T10:30:00Z"
    
    def test_calculate_busy_block_overlap(self):
        """Test calculation of overlapping time periods"""
        # Create test time periods
        base_time = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        
        event1_start = base_time
        event1_end = base_time + timedelta(hours=2)  # 10:00-12:00
        
        event2_start = base_time + timedelta(hours=1)  # 11:00
        event2_end = base_time + timedelta(hours=3)    # 13:00
        
        # Test overlapping events
        overlap = calculate_busy_block_overlap(
            event1_start, event1_end,
            event2_start, event2_end
        )
        
        # Should overlap from 11:00-12:00 (1 hour)
        assert overlap['has_overlap']
        assert overlap['overlap_start'] == event2_start  # 11:00
        assert overlap['overlap_end'] == event1_end      # 12:00
        assert overlap['overlap_duration'] == timedelta(hours=1)
        
        # Test non-overlapping events
        event3_start = base_time + timedelta(hours=3)  # 13:00
        event3_end = base_time + timedelta(hours=4)    # 14:00
        
        no_overlap = calculate_busy_block_overlap(
            event1_start, event1_end,
            event3_start, event3_end
        )
        
        assert not no_overlap['has_overlap']
        assert no_overlap['overlap_duration'] == timedelta(0)
        
        # Test complete containment
        contained_start = base_time + timedelta(minutes=30)  # 10:30
        contained_end = base_time + timedelta(minutes=90)    # 11:30
        
        containment = calculate_busy_block_overlap(
            event1_start, event1_end,    # 10:00-12:00
            contained_start, contained_end  # 10:30-11:30
        )
        
        assert containment['has_overlap']
        assert containment['overlap_start'] == contained_start
        assert containment['overlap_end'] == contained_end
        assert containment['overlap_duration'] == timedelta(hours=1)
    
    def test_get_sync_time_range(self):
        """Test calculation of sync time ranges"""
        # Test default range (30 days past, 90 days future)
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = datetime(2023, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
            
            time_range = get_sync_time_range()
            
            # Should be 30 days in past
            expected_start = datetime(2023, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
            assert abs((time_range['start'] - expected_start).total_seconds()) < 60
            
            # Should be 90 days in future  
            expected_end = datetime(2023, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
            assert abs((time_range['end'] - expected_end).total_seconds()) < 60
        
        # Test custom range
        custom_range = get_sync_time_range(days_past=7, days_future=30)
        total_days = (custom_range['end'] - custom_range['start']).days
        assert total_days == 37  # 7 + 30
    
    def test_is_within_business_hours(self):
        """Test business hours calculation"""
        # Create test datetime (Tuesday 2:00 PM)
        tuesday_2pm = datetime(2023, 6, 6, 14, 0, 0, tzinfo=timezone.utc)
        assert is_within_business_hours(tuesday_2pm)
        
        # Early morning (6 AM)
        tuesday_6am = datetime(2023, 6, 6, 6, 0, 0, tzinfo=timezone.utc)
        assert not is_within_business_hours(tuesday_6am)
        
        # Late evening (8 PM)
        tuesday_8pm = datetime(2023, 6, 6, 20, 0, 0, tzinfo=timezone.utc)
        assert not is_within_business_hours(tuesday_8pm)
        
        # Weekend (Saturday)
        saturday_2pm = datetime(2023, 6, 3, 14, 0, 0, tzinfo=timezone.utc)
        assert not is_within_business_hours(saturday_2pm)
        
        # Test custom business hours
        custom_result = is_within_business_hours(
            tuesday_2pm, 
            start_hour=10, 
            end_hour=18,
            weekend_work=True
        )
        assert custom_result
        
        # Test with weekend work enabled
        weekend_custom = is_within_business_hours(
            saturday_2pm,
            weekend_work=True
        )
        assert weekend_custom


class TestSyncTokenHandling:
    """Test sync token calculation and validation"""
    
    def test_generate_sync_token(self):
        """Test sync token generation logic"""
        from apps.calendars.utils import generate_sync_token
        
        # Test token generation with timestamp
        base_time = timezone.now()
        token1 = generate_sync_token(base_time)
        token2 = generate_sync_token(base_time)
        
        # Should be deterministic for same timestamp
        assert token1 == token2
        
        # Should be different for different timestamps
        future_time = base_time + timedelta(seconds=1)
        token3 = generate_sync_token(future_time)
        assert token1 != token3
    
    def test_validate_sync_token(self):
        """Test sync token validation"""
        from apps.calendars.utils import validate_sync_token, generate_sync_token
        
        # Valid token
        current_time = timezone.now()
        valid_token = generate_sync_token(current_time)
        assert validate_sync_token(valid_token)
        
        # Invalid tokens
        assert not validate_sync_token("invalid_token")
        assert not validate_sync_token("")
        assert not validate_sync_token(None)
        
        # Expired token (older than 7 days)
        old_time = current_time - timedelta(days=8)
        old_token = generate_sync_token(old_time)
        assert not validate_sync_token(old_token)
```

### Step 4: Input Validation Unit Tests (30 minutes)

Create `tests/unit/test_validation_utils.py`:

```python
"""
Unit tests for input validation utilities
These are pure validation functions with complex edge cases
"""

import pytest
from django.core.exceptions import ValidationError

from apps.calendars.validators import (
    validate_google_calendar_id,
    validate_event_title,
    validate_color_hex,
    sanitize_user_input,
    validate_webhook_headers
)


class TestInputValidation:
    """Test input validation utilities"""
    
    def test_validate_google_calendar_id(self):
        """Test Google Calendar ID validation"""
        # Valid calendar IDs
        valid_ids = [
            "primary",
            "user@gmail.com",
            "calendar_id_123@group.calendar.google.com",
            "en.usa#holiday@group.v.calendar.google.com"
        ]
        
        for valid_id in valid_ids:
            validate_google_calendar_id(valid_id)  # Should not raise
        
        # Invalid calendar IDs
        invalid_ids = [
            "",
            None,
            "spaces not allowed",
            "toolong" * 100,  # Too long
            "invalid@characters!@#",
            "<script>alert('xss')</script>"
        ]
        
        for invalid_id in invalid_ids:
            with pytest.raises(ValidationError):
                validate_google_calendar_id(invalid_id)
    
    def test_validate_event_title(self):
        """Test event title validation and sanitization"""
        # Valid titles
        valid_titles = [
            "Normal Meeting",
            "Meeting with special chars: áéíóú",
            "Numbers 123 and symbols !@#$%",
            "Very " + "long " * 50 + "title"  # Long but acceptable
        ]
        
        for title in valid_titles:
            sanitized = validate_event_title(title)
            assert len(sanitized) > 0
            assert sanitized == title or len(sanitized) <= 255  # May be truncated
        
        # Titles that need sanitization
        malicious_titles = [
            "<script>alert('xss')</script>",
            "Normal title<script>evil()</script>",
            "Title with\n\r\t special whitespace",
            "   Title with excess whitespace   "
        ]
        
        for title in malicious_titles:
            sanitized = validate_event_title(title)
            assert "<script>" not in sanitized
            assert "alert" not in sanitized
            assert "\n" not in sanitized
            assert not sanitized.startswith(" ")
            assert not sanitized.endswith(" ")
        
        # Invalid titles
        with pytest.raises(ValidationError):
            validate_event_title("")  # Empty
        
        with pytest.raises(ValidationError):
            validate_event_title(None)  # None
    
    def test_validate_color_hex(self):
        """Test hex color validation"""
        # Valid colors
        valid_colors = [
            "#FF0000",  # Red
            "#00FF00",  # Green  
            "#0000FF",  # Blue
            "#FFFFFF",  # White
            "#000000",  # Black
            "#1f4788",  # Google Calendar blue
            "#d50000"   # Google Calendar red
        ]
        
        for color in valid_colors:
            validate_color_hex(color)  # Should not raise
        
        # Invalid colors
        invalid_colors = [
            "FF0000",    # Missing #
            "#FF00",     # Too short
            "#FF00000",  # Too long
            "#GGGGGG",   # Invalid hex chars
            "#ff0000",   # Lowercase (depending on requirements)
            "",          # Empty
            None,        # None
            "red",       # Color name instead of hex
            "#RGB"       # Wrong format
        ]
        
        for color in invalid_colors:
            with pytest.raises(ValidationError):
                validate_color_hex(color)
    
    def test_sanitize_user_input(self):
        """Test general user input sanitization"""
        # Test XSS prevention
        xss_inputs = [
            "<script>alert('xss')</script>",
            "Normal text<script>evil()</script>",
            "<img src=x onerror='alert(1)'>",
            "javascript:alert('xss')",
            "<iframe src='evil.com'></iframe>"
        ]
        
        for malicious_input in xss_inputs:
            sanitized = sanitize_user_input(malicious_input)
            assert "<script>" not in sanitized
            assert "javascript:" not in sanitized
            assert "<iframe>" not in sanitized
            assert "onerror=" not in sanitized
        
        # Test SQL injection prevention  
        sql_inputs = [
            "'; DROP TABLE users; --",
            "admin'--",
            "1' OR '1'='1",
            "'; INSERT INTO users VALUES ('hacker'); --"
        ]
        
        for sql_input in sql_inputs:
            sanitized = sanitize_user_input(sql_input)
            # Should be safely escaped or removed
            assert "DROP TABLE" not in sanitized.upper()
            assert "INSERT INTO" not in sanitized.upper()
            # But should preserve legitimate single quotes
            assert "can't" in sanitize_user_input("can't do this")
        
        # Test whitespace normalization
        whitespace_tests = [
            ("  extra   spaces  ", "extra spaces"),
            ("\n\r\t mixed whitespace \n", "mixed whitespace"),
            ("normal text", "normal text")
        ]
        
        for input_text, expected in whitespace_tests:
            sanitized = sanitize_user_input(input_text)
            assert sanitized == expected
    
    def test_validate_webhook_headers(self):
        """Test webhook header validation"""
        # Valid webhook headers
        valid_headers = {
            'HTTP_X_GOOG_RESOURCE_ID': 'calendar_123@gmail.com',
            'HTTP_X_GOOG_CHANNEL_ID': 'webhook_channel_456',
            'HTTP_X_GOOG_RESOURCE_STATE': 'sync',
            'HTTP_X_GOOG_MESSAGE_NUMBER': '1'
        }
        
        validate_webhook_headers(valid_headers)  # Should not raise
        
        # Missing required headers
        incomplete_headers = {
            'HTTP_X_GOOG_RESOURCE_ID': 'calendar_123@gmail.com'
            # Missing channel ID
        }
        
        with pytest.raises(ValidationError, match="Missing required webhook header"):
            validate_webhook_headers(incomplete_headers)
        
        # Invalid header values
        invalid_headers = {
            'HTTP_X_GOOG_RESOURCE_ID': '<script>alert("xss")</script>',
            'HTTP_X_GOOG_CHANNEL_ID': 'valid_channel'
        }
        
        with pytest.raises(ValidationError, match="Invalid webhook header value"):
            validate_webhook_headers(invalid_headers)
        
        # Empty headers
        with pytest.raises(ValidationError):
            validate_webhook_headers({})
```

---

## Files to Create/Modify

### New Files:
- `tests/unit/test_rate_limiting.py` - Rate limiting algorithm tests
- `tests/unit/test_token_encryption.py` - Encryption/decryption tests
- `tests/unit/test_datetime_utils.py` - Date/time utility tests
- `tests/unit/test_validation_utils.py` - Input validation tests
- `tests/unit/__init__.py` - Package initialization

### Unit Test Structure:
```
tests/unit/
├── __init__.py
├── test_rate_limiting.py          # Complex retry algorithms
├── test_token_encryption.py       # Cryptographic functions
├── test_datetime_utils.py          # Date/time calculations
└── test_validation_utils.py       # Input validation logic
```

---

## Validation Steps

1. **Run Unit Tests**:
   ```bash
   cd src
   pytest tests/unit/ -v --tb=short
   ```

2. **Verify Speed**:
   ```bash
   pytest tests/unit/ --durations=10
   # All unit tests should complete in <1 second total
   ```

3. **Test Coverage of Unit-Testable Code**:
   ```bash
   pytest tests/unit/ --cov=apps.calendars.utils --cov=apps.accounts.utils
   ```

4. **Validate No External Dependencies**:
   ```bash
   pytest tests/unit/ --disable-socket
   # Should pass - no network calls in unit tests
   ```

---

## Success Criteria

- [ ] Unit tests only for complex algorithms and pure functions
- [ ] No unit tests for database operations, HTTP requests, or service orchestration
- [ ] All unit tests run in <1 second total execution time
- [ ] Rate limiting algorithm thoroughly tested with edge cases
- [ ] Encryption/decryption functions tested with security edge cases
- [ ] Date/time utilities tested with timezone and format edge cases
- [ ] Input validation tested with malicious input attempts
- [ ] No mocking of internal services or business logic
- [ ] Tests verify mathematical correctness of algorithms

---

## Definition of Done

- [ ] Only algorithms and utilities that meet Guilfoyle criteria have unit tests
- [ ] All unit tests are fast, isolated, and deterministic
- [ ] Complex business logic edge cases are thoroughly covered
- [ ] Security-critical functions (encryption, validation) are bulletproof
- [ ] No unit tests duplicate coverage already provided by integration tests
- [ ] Tests focus on mathematical correctness, not implementation details
- [ ] Unit test suite complements (not competes with) integration tests

This focused approach ensures unit tests provide value without the maintenance burden of over-testing. Most business logic verification happens through integration tests, while unit tests handle the complex algorithms that genuinely benefit from isolation.
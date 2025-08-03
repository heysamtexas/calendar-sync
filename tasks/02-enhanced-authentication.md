# Enhanced Authentication & OAuth Tasks

## Overview
Implement production-grade OAuth flow and token management with real-world edge case handling.

## Priority: CRITICAL (Foundation for all sync operations)

**Total Enhanced Time: 16 hours** (vs 8.5 hours original)

---

## TASK-007: Production OAuth Flow Implementation
**Status:** Not Started  
**Estimated Time:** 240 minutes (4 hours)  
**Dependencies:** TASK-006 (Enhanced Models)  
**Complexity Level:** High

### Description
Implement a production-ready OAuth flow that handles real-world scenarios and edge cases.

### Enhanced Acceptance Criteria
- [ ] `accounts/views.py` with OAuth views:
  - [ ] `oauth_start()` - Initiate OAuth with state validation
  - [ ] `oauth_callback()` - Handle callback with error recovery
  - [ ] `oauth_revoke()` - Clean revocation handling
  - [ ] `oauth_status()` - Account connection status
- [ ] Multi-account OAuth support with proper isolation
- [ ] State parameter validation to prevent CSRF attacks
- [ ] OAuth scope validation and degradation handling
- [ ] Comprehensive error handling for interrupted flows
- [ ] Session management for OAuth state
- [ ] Redirect URI validation and security

### LLM Prerequisites Section
**MANDATORY validation before starting:**
```bash
# Verify Google Cloud Console setup
echo "Validating Google OAuth configuration..."
python manage.py shell -c "
import os
from django.conf import settings
assert settings.GOOGLE_OAUTH_CLIENT_ID, 'Client ID not configured'
assert settings.GOOGLE_OAUTH_CLIENT_SECRET, 'Client secret not configured'
print('OAuth configuration validated')
"

# Verify models are migrated
python manage.py showmigrations accounts
# Expected: All migrations should show [X] (applied)

# Verify test environment
python manage.py test accounts.tests.test_models --verbosity=0
# Expected: Exit code 0
```

### LLM Success Criteria Section
**CONCRETE success indicators:**
- [ ] File exists: `/path/to/src/accounts/views.py`
- [ ] URL patterns work: `curl http://localhost:8000/auth/start/` returns 302
- [ ] OAuth flow redirects to Google with correct parameters
- [ ] Callback URL handles both success and error cases
- [ ] Session state is properly managed throughout flow
- [ ] CalendarAccount records created successfully

### LLM Failure Detection Section
**STOP immediately if ANY of these occur:**
- Error message contains "Invalid client_id" or "Client authentication failed"
- OAuth redirect URL includes `error=access_denied`
- Session state validation fails with 400/403 errors
- CalendarAccount creation fails with database integrity errors
- Test suite fails with authentication-related errors

### LLM Recovery Procedures Section
**If task fails:**
1. **Client ID/Secret Issues**: 
   - Verify Google Cloud Console configuration
   - Check `.env` file has correct values
   - Restart Django server to pick up new environment variables
2. **Redirect URI Issues**:
   - Verify Google Console has exact redirect URI configured
   - Check Django URL patterns match expected paths
3. **Permission Issues**:
   - Verify Google OAuth scope is correctly set to calendar scope
   - Check if test Google account has necessary permissions

### LLM Validation Commands Section
**Run these EXACT commands to verify success:**
```bash
# Test 1: Verify OAuth views exist and load
python manage.py shell -c "
from accounts.views import oauth_start, oauth_callback
print('OAuth views imported successfully')
"

# Test 2: Test OAuth start redirects correctly
python manage.py test accounts.tests.test_oauth.TestOAuthFlow.test_oauth_start_redirect

# Test 3: Test callback handling
python manage.py test accounts.tests.test_oauth.TestOAuthFlow.test_oauth_callback_success

# Test 4: Verify session management
python manage.py test accounts.tests.test_oauth.TestOAuthFlow.test_oauth_state_validation
```

### Enhanced Implementation Notes
- **State Management**: Use cryptographically secure random state with expiration
- **Error Recovery**: Handle network failures during OAuth dance gracefully
- **Multi-Account**: Support connecting multiple Google accounts per user
- **Security**: Validate all parameters to prevent OAuth attacks
- **Logging**: Comprehensive audit trail for OAuth operations

### Production Considerations
```python
# Example secure state generation
import secrets
import time

def generate_oauth_state():
    """Generate secure OAuth state with timestamp"""
    timestamp = str(int(time.time()))
    random_part = secrets.token_urlsafe(32)
    return f"{timestamp}:{random_part}"

def validate_oauth_state(state, max_age_seconds=600):
    """Validate OAuth state and check expiration"""
    try:
        timestamp_str, _ = state.split(':', 1)
        timestamp = int(timestamp_str)
        if time.time() - timestamp > max_age_seconds:
            raise ValueError("State expired")
        return True
    except (ValueError, IndexError):
        return False
```

---

## TASK-008: Token Lifecycle Management
**Status:** Not Started  
**Estimated Time:** 120 minutes (2 hours)  
**Dependencies:** TASK-007  
**Complexity Level:** High

### Description
Implement production-grade token lifecycle management that handles refresh during active operations.

### Enhanced Acceptance Criteria
- [ ] `accounts/services/token_manager.py` created
- [ ] TokenManager class with methods:
  - [ ] `ensure_valid_token(account)` - Check and refresh if needed
  - [ ] `refresh_token_with_retry(account)` - Robust refresh with retries
  - [ ] `handle_token_refresh_during_operation(account, operation)` - Operation-aware refresh
  - [ ] `validate_token_scope(account, required_scopes)` - Scope validation
  - [ ] `handle_revoked_token(account)` - Clean revocation handling
- [ ] Automatic token refresh before expiration (5-minute buffer)
- [ ] Token refresh during long-running operations
- [ ] Graceful handling of revoked or invalid tokens
- [ ] Thread-safe token refresh for concurrent operations
- [ ] Token encryption at rest

### LLM Prerequisites Section
**MANDATORY validation before starting:**
```bash
# Verify OAuth flow is working
python manage.py test accounts.tests.test_oauth --verbosity=0

# Verify CalendarAccount model has token fields
python manage.py shell -c "
from accounts.models import CalendarAccount
fields = [f.name for f in CalendarAccount._meta.fields]
assert 'access_token' in fields, 'Missing access_token field'
assert 'refresh_token' in fields, 'Missing refresh_token field'
assert 'token_expires_at' in fields, 'Missing token_expires_at field'
print('Token fields validated')
"

# Verify Google API client libraries
python -c "
import google.oauth2.credentials
import google.auth.transport.requests
print('Google auth libraries available')
"
```

### LLM Success Criteria Section
**CONCRETE success indicators:**
- [ ] File exists: `/path/to/src/accounts/services/token_manager.py`
- [ ] TokenManager can refresh expired tokens successfully
- [ ] Token refresh works during ongoing API operations
- [ ] Revoked tokens are handled without crashing
- [ ] Thread safety validated with concurrent operations
- [ ] Token encryption/decryption works correctly

### LLM Failure Detection Section
**STOP immediately if ANY of these occur:**
- Token refresh fails with "invalid_grant" error
- Concurrent token refresh causes database deadlocks
- Token encryption/decryption fails with crypto errors
- Memory leaks during token refresh operations
- Thread safety tests fail with race conditions

### LLM Recovery Procedures Section
**If task fails:**
1. **Invalid Grant Errors**:
   - Check if refresh token is valid and not revoked
   - Verify Google OAuth client credentials are correct
   - Test with a fresh OAuth flow to get new tokens
2. **Concurrency Issues**:
   - Add database transaction isolation
   - Implement proper locking mechanisms
   - Test with realistic concurrent scenarios
3. **Encryption Issues**:
   - Verify Django SECRET_KEY is properly configured
   - Check cryptography library is installed correctly
   - Test encryption/decryption with known test data

### Enhanced Implementation Pattern
```python
import threading
from contextlib import contextmanager
from django.db import transaction

class TokenManager:
    _refresh_locks = {}  # Account ID -> Lock
    
    @contextmanager
    def token_refresh_lock(self, account_id):
        """Ensure only one thread refreshes tokens per account"""
        if account_id not in self._refresh_locks:
            self._refresh_locks[account_id] = threading.Lock()
        
        with self._refresh_locks[account_id]:
            yield
    
    def execute_with_token_safety(self, account, operation, *args, **kwargs):
        """Execute operation with automatic token refresh on auth failure"""
        max_retries = 2
        
        for attempt in range(max_retries):
            # Ensure token is valid before operation
            if self.ensure_valid_token(account):
                try:
                    return operation(*args, **kwargs)
                except AuthenticationError:
                    if attempt < max_retries - 1:
                        # Force token refresh and retry
                        with self.token_refresh_lock(account.id):
                            self.force_token_refresh(account)
                        continue
                    raise
        
        raise TokenRefreshError("Failed to refresh token after retries")
```

---

## TASK-009: OAuth Edge Case Handling
**Status:** Not Started  
**Estimated Time:** 90 minutes (1.5 hours)  
**Dependencies:** TASK-008  
**Complexity Level:** Medium

### Description
Handle OAuth edge cases that occur in production: interrupted flows, permission changes, account linking/unlinking.

### Enhanced Acceptance Criteria
- [ ] OAuth flow interruption recovery (user closes browser mid-flow)
- [ ] Permission scope reduction handling (user denies some permissions)
- [ ] Account reconnection flow for revoked tokens
- [ ] Duplicate account prevention (same Google account linked twice)
- [ ] OAuth timeout handling (user takes too long to authorize)
- [ ] Comprehensive error messages for user-facing scenarios
- [ ] Admin interface for OAuth troubleshooting

### LLM Prerequisites Section
**MANDATORY validation before starting:**
```bash
# Verify token management is working
python manage.py test accounts.tests.test_token_manager --verbosity=0

# Verify OAuth views handle basic cases
python manage.py test accounts.tests.test_oauth --verbosity=0

# Check error handling infrastructure exists
python manage.py shell -c "
from accounts.services.token_manager import TokenManager
tm = TokenManager()
print('TokenManager available for edge case handling')
"
```

### Enhanced Edge Cases to Handle

#### 1. Interrupted OAuth Flow
```python
def handle_oauth_interruption(request):
    """Handle when user abandons OAuth flow"""
    # Clean up any partial OAuth state
    if 'oauth_state' in request.session:
        state = request.session['oauth_state']
        # Log abandonment for analytics
        logger.info(f"OAuth flow abandoned: state={state}")
        del request.session['oauth_state']
    
    return redirect('oauth_start')
```

#### 2. Permission Scope Changes
```python
def handle_reduced_permissions(account, granted_scopes):
    """Handle when user grants fewer permissions than requested"""
    required_scopes = {'https://www.googleapis.com/auth/calendar'}
    
    if not required_scopes.issubset(set(granted_scopes)):
        # Mark account as having insufficient permissions
        account.status = 'insufficient_permissions'
        account.save()
        
        return False, "Calendar permission required for sync functionality"
    
    return True, "Permissions validated"
```

#### 3. Account Reconnection Flow
```python
def handle_account_reconnection(user, google_account_id):
    """Handle reconnecting a previously linked account"""
    try:
        existing_account = CalendarAccount.objects.get(
            user=user,
            google_account_id=google_account_id,
            status='revoked'
        )
        # Reactivate existing account instead of creating new one
        existing_account.status = 'active'
        existing_account.save()
        return existing_account
    except CalendarAccount.DoesNotExist:
        # Create new account record
        return None
```

### LLM Validation Commands Section
```bash
# Test edge case handling
python manage.py test accounts.tests.test_oauth_edge_cases.TestOAuthEdgeCases.test_interrupted_flow
python manage.py test accounts.tests.test_oauth_edge_cases.TestOAuthEdgeCases.test_reduced_permissions
python manage.py test accounts.tests.test_oauth_edge_cases.TestOAuthEdgeCases.test_account_reconnection
python manage.py test accounts.tests.test_oauth_edge_cases.TestOAuthEdgeCases.test_duplicate_account_prevention

# Test timeout handling
python manage.py test accounts.tests.test_oauth_edge_cases.TestOAuthEdgeCases.test_oauth_timeout
```

---

## TASK-010: Enhanced Security & Audit
**Status:** Not Started  
**Estimated Time:** 60 minutes (1 hour)  
**Dependencies:** TASK-009  
**Complexity Level:** Medium

### Description
Implement security hardening and audit trail for OAuth operations.

### Enhanced Acceptance Criteria
- [ ] Audit logging for all OAuth operations
- [ ] Rate limiting for OAuth endpoints
- [ ] CSRF protection for OAuth flows
- [ ] Secure token storage with encryption
- [ ] OAuth session timeout enforcement
- [ ] Security headers for OAuth endpoints
- [ ] Intrusion detection for OAuth abuse

### Security Implementation Pattern
```python
from django.core.cache import cache
from django.http import HttpResponseTooManyRequests
import hashlib

class OAuthSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.path.startswith('/auth/'):
            # Rate limiting
            if self.is_rate_limited(request):
                return HttpResponseTooManyRequests("Too many OAuth attempts")
            
            # Security headers
            response = self.get_response(request)
            response['X-Frame-Options'] = 'DENY'
            response['X-Content-Type-Options'] = 'nosniff'
            return response
        
        return self.get_response(request)
    
    def is_rate_limited(self, request):
        """Rate limit OAuth attempts per IP"""
        ip = self.get_client_ip(request)
        key = f"oauth_attempts:{ip}"
        attempts = cache.get(key, 0)
        
        if attempts >= 10:  # Max 10 attempts per hour
            return True
        
        cache.set(key, attempts + 1, 3600)  # 1 hour
        return False
```

---

## Summary: Enhanced Authentication

**Total Enhanced Time: 16 hours** (vs 8.5 hours original)

### Key Enhancements
1. **Production OAuth Flow**: Handles real-world edge cases (+4 hours)
2. **Token Lifecycle Management**: Operation-aware token refresh (+2 hours)
3. **Edge Case Handling**: Interrupted flows, permission changes (+1.5 hours)
4. **Security & Audit**: Rate limiting, encryption, audit trail (+1 hour)

### Critical Success Factors
- **Bulletproof Token Management**: Never fail operations due to token issues
- **Graceful Error Handling**: User-friendly errors for all OAuth scenarios
- **Security First**: Protect against OAuth attacks and abuse
- **Production Ready**: Handle the complexity of real-world OAuth flows

### AI Agent Guardrails
- **Clear Prerequisites**: Every task has concrete validation steps
- **Success Criteria**: Specific, measurable outcomes
- **Failure Detection**: Explicit failure conditions and recovery procedures
- **Validation Commands**: Exact commands to verify task completion

This enhanced authentication foundation provides the reliability needed for a production calendar sync system while giving AI agents the structure to implement it correctly.
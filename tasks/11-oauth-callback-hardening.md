# TASK-11: OAuth Callback Hardening

## Priority: HIGH
## Estimated Time: 3-4 hours
## Dependencies: TASK-10 (Business Logic Extraction)

## Problem Statement

Guilfoyle identified critical security vulnerabilities in the OAuth callback implementation that could lead to account takeover, data corruption, and inconsistent application state:

### OAuth Security Issues Found:
1. **State Parameter Validation Missing**
   - No OAuth state parameter generation or validation
   - Vulnerable to CSRF attacks on OAuth flow
   - No protection against authorization code injection

2. **Insufficient Error Handling**
   - Generic error responses leak implementation details
   - No structured error logging for security events
   - Missing validation of OAuth response parameters

3. **Token Security Weaknesses**
   - No token validation before storage
   - Missing expiry time validation
   - No secure token rotation on refresh

4. **Session Security Issues**
   - No session invalidation on OAuth errors
   - Missing rate limiting for OAuth attempts
   - No audit trail for authentication events

## Acceptance Criteria

- [ ] OAuth state parameter implemented with CSRF protection
- [ ] Comprehensive parameter validation for OAuth responses
- [ ] Secure token handling with proper validation
- [ ] Structured error logging for all OAuth events
- [ ] Rate limiting implemented for OAuth endpoints
- [ ] Session security enhanced throughout OAuth flow
- [ ] Audit trail created for authentication events
- [ ] All existing OAuth functionality preserved
- [ ] Security tests validate all attack vectors
- [ ] OWASP OAuth security guidelines followed

## Implementation Steps

### Step 1: OAuth State Parameter Implementation (1.5 hours)

1. **Generate Secure State Parameters**
   - Create cryptographically secure state generation
   - Store state in secure session with expiry
   - Validate state on callback with timing-safe comparison

2. **CSRF Protection Enhancement**
   - Tie state to user session
   - Implement state expiry (5-minute window)
   - Add state replay protection

3. **State Validation Logic**
   - Secure state comparison
   - Proper error handling for invalid state
   - Session cleanup on validation failure

### Step 2: Enhanced OAuth Parameter Validation (1 hour)

1. **Authorization Code Validation**
   - Verify code format and length
   - Validate against expected patterns
   - Prevent code injection attacks

2. **Error Response Handling**
   - Validate OAuth error parameters
   - Log security-relevant errors
   - Provide user-safe error messages

3. **Scope and Permission Validation**
   - Verify returned scopes match requested
   - Validate user consent properly received
   - Handle scope reduction scenarios

### Step 3: Token Security Hardening (1 hour)

1. **Token Validation Enhancement**
   - Validate token format before storage
   - Verify token expiry times
   - Implement secure token rotation

2. **Refresh Token Security**
   - Implement refresh token rotation
   - Secure refresh token storage
   - Add refresh token expiry validation

3. **Token Lifecycle Management**
   - Proper token invalidation
   - Secure token cleanup
   - Token usage audit logging

### Step 4: Security Monitoring and Audit (30 minutes)

1. **Authentication Event Logging**
   - Log all OAuth attempts and outcomes
   - Record suspicious activity patterns
   - Create security event metrics

2. **Rate Limiting Implementation**
   - Limit OAuth callback attempts per IP/user
   - Implement progressive delays for failures
   - Add temporary account lockout for abuse

3. **Security Monitoring**
   - Monitor for OAuth abuse patterns
   - Alert on suspicious authentication activity
   - Track token usage anomalies

## Files to Create/Modify

### OAuth Security Enhancement
- `apps/accounts/services/oauth_security.py` - OAuth security utilities
- `apps/accounts/middleware.py` - Rate limiting middleware
- `apps/accounts/views.py` - Enhanced OAuth views with security
- `apps/accounts/models.py` - Add OAuth audit fields

### Security Monitoring
- `apps/accounts/monitoring.py` - Security event monitoring
- `apps/accounts/utils.py` - Security utility functions

### Testing
- `apps/accounts/tests/test_oauth_security.py` - Comprehensive security tests
- `apps/accounts/tests/test_rate_limiting.py` - Rate limiting tests

## Code Examples

### OAuth State Management
```python
# apps/accounts/services/oauth_security.py
import secrets
import hmac
import hashlib
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class OAuthStateManager:
    """Secure OAuth state parameter management"""
    
    STATE_EXPIRY = 300  # 5 minutes
    STATE_LENGTH = 32
    
    @classmethod
    def generate_state(cls, user_id, session_key):
        """Generate cryptographically secure OAuth state"""
        # Generate random state
        random_state = secrets.token_urlsafe(cls.STATE_LENGTH)
        
        # Create signed state tied to user session
        state_data = f"{user_id}:{session_key}:{timezone.now().isoformat()}"
        signature = hmac.new(
            settings.SECRET_KEY.encode(),
            f"{random_state}:{state_data}".encode(),
            hashlib.sha256
        ).hexdigest()
        
        full_state = f"{random_state}.{signature}"
        
        # Store state with expiry
        cache_key = f"oauth_state:{random_state}"
        cache.set(cache_key, {
            'user_id': user_id,
            'session_key': session_key,
            'created_at': timezone.now().isoformat(),
            'signature': signature
        }, timeout=cls.STATE_EXPIRY)
        
        logger.info(
            "OAuth state generated",
            extra={
                'user_id': user_id,
                'state_prefix': random_state[:8],
                'expires_at': timezone.now() + timedelta(seconds=cls.STATE_EXPIRY)
            }
        )
        
        return full_state
    
    @classmethod
    def validate_state(cls, state, user_id, session_key):
        """Validate OAuth state with timing-safe comparison"""
        if not state or '.' not in state:
            logger.warning(
                "OAuth state validation failed: invalid format",
                extra={'user_id': user_id, 'state_format': bool(state)}
            )
            return False
        
        try:
            random_state, provided_signature = state.split('.', 1)
            
            # Retrieve stored state
            cache_key = f"oauth_state:{random_state}"
            stored_data = cache.get(cache_key)
            
            if not stored_data:
                logger.warning(
                    "OAuth state validation failed: state not found or expired",
                    extra={'user_id': user_id, 'state_prefix': random_state[:8]}
                )
                return False
            
            # Validate user and session match
            if stored_data['user_id'] != user_id or stored_data['session_key'] != session_key:
                logger.warning(
                    "OAuth state validation failed: user/session mismatch",
                    extra={
                        'user_id': user_id,
                        'stored_user_id': stored_data['user_id'],
                        'session_match': stored_data['session_key'] == session_key
                    }
                )
                cache.delete(cache_key)  # Clean up invalid state
                return False
            
            # Timing-safe signature comparison
            expected_signature = stored_data['signature']
            if not hmac.compare_digest(provided_signature, expected_signature):
                logger.warning(
                    "OAuth state validation failed: signature mismatch",
                    extra={'user_id': user_id, 'state_prefix': random_state[:8]}
                )
                cache.delete(cache_key)
                return False
            
            # Clean up used state (one-time use)
            cache.delete(cache_key)
            
            logger.info(
                "OAuth state validated successfully",
                extra={'user_id': user_id, 'state_prefix': random_state[:8]}
            )
            
            return True
            
        except (ValueError, KeyError) as e:
            logger.warning(
                f"OAuth state validation failed: {e}",
                extra={'user_id': user_id, 'error': str(e)}
            )
            return False

class OAuthParameterValidator:
    """Validate OAuth callback parameters"""
    
    @staticmethod
    def validate_authorization_code(code):
        """Validate authorization code format and content"""
        if not code:
            return False, "Authorization code missing"
        
        # Google authorization codes are typically 4/0A... format
        if not re.match(r'^4/[0-9A-Za-z\-._~]{10,}$', code):
            logger.warning(
                "Invalid authorization code format",
                extra={'code_prefix': code[:10] if len(code) >= 10 else code}
            )
            return False, "Invalid authorization code format"
        
        if len(code) > 512:  # Reasonable length limit
            return False, "Authorization code too long"
        
        return True, None
    
    @staticmethod
    def validate_error_response(error, error_description=None):
        """Validate and log OAuth error responses"""
        valid_errors = {
            'access_denied', 'invalid_request', 'invalid_client',
            'invalid_grant', 'unauthorized_client', 'unsupported_grant_type',
            'invalid_scope', 'server_error', 'temporarily_unavailable'
        }
        
        if error not in valid_errors:
            logger.warning(
                f"Unknown OAuth error received: {error}",
                extra={'error': error, 'description': error_description}
            )
            return False, "Unknown error type"
        
        # Log the specific error for monitoring
        logger.info(
            f"OAuth error received: {error}",
            extra={'error': error, 'description': error_description}
        )
        
        return True, error
```

### Enhanced OAuth Callback View
```python
# apps/accounts/views.py - Enhanced oauth_callback
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.shortcuts import redirect
from django.contrib import messages
from django.db import transaction
from .services.oauth_security import OAuthStateManager, OAuthParameterValidator
from .services.oauth_service import OAuthService
from .monitoring import SecurityEventLogger

@login_required
@require_GET
@csrf_exempt  # OAuth callback doesn't include CSRF token
def oauth_callback(request: HttpRequest) -> HttpResponse:
    """Secure OAuth callback with comprehensive validation"""
    security_logger = SecurityEventLogger(request.user, request.META.get('REMOTE_ADDR'))
    
    try:
        # Extract and validate parameters
        code = request.GET.get('code')
        state = request.GET.get('state')
        error = request.GET.get('error')
        error_description = request.GET.get('error_description')
        
        # Handle OAuth errors first
        if error:
            is_valid, error_msg = OAuthParameterValidator.validate_error_response(
                error, error_description
            )
            if not is_valid:
                security_logger.log_oauth_abuse('invalid_error_parameter', {
                    'error': error,
                    'description': error_description
                })
                messages.error(request, "Authentication failed due to invalid response.")
                return redirect("dashboard:index")
            
            # Log legitimate OAuth denial
            security_logger.log_oauth_event('user_denied_access', {'error': error})
            
            if error == 'access_denied':
                messages.info(request, "Google Calendar access was denied.")
            else:
                messages.error(request, f"Authentication failed: {error}")
            
            return redirect("dashboard:index")
        
        # Validate required parameters
        if not code or not state:
            security_logger.log_oauth_abuse('missing_required_parameters', {
                'has_code': bool(code),
                'has_state': bool(state)
            })
            messages.error(request, "Invalid authentication response.")
            return redirect("dashboard:index")
        
        # Validate authorization code
        is_valid_code, code_error = OAuthParameterValidator.validate_authorization_code(code)
        if not is_valid_code:
            security_logger.log_oauth_abuse('invalid_authorization_code', {
                'error': code_error,
                'code_length': len(code)
            })
            messages.error(request, "Invalid authorization code received.")
            return redirect("dashboard:index")
        
        # Validate OAuth state (CSRF protection)
        if not OAuthStateManager.validate_state(state, request.user.id, request.session.session_key):
            security_logger.log_oauth_abuse('invalid_state_parameter', {
                'state_provided': bool(state),
                'user_id': request.user.id
            })
            messages.error(request, "Authentication request validation failed.")
            return redirect("dashboard:index")
        
        # Exchange code for tokens
        oauth_service = OAuthService(request.user)
        
        try:
            with transaction.atomic():
                result = oauth_service.exchange_code_for_tokens(code)
                
                if result['success']:
                    security_logger.log_oauth_event('successful_authentication', {
                        'account_id': result['account'].id,
                        'email': result['account'].email,
                        'calendars_discovered': result.get('calendars_created', 0)
                    })
                    
                    messages.success(request, result['message'])
                    return redirect("dashboard:account_detail", account_id=result['account'].id)
                else:
                    security_logger.log_oauth_event('token_exchange_failed', {
                        'error': result.get('error', 'Unknown error')
                    })
                    messages.error(request, result['message'])
                    return redirect("dashboard:index")
                    
        except Exception as e:
            security_logger.log_oauth_event('token_exchange_exception', {
                'error': str(e),
                'error_type': type(e).__name__
            })
            logger.exception(f"OAuth token exchange failed for user {request.user.username}")
            messages.error(request, "Failed to complete authentication. Please try again.")
            return redirect("dashboard:index")
            
    except Exception as e:
        security_logger.log_oauth_event('callback_exception', {
            'error': str(e),
            'error_type': type(e).__name__
        })
        logger.exception(f"OAuth callback failed for user {request.user.username}")
        messages.error(request, "Authentication failed. Please try again.")
        return redirect("dashboard:index")
```

### Rate Limiting Middleware
```python
# apps/accounts/middleware.py
from django.http import HttpResponseTooManyRequests, JsonResponse
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class OAuthRateLimitMiddleware:
    """Rate limiting for OAuth endpoints"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Rate limit configuration
        self.oauth_paths = ['/auth/google/', '/auth/callback/']
        self.rate_limits = {
            'per_ip': {'requests': 10, 'window': 300},  # 10 requests per 5 minutes
            'per_user': {'requests': 5, 'window': 300},  # 5 requests per 5 minutes
        }
    
    def __call__(self, request):
        # Check if this is an OAuth endpoint
        if any(request.path.startswith(path) for path in self.oauth_paths):
            if not self._check_rate_limits(request):
                logger.warning(
                    "OAuth rate limit exceeded",
                    extra={
                        'ip': request.META.get('REMOTE_ADDR'),
                        'user_id': request.user.id if request.user.is_authenticated else None,
                        'path': request.path
                    }
                )
                
                if request.path.startswith('/auth/callback/'):
                    # For callback, redirect with error message
                    from django.shortcuts import redirect
                    from django.contrib import messages
                    messages.error(request, "Too many authentication attempts. Please try again later.")
                    return redirect('dashboard:index')
                else:
                    # For other endpoints, return 429
                    return HttpResponseTooManyRequests(
                        "Too many requests. Please try again later.",
                        content_type="text/plain"
                    )
        
        response = self.get_response(request)
        return response
    
    def _check_rate_limits(self, request):
        """Check rate limits for IP and user"""
        ip = request.META.get('REMOTE_ADDR')
        user_id = request.user.id if request.user.is_authenticated else None
        
        # Check IP-based rate limit
        if not self._check_limit('ip', ip, self.rate_limits['per_ip']):
            return False
        
        # Check user-based rate limit
        if user_id and not self._check_limit('user', user_id, self.rate_limits['per_user']):
            return False
        
        return True
    
    def _check_limit(self, limit_type, identifier, config):
        """Check specific rate limit"""
        cache_key = f"oauth_rate_limit:{limit_type}:{identifier}"
        
        current_time = timezone.now()
        window_start = current_time - timedelta(seconds=config['window'])
        
        # Get current request timestamps
        requests = cache.get(cache_key, [])
        
        # Filter out old requests
        requests = [req_time for req_time in requests if req_time > window_start]
        
        # Check if limit exceeded
        if len(requests) >= config['requests']:
            return False
        
        # Add current request
        requests.append(current_time)
        
        # Store updated list
        cache.set(cache_key, requests, timeout=config['window'])
        
        return True
```

## Testing Requirements

### Security Tests
- Test OAuth state parameter generation and validation
- Test authorization code validation and injection attempts
- Test rate limiting functionality
- Test error handling and information disclosure

### Integration Tests
- Test complete OAuth flow with security enhancements
- Test transaction rollback on security failures
- Test audit logging functionality

### Penetration Testing
- Test CSRF attacks on OAuth flow
- Test authorization code injection
- Test rate limit bypass attempts
- Test session hijacking scenarios

## Definition of Done

- [ ] OAuth state parameter implemented with CSRF protection
- [ ] All OAuth parameters validated with security checks
- [ ] Rate limiting implemented and tested
- [ ] Security event logging comprehensive
- [ ] All existing OAuth functionality preserved
- [ ] Security tests achieve 100% coverage of attack vectors
- [ ] OWASP OAuth security guidelines compliance verified
- [ ] No information disclosure in error messages
- [ ] Audit trail complete for all authentication events
- [ ] Code review completed by security expert

## Success Metrics

- Zero OAuth CSRF vulnerabilities in security scan
- All OAuth abuse attempts logged and blocked
- Rate limiting prevents OAuth endpoint abuse
- Security audit shows no critical OAuth vulnerabilities
- Authentication events properly tracked and monitored
- OAuth flow completion rate maintained after security enhancements

This task implements enterprise-grade OAuth security following OWASP guidelines and industry best practices.
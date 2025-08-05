# TASK GT-06: Testing Guidelines and Patterns
## *"Establish testing standards and code review criteria"*

### Priority: HIGH - GOVERNANCE
### Estimated Time: 2-3 hours
### Dependencies: GT-01 through GT-05 (All previous tasks)
### Status: Ready for Implementation

---

## Problem Statement

Without clear testing guidelines, teams will inevitably drift back to the old anti-patterns:
- New tests will mock internal services
- Complex algorithms will lack proper unit test coverage
- Integration tests will become cluttered with implementation details
- Code reviews won't catch testing anti-patterns

**Guilfoyle's Approach**: Establish clear, enforceable guidelines with specific patterns and anti-patterns. Make testing standards part of the development culture, not just documentation.

---

## Testing Guidelines Philosophy

**The Four Pillars of Guilfoyle Testing:**

1. **Integration Tests First** - Test business outcomes through complete workflows
2. **Mock at Boundaries Only** - External APIs only, never internal services
3. **Unit Tests for Algorithms** - Complex logic that benefits from isolation
4. **Security at Real Boundaries** - Test auth/authz with real Django mechanisms

**Code Review Mantras:**
- "Does this test business outcomes or implementation details?"
- "Would this test still pass if the feature was broken?"
- "Are we testing our code or testing mocks?"
- "Is this complex enough to deserve isolation?"

---

## Acceptance Criteria

- [ ] Comprehensive testing guidelines document
- [ ] Code review checklist for testing patterns
- [ ] Specific examples of good vs bad tests
- [ ] Pre-commit hooks for testing anti-patterns
- [ ] Team training materials and decision trees
- [ ] Testing pattern templates for common scenarios
- [ ] Integration with CI/CD for automated pattern checking
- [ ] Documentation for onboarding new developers

---

## Implementation Steps

### Step 1: Core Testing Guidelines (90 minutes)

Create comprehensive guidelines document:

**File: `docs/testing_guidelines.md`**

```markdown
# Testing Guidelines - The Guilfoyle Standard

## Philosophy

> "A few reliable tests that catch real bugs are infinitely more valuable than hundreds of brittle tests that give false confidence."

## The Decision Tree

For every test you write, ask these questions in order:

### 1. What am I testing?
- **Business workflow?** → Integration test
- **Complex algorithm?** → Unit test (if it meets the criteria)
- **External API integration?** → Integration test with mocked external calls
- **Security boundary?** → Integration test with real Django auth
- **Framework functionality?** → Don't test (Django/Python handle this)

### 2. Does this need isolation? (Unit Test Criteria)
**ALL must be true:**
- [ ] Complex algorithm with multiple edge cases
- [ ] Pure function (no external dependencies)
- [ ] Critical business logic that must be bulletproof
- [ ] Hard to test thoroughly in integration tests

**If ANY is false → Use integration test instead**

### 3. What should I mock?
- **External APIs** → Mock (Google Calendar API, etc.)
- **Internal services** → Never mock (test the real interaction)
- **Database** → Use real database (with transactions/rollback)
- **Time/randomness** → Mock only when necessary for deterministic tests

## Testing Patterns

### ✅ GOOD: Integration Test Pattern

```python
def test_user_connects_google_account_and_syncs_calendar(self):
    """Tests complete business workflow with real components"""
    # Setup: Real user, real database
    user = User.objects.create_user(username='testuser')
    self.client.force_login(user)
    
    # Mock only external boundary (Google API)
    with patch('googleapiclient.discovery.build') as mock_build:
        mock_service = Mock()
        mock_build.return_value = mock_service
        mock_service.userinfo().get().execute.return_value = {
            'id': 'google123', 'email': user.email
        }
        
        # Test complete workflow
        response = self.client.post('/connect-google/')
        
        # Verify business outcomes
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CalendarAccount.objects.filter(user=user).exists())
        
        # Real database, real models, real business logic
```

### ❌ BAD: Mock Inception Anti-Pattern

```python
def test_sync_engine_calls_google_client(self):
    """DON'T DO THIS: Tests mocks, not business logic"""
    with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient') as mock_client:
        mock_client.return_value.list_events.return_value = []
        
        sync_engine = SyncEngine()
        sync_engine.sync_calendar(calendar_id=123)
        
        # This tests that we called a mock, not that sync actually works
        mock_client.return_value.list_events.assert_called_once()
```

### ✅ GOOD: Unit Test Pattern

```python
def test_rate_limiting_exponential_backoff_calculation(self):
    """Tests complex algorithm in isolation"""
    # Pure function with mathematical complexity
    def calculate_backoff_delay(attempt, base_delay=3):
        return base_delay * (2 ** attempt)
    
    # Test edge cases of algorithm
    assert calculate_backoff_delay(0) == 3   # First retry: 3s
    assert calculate_backoff_delay(1) == 6   # Second retry: 6s
    assert calculate_backoff_delay(2) == 12  # Third retry: 12s
    
    # Test boundary conditions
    assert calculate_backoff_delay(10) == 3072  # 10th retry
```

### ❌ BAD: Unnecessary Unit Test

```python
def test_calendar_save_creates_database_record(self):
    """DON'T DO THIS: Tests Django ORM, not our code"""
    calendar = Calendar(name="Test")
    calendar.save()
    
    # This tests Django's save() method, not our business logic
    self.assertTrue(Calendar.objects.filter(name="Test").exists())
```

## Test Organization

### Directory Structure
```
tests/
├── integration/           # Business workflows (most tests here)
│   ├── test_oauth_flow.py        # Complete OAuth connection flow
│   ├── test_calendar_sync.py     # End-to-end calendar synchronization
│   ├── test_webhook_processing.py # Webhook → sync workflows
│   └── test_user_workflows.py    # Multi-step user scenarios
├── unit/                  # Complex algorithms only
│   ├── test_rate_limiting.py     # Retry algorithm edge cases
│   ├── test_token_encryption.py  # Cryptographic functions
│   ├── test_datetime_utils.py    # Date/time calculations
│   └── test_validation_utils.py  # Input validation logic
└── security/              # Auth/authz boundaries
    ├── test_authentication.py    # Login/logout with real sessions
    └── test_authorization.py     # Permission checking
```

### Naming Conventions

**Integration Tests:**
- `test_user_can_[business_outcome]`
- `test_[workflow]_handles_[error_scenario]`
- `test_[feature]_integration_with_[external_system]`

**Unit Tests:**
- `test_[algorithm]_[specific_case]`
- `test_[function]_edge_case_[description]`
- `test_[calculation]_boundary_conditions`

**Security Tests:**
- `test_[action]_requires_authentication`
- `test_[resource]_access_control`
- `test_[endpoint]_csrf_protection`

## What NOT to Test

### Don't Test Framework Code
```python
# ❌ DON'T DO THIS
def test_user_model_has_username_field(self):
    user = User(username="test")
    self.assertEqual(user.username, "test")  # Tests Django, not our code

# ❌ DON'T DO THIS  
def test_url_routing_works(self):
    response = self.client.get('/dashboard/')
    # Tests Django URL routing, not our business logic
```

### Don't Test Simple CRUD
```python
# ❌ DON'T DO THIS - Integration tests cover this
def test_calendar_model_save(self):
    calendar = Calendar.objects.create(name="Test")
    self.assertEqual(calendar.name, "Test")

# ✅ DO THIS INSTEAD - Test business logic
def test_user_can_create_and_access_calendar(self):
    # Tests complete workflow including permissions, validation, etc.
```

### Don't Mock Internal Services
```python
# ❌ DON'T DO THIS
@patch('apps.calendars.services.sync_engine.SyncEngine')
def test_webhook_triggers_sync(self, mock_sync):
    # Tests interaction with mock, not real sync behavior

# ✅ DO THIS INSTEAD
def test_webhook_triggers_calendar_synchronization(self):
    # Test with real SyncEngine, mock only Google API
    with patch('googleapiclient.discovery.build'):
        # Real webhook → real sync → mocked external API
```

## Error Testing Patterns

### ✅ GOOD: Test Business Error Handling
```python
def test_oauth_flow_handles_google_api_downtime(self):
    """Test business resilience to external failures"""
    with patch('googleapiclient.discovery.build') as mock_build:
        mock_build.side_effect = ConnectionError("Google API unavailable")
        
        response = self.client.get('/oauth/callback/', {'code': 'test'})
        
        # Should handle gracefully, not crash the user experience
        self.assertEqual(response.status_code, 302)
        self.assertContains(response, "temporary error")
```

### ❌ BAD: Test Mock Error Handling
```python
def test_sync_engine_handles_client_error(self):
    """DON'T DO THIS: Tests mock error, not real error handling"""
    with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient') as mock:
        mock.return_value.list_events.side_effect = Exception("Mock error")
        # This doesn't test real error handling
```

## Performance Testing Guidelines

### Integration Performance Tests
```python
def test_calendar_sync_performance_with_large_dataset(self):
    """Test performance with realistic data volumes"""
    # Create realistic test data
    calendar = self._create_calendar_with_100_events()
    
    start_time = time.time()
    sync_engine = SyncEngine()
    sync_engine.sync_calendar(calendar.id)
    elapsed = time.time() - start_time
    
    # Should sync 100 events in under 30 seconds
    self.assertLess(elapsed, 30.0)
```

### Unit Performance Tests
```python
def test_encryption_performance_benchmark(self):
    """Test algorithm performance characteristics"""
    token = "test_token_" * 100  # Realistic size
    
    start_time = time.time()
    for _ in range(1000):
        encrypted = encrypt_token(token)
        decrypt_token(encrypted)
    elapsed = time.time() - start_time
    
    # Should encrypt/decrypt 1000 tokens in under 1 second
    self.assertLess(elapsed, 1.0)
```

## Code Review Checklist

See Step 2 for detailed checklist.
```

### Step 2: Code Review Checklist (60 minutes)

Create enforceable code review criteria:

**File: `docs/testing_code_review_checklist.md`**

```markdown
# Testing Code Review Checklist

## Pre-Review Questions

Before reviewing any test, ask:
1. **Is this test necessary?** (Does it test business logic not covered elsewhere?)
2. **Is this test in the right category?** (Integration vs Unit vs Security)
3. **Does this test provide value?** (Would it catch real bugs?)

## Integration Test Review

### ✅ Approve If:
- [ ] Tests complete business workflow end-to-end
- [ ] Uses real Django components (models, views, auth)
- [ ] Mocks only external APIs (Google, etc.)
- [ ] Verifies business outcomes, not implementation details
- [ ] Would catch bugs if business logic changed
- [ ] Test name describes user scenario or business outcome
- [ ] Setup uses factories or realistic test data
- [ ] Assertions check meaningful business state

### ❌ Request Changes If:
- [ ] Mocks internal services (SyncEngine, CalendarService, etc.)
- [ ] Tests implementation details instead of outcomes
- [ ] Duplicates coverage already provided by other tests
- [ ] Uses unrealistic test data or scenarios
- [ ] Assertions check internal state variables
- [ ] Test would pass even if feature was broken
- [ ] Overly complex setup that obscures the test purpose

### Red Flags (Automatic Rejection):
- `@patch('apps.calendars.services.sync_engine.SyncEngine')`
- `@patch('apps.accounts.services.oauth_service.OAuthService')`
- Testing method calls: `mock_service.method.assert_called_with()`
- Testing internal attributes: `self.assertEqual(obj._internal_var, value)`

## Unit Test Review

### ✅ Approve If:
- [ ] Tests complex algorithm with mathematical logic
- [ ] Function is pure (no external dependencies)
- [ ] Tests edge cases and boundary conditions
- [ ] Critical business logic that needs bulletproof reliability
- [ ] Hard to test thoroughly in integration tests
- [ ] Fast execution (milliseconds, not seconds)
- [ ] No database or HTTP calls

### ❌ Request Changes If:
- [ ] Could be adequately tested by integration test
- [ ] Tests simple CRUD operations
- [ ] Tests Django framework functionality
- [ ] Requires complex mocking to isolate
- [ ] Tests trivial getters/setters
- [ ] Duplicates integration test coverage

### Algorithm Unit Test Criteria:
```python
# ✅ GOOD: Complex algorithm deserving unit test
def test_exponential_backoff_calculation_edge_cases(self):
    """Tests mathematical correctness of retry algorithm"""
    # Multiple edge cases, mathematical complexity
    assert calculate_backoff(0, base=2) == 2
    assert calculate_backoff(5, base=3) == 96
    assert calculate_backoff(10, base=1) == 1024

# ❌ BAD: Simple logic that doesn't need isolation
def test_user_full_name_concatenation(self):
    """Tests trivial string concatenation"""
    user = User(first_name="John", last_name="Doe")
    assert user.get_full_name() == "John Doe"  # Too simple for unit test
```

## Security Test Review

### ✅ Approve If:
- [ ] Tests authentication boundaries with real Django auth
- [ ] Tests authorization with real permission checking
- [ ] Tests CSRF protection with real middleware
- [ ] Tests session security with real session framework
- [ ] Uses realistic attack scenarios
- [ ] Verifies security outcomes, not internal auth details

### ❌ Request Changes If:
- [ ] Mocks authentication or authorization logic
- [ ] Tests internal auth implementation details
- [ ] Uses fake or trivial security scenarios
- [ ] Bypasses security middleware in tests

### Security Test Examples:
```python
# ✅ GOOD: Tests real security boundary
def test_user_cannot_access_other_users_calendars(self):
    """Tests authorization with real permission checking"""
    user1 = User.objects.create_user('user1')
    user2 = User.objects.create_user('user2')
    calendar = Calendar.objects.create(user=user2)
    
    self.client.force_login(user1)
    response = self.client.get(f'/calendars/{calendar.id}/')
    self.assertEqual(response.status_code, 403)  # Real 403 from real auth

# ❌ BAD: Mocks security logic
@patch('django.contrib.auth.decorators.permission_required')
def test_calendar_view_requires_permission(self, mock_perm):
    """DON'T DO THIS: Tests mock, not real security"""
    # This doesn't test real security enforcement
```

## Common Anti-Patterns to Reject

### 1. Mock Inception
```python
# ❌ REJECT: Mocking internal services
@patch('apps.calendars.services.sync_engine.SyncEngine')
def test_webhook_calls_sync_engine(self, mock_sync):
    # This tests mock interaction, not business logic
```

### 2. Testing Implementation Details
```python
# ❌ REJECT: Tests how, not what
def test_sync_engine_calls_google_client_three_times(self):
    # Tests implementation, breaks during refactoring
```

### 3. Framework Testing
```python
# ❌ REJECT: Tests Django, not our code
def test_calendar_model_saves_to_database(self):
    calendar = Calendar.objects.create(name="Test")
    self.assertTrue(Calendar.objects.filter(name="Test").exists())
```

### 4. Trivial Unit Tests
```python
# ❌ REJECT: Too simple for unit test
def test_user_email_property_returns_email(self):
    user = User(email="test@example.com")
    self.assertEqual(user.email, "test@example.com")
```

## Review Comments Templates

### For Mock Inception:
```
❌ This test mocks internal services. Instead:
1. Test the complete workflow with integration test
2. Mock only external APIs (Google Calendar, etc.)
3. Verify business outcomes, not mock interactions

See: docs/testing_guidelines.md#mock-at-boundaries-only
```

### For Implementation Details:
```
❌ This test checks implementation details that could change during refactoring. Instead:
1. Test business outcomes
2. Verify user-visible behavior
3. Focus on "what" not "how"

See: docs/testing_guidelines.md#test-business-outcomes
```

### For Unnecessary Unit Tests:
```
❌ This logic is simple enough to test through integration tests. Instead:
1. Add integration test that covers this behavior
2. Reserve unit tests for complex algorithms only
3. Apply the unit test criteria checklist

See: docs/testing_guidelines.md#unit-test-criteria
```

### For Missing Integration Coverage:
```
✅ Good unit test, but ensure this is covered by integration tests too:
1. Add integration test for the workflow containing this algorithm
2. Unit test should complement, not replace integration coverage

See: docs/testing_guidelines.md#integration-tests-first
```

## Automated Review Checks

### Pre-commit Hook Patterns:
```bash
# File: .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: check-test-patterns
        name: Check for testing anti-patterns
        entry: scripts/check_test_patterns.sh
        language: script
        files: "test_.*\\.py$"
```

### Pattern Detection Script:
```bash
#!/bin/bash
# File: scripts/check_test_patterns.sh

# Check for mock inception anti-patterns
if grep -r "@patch.*apps\." tests/ --include="*.py"; then
    echo "❌ Found mock inception: Don't mock internal services"
    exit 1
fi

# Check for framework testing
if grep -r "assert.*\.save()" tests/ --include="*.py"; then
    echo "❌ Found framework testing: Don't test Django ORM"
    exit 1
fi

# Check for implementation detail testing
if grep -r "assert_called_with\|assert_called_once" tests/ --include="*.py"; then
    echo "❌ Found implementation detail testing: Test outcomes, not calls"
    exit 1
fi

echo "✅ Test patterns look good"
```
```

### Step 3: Testing Templates and Examples (45 minutes)

Create reusable templates for common scenarios:

**File: `docs/testing_templates.md`**

```markdown
# Testing Templates

## Integration Test Templates

### OAuth Flow Template
```python
def test_user_connects_google_account_workflow(self):
    """Template for OAuth integration testing"""
    # Setup: Real user, real database
    user = User.objects.create_user(username='testuser', password='pass')
    self.client.force_login(user)
    
    # Mock external API boundary only
    with patch('googleapiclient.discovery.build') as mock_build:
        # Setup realistic API responses
        mock_oauth_service = Mock()
        mock_calendar_service = Mock()
        
        def build_side_effect(service_name, version, credentials=None):
            if service_name == 'oauth2':
                return mock_oauth_service
            elif service_name == 'calendar':
                return mock_calendar_service
            return Mock()
        
        mock_build.side_effect = build_side_effect
        
        # Mock realistic user info
        mock_oauth_service.userinfo().get().execute.return_value = {
            'id': 'google_user_123',
            'email': user.email,
            'name': 'Test User'
        }
        
        # Mock realistic calendar list
        mock_calendar_service.calendarList().list().execute.return_value = {
            'items': [
                {
                    'id': 'primary',
                    'summary': user.email,
                    'primary': True,
                    'backgroundColor': '#1f4788'
                }
            ]
        }
        
        # Execute complete workflow
        # 1. Initiate OAuth
        response = self.client.get(reverse('accounts:connect'))
        self.assertEqual(response.status_code, 302)
        
        oauth_state = self.client.session.get('oauth_state')
        self.assertIsNotNone(oauth_state)
        
        # 2. Complete OAuth callback
        response = self.client.get(reverse('accounts:oauth_callback'), {
            'code': 'mock_auth_code',
            'state': oauth_state
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify business outcomes
        # 3. Account created
        self.assertTrue(
            CalendarAccount.objects.filter(
                user=user,
                google_account_id='google_user_123'
            ).exists()
        )
        
        # 4. Calendar imported
        account = CalendarAccount.objects.get(user=user)
        self.assertTrue(
            Calendar.objects.filter(
                calendar_account=account,
                google_calendar_id='primary'
            ).exists()
        )
        
        # 5. Session cleaned up
        self.assertNotIn('oauth_state', self.client.session)
```

### Webhook Processing Template
```python
def test_webhook_triggers_calendar_sync_workflow(self):
    """Template for webhook integration testing"""
    # Setup: Real calendar with sync enabled
    user = User.objects.create_user(username='webhookuser')
    account = CalendarAccount.objects.create(
        user=user,
        google_account_id='webhook_test_123',
        email='test@gmail.com',
        is_active=True
    )
    calendar = Calendar.objects.create(
        calendar_account=account,
        google_calendar_id='webhook_calendar_456',
        name='Webhook Test Calendar',
        sync_enabled=True,
        webhook_channel_id='webhook_channel_789'
    )
    
    # Mock external API only
    with patch('googleapiclient.discovery.build') as mock_build:
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        # Mock realistic event list response
        mock_service.events().list().execute.return_value = {
            'items': [
                {
                    'id': 'event_123',
                    'summary': 'Test Event',
                    'start': {'dateTime': '2023-06-01T10:00:00Z'},
                    'end': {'dateTime': '2023-06-01T11:00:00Z'}
                }
            ]
        }
        
        # Trigger webhook
        response = self.client.post(
            reverse('webhooks:google_webhook'),
            HTTP_X_GOOG_RESOURCE_ID=calendar.google_calendar_id,
            HTTP_X_GOOG_CHANNEL_ID='webhook_channel_789'
        )
        
        # Verify webhook processing
        self.assertEqual(response.status_code, 200)
        
        # Verify sync was triggered (Google API called)
        mock_service.events().list.assert_called()
        
        # Verify business outcome (events imported)
        # Note: Actual event creation depends on sync implementation
```

### Error Handling Template
```python
def test_oauth_flow_handles_google_api_errors(self):
    """Template for error scenario testing"""
    user = User.objects.create_user(username='erroruser')
    self.client.force_login(user)
    
    # Test different error scenarios
    error_scenarios = [
        {
            'error': ConnectionError("Network timeout"),
            'expected_behavior': 'graceful_failure',
            'user_message': 'temporary error'
        },
        {
            'error': HttpError(
                resp=Mock(status=403),
                content=b'{"error": "access_denied"}'
            ),
            'expected_behavior': 'permission_error',
            'user_message': 'permission denied'
        }
    ]
    
    for scenario in error_scenarios:
        with patch('googleapiclient.discovery.build') as mock_build:
            mock_build.side_effect = scenario['error']
            
            response = self.client.get(reverse('accounts:oauth_callback'), {
                'code': 'test_code',
                'state': 'test_state'
            })
            
            # Should handle error gracefully
            self.assertEqual(response.status_code, 302)
            
            # Should not create broken account
            self.assertFalse(
                CalendarAccount.objects.filter(user=user).exists()
            )
            
            # Should provide user feedback
            messages = list(response.wsgi_request._messages)
            self.assertTrue(
                any(scenario['user_message'] in str(m) for m in messages)
            )
```

## Unit Test Templates

### Algorithm Testing Template
```python
def test_rate_limiting_algorithm_edge_cases(self):
    """Template for algorithm unit testing"""
    # Test mathematical correctness
    test_cases = [
        # (attempt, base_delay, expected_delay)
        (0, 3, 3),    # First retry
        (1, 3, 6),    # Second retry
        (2, 3, 12),   # Third retry
        (3, 3, 24),   # Fourth retry
        (0, 1, 1),    # Minimum base delay
        (0, 10, 10),  # Large base delay
        (10, 2, 2048) # Many retries
    ]
    
    for attempt, base_delay, expected in test_cases:
        actual = calculate_exponential_backoff(attempt, base_delay)
        self.assertEqual(
            actual, expected,
            f"Failed for attempt={attempt}, base={base_delay}"
        )
    
    # Test boundary conditions
    with self.assertRaises(ValueError):
        calculate_exponential_backoff(-1, 3)  # Negative attempt
    
    with self.assertRaises(ValueError):
        calculate_exponential_backoff(0, 0)   # Zero base delay
```

### Validation Testing Template
```python
def test_input_validation_security_cases(self):
    """Template for validation unit testing"""
    # Test XSS prevention
    xss_inputs = [
        "<script>alert('xss')</script>",
        "Normal text<script>evil()</script>",
        "<img src=x onerror='alert(1)'>",
        "javascript:alert('xss')"
    ]
    
    for malicious_input in xss_inputs:
        sanitized = sanitize_user_input(malicious_input)
        
        # Should remove dangerous content
        self.assertNotIn('<script>', sanitized)
        self.assertNotIn('javascript:', sanitized)
        self.assertNotIn('onerror=', sanitized)
        
        # Should preserve safe content
        if 'Normal text' in malicious_input:
            self.assertIn('Normal text', sanitized)
    
    # Test SQL injection prevention
    sql_inputs = [
        "'; DROP TABLE users; --",
        "admin'--",
        "1' OR '1'='1"
    ]
    
    for sql_input in sql_inputs:
        sanitized = sanitize_user_input(sql_input)
        
        # Should escape or remove dangerous SQL
        self.assertNotIn('DROP TABLE', sanitized.upper())
        self.assertNotIn("1'='1", sanitized)
    
    # Test edge cases
    edge_cases = [
        ("", ""),  # Empty string
        ("   ", ""),  # Whitespace only
        ("normal text", "normal text"),  # Safe content
        ("a" * 1000, "a" * 255)  # Length limiting
    ]
    
    for input_val, expected in edge_cases:
        actual = sanitize_user_input(input_val)
        self.assertEqual(actual, expected)
```

## Security Test Templates

### Authentication Template
```python
def test_endpoint_requires_authentication(self):
    """Template for authentication testing"""
    # Test endpoints requiring authentication
    protected_endpoints = [
        reverse('dashboard:index'),
        reverse('accounts:connect'),
        reverse('calendars:list')
    ]
    
    for endpoint in protected_endpoints:
        # Unauthenticated request should redirect
        response = self.client.get(endpoint)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/login/'))
        
        # Authenticated request should succeed
        user = User.objects.create_user('testuser', password='pass')
        self.client.force_login(user)
        response = self.client.get(endpoint)
        self.assertIn(response.status_code, [200, 302])  # 302 for redirects
```

### Authorization Template
```python
def test_user_can_only_access_own_resources(self):
    """Template for authorization testing"""
    # Setup: Two users with separate resources
    user1 = User.objects.create_user('user1')
    user2 = User.objects.create_user('user2')
    
    account1 = CalendarAccount.objects.create(user=user1, email='user1@test.com')
    account2 = CalendarAccount.objects.create(user=user2, email='user2@test.com')
    
    # Test: User1 can access their resources
    self.client.force_login(user1)
    response = self.client.get(
        reverse('accounts:detail', args=[account1.id])
    )
    self.assertEqual(response.status_code, 200)
    
    # Test: User1 cannot access user2's resources
    response = self.client.get(
        reverse('accounts:detail', args=[account2.id])
    )
    self.assertIn(response.status_code, [403, 404])
```
```

### Step 4: Developer Onboarding Guide (30 minutes)

Create guide for new team members:

**File: `docs/testing_onboarding.md`**

```markdown
# Testing Onboarding Guide

## Welcome to Guilfoyle Testing Standards

This guide will get you up to speed with our testing philosophy and practices.

## Quick Start

### 1. Read This First
- [Testing Guidelines](testing_guidelines.md) - Core philosophy and patterns
- [Code Review Checklist](testing_code_review_checklist.md) - What to look for in reviews

### 2. Understand the Decision Tree
Before writing any test, ask yourself:

```
What am I testing?
├── Complete user workflow? 
│   └── → Integration test (tests/integration/)
├── Complex algorithm with edge cases?
│   ├── Pure function? → Unit test (tests/unit/)
│   └── Has dependencies? → Integration test
├── Security boundary?
│   └── → Integration test with real Django auth
└── Framework functionality?
    └── → Don't test (Django handles this)
```

### 3. Common Mistakes (Avoid These)
❌ **Mock Inception**: Don't mock internal services
❌ **Implementation Details**: Don't test "how", test "what"
❌ **Framework Testing**: Don't test Django's built-in functionality
❌ **Trivial Unit Tests**: Don't unit test simple getters/setters

### 4. Your First Tests

#### Write an Integration Test
```python
def test_user_can_connect_google_account(self):
    """Test complete business workflow"""
    user = User.objects.create_user('testuser')
    self.client.force_login(user)
    
    # Mock only external API
    with patch('googleapiclient.discovery.build') as mock_build:
        mock_service = Mock()
        mock_build.return_value = mock_service
        mock_service.userinfo().get().execute.return_value = {
            'id': 'google123',
            'email': user.email
        }
        
        # Test workflow
        response = self.client.post('/connect-google/')
        
        # Verify business outcome
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CalendarAccount.objects.filter(user=user).exists())
```

#### Write a Unit Test (Only for Complex Algorithms)
```python
def test_exponential_backoff_calculation(self):
    """Test complex algorithm in isolation"""
    # Test mathematical correctness
    assert calculate_backoff(0, base=3) == 3
    assert calculate_backoff(1, base=3) == 6
    assert calculate_backoff(2, base=3) == 12
    
    # Test edge cases
    with pytest.raises(ValueError):
        calculate_backoff(-1, base=3)
```

## Development Workflow

### Before Writing Tests
1. **Check existing coverage**: Is this already tested by integration tests?
2. **Apply decision tree**: Does this need a separate test?
3. **Choose test type**: Integration, unit, or security?

### Writing Tests
1. **Start with integration**: Test the complete workflow first
2. **Add unit tests sparingly**: Only for complex algorithms
3. **Use real components**: Database, models, Django auth
4. **Mock only boundaries**: External APIs, not internal services

### Code Review
1. **Check for anti-patterns**: Mock inception, implementation details
2. **Verify test value**: Would this catch real bugs?
3. **Ensure good practices**: Realistic data, business outcomes

### Running Tests
```bash
# Run all tests
python manage.py test

# Run by category
python manage.py test tests.integration  # Most important
python manage.py test tests.unit         # Algorithms only
python manage.py test tests.security     # Auth boundaries

# Check coverage
coverage run manage.py test
coverage report --fail-under=75
```

## Learning Resources

### Study These Examples
- `tests/integration/test_oauth_flow.py` - Excellent integration test
- `tests/unit/test_rate_limiting.py` - Good unit test example
- `tests/security/test_authentication.py` - Security boundary testing

### Anti-Pattern Examples (Learn What NOT to Do)
- Look at deleted files in git history for mock inception examples
- See PR reviews for implementation detail testing corrections

### When You're Stuck
1. **Ask**: "Am I testing business outcomes or implementation details?"
2. **Ask**: "Would this test still pass if the feature was broken?"
3. **Ask**: "Is this complex enough to deserve isolation?"
4. **Consult**: [Testing Templates](testing_templates.md) for patterns

## Mentorship Program

### New Developer Checklist
- [ ] Read testing guidelines completely
- [ ] Write first integration test with mentor review
- [ ] Write first unit test (if algorithm qualifies) with mentor review
- [ ] Participate in test-focused code review
- [ ] Help review another developer's tests

### Mentor Responsibilities
- [ ] Review new developer's first 5 tests closely
- [ ] Explain anti-pattern rejections thoroughly
- [ ] Share examples of good vs bad tests
- [ ] Gradually reduce oversight as understanding improves

### 30-Day Goals
- [ ] Understand testing philosophy completely
- [ ] Write integration tests confidently
- [ ] Recognize unit test opportunities correctly
- [ ] Spot anti-patterns in code reviews
- [ ] Contribute to testing documentation

## FAQ

### Q: Why don't we unit test everything?
**A**: Most business logic is tested more effectively through integration tests. Unit tests should be reserved for complex algorithms that benefit from isolation.

### Q: When should I mock internal services?
**A**: Never. Mock only external boundaries (APIs, file systems). Internal services should be tested together to verify real interactions.

### Q: How do I know if my test is good?
**A**: Ask: "If I broke the feature, would this test fail?" If no, improve the test or delete it.

### Q: Why are we deleting so many existing tests?
**A**: Tests that provide false confidence are worse than no tests. We're keeping tests that catch real bugs and removing brittle ones.

### Q: What if I'm not sure about a test?
**A**: Default to integration test. It's better to over-test with integration than under-test with brittle unit tests.
```

---

## Files to Create/Modify

### New Files:
- `docs/testing_guidelines.md` - Comprehensive testing standards
- `docs/testing_code_review_checklist.md` - Enforceable review criteria
- `docs/testing_templates.md` - Reusable test patterns
- `docs/testing_onboarding.md` - New developer guide
- `scripts/check_test_patterns.sh` - Automated pattern checking
- `.pre-commit-config.yaml` - Pre-commit hook configuration

### Files to Modify:
- `README.md` - Add testing section with links to guidelines
- `.github/workflows/test.yml` - Add pattern checking to CI (if exists)
- `pyproject.toml` - Add testing configuration

---

## Validation Steps

1. **Review Guidelines Completeness**:
   ```bash
   # Ensure all testing scenarios are covered
   grep -r "TODO\|FIXME" docs/testing_*.md
   ```

2. **Test Pattern Detection**:
   ```bash
   # Verify anti-pattern detection works
   bash scripts/check_test_patterns.sh
   ```

3. **Template Validation**:
   ```bash
   # Verify templates are syntactically correct
   python -m py_compile docs/testing_templates.md
   ```

4. **Documentation Links**:
   ```bash
   # Check all internal links work
   grep -r "\[.*\](" docs/testing_*.md
   ```

---

## Success Criteria

- [ ] Comprehensive testing guidelines document complete
- [ ] Enforceable code review checklist created
- [ ] Anti-pattern detection automated with pre-commit hooks
- [ ] Template library covers common testing scenarios
- [ ] New developer onboarding guide complete
- [ ] Guidelines integrated into CI/CD pipeline
- [ ] Documentation cross-references correct and complete
- [ ] Team training materials ready for distribution

---

## Definition of Done

- [ ] Testing philosophy clearly documented and communicated
- [ ] Code review standards established and enforceable
- [ ] Anti-pattern detection automated in development workflow
- [ ] Template library reduces barrier to writing good tests
- [ ] New developer onboarding streamlined and effective
- [ ] Guidelines enforced through tooling, not just documentation
- [ ] Team culture shift toward integration-first testing approach
- [ ] Sustainable testing practices established for long-term maintenance

This comprehensive guideline system ensures the Guilfoyle testing philosophy becomes ingrained in the development culture, preventing drift back to anti-patterns while making it easy for developers to write effective tests.
# TASK-07: Critical Security Fixes (Guilfoyle Round 1)

## Priority: CRITICAL
## Estimated Time: 6-8 hours
## Dependencies: None (must be completed immediately)

## Problem Statement

Guilfoyle identified critical security vulnerabilities in the HTMX toggle functionality and OAuth callback implementation that must be fixed before any production use:

### Critical Issues Found:
1. **HTMX Toggle Security Flaws**
   - Missing CSRF protection on toggle endpoint
   - No CSRF token in partial templates
   - Inline JavaScript violates CSP policies
   - No loading states or accessibility features

2. **OAuth Callback Security Risks**
   - No transaction safety - partial failures leave DB inconsistent
   - Dangerous default `sync_enabled=True` could cause unwanted syncing
   - No proper error handling for Google API calls
   - Potential for OAuth state manipulation

3. **Template Security Issues**
   - Missing CSRF tokens in HTMX forms
   - Inline styles and JavaScript
   - Poor accessibility (no labels, ARIA attributes)

## Acceptance Criteria

- [ ] All HTMX endpoints have proper CSRF protection
- [ ] No inline JavaScript or styles in templates
- [ ] OAuth callback wrapped in database transactions
- [ ] Default `sync_enabled=False` for security
- [ ] Proper error handling throughout
- [ ] All forms include CSRF tokens
- [ ] Loading indicators for HTMX operations
- [ ] Accessibility attributes added
- [ ] All existing tests still pass
- [ ] New security tests added and passing

## Implementation Steps

### Step 1: Fix HTMX Toggle Security (2 hours)

1. **Add Security Decorators to Toggle View**
   - Add `@require_POST` decorator
   - Add `@csrf_protect` decorator
   - Use `update_fields` for efficiency
   
2. **Update Partial Template Security**
   - Add CSRF token to HTMX requests
   - Remove inline JavaScript
   - Add loading indicators
   - Add accessibility attributes

3. **Test Security Changes**
   - Verify CSRF protection works
   - Test HTMX functionality still works
   - Test accessibility improvements

### Step 2: Secure OAuth Callback (3 hours)

1. **Add Transaction Safety**
   - Wrap calendar discovery in `@transaction.atomic`
   - Handle partial failures gracefully
   - Add proper rollback on errors

2. **Change Security Defaults**
   - Set `sync_enabled=False` by default
   - Require explicit user opt-in for sync
   - Add user feedback about defaults

3. **Improve Error Handling**
   - Add structured logging for failures
   - Provide user-friendly error messages
   - Handle Google API rate limits

### Step 3: Template Security Audit (2 hours)

1. **Remove Security Violations**
   - Remove all inline JavaScript
   - Remove all inline styles
   - Add proper CSS classes

2. **Add CSRF Protection**
   - Audit all forms for CSRF tokens
   - Add HTMX CSRF configuration
   - Test form submissions

3. **Accessibility Improvements**
   - Add proper labels and ARIA attributes
   - Add loading state indicators
   - Test with screen readers

### Step 4: Security Testing (1 hour)

1. **Add Security Tests**
   - Test CSRF protection on toggle endpoint
   - Test transaction rollback scenarios
   - Test OAuth state validation

2. **Penetration Testing**
   - Test for CSRF bypass attempts
   - Test for SQL injection vulnerabilities
   - Test for unauthorized access

## Files to Modify

### Core Security Fixes
- `apps/dashboard/views.py` - Add security decorators, improve error handling
- `templates/dashboard/partials/calendar_sync_status.html` - Add CSRF token, remove inline JS
- `templates/base.html` - Update HTMX CSRF configuration
- `apps/accounts/views.py` - Add transaction safety, change defaults

### Template Security
- `templates/dashboard/account_detail.html` - Remove inline styles
- `static/css/base.css` - Add proper CSS classes for styling

### Testing
- `apps/dashboard/tests.py` - Add security-specific tests
- New file: `apps/dashboard/test_security.py` - Comprehensive security tests

## Testing Requirements

### Unit Tests
- Test toggle view requires POST method
- Test toggle view requires CSRF token
- Test OAuth callback transaction rollback
- Test default sync_enabled=False

### Integration Tests
- Test HTMX toggle with CSRF protection
- Test OAuth flow with API failures
- Test partial template rendering

### Security Tests
- Test CSRF bypass attempts
- Test unauthorized access attempts
- Test transaction consistency

## Code Examples

### Secure Toggle View
```python
@login_required
@require_POST
@csrf_protect
def toggle_calendar_sync(request: HttpRequest, calendar_id: int) -> HttpResponse:
    """Toggle sync status for a specific calendar"""
    calendar = get_object_or_404(
        Calendar, 
        id=calendar_id, 
        calendar_account__user=request.user
    )
    
    calendar.sync_enabled = not calendar.sync_enabled
    calendar.save(update_fields=['sync_enabled'])
    
    logger.info(f"Sync {'enabled' if calendar.sync_enabled else 'disabled'} "
                f"for calendar {calendar.name} by user {request.user.username}")
    
    return render(request, "dashboard/partials/calendar_sync_status.html", {
        "calendar": calendar
    })
```

### Secure Partial Template
```html
{% csrf_token %}
<div id="calendar-{{ calendar.id }}-status" class="calendar-sync-toggle">
    <span class="sync-status">
        {% if calendar.sync_enabled %}
            <span class="status status-active">Enabled</span>
        {% else %}
            <span class="status status-inactive">Disabled</span>  
        {% endif %}
    </span>
    
    <button hx-post="{% url 'dashboard:toggle_calendar_sync' calendar.id %}" 
            hx-target="#calendar-{{ calendar.id }}-status"
            hx-swap="outerHTML"
            hx-indicator="#loading-{{ calendar.id }}"
            class="btn {% if calendar.sync_enabled %}btn-danger{% else %}btn-success{% endif %}"
            aria-label="{% if calendar.sync_enabled %}Disable{% else %}Enable{% endif %} sync for {{ calendar.name }}">
        {% if calendar.sync_enabled %}Disable{% else %}Enable{% endif %}
    </button>
    
    <div id="loading-{{ calendar.id }}" class="htmx-indicator">
        <small class="text-muted">Updating...</small>
    </div>
</div>
```

### Secure OAuth Callback
```python
@transaction.atomic
def oauth_callback(request: HttpRequest) -> HttpResponse:
    """Handle OAuth callback with transaction safety"""
    try:
        # ... OAuth validation logic ...
        
        # Create account with safe defaults
        account, created = CalendarAccount.objects.update_or_create(
            user=request.user,
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

        # Discover calendars with safe defaults
        calendars_created = _discover_calendars_safely(account, service)
        
        if calendars_created > 0:
            messages.success(
                request,
                f"Connected {email} and discovered {calendars_created} calendars. "
                "Sync is disabled by default - enable it for calendars you want to sync."
            )
        
        return redirect("dashboard:account_detail", account_id=account.id)
        
    except Exception as e:
        logger.exception(f"OAuth callback failed for user {request.user.username}: {e}")
        messages.error(
            request,
            "Failed to connect Google Calendar account. Please try again."
        )
        return redirect("dashboard:index")

def _discover_calendars_safely(account, service):
    """Discover calendars with safe defaults and error handling"""
    try:
        all_calendars_result = service.calendarList().list().execute()
        all_calendars = all_calendars_result.get("items", [])
        
        calendars_created = 0
        for cal_item in all_calendars:
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
        
        return calendars_created
        
    except Exception as e:
        logger.error(f"Calendar discovery failed for {account.email}: {e}")
        return 0
```

## Definition of Done

- [ ] All CSRF protection implemented and tested
- [ ] All inline JavaScript/styles removed
- [ ] OAuth callback transaction-safe
- [ ] Default sync_enabled=False implemented
- [ ] All accessibility attributes added
- [ ] Loading indicators implemented
- [ ] All existing functionality still works
- [ ] New security tests passing
- [ ] Code review completed
- [ ] Security audit passed

## Risk Mitigation

### High-Risk Changes
- OAuth callback modifications could break authentication flow
- CSRF protection could break HTMX functionality
- Transaction changes could affect data consistency

### Mitigation Strategies
- Test OAuth flow thoroughly before deployment
- Verify HTMX still works with CSRF protection
- Test transaction rollback scenarios
- Keep database backups during testing
- Deploy to staging environment first

## Success Metrics

- Zero CSRF vulnerabilities detected in security scan
- All HTMX functionality working with CSRF protection
- OAuth flow consistently creates accounts with safe defaults
- No SQL injection or authorization bypass vulnerabilities
- All accessibility requirements met (WCAG 2.1 AA compliance)

This task addresses Guilfoyle's most critical security concerns and makes the application safe for continued development and eventual production use.
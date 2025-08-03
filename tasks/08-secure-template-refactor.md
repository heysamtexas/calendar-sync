# TASK-08: Secure Template Refactor

## Priority: CRITICAL  
## Estimated Time: 4-5 hours
## Dependencies: TASK-07 (Critical Security Fixes)

## Problem Statement

Guilfoyle identified major template security and accessibility issues that violate modern web standards and create security vulnerabilities:

### Template Issues Found:
1. **Content Security Policy Violations**
   - Inline JavaScript in templates (`onchange="this.form.submit()"`)
   - Inline styles scattered throughout templates
   - Missing CSP-compliant event handling

2. **CSRF Token Issues**
   - HTMX forms missing CSRF tokens
   - Manual form handling without proper protection
   - Inconsistent CSRF implementation

3. **Accessibility Failures**
   - No labels for form inputs
   - Missing ARIA attributes
   - No loading state feedback
   - Poor screen reader support

4. **Poor User Experience**
   - No loading indicators during HTMX operations
   - No error state handling
   - No visual feedback for actions

## Acceptance Criteria

- [ ] Zero inline JavaScript in all templates
- [ ] Zero inline styles in all templates
- [ ] All forms have proper CSRF tokens
- [ ] All interactive elements have accessibility attributes
- [ ] Loading states implemented for all HTMX operations
- [ ] Error states properly handled and displayed
- [ ] CSP policy can be enabled without violations
- [ ] WCAG 2.1 AA compliance achieved
- [ ] All HTMX functionality preserved
- [ ] Tests pass for all template changes

## Implementation Steps

### Step 1: Remove CSP Violations (2 hours)

1. **Audit All Templates for Violations**
   - Find all inline JavaScript
   - Find all inline styles
   - Document current violations

2. **Replace Inline JavaScript**
   - Convert `onchange` handlers to HTMX triggers
   - Remove all `onclick` and similar handlers
   - Use proper HTMX attributes for events

3. **Move Inline Styles to CSS**
   - Extract all `style=""` attributes
   - Create proper CSS classes
   - Update base.css with new styles

### Step 2: HTMX CSRF Implementation (1.5 hours)

1. **Configure Global CSRF for HTMX**
   - Update HTMX configuration in base.html
   - Add automatic CSRF header inclusion
   - Test CSRF token passing

2. **Add CSRF Tokens to All Forms**
   - Audit all form elements
   - Add `{% csrf_token %}` where missing
   - Verify HTMX respects CSRF tokens

3. **Test CSRF Protection**
   - Test successful form submissions
   - Test CSRF failure scenarios
   - Verify error handling

### Step 3: Accessibility Improvements (2 hours)

1. **Add Proper Labels and ARIA**
   - Add labels for all form inputs
   - Add ARIA attributes for dynamic content
   - Add role attributes where needed

2. **Implement Loading States**
   - Add loading indicators for HTMX operations
   - Use ARIA live regions for status updates
   - Add visual feedback for user actions

3. **Error State Handling**
   - Add error message display areas
   - Implement HTMX error handling
   - Add retry mechanisms where appropriate

### Step 4: CSS Refactoring (30 minutes)

1. **Clean Up CSS Classes**
   - Remove unused styles
   - Organize CSS logically
   - Add component-based classes

2. **Add New Styles for Components**
   - Loading indicators
   - Error states
   - Interactive elements

## Files to Modify

### Template Security Updates
- `templates/base.html` - HTMX CSRF configuration, CSP compliance
- `templates/dashboard/partials/calendar_sync_status.html` - Complete refactor
- `templates/dashboard/account_detail.html` - Remove inline styles
- `templates/dashboard/index.html` - Add accessibility attributes

### CSS Updates
- `static/css/base.css` - Add component classes, loading states, error styles

### Testing
- `apps/dashboard/tests.py` - Update tests for template changes
- New: `apps/dashboard/test_templates.py` - Template-specific tests

## Code Examples

### Secure Base HTMX Configuration
```html
<!-- templates/base.html -->
<script src="https://unpkg.com/htmx.org@1.9.10"></script>
<script>
    // Configure HTMX CSRF protection
    document.addEventListener('DOMContentLoaded', function() {
        // Global CSRF token configuration
        document.body.addEventListener('htmx:configRequest', function(evt) {
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
            if (csrfToken) {
                evt.detail.headers['X-CSRFToken'] = csrfToken;
            }
        });
        
        // Global error handling
        document.body.addEventListener('htmx:responseError', function(evt) {
            const errorDiv = document.querySelector('.htmx-error-container');
            if (errorDiv) {
                errorDiv.innerHTML = '<div class="alert alert-danger">An error occurred. Please try again.</div>';
                errorDiv.style.display = 'block';
            }
        });
    });
</script>
```

### Secure Calendar Toggle Template
```html
<!-- templates/dashboard/partials/calendar_sync_status.html -->
<div id="calendar-{{ calendar.id }}-status" 
     class="calendar-sync-toggle" 
     role="region" 
     aria-label="Sync settings for {{ calendar.name }}">
     
    <form class="sync-toggle-form" method="post">
        {% csrf_token %}
        
        <div class="sync-status-container">
            <span id="sync-status-{{ calendar.id }}" 
                  class="sync-status"
                  aria-live="polite">
                {% if calendar.sync_enabled %}
                    <span class="status status-active" aria-label="Sync is enabled">
                        <i class="icon-sync" aria-hidden="true"></i>
                        Enabled
                    </span>
                {% else %}
                    <span class="status status-inactive" aria-label="Sync is disabled">
                        <i class="icon-pause" aria-hidden="true"></i>
                        Disabled
                    </span>
                {% endif %}
            </span>
            
            <button type="button"
                    id="toggle-{{ calendar.id }}"
                    class="btn btn-toggle {% if calendar.sync_enabled %}btn-danger{% else %}btn-success{% endif %}"
                    hx-post="{% url 'dashboard:toggle_calendar_sync' calendar.id %}"
                    hx-target="#calendar-{{ calendar.id }}-status"
                    hx-swap="outerHTML"
                    hx-indicator="#loading-{{ calendar.id }}"
                    aria-describedby="sync-status-{{ calendar.id }}"
                    aria-label="{% if calendar.sync_enabled %}Disable{% else %}Enable{% endif %} sync for {{ calendar.name }}">
                    
                <span class="btn-text">
                    {% if calendar.sync_enabled %}
                        <i class="icon-pause" aria-hidden="true"></i>
                        Disable
                    {% else %}
                        <i class="icon-play" aria-hidden="true"></i>
                        Enable
                    {% endif %}
                </span>
            </button>
        </div>
        
        <!-- Loading indicator -->
        <div id="loading-{{ calendar.id }}" 
             class="loading-indicator htmx-indicator"
             role="status"
             aria-label="Updating sync settings">
            <span class="loading-spinner" aria-hidden="true"></span>
            <span class="loading-text">Updating...</span>
        </div>
        
        <!-- Error container -->
        <div id="error-{{ calendar.id }}" 
             class="error-container"
             role="alert"
             aria-live="assertive"
             style="display: none;">
        </div>
    </form>
</div>
```

### Enhanced CSS Components
```css
/* static/css/base.css - New component styles */

/* Calendar Sync Toggle Components */
.calendar-sync-toggle {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
}

.sync-toggle-form {
    display: contents;
}

.sync-status-container {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.sync-status {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    font-weight: 500;
}

.btn-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.25rem 0.5rem;
    font-size: 0.875rem;
    border: none;
    border-radius: 0.25rem;
    cursor: pointer;
    transition: all 0.2s ease;
}

.btn-toggle:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.btn-toggle:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
}

/* Loading States */
.loading-indicator {
    display: none;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0.5rem;
    font-size: 0.875rem;
    color: #6c757d;
}

.loading-indicator.htmx-request {
    display: flex;
}

.loading-spinner {
    width: 1rem;
    height: 1rem;
    border: 2px solid #e9ecef;
    border-top: 2px solid #007bff;
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

/* Error States */
.error-container {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    z-index: 10;
    margin-top: 0.25rem;
}

.error-container .alert {
    margin: 0;
    padding: 0.5rem;
    font-size: 0.875rem;
}

/* Status Icons */
.icon-sync,
.icon-pause,
.icon-play {
    width: 1rem;
    height: 1rem;
    display: inline-block;
}

.icon-sync::before { content: "🔄"; }
.icon-pause::before { content: "⏸️"; }
.icon-play::before { content: "▶️"; }

/* HTMX Loading States */
.htmx-indicator {
    display: none;
}

.htmx-request .htmx-indicator {
    display: inline-flex;
}

.htmx-request.loading-indicator {
    display: flex;
}

/* Accessibility Improvements */
.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
}

/* Focus indicators */
.btn-toggle:focus {
    outline: 2px solid #007bff;
    outline-offset: 2px;
}

/* High contrast support */
@media (prefers-contrast: high) {
    .status-active {
        background-color: #000;
        color: #fff;
    }
    
    .status-inactive {
        background-color: #666;
        color: #fff;
    }
}

/* Reduced motion support */
@media (prefers-reduced-motion: reduce) {
    .btn-toggle {
        transition: none;
    }
    
    .loading-spinner {
        animation: none;
    }
    
    .loading-spinner::after {
        content: "⟳";
        display: block;
    }
}
```

## Testing Requirements

### Template Tests
```python
# apps/dashboard/test_templates.py
from django.test import TestCase
from django.contrib.auth.models import User
from apps.calendars.models import Calendar, CalendarAccount

class TemplateSecurityTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@example.com', 'pass')
        self.account = CalendarAccount.objects.create(
            user=self.user,
            email='test@gmail.com',
            google_account_id='test123',
            is_active=True,
            token_expires_at=timezone.now() + timedelta(hours=1)
        )
        self.calendar = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id='cal123',
            name='Test Calendar'
        )

    def test_no_inline_javascript(self):
        """Verify no inline JavaScript in templates"""
        self.client.login(username='testuser', password='pass')
        response = self.client.get(f'/account/{self.account.id}/')
        
        content = response.content.decode()
        self.assertNotIn('onclick=', content)
        self.assertNotIn('onchange=', content)
        self.assertNotIn('javascript:', content)

    def test_no_inline_styles(self):
        """Verify no inline styles in templates"""
        self.client.login(username='testuser', password='pass')
        response = self.client.get(f'/account/{self.account.id}/')
        
        content = response.content.decode()
        # Allow data attributes and specific exceptions
        style_matches = re.findall(r'style="[^"]*"', content)
        allowed_styles = ['style="display: none"']  # Only allowed inline styles
        
        for style in style_matches:
            self.assertIn(style, allowed_styles, f"Unauthorized inline style: {style}")

    def test_csrf_tokens_present(self):
        """Verify CSRF tokens in all forms"""
        self.client.login(username='testuser', password='pass')
        response = self.client.get(f'/account/{self.account.id}/')
        
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_accessibility_attributes(self):
        """Verify accessibility attributes present"""
        self.client.login(username='testuser', password='pass')
        response = self.client.get(f'/account/{self.account.id}/')
        
        content = response.content.decode()
        self.assertIn('aria-label=', content)
        self.assertIn('role=', content)
        self.assertIn('aria-live=', content)

    def test_loading_indicators(self):
        """Verify loading indicators present"""
        self.client.login(username='testuser', password='pass')
        response = self.client.get(f'/account/{self.account.id}/')
        
        self.assertContains(response, 'loading-indicator')
        self.assertContains(response, 'htmx-indicator')
```

## Definition of Done

- [ ] Zero inline JavaScript violations
- [ ] Zero inline styles (except display:none for progressive enhancement)
- [ ] All forms have CSRF tokens
- [ ] All interactive elements have proper ARIA attributes
- [ ] Loading states implemented and tested
- [ ] Error states implemented and tested
- [ ] CSP policy can be enabled without template violations
- [ ] WCAG 2.1 AA compliance verified
- [ ] All HTMX functionality working
- [ ] Template tests passing
- [ ] Cross-browser compatibility verified
- [ ] Screen reader testing completed

## Success Metrics

- CSP policy can be enabled in production
- Accessibility audit shows 100% compliance
- No JavaScript errors in browser console
- HTMX operations provide clear user feedback
- Form submissions work correctly with CSRF protection
- Template rendering performance maintained or improved

This task ensures our templates follow modern security and accessibility standards while maintaining the HTMX functionality users expect.
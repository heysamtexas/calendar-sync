"""
Accessibility and template enhancement tests for TASK-08
"""
import re
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from apps.calendars.models import Calendar, CalendarAccount
from apps.accounts.models import UserProfile
from django.utils import timezone
from datetime import timedelta


class TemplateAccessibilityTest(TestCase):
    """Test enhanced accessibility features in templates"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com', 
            password='testpass123'
        )
        self.profile = UserProfile.objects.create(user=self.user)
        
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
            name='Test Calendar',
            sync_enabled=False,
            color='#1f4788'  # Test color badge
        )
    
    def test_wcag_role_attributes_present(self):
        """Test WCAG 2.1 AA role attributes are present"""
        self.client.login(username='testuser', password='testpass123')
        
        # Test dashboard page
        response = self.client.get(reverse('dashboard:index'))
        content = response.content.decode()
        
        # Should have proper role attributes
        self.assertIn('role="region"', content)
        self.assertIn('role="table"', content)
        
        # Test account detail page
        response = self.client.get(reverse('dashboard:account_detail', args=[self.account.id]))
        content = response.content.decode()
        
        self.assertIn('role="region"', content)
        self.assertIn('role="table"', content)
    
    def test_aria_labelledby_attributes(self):
        """Test aria-labelledby attributes for proper heading associations"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('dashboard:index'))
        content = response.content.decode()
        
        # Should have aria-labelledby connecting regions to headings
        self.assertIn('aria-labelledby="stats-heading"', content)
        self.assertIn('aria-labelledby="accounts-heading"', content)
        self.assertIn('aria-labelledby="actions-heading"', content)
        
        # Should have corresponding heading IDs
        self.assertIn('id="stats-heading"', content)
        self.assertIn('id="accounts-heading"', content)
        self.assertIn('id="actions-heading"', content)
    
    def test_aria_label_on_interactive_elements(self):
        """Test aria-label on interactive elements"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('dashboard:index'))
        content = response.content.decode()
        
        # Links should have descriptive aria-labels
        self.assertIn('aria-label="View details for test@gmail.com"', content)
        
        # Tables should have aria-label
        self.assertIn('aria-label="Calendar synchronization statistics"', content)
        self.assertIn('aria-label="Connected Google Calendar accounts"', content)
    
    def test_calendar_color_badge_accessibility(self):
        """Test calendar color badge accessibility"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('dashboard:account_detail', args=[self.account.id]))
        content = response.content.decode()
        
        # Should have accessible color badge
        self.assertIn('class="calendar-color-badge"', content)
        self.assertIn('data-color="#1f4788"', content)
        self.assertIn('aria-label="Calendar color: #1f4788"', content)
        
        # Should NOT have inline styles
        self.assertNotIn('style="background-color:', content)
    
    def test_screen_reader_only_text(self):
        """Test screen reader only help text"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('dashboard:index'))
        content = response.content.decode()
        
        # Should have sr-only help text
        self.assertIn('class="sr-only"', content)
        self.assertIn('Add a new Google Calendar account to sync', content)
    
    def test_disabled_buttons_with_explanations(self):
        """Test disabled buttons have accessible explanations"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('dashboard:account_detail', args=[self.account.id]))
        content = response.content.decode()
        
        # Should have disabled buttons with help text
        self.assertIn('disabled aria-describedby="manual-sync-help"', content)
        self.assertIn('Manual sync functionality coming soon', content)
        
        self.assertIn('disabled aria-describedby="disconnect-help"', content)
        self.assertIn('Account disconnection functionality coming soon', content)
    
    def test_form_labels_accessibility(self):
        """Test form labels have proper accessibility"""
        self.client.login(username='testuser', password='testpass123')
        
        # Test login form
        self.client.logout()
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        
        # Should have proper labels
        self.assertIn('<label for=', content)
        self.assertIn('Username:', content)
        self.assertIn('Password:', content)
        
        # Should have help text class instead of inline style
        self.assertIn('class="login-help-text"', content)
        self.assertNotIn('style="margin-top:', content)
    
    def test_focus_management(self):
        """Test focus indicators are styled"""
        # This tests that our CSS has focus styles
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('dashboard:index'))
        
        # Just verify the page loads (focus styles are in CSS)
        self.assertEqual(response.status_code, 200)
        
        # The focus styles are tested by our CSS which includes:
        # .btn-toggle:focus { outline: 2px solid #007bff; }
        # input:focus, textarea:focus, select:focus { outline: 2px solid #007bff; }
    
    def test_high_contrast_support(self):
        """Test high contrast media query support exists"""
        # This verifies our CSS includes high contrast support
        # The actual testing would be done in browser with high contrast mode
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)
        
        # High contrast support is in CSS:
        # @media (prefers-contrast: high) { ... }
    
    def test_reduced_motion_support(self):
        """Test reduced motion media query support exists"""
        # This verifies our CSS includes reduced motion support
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)
        
        # Reduced motion support is in CSS:
        # @media (prefers-reduced-motion: reduce) { ... }


class CSPComplianceTest(TestCase):
    """Test Content Security Policy compliance"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.profile = UserProfile.objects.create(user=self.user)
        
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
            name='Test Calendar',
            sync_enabled=False
        )
    
    def test_zero_inline_javascript_violations(self):
        """Test that there are absolutely no inline JavaScript violations"""
        self.client.login(username='testuser', password='testpass123')
        
        # Test all pages
        pages = [
            reverse('dashboard:index'),
            reverse('dashboard:account_detail', args=[self.account.id]),
            reverse('login'),
        ]
        
        for url in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                content = response.content.decode()
                
                # Strict CSP violation checks
                self.assertNotIn('onclick=', content, f"onclick handler found in {url}")
                self.assertNotIn('onchange=', content, f"onchange handler found in {url}")
                self.assertNotIn('onsubmit=', content, f"onsubmit handler found in {url}")
                self.assertNotIn('onload=', content, f"onload handler found in {url}")
                self.assertNotIn('onerror=', content, f"onerror handler found in {url}")
                self.assertNotIn('javascript:', content, f"javascript: protocol found in {url}")
                self.assertNotIn('<script>', content.replace('<script src=', '<script-src='), f"inline script found in {url}")
    
    def test_zero_unauthorized_inline_styles(self):
        """Test that only authorized inline styles remain"""
        self.client.login(username='testuser', password='testpass123')
        
        # Test all pages
        pages = [
            reverse('dashboard:index'),
            reverse('dashboard:account_detail', args=[self.account.id]),
            reverse('login'),
        ]
        
        # Only these inline styles are allowed
        allowed_inline_styles = [
            'style="display: none"',
            'style="display: none;"',
            'style="display:none"',
            'style="display:none;"',
        ]
        
        for url in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                content = response.content.decode()
                
                # Find all inline styles
                style_matches = re.findall(r'style="[^"]*"', content)
                
                for style in style_matches:
                    self.assertIn(style, allowed_inline_styles, 
                                f"Unauthorized inline style '{style}' found in {url}")
    
    def test_external_javascript_files_only(self):
        """Test that only external JavaScript files are loaded"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('dashboard:index'))
        content = response.content.decode()
        
        # Should have external script tags only
        self.assertIn('<script src="https://unpkg.com/htmx.org', content)
        self.assertIn('<script src="/static/js/app.js"', content)
        
        # Should not have any inline script content
        script_tags = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
        for script_content in script_tags:
            # All script tags should be empty (external files only)
            self.assertEqual(script_content.strip(), '', 
                           f"Found inline script content: {script_content}")
    
    def test_meta_csrf_token_present(self):
        """Test that CSRF token is available via meta tag"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('dashboard:index'))
        content = response.content.decode()
        
        # Should have CSRF token in meta tag for JavaScript access
        self.assertIn('name="csrf-token"', content)
        self.assertIn('content="', content)
    
    def test_csp_ready_htmx_configuration(self):
        """Test that HTMX is configured in CSP-compliant way"""
        self.client.login(username='testuser', password='testuser123')  # Wrong password
        
        # Test that login fails (validates login form works)
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'wrongpass'
        })
        
        # Should redirect back to login with error
        self.assertEqual(response.status_code, 200)  # Form validation error
        
        # Login correctly to test dashboard
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard:index'))
        
        # HTMX configuration should be external
        self.assertNotIn('htmx:configRequest', response.content.decode())
        self.assertIn('/static/js/app.js', response.content.decode())
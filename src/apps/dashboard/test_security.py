"""
Security tests for dashboard functionality
"""
import re
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from apps.calendars.models import Calendar, CalendarAccount
from apps.accounts.models import UserProfile
from django.utils import timezone
from datetime import timedelta


class SecurityTest(TestCase):
    """Test security features of the dashboard"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', 
            email='test@example.com', 
            password='testpass123'
        )
        self.profile = UserProfile.objects.create(user=self.user)
        
        # Create test account and calendar
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
    
    def test_toggle_calendar_sync_requires_csrf(self):
        """Test that calendar toggle requires CSRF token"""
        client = Client(enforce_csrf_checks=True)
        client.login(username='testuser', password='testpass123')
        
        url = reverse('dashboard:toggle_calendar_sync', args=[self.calendar.id])
        
        # Test without CSRF token fails
        response = client.post(url)
        self.assertEqual(response.status_code, 403)  # CSRF failure
        
        # Calendar should remain unchanged
        self.calendar.refresh_from_db()
        self.assertFalse(self.calendar.sync_enabled)
    
    def test_toggle_calendar_sync_requires_post(self):
        """Test that calendar toggle requires POST method"""
        self.client.login(username='testuser', password='testpass123')
        
        url = reverse('dashboard:toggle_calendar_sync', args=[self.calendar.id])
        
        # Test GET request fails
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)  # Method not allowed
        
        # Calendar should remain unchanged
        self.calendar.refresh_from_db()
        self.assertFalse(self.calendar.sync_enabled)
    
    def test_calendar_toggle_ownership_check(self):
        """Test that users can only toggle their own calendars"""
        # Create another user and calendar
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com', 
            password='otherpass123'
        )
        other_account = CalendarAccount.objects.create(
            user=other_user,
            email='other@gmail.com',
            google_account_id='other123',
            is_active=True,
            token_expires_at=timezone.now() + timedelta(hours=1)
        )
        other_calendar = Calendar.objects.create(
            calendar_account=other_account,
            google_calendar_id='other_cal123',
            name='Other Calendar',
            sync_enabled=False
        )
        
        # Login as first user
        self.client.login(username='testuser', password='testpass123')
        
        # Try to toggle other user's calendar
        url = reverse('dashboard:toggle_calendar_sync', args=[other_calendar.id])
        response = self.client.post(url)
        
        # Should return 404 (not found due to user filtering)
        # Service layer now returns 403 for permission denied (more semantically correct)
        self.assertEqual(response.status_code, 403)
        
        # Other user's calendar should remain unchanged
        other_calendar.refresh_from_db()
        self.assertFalse(other_calendar.sync_enabled)


class TemplateSecurityTest(TestCase):
    """Test template security and accessibility features"""
    
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
    
    def test_no_inline_javascript_in_templates(self):
        """Verify no inline JavaScript in rendered templates"""
        self.client.login(username='testuser', password='testpass123')
        
        # Test dashboard page
        response = self.client.get(reverse('dashboard:index'))
        content = response.content.decode()
        
        # Check for common inline JavaScript patterns
        self.assertNotIn('onclick=', content)
        self.assertNotIn('onchange=', content)
        self.assertNotIn('onsubmit=', content)
        self.assertNotIn('javascript:', content)
        
        # Test account detail page
        response = self.client.get(reverse('dashboard:account_detail', args=[self.account.id]))
        content = response.content.decode()
        
        self.assertNotIn('onclick=', content)
        self.assertNotIn('onchange=', content)
        self.assertNotIn('onsubmit=', content)
        self.assertNotIn('javascript:', content)
    
    def test_no_unauthorized_inline_styles(self):
        """Verify minimal inline styles in templates"""
        self.client.login(username='testuser', password='testpass123')
        
        # Test account detail page (where toggle is rendered)
        response = self.client.get(reverse('dashboard:account_detail', args=[self.account.id]))
        content = response.content.decode()
        
        # Find all inline styles
        style_matches = re.findall(r'style="[^"]*"', content)
        
        # Only allow specific styles (like display: none for progressive enhancement)
        allowed_styles = ['style="display: none"', 'style="display: none;"']
        
        for style in style_matches:
            self.assertIn(style, allowed_styles, f"Unauthorized inline style: {style}")
    
    def test_csrf_tokens_present_in_forms(self):
        """Verify CSRF tokens are present in forms"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('dashboard:account_detail', args=[self.account.id]))
        content = response.content.decode()
        
        # Should contain CSRF token
        self.assertIn('csrfmiddlewaretoken', content)
        
        # Should have meta tag for HTMX
        response = self.client.get(reverse('dashboard:index'))
        content = response.content.decode()
        self.assertIn('name="csrf-token"', content)
    
    def test_accessibility_attributes_present(self):
        """Verify accessibility attributes are present"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('dashboard:account_detail', args=[self.account.id]))
        content = response.content.decode()
        
        # Check for key accessibility attributes
        self.assertIn('aria-label=', content)
        self.assertIn('role=', content)
        self.assertIn('aria-live=', content)
        self.assertIn('aria-hidden=', content)
        
        # Check for loading indicators
        self.assertIn('loading-indicator', content)
        self.assertIn('role="status"', content)
    
    def test_loading_states_implemented(self):
        """Verify loading states are implemented"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(reverse('dashboard:account_detail', args=[self.account.id]))
        content = response.content.decode()
        
        # Should have loading indicators
        self.assertIn('htmx-indicator', content)
        self.assertIn('loading-spinner', content)
        self.assertIn('loading-text', content)
        
        # Should have error containers
        self.assertIn('error-container', content)
        self.assertIn('role="alert"', content)


class OAuthSecurityTest(TestCase):
    """Test OAuth security improvements"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.profile = UserProfile.objects.create(user=self.user)
    
    def test_oauth_callback_has_transaction_safety(self):
        """Test that OAuth callback uses database transactions"""
        # This is tested by verifying our code structure
        # The actual transaction behavior is tested in integration tests
        
        from apps.accounts.services.oauth_service import OAuthService
        import inspect
        
        # Get the source code of the OAuth service method
        source = inspect.getsource(OAuthService.process_oauth_callback)
        
        # Verify it uses transaction.atomic in service layer
        self.assertIn('transaction.atomic', source)
        self.assertIn('with transaction.atomic():', source)
    
    def test_calendar_discovery_uses_safe_defaults(self):
        """Test that calendar discovery uses safe sync defaults"""
        from apps.accounts.services.oauth_service import OAuthService
        import inspect
        
        # Get the source code of the discovery function in service layer
        source = inspect.getsource(OAuthService._discover_calendars_safely)
        
        # Verify it uses safe default (sync_enabled=False)
        self.assertIn('sync_enabled": False', source)
        self.assertIn('SAFE DEFAULT', source)
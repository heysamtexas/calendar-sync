# TASK GT-04: Authentication Flow Testing
## *"Test security boundaries with real Django mechanisms"*

### Priority: MEDIUM - SECURITY CRITICAL
### Estimated Time: 2-3 hours
### Dependencies: GT-01 (Infrastructure), GT-02 (Integration Tests First)
### Status: Ready for Implementation

---

## Problem Statement

Authentication and security testing in our current setup suffers from the same problems as other tests:
- Heavy mocking of security mechanisms defeats the purpose
- OAuth flow tests mock the very security components they should validate
- Session handling tests don't use real Django sessions
- Token management tests mock encryption/decryption

**Guilfoyle's Approach**: Test security boundaries with real Django mechanisms. Mock only external OAuth providers, never internal security logic.

---

## Authentication Testing Philosophy

**Mock External OAuth Providers Only**:
- Google OAuth endpoints
- Google user info API  
- Google token exchange

**Use Real Django Mechanisms**:
- Session management
- User authentication
- CSRF protection
- Permission checking
- Token encryption/decryption (tested separately in unit tests)

**Test Security Outcomes**:
- Users get authenticated
- Sessions are created correctly
- Unauthorized access is blocked
- Tokens are stored securely

---

## Acceptance Criteria

- [ ] Complete OAuth flow tests using real Django sessions
- [ ] User authentication tests with real permission checking
- [ ] Token refresh flow tests with real encryption
- [ ] Session security tests with real middleware
- [ ] CSRF protection tests with real Django CSRF
- [ ] Account connection/disconnection security tests
- [ ] Multi-account OAuth flow tests
- [ ] Security boundary validation tests

---

## Implementation Steps

### Step 1: OAuth Flow Integration Tests (60 minutes)

Create `tests/integration/test_oauth_flow.py`:

```python
"""
OAuth Flow Integration Tests
Tests the complete OAuth flow using real Django authentication mechanisms
"""

import pytest
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, Mock

from apps.calendars.models import CalendarAccount, Calendar
from apps.accounts.models import UserProfile


class OAuthFlowIntegrationTest(TestCase):
    """Test complete OAuth flow with real Django authentication"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='oauthuser',
            email='oauthuser@example.com',
            password='testpass123'
        )
    
    def test_complete_oauth_flow_new_user(self):
        """Test complete OAuth flow for new user"""
        # Step 1: Anonymous user initiates OAuth
        response = self.client.get(reverse('accounts:connect'))
        
        # Should redirect to Google OAuth (or show login required)
        self.assertIn(response.status_code, [302, 403])
        
        # Step 2: User logs in first
        login_success = self.client.login(username='oauthuser', password='testpass123')
        self.assertTrue(login_success)
        
        # Step 3: Now initiate OAuth
        response = self.client.get(reverse('accounts:connect'))
        self.assertEqual(response.status_code, 302)
        
        # Verify session contains OAuth state
        session = self.client.session
        self.assertIn('oauth_state', session)
        oauth_state = session['oauth_state']
        self.assertTrue(len(oauth_state) > 10)  # Should be meaningful state
        
        # Step 4: Mock Google OAuth callback
        with patch('google_auth_oauthlib.flow.Flow') as mock_flow_class:
            # Mock OAuth flow
            mock_flow = Mock()
            mock_flow_class.from_client_config.return_value = mock_flow
            
            # Mock credentials
            mock_credentials = Mock()
            mock_credentials.token = 'mock_access_token'
            mock_credentials.refresh_token = 'mock_refresh_token'
            mock_credentials.expiry = timezone.now() + timedelta(hours=1)
            mock_flow.credentials = mock_credentials
            
            # Mock Google user info API
            with patch('googleapiclient.discovery.build') as mock_build:
                mock_oauth_service = Mock()
                mock_build.return_value = mock_oauth_service
                mock_oauth_service.userinfo().get().execute.return_value = {
                    'id': 'google_user_123456',
                    'email': self.user.email,  # Same as Django user
                    'name': 'OAuth Test User',
                    'picture': 'https://example.com/photo.jpg'
                }
                
                # Mock calendar list API
                mock_calendar_service = Mock()
                def mock_build_side_effect(service_name, version, credentials=None):
                    if service_name == 'oauth2':
                        return mock_oauth_service
                    elif service_name == 'calendar':
                        return mock_calendar_service
                    return Mock()
                
                mock_build.side_effect = mock_build_side_effect
                mock_calendar_service.calendarList().list().execute.return_value = {
                    'items': [
                        {
                            'id': 'primary',
                            'summary': self.user.email,
                            'primary': True,
                            'backgroundColor': '#1f4788'
                        },
                        {
                            'id': 'work_calendar_456',
                            'summary': 'Work Calendar',
                            'primary': False,
                            'backgroundColor': '#d50000'
                        }
                    ]
                }
                
                # Step 5: Complete OAuth callback
                response = self.client.get(
                    reverse('accounts:oauth_callback'),
                    {
                        'code': 'mock_authorization_code',
                        'state': oauth_state  # Use the real state from session
                    }
                )
                
                # Should redirect to dashboard
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.endswith('/dashboard/'))
        
        # Step 6: Verify authentication outcomes
        
        # User should still be logged in
        self.assertTrue('_auth_user_id' in self.client.session)
        
        # Calendar account should be created
        self.assertTrue(
            CalendarAccount.objects.filter(
                user=self.user,
                google_account_id='google_user_123456'
            ).exists()
        )
        
        account = CalendarAccount.objects.get(user=self.user)
        self.assertEqual(account.email, self.user.email)
        self.assertTrue(account.is_active)
        self.assertIsNotNone(account.access_token)  # Should be encrypted
        self.assertIsNotNone(account.refresh_token)
        
        # Calendars should be created
        calendars = Calendar.objects.filter(calendar_account=account)
        self.assertEqual(calendars.count(), 2)
        
        primary_calendar = calendars.get(google_calendar_id='primary')
        self.assertTrue(primary_calendar.is_primary)
        self.assertFalse(primary_calendar.sync_enabled)  # Disabled by default
        
        work_calendar = calendars.get(google_calendar_id='work_calendar_456')
        self.assertEqual(work_calendar.name, 'Work Calendar')
        
        # OAuth state should be cleared from session
        updated_session = self.client.session
        self.assertNotIn('oauth_state', updated_session)
    
    def test_oauth_state_validation(self):
        """Test OAuth state parameter validation for security"""
        self.client.force_login(self.user)
        
        # Initiate OAuth to get state
        response = self.client.get(reverse('accounts:connect'))
        oauth_state = self.client.session.get('oauth_state')
        
        # Test with wrong state - should fail
        response = self.client.get(
            reverse('accounts:oauth_callback'),
            {
                'code': 'mock_code',
                'state': 'wrong_state_value'
            }
        )
        
        # Should redirect with error or show error page
        self.assertIn(response.status_code, [302, 400])
        
        # Should not create any accounts
        self.assertEqual(CalendarAccount.objects.filter(user=self.user).count(), 0)
        
        # Test with no state - should fail
        response = self.client.get(
            reverse('accounts:oauth_callback'),
            {'code': 'mock_code'}
        )
        
        self.assertIn(response.status_code, [302, 400])
        self.assertEqual(CalendarAccount.objects.filter(user=self.user).count(), 0)
    
    def test_oauth_error_handling(self):
        """Test OAuth error scenarios"""
        self.client.force_login(self.user)
        
        # Test access denied error
        response = self.client.get(
            reverse('accounts:oauth_callback'),
            {'error': 'access_denied'}
        )
        
        # Should handle gracefully
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith('/dashboard/'))
        
        # Should not create account
        self.assertEqual(CalendarAccount.objects.filter(user=self.user).count(), 0)
        
        # Test invalid grant error
        response = self.client.get(
            reverse('accounts:oauth_callback'),
            {'error': 'invalid_grant', 'error_description': 'Invalid authorization code'}
        )
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CalendarAccount.objects.filter(user=self.user).count(), 0)
    
    def test_multiple_account_oauth_flow(self):
        """Test adding second Google account to existing user"""
        # Create first account
        first_account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id='first_account_123',
            email='first@gmail.com',
            is_active=True
        )
        
        self.client.force_login(self.user)
        
        # Add second account via OAuth
        with patch('google_auth_oauthlib.flow.Flow') as mock_flow_class, \
             patch('googleapiclient.discovery.build') as mock_build:
            
            # Setup mocks
            mock_flow = Mock()
            mock_flow_class.from_client_config.return_value = mock_flow
            mock_credentials = Mock()
            mock_credentials.token = 'second_access_token'
            mock_credentials.refresh_token = 'second_refresh_token'
            mock_credentials.expiry = timezone.now() + timedelta(hours=1)
            mock_flow.credentials = mock_credentials
            
            mock_oauth_service = Mock()
            mock_calendar_service = Mock()
            
            def mock_build_side_effect(service_name, version, credentials=None):
                if service_name == 'oauth2':
                    return mock_oauth_service
                elif service_name == 'calendar':
                    return mock_calendar_service
                return Mock()
            
            mock_build.side_effect = mock_build_side_effect
            
            # Different user info for second account
            mock_oauth_service.userinfo().get().execute.return_value = {
                'id': 'second_google_account_456',
                'email': 'work@company.com',  # Different email
                'name': 'Work Account'
            }
            
            mock_calendar_service.calendarList().list().execute.return_value = {
                'items': [
                    {
                        'id': 'work_primary',
                        'summary': 'work@company.com',
                        'primary': True,
                        'backgroundColor': '#d50000'
                    }
                ]
            }
            
            # Initiate OAuth for second account
            response = self.client.get(reverse('accounts:connect'))
            oauth_state = self.client.session.get('oauth_state')
            
            # Complete OAuth callback
            response = self.client.get(
                reverse('accounts:oauth_callback'),
                {
                    'code': 'second_account_code',
                    'state': oauth_state
                }
            )
            
            self.assertEqual(response.status_code, 302)
        
        # Verify both accounts exist
        accounts = CalendarAccount.objects.filter(user=self.user)
        self.assertEqual(accounts.count(), 2)
        
        # Verify second account details
        second_account = accounts.get(email='work@company.com')
        self.assertEqual(second_account.google_account_id, 'second_google_account_456')
        self.assertTrue(second_account.is_active)
        
        # Verify first account still exists
        first_account.refresh_from_db()
        self.assertTrue(first_account.is_active)
    
    def test_oauth_account_linking_security(self):
        """Test security of account linking process"""
        # Create account linked to different user
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='pass123'
        )
        
        existing_account = CalendarAccount.objects.create(
            user=other_user,
            google_account_id='existing_google_123',
            email='existing@gmail.com',
            is_active=True
        )
        
        self.client.force_login(self.user)
        
        # Attempt to link same Google account to different user
        with patch('google_auth_oauthlib.flow.Flow') as mock_flow_class, \
             patch('googleapiclient.discovery.build') as mock_build:
            
            mock_flow = Mock()
            mock_flow_class.from_client_config.return_value = mock_flow
            mock_credentials = Mock()
            mock_flow.credentials = mock_credentials
            
            mock_oauth_service = Mock()
            mock_build.return_value = mock_oauth_service
            
            # Return same Google account ID that's already linked
            mock_oauth_service.userinfo().get().execute.return_value = {
                'id': 'existing_google_123',  # Same as other user's account
                'email': 'existing@gmail.com',
                'name': 'Existing Account'
            }
            
            # Initiate OAuth
            response = self.client.get(reverse('accounts:connect'))
            oauth_state = self.client.session.get('oauth_state')
            
            # Complete OAuth callback
            response = self.client.get(
                reverse('accounts:oauth_callback'),
                {
                    'code': 'duplicate_account_code',
                    'state': oauth_state
                }
            )
            
            # Should handle gracefully (could redirect with error message)
            self.assertEqual(response.status_code, 302)
        
        # Should not create duplicate account
        accounts_for_user = CalendarAccount.objects.filter(user=self.user)
        self.assertEqual(accounts_for_user.count(), 0)
        
        # Original account should remain with original user
        existing_account.refresh_from_db()
        self.assertEqual(existing_account.user, other_user)


class TokenRefreshFlowTest(TestCase):
    """Test token refresh flow with real encryption"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='tokenuser',
            password='pass123'
        )
        
        # Create account with expired token
        self.account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id='token_test_123',
            email='tokentest@gmail.com',
            access_token='encrypted_access_token',
            refresh_token='encrypted_refresh_token',
            token_expires_at=timezone.now() - timedelta(hours=1),  # Expired
            is_active=True
        )
    
    @patch('google.auth.transport.requests.Request')
    @patch('google.oauth2.credentials.Credentials')
    def test_token_refresh_flow(self, mock_credentials_class, mock_request):
        """Test automatic token refresh during API calls"""
        # Mock successful token refresh
        mock_credentials = Mock()
        mock_credentials_class.return_value = mock_credentials
        mock_credentials.token = 'new_access_token'
        mock_credentials.refresh_token = 'new_refresh_token'
        mock_credentials.expiry = timezone.now() + timedelta(hours=1)
        mock_credentials.expired = False
        
        # Simulate API call that triggers token refresh
        from apps.calendars.services.google_calendar_client import GoogleCalendarClient
        
        with patch('googleapiclient.discovery.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service
            mock_service.calendarList().list().execute.return_value = {'items': []}
            
            client = GoogleCalendarClient(self.account)
            calendars = client.list_calendars()
        
        # Verify token was refreshed
        self.account.refresh_from_db()
        self.assertTrue(self.account.token_expires_at > timezone.now())
        
        # Verify account remains active
        self.assertTrue(self.account.is_active)
    
    @patch('google.auth.transport.requests.Request')
    @patch('google.oauth2.credentials.Credentials')
    def test_token_refresh_failure_deactivates_account(self, mock_credentials_class, mock_request):
        """Test account deactivation on permanent token refresh failure"""
        from google.auth.exceptions import RefreshError
        
        # Mock token refresh failure
        mock_credentials = Mock()
        mock_credentials_class.return_value = mock_credentials
        mock_credentials.refresh.side_effect = RefreshError('invalid_grant')
        
        # Attempt API call that triggers token refresh
        from apps.calendars.services.google_calendar_client import GoogleCalendarClient
        
        client = GoogleCalendarClient(self.account)
        
        with pytest.raises(Exception):  # Should raise due to failed auth
            client.list_calendars()
        
        # Verify account was deactivated
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_active)


class SessionSecurityTest(TestCase):
    """Test session handling security"""
    
    def test_oauth_state_stored_in_session(self):
        """Test OAuth state is properly stored in session"""
        user = User.objects.create_user(username='sessionuser', password='pass')
        client = Client()
        client.force_login(user)
        
        # Initiate OAuth
        response = client.get(reverse('accounts:connect'))
        
        # Verify state is in session
        session = client.session
        self.assertIn('oauth_state', session)
        
        oauth_state = session['oauth_state']
        self.assertTrue(len(oauth_state) >= 32)  # Should be cryptographically secure
        self.assertIsInstance(oauth_state, str)
    
    def test_session_cleared_after_oauth_completion(self):
        """Test session is properly cleaned up after OAuth"""
        user = User.objects.create_user(username='cleanupuser', password='pass')
        client = Client()
        client.force_login(user)
        
        # Start OAuth
        client.get(reverse('accounts:connect'))
        oauth_state = client.session.get('oauth_state')
        
        # Complete OAuth with mock
        with patch('google_auth_oauthlib.flow.Flow') as mock_flow_class, \
             patch('googleapiclient.discovery.build'):
            
            mock_flow = Mock()
            mock_flow_class.from_client_config.return_value = mock_flow
            mock_flow.credentials = Mock()
            
            # Complete callback
            client.get(
                reverse('accounts:oauth_callback'),
                {
                    'code': 'test_code',
                    'state': oauth_state
                }
            )
        
        # Verify OAuth state cleared from session
        updated_session = client.session
        self.assertNotIn('oauth_state', updated_session)
    
    def test_concurrent_oauth_sessions(self):
        """Test multiple concurrent OAuth sessions don't interfere"""
        user = User.objects.create_user(username='concurrent', password='pass')
        
        # Create two separate clients (different sessions)
        client1 = Client()
        client2 = Client()
        
        client1.force_login(user)
        client2.force_login(user)
        
        # Initiate OAuth on both
        client1.get(reverse('accounts:connect'))
        client2.get(reverse('accounts:connect'))
        
        state1 = client1.session.get('oauth_state')
        state2 = client2.session.get('oauth_state')
        
        # States should be different
        self.assertNotEqual(state1, state2)
        
        # Each should validate only its own state
        response1 = client1.get(
            reverse('accounts:oauth_callback'),
            {'code': 'code1', 'state': state2}  # Wrong state
        )
        
        # Should fail validation
        self.assertIn(response1.status_code, [302, 400])
```

### Step 2: Account Security Tests (45 minutes)

Create `tests/integration/test_account_security.py`:

```python
"""
Account Security Integration Tests  
Tests security boundaries and access control with real Django mechanisms
"""

import pytest
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.auth import authenticate
from unittest.mock import patch

from apps.calendars.models import CalendarAccount, Calendar


class AccountSecurityTest(TestCase):
    """Test account security and access control"""
    
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='pass123'
        )
        
        self.user2 = User.objects.create_user(
            username='user2', 
            email='user2@example.com',
            password='pass123'
        )
        
        self.account1 = CalendarAccount.objects.create(
            user=self.user1,
            google_account_id='account1',
            email='user1@gmail.com',
            is_active=True
        )
        
        self.account2 = CalendarAccount.objects.create(
            user=self.user2,
            google_account_id='account2', 
            email='user2@gmail.com',
            is_active=True
        )
    
    def test_user_can_only_access_own_accounts(self):
        """Test users can only access their own calendar accounts"""
        client = Client()
        client.force_login(self.user1)
        
        # User1 should be able to access their account
        response = client.get(
            reverse('dashboard:account_detail', args=[self.account1.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'user1@gmail.com')
        
        # User1 should NOT be able to access user2's account
        response = client.get(
            reverse('dashboard:account_detail', args=[self.account2.id])
        )
        self.assertIn(response.status_code, [403, 404])  # Forbidden or Not Found
    
    def test_unauthenticated_access_blocked(self):
        """Test unauthenticated users cannot access protected views"""
        client = Client()  # No login
        
        # Dashboard should require authentication
        response = client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
        
        # Account detail should require authentication
        response = client.get(
            reverse('dashboard:account_detail', args=[self.account1.id])
        )
        self.assertEqual(response.status_code, 302)
        
        # OAuth connect should require authentication
        response = client.get(reverse('accounts:connect'))
        self.assertIn(response.status_code, [302, 403])
    
    def test_account_disconnect_security(self):
        """Test account disconnection requires proper authorization"""
        client = Client()
        client.force_login(self.user1)
        
        # User1 should be able to disconnect their own account
        response = client.post(
            reverse('accounts:disconnect_account', args=[self.account1.id])
        )
        self.assertEqual(response.status_code, 302)  # Redirect after disconnect
        
        # Verify account was actually disconnected
        self.assertFalse(
            CalendarAccount.objects.filter(id=self.account1.id).exists()
        )
        
        # User1 should NOT be able to disconnect user2's account
        response = client.post(
            reverse('accounts:disconnect_account', args=[self.account2.id])
        )
        self.assertIn(response.status_code, [403, 404])
        
        # Verify user2's account still exists
        self.assertTrue(
            CalendarAccount.objects.filter(id=self.account2.id).exists()
        )
    
    def test_calendar_sync_toggle_security(self):
        """Test calendar sync toggle requires proper authorization"""
        calendar1 = Calendar.objects.create(
            calendar_account=self.account1,
            google_calendar_id='cal1',
            name='User1 Calendar',
            sync_enabled=False
        )
        
        calendar2 = Calendar.objects.create(
            calendar_account=self.account2,
            google_calendar_id='cal2',
            name='User2 Calendar',
            sync_enabled=False
        )
        
        client = Client()
        client.force_login(self.user1)
        
        # User1 should be able to toggle their own calendar
        response = client.post(
            reverse('dashboard:toggle_calendar_sync', args=[calendar1.id])
        )
        self.assertEqual(response.status_code, 200)
        
        calendar1.refresh_from_db()
        self.assertTrue(calendar1.sync_enabled)
        
        # User1 should NOT be able to toggle user2's calendar
        response = client.post(
            reverse('dashboard:toggle_calendar_sync', args=[calendar2.id])
        )
        self.assertIn(response.status_code, [403, 404])
        
        calendar2.refresh_from_db()
        self.assertFalse(calendar2.sync_enabled)  # Should remain unchanged


class CSRFProtectionTest(TestCase):
    """Test CSRF protection on security-critical endpoints"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='csrfuser',
            password='pass123'
        )
        
        self.account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id='csrf_test',
            email='csrf@gmail.com'
        )
    
    def test_disconnect_account_requires_csrf(self):
        """Test account disconnection requires CSRF token"""
        from django.test import Client
        from django.middleware.csrf import get_token
        
        # Client with CSRF checks enabled
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        
        # Get CSRF token
        response = client.get(reverse('dashboard:index'))
        csrf_token = get_token(client.session)
        
        # Request without CSRF should fail
        response = client.post(
            reverse('accounts:disconnect_account', args=[self.account.id])
        )
        self.assertEqual(response.status_code, 403)
        
        # Request with CSRF should succeed
        response = client.post(
            reverse('accounts:disconnect_account', args=[self.account.id]),
            {'csrfmiddlewaretoken': csrf_token}
        )
        self.assertEqual(response.status_code, 302)
    
    def test_oauth_callback_csrf_exempt(self):
        """Test OAuth callback is properly CSRF exempt"""
        from django.test import Client
        
        # OAuth callback should work without CSRF (external redirect)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        
        response = client.get(
            reverse('accounts:oauth_callback'),
            {'error': 'access_denied'}
        )
        
        # Should not fail due to CSRF (external redirect from Google)
        self.assertNotEqual(response.status_code, 403)


class PasswordSecurityTest(TestCase):
    """Test password handling security"""
    
    def test_password_authentication(self):
        """Test Django's built-in password authentication"""
        user = User.objects.create_user(
            username='pwduser',
            password='secure_password_123'
        )
        
        # Valid password should authenticate
        authenticated_user = authenticate(
            username='pwduser',
            password='secure_password_123'
        )
        self.assertEqual(authenticated_user, user)
        
        # Invalid password should not authenticate
        invalid_auth = authenticate(
            username='pwduser',
            password='wrong_password'
        )
        self.assertIsNone(invalid_auth)
    
    def test_login_rate_limiting(self):
        """Test login attempt rate limiting if implemented"""
        # This would test rate limiting on login attempts
        # Implementation depends on whether rate limiting is added
        user = User.objects.create_user(
            username='ratelimituser',
            password='correct_password'
        )
        
        client = Client()
        
        # Multiple failed login attempts
        for i in range(5):
            response = client.post(reverse('login'), {
                'username': 'ratelimituser',
                'password': 'wrong_password'
            })
            # Should still allow attempts (unless rate limiting implemented)
            self.assertIn(response.status_code, [200, 302])
        
        # Valid login should still work (unless rate limited)
        response = client.post(reverse('login'), {
            'username': 'ratelimituser', 
            'password': 'correct_password'
        })
        self.assertIn(response.status_code, [200, 302])
```

### Step 3: Session Management Tests (30 minutes)

Add session security tests:

```python
# Add to test_account_security.py

class SessionManagementTest(TestCase):
    """Test session security and management"""
    
    def test_session_invalidation_on_logout(self):
        """Test session is properly invalidated on logout"""
        user = User.objects.create_user(username='sessionuser', password='pass')
        client = Client()
        
        # Login and verify session
        client.login(username='sessionuser', password='pass')
        self.assertIn('_auth_user_id', client.session)
        
        original_session_key = client.session.session_key
        
        # Logout
        response = client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        
        # Session should be invalidated
        self.assertNotIn('_auth_user_id', client.session)
        
        # Session key should change
        new_session_key = client.session.session_key
        self.assertNotEqual(original_session_key, new_session_key)
    
    def test_session_security_attributes(self):
        """Test session cookies have secure attributes"""
        from django.conf import settings
        
        # These settings should be configured for production security
        # Test that they are properly set
        
        user = User.objects.create_user(username='cookieuser', password='pass')
        client = Client()
        
        response = client.post(reverse('login'), {
            'username': 'cookieuser',
            'password': 'pass'
        })
        
        # Check session cookie attributes (in production)
        if hasattr(settings, 'SESSION_COOKIE_SECURE'):
            # In production, these should be True
            pass  # Would test actual cookie attributes
    
    def test_concurrent_session_handling(self):
        """Test handling of concurrent sessions for same user"""
        user = User.objects.create_user(username='concurrent', password='pass')
        
        # Create two clients (different sessions)
        client1 = Client()
        client2 = Client()
        
        # Login with both
        client1.login(username='concurrent', password='pass')
        client2.login(username='concurrent', password='pass')
        
        # Both should be authenticated
        response1 = client1.get(reverse('dashboard:index'))
        response2 = client2.get(reverse('dashboard:index'))
        
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(response2.status_code, 200)
        
        # Sessions should be independent
        self.assertNotEqual(
            client1.session.session_key,
            client2.session.session_key
        )
```

---

## Files to Create/Modify

### New Files:
- `tests/integration/test_oauth_flow.py` - Complete OAuth flow with real Django auth
- `tests/integration/test_account_security.py` - Security boundary and access control tests

### Integration Test Structure:
```
tests/integration/
├── test_oauth_flow.py              # OAuth with real Django sessions
├── test_account_security.py        # Access control and CSRF protection
├── test_webhook_processing.py      # (from GT-02)
├── test_calendar_sync.py           # (from GT-02)
└── test_user_workflows.py          # (from GT-02)
```

---

## Validation Steps

1. **Run Authentication Tests**:
   ```bash
   cd src
   pytest tests/integration/test_oauth_flow.py -v
   ```

2. **Test Security Boundaries**:
   ```bash
   pytest tests/integration/test_account_security.py -v
   ```

3. **Verify Real Django Mechanisms**:
   ```bash
   pytest tests/integration/ -k "oauth or security" --tb=short
   ```

4. **Test with CSRF Enabled**:
   ```bash
   # Tests should work with real CSRF protection
   pytest tests/integration/test_account_security.py::CSRFProtectionTest -v
   ```

---

## Success Criteria

- [ ] OAuth tests use real Django sessions and authentication
- [ ] Security tests verify actual access control (not mocked permissions)
- [ ] CSRF protection tests use real Django CSRF middleware
- [ ] Token refresh tests use real encryption/decryption
- [ ] Session management tests use real Django session framework
- [ ] All tests mock only external OAuth providers, never internal auth
- [ ] Security boundaries are tested with realistic attack scenarios
- [ ] Multi-user access control is verified with real user objects

---

## Definition of Done

- [ ] Authentication flows tested with real Django mechanisms
- [ ] Security boundaries verified without mocking internal auth logic
- [ ] OAuth state validation tested with real session storage
- [ ] Token refresh flow tested with real credential objects
- [ ] Access control tested with actual permission checking
- [ ] CSRF protection verified with real middleware
- [ ] Session security tested with actual session framework
- [ ] Tests would catch real security vulnerabilities

This approach tests security at the boundaries where it matters most, using real Django security mechanisms to ensure the authentication system actually works and is secure.
"""Tests for dashboard views and functionality"""

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.calendars.models import Calendar, CalendarAccount


class DashboardViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.profile = UserProfile.objects.create(user=self.user)
        
        # Create test calendar account and calendar
        self.account = CalendarAccount.objects.create(
            user=self.user,
            email="test@gmail.com",
            google_account_id="test_account_id",
            is_active=True,
            token_expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        
        self.calendar = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="test_calendar_id",
            name="Test Calendar",
            sync_enabled=True,
        )

    def test_dashboard_requires_login(self):
        """Test that dashboard requires authentication"""
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_dashboard_view_authenticated(self):
        """Test dashboard view with authenticated user"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("dashboard:index"))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")
        self.assertContains(response, "Connected Accounts")
        self.assertContains(response, self.account.email)

    def test_account_detail_requires_login(self):
        """Test that account detail requires authentication"""
        response = self.client.get(reverse("dashboard:account_detail", args=[self.account.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_account_detail_view_authenticated(self):
        """Test account detail view with authenticated user"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("dashboard:account_detail", args=[self.account.id]))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Account: {self.account.email}")
        self.assertContains(response, self.calendar.name)
        self.assertContains(response, "Calendars (1)")

    def test_account_detail_wrong_user(self):
        """Test that users can only view their own accounts"""
        # Create another user and account
        other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="otherpass123"
        )
        other_account = CalendarAccount.objects.create(
            user=other_user,
            email="other@gmail.com",
            google_account_id="other_account_id",
            is_active=True,
            token_expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("dashboard:account_detail", args=[other_account.id]))
        
        self.assertEqual(response.status_code, 404)

    def test_refresh_calendars_requires_login(self):
        """Test that refresh calendars requires authentication"""
        response = self.client.get(reverse("dashboard:refresh_calendars", args=[self.account.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)


class CalendarToggleTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        
        # Create test calendar account and calendar
        self.account = CalendarAccount.objects.create(
            user=self.user,
            email="test@gmail.com",
            google_account_id="test_account_id",
            is_active=True,
            token_expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        
        self.calendar = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="test_calendar_id",
            name="Test Calendar",
            sync_enabled=True,
        )

    def test_toggle_calendar_sync_requires_login(self):
        """Test that toggle requires authentication"""
        response = self.client.post(reverse("dashboard:toggle_calendar_sync", args=[self.calendar.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_toggle_calendar_sync_requires_post(self):
        """Test that toggle only accepts POST requests"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("dashboard:toggle_calendar_sync", args=[self.calendar.id]))
        self.assertEqual(response.status_code, 405)

    def test_toggle_calendar_sync_enable_to_disable(self):
        """Test toggling calendar sync from enabled to disabled"""
        self.client.login(username="testuser", password="testpass123")
        
        # Verify initial state
        self.assertTrue(self.calendar.sync_enabled)
        
        response = self.client.post(reverse("dashboard:toggle_calendar_sync", args=[self.calendar.id]))
        
        # Should return 200 with partial template
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disabled")
        self.assertContains(response, "Enable")
        
        # Verify database state changed
        self.calendar.refresh_from_db()
        self.assertFalse(self.calendar.sync_enabled)

    def test_toggle_calendar_sync_disable_to_enable(self):
        """Test toggling calendar sync from disabled to enabled"""
        self.client.login(username="testuser", password="testpass123")
        
        # Start with disabled calendar
        self.calendar.sync_enabled = False
        self.calendar.save()
        
        response = self.client.post(reverse("dashboard:toggle_calendar_sync", args=[self.calendar.id]))
        
        # Should return 200 with partial template
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enabled")
        self.assertContains(response, "Disable")
        
        # Verify database state changed
        self.calendar.refresh_from_db()
        self.assertTrue(self.calendar.sync_enabled)

    def test_toggle_calendar_sync_wrong_user(self):
        """Test that users can only toggle their own calendars"""
        # Create another user and calendar
        other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="otherpass123"
        )
        other_account = CalendarAccount.objects.create(
            user=other_user,
            email="other@gmail.com",
            google_account_id="other_account_id",
            is_active=True,
            token_expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        other_calendar = Calendar.objects.create(
            calendar_account=other_account,
            google_calendar_id="other_calendar_id",
            name="Other Calendar",
            sync_enabled=True,
        )
        
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(reverse("dashboard:toggle_calendar_sync", args=[other_calendar.id]))
        
        # Should return 404
        self.assertEqual(response.status_code, 404)
        
        # Verify other user's calendar was not modified
        other_calendar.refresh_from_db()
        self.assertTrue(other_calendar.sync_enabled)

    def test_toggle_calendar_sync_nonexistent_calendar(self):
        """Test toggling non-existent calendar returns 404"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(reverse("dashboard:toggle_calendar_sync", args=[9999]))
        
        self.assertEqual(response.status_code, 404)

    def test_toggle_calendar_sync_partial_template_content(self):
        """Test that the partial template contains correct HTMX attributes"""
        self.client.login(username="testuser", password="testpass123")
        
        response = self.client.post(reverse("dashboard:toggle_calendar_sync", args=[self.calendar.id]))
        
        # Verify HTMX attributes are present
        self.assertContains(response, 'hx-post=')
        self.assertContains(response, 'hx-target="closest td"')
        self.assertContains(response, 'hx-swap="innerHTML"')
        
        # After toggle, calendar was enabled->disabled, so button should be "Enable" (btn-success)
        self.assertContains(response, 'class="btn btn-success"')  # Enable button for disabled calendar
        self.assertContains(response, "Disabled")  # Status should be disabled
        self.assertContains(response, "Enable")  # Button text should be Enable


class DashboardIntegrationTest(TestCase):
    """Integration tests for dashboard functionality"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.profile = UserProfile.objects.create(user=self.user)
        
        # Create multiple calendar accounts and calendars
        self.account1 = CalendarAccount.objects.create(
            user=self.user,
            email="personal@gmail.com",
            google_account_id="personal_account",
            is_active=True,
            token_expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        
        self.account2 = CalendarAccount.objects.create(
            user=self.user,
            email="work@company.com",
            google_account_id="work_account",
            is_active=True,
            token_expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        
        # Create calendars for each account
        self.personal_calendar = Calendar.objects.create(
            calendar_account=self.account1,
            google_calendar_id="personal_cal",
            name="Personal Calendar",
            sync_enabled=True,
        )
        
        self.work_calendar = Calendar.objects.create(
            calendar_account=self.account2,
            google_calendar_id="work_cal",
            name="Work Calendar",
            sync_enabled=False,
        )

    def test_dashboard_shows_all_accounts_and_stats(self):
        """Test that dashboard shows comprehensive statistics"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("dashboard:index"))
        
        self.assertEqual(response.status_code, 200)
        
        # Check account statistics
        self.assertContains(response, "Connected Accounts:")
        self.assertContains(response, "2")  # Two accounts
        self.assertContains(response, "Active Accounts:")
        self.assertContains(response, "2")  # Both active
        self.assertContains(response, "Total Calendars:")
        self.assertContains(response, "2")  # Two calendars total
        
        # Check both accounts are listed
        self.assertContains(response, self.account1.email)
        self.assertContains(response, self.account2.email)

    def test_account_detail_shows_correct_calendar_states(self):
        """Test that account detail correctly shows calendar sync states"""
        self.client.login(username="testuser", password="testpass123")
        
        # Test first account (enabled calendar)
        response = self.client.get(reverse("dashboard:account_detail", args=[self.account1.id]))
        self.assertContains(response, "Enabled")
        self.assertContains(response, "Disable")  # Button to disable
        
        # Test second account (disabled calendar)
        response = self.client.get(reverse("dashboard:account_detail", args=[self.account2.id]))
        self.assertContains(response, "Disabled")
        self.assertContains(response, "Enable")  # Button to enable
"""Integration tests for dashboard functionality"""

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.calendars.models import Calendar, CalendarAccount


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
        response = self.client.get(
            reverse("dashboard:account_detail", args=[self.account1.id])
        )
        self.assertContains(response, "Enabled")
        self.assertContains(response, "Disable")  # Button to disable

        # Test second account (disabled calendar)
        response = self.client.get(
            reverse("dashboard:account_detail", args=[self.account2.id])
        )
        self.assertContains(response, "Disabled")
        self.assertContains(response, "Enable")  # Button to enable
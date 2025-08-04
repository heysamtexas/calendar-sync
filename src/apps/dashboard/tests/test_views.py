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
        response = self.client.get(
            reverse("dashboard:account_detail", args=[self.account.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_account_detail_view_authenticated(self):
        """Test account detail view with authenticated user"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(
            reverse("dashboard:account_detail", args=[self.account.id])
        )

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
        response = self.client.get(
            reverse("dashboard:account_detail", args=[other_account.id])
        )

        # Service layer now returns permission error, view redirects
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("dashboard:index"))

    def test_refresh_calendars_requires_login(self):
        """Test that refresh calendars requires authentication"""
        response = self.client.get(
            reverse("dashboard:refresh_calendars", args=[self.account.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

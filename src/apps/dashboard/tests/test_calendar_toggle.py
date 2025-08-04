"""Tests for calendar sync toggle functionality"""

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.calendars.models import Calendar, CalendarAccount


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
        response = self.client.post(
            reverse("dashboard:toggle_calendar_sync", args=[self.calendar.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_toggle_calendar_sync_requires_post(self):
        """Test that toggle only accepts POST requests"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(
            reverse("dashboard:toggle_calendar_sync", args=[self.calendar.id])
        )
        self.assertEqual(response.status_code, 405)

    def test_toggle_calendar_sync_enable_to_disable(self):
        """Test toggling calendar sync from enabled to disabled"""
        self.client.login(username="testuser", password="testpass123")

        # Verify initial state
        self.assertTrue(self.calendar.sync_enabled)

        response = self.client.post(
            reverse("dashboard:toggle_calendar_sync", args=[self.calendar.id])
        )

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

        response = self.client.post(
            reverse("dashboard:toggle_calendar_sync", args=[self.calendar.id])
        )

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
        response = self.client.post(
            reverse("dashboard:toggle_calendar_sync", args=[other_calendar.id])
        )

        # Service layer now returns 403 for permission denied (more accurate)
        self.assertEqual(response.status_code, 403)

        # Verify other user's calendar was not modified
        other_calendar.refresh_from_db()
        self.assertTrue(other_calendar.sync_enabled)

    def test_toggle_calendar_sync_nonexistent_calendar(self):
        """Test toggling non-existent calendar returns 404"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(
            reverse("dashboard:toggle_calendar_sync", args=[9999])
        )

        self.assertEqual(response.status_code, 404)

    def test_toggle_calendar_sync_partial_template_content(self):
        """Test that the partial template contains correct HTMX attributes"""
        self.client.login(username="testuser", password="testpass123")

        response = self.client.post(
            reverse("dashboard:toggle_calendar_sync", args=[self.calendar.id])
        )

        # Verify HTMX attributes are present
        self.assertContains(response, "hx-post=")
        self.assertContains(response, 'hx-target="closest td"')
        self.assertContains(response, 'hx-swap="innerHTML"')

        # After toggle, calendar was enabled->disabled, so status should show "Disabled"
        self.assertContains(response, "Disabled")  # Status should be disabled
        self.assertContains(response, "status-disabled")  # CSS class for disabled status
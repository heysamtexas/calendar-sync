"""Test dashboard with multiple connected accounts"""

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import UserProfile
from apps.calendars.models import Calendar, CalendarAccount, Event, SyncLog


class MultipleAccountsTest(TestCase):
    """Test dashboard behavior with multiple connected accounts"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", 
            email="test@example.com", 
            password="testpass123"
        )
        self.profile = UserProfile.objects.create(user=self.user)
        
        # Create first account (Personal Gmail)
        self.account1 = CalendarAccount.objects.create(
            user=self.user,
            email="personal@gmail.com",
            google_account_id="personal_google_id",
            is_active=True,
            token_expires_at=timezone.now() + timedelta(hours=1),
        )
        
        # Create second account (Work Gmail)
        self.account2 = CalendarAccount.objects.create(
            user=self.user,
            email="work@company.com", 
            google_account_id="work_google_id",
            is_active=True,
            token_expires_at=timezone.now() + timedelta(hours=1),
        )
        
        # Create calendars for first account
        self.personal_cal1 = Calendar.objects.create(
            calendar_account=self.account1,
            google_calendar_id="personal_cal_1",
            name="Personal Calendar",
            is_primary=True,
            sync_enabled=True,
        )
        
        self.personal_cal2 = Calendar.objects.create(
            calendar_account=self.account1,
            google_calendar_id="personal_cal_2", 
            name="Personal Tasks",
            is_primary=False,
            sync_enabled=False,
        )
        
        # Create calendars for second account
        self.work_cal1 = Calendar.objects.create(
            calendar_account=self.account2,
            google_calendar_id="work_cal_1",
            name="Work Calendar",
            is_primary=True, 
            sync_enabled=True,
        )
        
        self.work_cal2 = Calendar.objects.create(
            calendar_account=self.account2,
            google_calendar_id="work_cal_2",
            name="Team Meetings",
            is_primary=False,
            sync_enabled=True,
        )
        
        # Create some test events
        Event.objects.create(
            calendar=self.personal_cal1,
            google_event_id="personal_event_1",
            title="Personal Meeting",
            start_time=timezone.now() + timedelta(hours=2),
            end_time=timezone.now() + timedelta(hours=3),
        )
        
        Event.objects.create(
            calendar=self.work_cal1,
            google_event_id="work_event_1", 
            title="Work Meeting",
            start_time=timezone.now() + timedelta(hours=4),
            end_time=timezone.now() + timedelta(hours=5),
        )
        
        # Create sync logs
        SyncLog.objects.create(
            calendar_account=self.account1,
            sync_type="manual",
            status="success",
            events_processed=5,
            events_created=2,
            busy_blocks_created=3,
            completed_at=timezone.now(),
        )
        
        SyncLog.objects.create(
            calendar_account=self.account2,
            sync_type="manual", 
            status="success",
            events_processed=3,
            events_created=1,
            busy_blocks_created=2,
            completed_at=timezone.now() - timedelta(minutes=30),
        )

    def test_dashboard_shows_both_accounts(self):
        """Test that dashboard displays both connected accounts"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("dashboard:index"))
        
        self.assertEqual(response.status_code, 200)
        
        # Check context data
        context = response.context
        calendar_accounts = context["calendar_accounts"]
        
        print(f"\n=== DASHBOARD CONTEXT DEBUG ===")
        print(f"Total accounts in context: {len(calendar_accounts)}")
        print(f"Active accounts: {context['active_accounts']}")
        print(f"Total calendars: {context['total_calendars']}")
        
        for i, account in enumerate(calendar_accounts):
            print(f"Account {i+1}: {account.email} (Active: {account.is_active})")
            print(f"  - Calendars: {account.calendar_count}")
            print(f"  - Active calendars: {account.active_calendar_count}")
        
        # Assertions
        self.assertEqual(len(calendar_accounts), 2, "Should show 2 accounts")
        self.assertEqual(context["active_accounts"], 2, "Should show 2 active accounts")
        self.assertEqual(context["total_calendars"], 4, "Should show 4 total calendars")
        
        # Check that both account emails are in context
        account_emails = [acc.email for acc in calendar_accounts]
        self.assertIn("personal@gmail.com", account_emails)
        self.assertIn("work@company.com", account_emails)

    def test_dashboard_template_renders_both_accounts(self):
        """Test that template actually renders both accounts in HTML"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("dashboard:index"))
        
        content = response.content.decode()
        
        print(f"\n=== TEMPLATE RENDERING DEBUG ===")
        
        # Check Quick Stats section
        self.assertIn("Connected Accounts:", content)
        self.assertIn(">2<", content, "Should show '2' connected accounts in stats")
        
        # Check that both emails appear in the accounts table
        self.assertIn("personal@gmail.com", content, "Personal account should be visible")
        self.assertIn("work@company.com", content, "Work account should be visible")
        
        # Check calendar counts are correct
        self.assertIn("Total Calendars:", content)
        self.assertIn(">4<", content, "Should show '4' total calendars")
        
        # Count occurrences of "View Details" buttons (one per account)
        view_details_count = content.count("View Details")
        self.assertEqual(view_details_count, 2, f"Should have 2 'View Details' buttons, found {view_details_count}")
        
        # Check account table structure
        account_rows = content.count("<tr>") - 2  # Subtract header row and any other non-account rows
        print(f"Account table rows found: {account_rows}")
        
        # Debug: Print relevant HTML sections
        if "Connected Accounts" in content:
            start = content.find("Connected Accounts")
            end = content.find("</table>", start) + 8
            table_html = content[start:end]
            print(f"Accounts table HTML:\n{table_html[:500]}...")

    def test_account_detail_pages_work_for_both(self):
        """Test that both account detail pages work"""
        self.client.login(username="testuser", password="testpass123")
        
        # Test first account detail
        response1 = self.client.get(reverse("dashboard:account_detail", args=[self.account1.id]))
        self.assertEqual(response1.status_code, 200)
        self.assertContains(response1, "personal@gmail.com")
        self.assertContains(response1, "Personal Calendar")
        
        # Test second account detail
        response2 = self.client.get(reverse("dashboard:account_detail", args=[self.account2.id]))
        self.assertEqual(response2.status_code, 200)
        self.assertContains(response2, "work@company.com")
        self.assertContains(response2, "Work Calendar")

    def test_dashboard_service_returns_correct_data(self):
        """Test the dashboard service directly"""
        from apps.dashboard.services import DashboardService
        
        service = DashboardService(self.user)
        dashboard_data = service.get_dashboard_data()
        
        print(f"\n=== DASHBOARD SERVICE DEBUG ===")
        print(f"Service returned accounts: {len(dashboard_data['calendar_accounts'])}")
        print(f"Active accounts: {dashboard_data['active_accounts']}")
        print(f"Total calendars: {dashboard_data['total_calendars']}")
        
        # Test service data
        self.assertEqual(len(dashboard_data["calendar_accounts"]), 2)
        self.assertEqual(dashboard_data["active_accounts"], 2)
        self.assertEqual(dashboard_data["total_calendars"], 4)
        
        accounts = dashboard_data["calendar_accounts"]
        emails = [acc.email for acc in accounts]
        self.assertIn("personal@gmail.com", emails)
        self.assertIn("work@company.com", emails)

    def test_with_one_inactive_account(self):
        """Test dashboard when one account is inactive"""
        # Deactivate second account
        self.account2.is_active = False
        self.account2.save()
        
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("dashboard:index"))
        
        context = response.context
        print(f"\n=== INACTIVE ACCOUNT TEST ===")
        print(f"Total accounts: {len(context['calendar_accounts'])}")
        print(f"Active accounts: {context['active_accounts']}")
        
        # Should still show both accounts, but only 1 active
        self.assertEqual(len(context["calendar_accounts"]), 2, "Should show both accounts")
        self.assertEqual(context["active_accounts"], 1, "Should show 1 active account")
        
        content = response.content.decode()
        self.assertIn("personal@gmail.com", content)
        self.assertIn("work@company.com", content)
        self.assertIn("Inactive", content)  # Should show inactive status
"""Test dashboard with multiple connected accounts"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.calendars.models import Calendar, CalendarAccount, Event, SyncLog


class MultipleAccountsTest(TestCase):
    """Test dashboard behavior with multiple connected accounts"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
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

        print("\n=== DASHBOARD CONTEXT DEBUG ===")
        print(f"Total accounts in context: {len(calendar_accounts)}")
        print(f"Active accounts: {context['active_accounts']}")
        print(f"Total calendars: {context['total_calendars']}")

        for i, account in enumerate(calendar_accounts):
            print(f"Account {i + 1}: {account.email} (Active: {account.is_active})")
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

        print("\n=== TEMPLATE RENDERING DEBUG ===")

        # Check Quick Stats section
        self.assertIn("Connected Accounts:", content)
        self.assertIn(">2<", content, "Should show '2' connected accounts in stats")

        # Check that both emails appear in the accounts table
        self.assertIn(
            "personal@gmail.com", content, "Personal account should be visible"
        )
        self.assertIn("work@company.com", content, "Work account should be visible")

        # Check calendar counts are correct
        self.assertIn("Total Calendars:", content)
        self.assertIn(">4<", content, "Should show '4' total calendars")

        # Count occurrences of "View Details" buttons (one per account)
        view_details_count = content.count("View Details")
        self.assertEqual(
            view_details_count,
            2,
            f"Should have 2 'View Details' buttons, found {view_details_count}",
        )

        # Check account table structure
        account_rows = (
            content.count("<tr>") - 2
        )  # Subtract header row and any other non-account rows
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
        response1 = self.client.get(
            reverse("dashboard:account_detail", args=[self.account1.id])
        )
        self.assertEqual(response1.status_code, 200)
        self.assertContains(response1, "personal@gmail.com")
        self.assertContains(response1, "Personal Calendar")

        # Test second account detail
        response2 = self.client.get(
            reverse("dashboard:account_detail", args=[self.account2.id])
        )
        self.assertEqual(response2.status_code, 200)
        self.assertContains(response2, "work@company.com")
        self.assertContains(response2, "Work Calendar")

    def test_dashboard_service_returns_correct_data(self):
        """Test the dashboard service directly"""
        from apps.dashboard.services import DashboardService

        service = DashboardService(self.user)
        dashboard_data = service.get_dashboard_data()

        print("\n=== DASHBOARD SERVICE DEBUG ===")
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
        print("\n=== INACTIVE ACCOUNT TEST ===")
        print(f"Total accounts: {len(context['calendar_accounts'])}")
        print(f"Active accounts: {context['active_accounts']}")

        # Should still show both accounts, but only 1 active
        self.assertEqual(
            len(context["calendar_accounts"]), 2, "Should show both accounts"
        )
        self.assertEqual(context["active_accounts"], 1, "Should show 1 active account")

        content = response.content.decode()
        self.assertIn("personal@gmail.com", content)
        self.assertIn("work@company.com", content)
        self.assertIn("Inactive", content)  # Should show inactive status

    def test_dashboard_shows_last_sync_times(self):
        """Test that dashboard properly displays last sync times for accounts"""
        from apps.dashboard.services import DashboardService

        # Create additional sync logs with different statuses to test filtering
        older_success = SyncLog.objects.create(
            calendar_account=self.account1,
            sync_type="incremental",
            status="success",
            events_processed=3,
            completed_at=timezone.now() - timedelta(hours=2),
        )

        recent_failure = SyncLog.objects.create(
            calendar_account=self.account1,
            sync_type="manual",
            status="error",
            error_message="Test error",
            completed_at=timezone.now() - timedelta(minutes=10),
        )

        # Test dashboard service directly
        service = DashboardService(self.user)
        dashboard_data = service.get_dashboard_data()

        accounts = dashboard_data["calendar_accounts"]
        self.assertEqual(len(accounts), 2)

        # Verify each account has last_sync attribute populated
        for account in accounts:
            self.assertTrue(
                hasattr(account, "last_sync"),
                f"Account {account.email} should have last_sync attribute",
            )

            if account.email == "personal@gmail.com":
                # Should have the most recent successful sync (from setUp, not the error)
                self.assertIsNotNone(
                    account.last_sync,
                    f"Account {account.email} should have a last sync time",
                )
                # Verify it gets the successful sync, not the failed one
                last_sync_obj = account.get_last_successful_sync()
                self.assertIsNotNone(last_sync_obj)
                self.assertEqual(account.last_sync, last_sync_obj.completed_at)

            elif account.email == "work@company.com":
                # Should have sync from setUp
                self.assertIsNotNone(
                    account.last_sync,
                    f"Account {account.email} should have a last sync time",
                )

        # Test the template rendering shows sync times instead of "Never"
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("dashboard:index"))
        content = response.content.decode()

        # Should not show "Never" for accounts with sync history
        self.assertNotIn(
            "Never",
            content,
            "Dashboard should not show 'Never' for accounts with sync history",
        )

        # Should show some date/time format (look for common date patterns)
        import re

        # Look for date patterns like "Jan 01, 2024 12:34" or similar
        date_pattern = r"\w{3}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}"
        date_matches = re.findall(date_pattern, content)
        self.assertGreater(
            len(date_matches), 0, "Dashboard should show formatted sync timestamps"
        )

    def test_dashboard_handles_accounts_without_sync_history(self):
        """Test that accounts without successful syncs show 'Never'"""
        from apps.dashboard.services import DashboardService

        # Create a new account with no sync history
        account_no_sync = CalendarAccount.objects.create(
            user=self.user,
            email="nosync@example.com",
            google_account_id="nosync_google_id",
            is_active=True,
            token_expires_at=timezone.now() + timedelta(hours=1),
        )

        # Create only failed sync logs for this account
        SyncLog.objects.create(
            calendar_account=account_no_sync,
            sync_type="manual",
            status="error",
            error_message="Failed sync",
            completed_at=timezone.now() - timedelta(hours=1),
        )

        # Test dashboard service
        service = DashboardService(self.user)
        dashboard_data = service.get_dashboard_data()

        # Find the account with no successful syncs
        no_sync_account = None
        for account in dashboard_data["calendar_accounts"]:
            if account.email == "nosync@example.com":
                no_sync_account = account
                break

        self.assertIsNotNone(no_sync_account)
        self.assertTrue(hasattr(no_sync_account, "last_sync"))
        self.assertIsNone(
            no_sync_account.last_sync,
            "Account with no successful syncs should have None for last_sync",
        )

        # Test template shows "Never" for this account
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("dashboard:index"))
        content = response.content.decode()

        # Should show "Never" for the account without successful syncs
        self.assertIn(
            "Never",
            content,
            "Dashboard should show 'Never' for accounts without successful sync history",
        )

    def test_account_detail_shows_last_sync_times(self):
        """Test that account detail page shows last sync times"""
        from apps.dashboard.services import DashboardService

        # Create additional sync logs with different statuses to test filtering
        older_success = SyncLog.objects.create(
            calendar_account=self.account1,
            sync_type="incremental",
            status="success",
            events_processed=3,
            completed_at=timezone.now() - timedelta(hours=2),
        )

        recent_failure = SyncLog.objects.create(
            calendar_account=self.account1,
            sync_type="manual",
            status="error",
            error_message="Test error",
            completed_at=timezone.now() - timedelta(minutes=10),
        )

        # Test dashboard service directly
        service = DashboardService(self.user)
        account_data = service.get_account_detail_data(self.account1.id)

        account = account_data["account"]

        # Verify the account has last_sync attribute populated
        self.assertTrue(
            hasattr(account, "last_sync"),
            f"Account {account.email} should have last_sync attribute",
        )
        self.assertIsNotNone(
            account.last_sync, f"Account {account.email} should have a last sync time"
        )

        # Verify it gets the successful sync, not the failed one
        last_sync_obj = account.get_last_successful_sync()
        self.assertIsNotNone(last_sync_obj)
        self.assertEqual(account.last_sync, last_sync_obj.completed_at)

        # Test the template rendering shows sync times instead of "Never"
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(
            reverse("dashboard:account_detail", args=[self.account1.id])
        )
        content = response.content.decode()

        # Should not show "Never" for accounts with sync history
        last_sync_section = content[
            content.find("Last Sync:") : content.find("Last Sync:") + 200
        ]
        self.assertNotIn(
            "Never",
            last_sync_section,
            "Account detail should not show 'Never' for accounts with sync history",
        )

        # Should show some date/time format (look for common date patterns)
        import re

        # Look for date patterns like "Jan 01, 2024 12:34" or similar
        date_pattern = r"\w{3}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}"
        date_matches = re.findall(date_pattern, last_sync_section)
        self.assertGreater(
            len(date_matches), 0, "Account detail should show formatted sync timestamps"
        )

"""Performance tests for dashboard views query optimization"""

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.test.utils import override_settings
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.calendars.models import Calendar, CalendarAccount, Event, SyncLog


User = get_user_model()


@override_settings(
    DEBUG=True,  # Enable query counting
    # Disable debug toolbar for tests to avoid URL resolution issues
    INSTALLED_APPS=[
        app
        for app in __import__(
            "django.conf", fromlist=["settings"]
        ).settings.INSTALLED_APPS
        if app != "debug_toolbar"
    ],
    MIDDLEWARE=[
        mw
        for mw in __import__("django.conf", fromlist=["settings"]).settings.MIDDLEWARE
        if "debug_toolbar" not in mw
    ],
)
class DashboardPerformanceTestCase(TransactionTestCase):
    """Test database query performance for dashboard views"""

    def setUp(self):
        """Create test data for performance testing"""
        # Create test user and profile
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.profile = UserProfile.objects.create(user=self.user, sync_enabled=True)

        # Create multiple calendar accounts
        self.accounts = []
        for i in range(3):
            account = CalendarAccount.objects.create(
                user=self.user,
                google_account_id=f"google_account_{i}",
                email=f"account{i}@gmail.com",
                access_token="encrypted_access_token",
                refresh_token="encrypted_refresh_token",
                token_expires_at="2025-12-31 23:59:59+00:00",
                is_active=True,
            )
            self.accounts.append(account)

            # Create calendars for each account
            for j in range(4):  # 4 calendars per account = 12 total
                calendar = Calendar.objects.create(
                    calendar_account=account,
                    google_calendar_id=f"cal_{i}_{j}",
                    name=f"Calendar {i}-{j}",
                    sync_enabled=j % 2 == 0,  # Half enabled, half disabled
                )

                # Create regular events first
                regular_events = []
                for k in range(3):  # 3 regular events per calendar
                    event = Event.objects.create(
                        calendar=calendar,
                        google_event_id=f"event_{i}_{j}_{k}",
                        title=f"Event {i}-{j}-{k}",
                        start_time="2025-01-15 10:00:00+00:00",
                        end_time="2025-01-15 11:00:00+00:00",
                        is_busy_block=False,
                    )
                    regular_events.append(event)

                # Create busy blocks with proper source events
                for k in range(2):  # 2 busy blocks per calendar
                    source_event = (
                        regular_events[k]
                        if k < len(regular_events)
                        else regular_events[0]
                    )
                    Event.objects.create(
                        calendar=calendar,
                        google_event_id=f"busy_{i}_{j}_{k}",
                        title=f"🔒 Busy - CalSync [source:cal{i}:event{k}]",
                        start_time="2025-01-15 14:00:00+00:00",
                        end_time="2025-01-15 15:00:00+00:00",
                        is_busy_block=True,
                        source_event=source_event,
                    )

            # Create sync logs for each account
            for l in range(15):  # 15 sync logs per account = 45 total
                SyncLog.objects.create(
                    calendar_account=account,
                    sync_type="incremental",
                    status="success",
                    events_processed=10,
                    events_created=2,
                    events_updated=1,
                    api_calls_made=5,
                )

        # Login user for tests
        self.client.force_login(self.user)

    def test_dashboard_view_query_count(self):
        """Test that dashboard view uses optimal number of queries"""
        url = reverse("dashboard:index")

        # Test query count with assertNumQueries
        with self.assertNumQueries(5):  # Target: 2 framework + 3 app queries = 5 total
            response = self.client.get(url)

        # Verify response is successful
        self.assertEqual(response.status_code, 200)

        # Verify context data is present
        self.assertIn("calendar_accounts", response.context)
        self.assertIn("recent_syncs", response.context)
        self.assertIn("total_calendars", response.context)
        self.assertIn("active_accounts", response.context)

        # Verify statistics are correct
        self.assertEqual(
            response.context["total_calendars"], 12
        )  # 3 accounts × 4 calendars
        self.assertEqual(response.context["active_accounts"], 3)  # All accounts active

    def test_dashboard_view_data_accuracy(self):
        """Test that optimized queries return accurate data"""
        url = reverse("dashboard:index")
        response = self.client.get(url)

        # Verify calendar accounts have annotated counts
        calendar_accounts = response.context["calendar_accounts"]
        for account in calendar_accounts:
            self.assertTrue(hasattr(account, "calendar_count"))
            self.assertTrue(hasattr(account, "active_calendar_count"))
            self.assertEqual(account.calendar_count, 4)  # 4 calendars per account
            self.assertEqual(account.active_calendar_count, 2)  # 2 enabled per account

        # Verify recent syncs have calendar_account data
        recent_syncs = response.context["recent_syncs"]
        self.assertEqual(len(recent_syncs), 10)  # Limited to 10 most recent
        for sync_log in recent_syncs:
            # Should not trigger additional queries to access calendar_account
            self.assertIsNotNone(sync_log.calendar_account.email)

    def test_account_detail_view_query_count(self):
        """Test that account detail view uses optimal number of queries"""
        account = self.accounts[0]
        url = reverse("dashboard:account_detail", args=[account.id])

        # Test query count with assertNumQueries
        with self.assertNumQueries(5):  # Target: 2 framework + 3 app queries = 5 total
            response = self.client.get(url)

        # Verify response is successful
        self.assertEqual(response.status_code, 200)

        # Verify context data is present
        self.assertIn("account", response.context)
        self.assertIn("calendars", response.context)
        self.assertIn("sync_logs", response.context)

    def test_account_detail_view_data_accuracy(self):
        """Test that optimized account detail queries return accurate data"""
        account = self.accounts[0]
        url = reverse("dashboard:account_detail", args=[account.id])
        response = self.client.get(url)

        # Verify account data
        context_account = response.context["account"]
        self.assertEqual(context_account.id, account.id)

        # Verify calendars have annotated counts
        calendars = response.context["calendars"]
        self.assertEqual(len(calendars), 4)  # 4 calendars for this account
        for calendar in calendars:
            self.assertTrue(hasattr(calendar, "event_count"))
            self.assertTrue(hasattr(calendar, "busy_block_count"))
            self.assertEqual(
                calendar.event_count, 5
            )  # 3 regular + 2 busy blocks per calendar
            self.assertEqual(calendar.busy_block_count, 2)  # 2 busy blocks per calendar

        # Verify sync logs
        sync_logs = response.context["sync_logs"]
        self.assertEqual(len(sync_logs), 15)  # All 15 sync logs for this account

    def test_performance_with_no_data(self):
        """Test query performance with empty user account"""
        # Create user with no calendar accounts
        empty_user = User.objects.create_user(
            username="emptyuser", email="empty@example.com", password="testpass123"
        )
        UserProfile.objects.create(user=empty_user, sync_enabled=True)
        self.client.force_login(empty_user)

        url = reverse("dashboard:index")

        # Should still use minimal queries even with no data
        with self.assertNumQueries(5):  # Same query count regardless of data volume
            response = self.client.get(url)

        # Verify empty state handling
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_calendars"], 0)
        self.assertEqual(response.context["active_accounts"], 0)
        self.assertEqual(len(response.context["calendar_accounts"]), 0)
        self.assertEqual(len(response.context["recent_syncs"]), 0)

    def test_query_optimization_benchmark(self):
        """Benchmark query performance to ensure optimization targets are met"""
        url = reverse("dashboard:index")

        # Measure performance with query counting
        with self.assertNumQueries(5) as context:
            response = self.client.get(url)

        # Verify all required data is accessible without additional queries
        calendar_accounts = response.context["calendar_accounts"]

        # Access annotated fields (should not trigger additional queries)
        total_calendar_count = sum(acc.calendar_count for acc in calendar_accounts)
        total_active_count = sum(acc.active_calendar_count for acc in calendar_accounts)

        self.assertEqual(total_calendar_count, 12)
        self.assertEqual(total_active_count, 6)  # 2 active per account × 3 accounts

        # Access prefetched calendars (should not trigger additional queries)
        for account in calendar_accounts:
            calendars = list(account.calendars.all())  # Force evaluation
            self.assertEqual(len(calendars), 4)

    def test_account_detail_benchmark(self):
        """Benchmark account detail query performance"""
        account = self.accounts[0]
        url = reverse("dashboard:account_detail", args=[account.id])

        with self.assertNumQueries(5) as context:
            response = self.client.get(url)

        # Verify prefetched data is accessible without additional queries
        calendars = response.context["calendars"]

        # Access annotated fields (should not trigger additional queries)
        total_events = sum(cal.event_count for cal in calendars)
        total_busy_blocks = sum(cal.busy_block_count for cal in calendars)

        self.assertEqual(total_events, 20)  # 5 events × 4 calendars
        self.assertEqual(total_busy_blocks, 8)  # 2 busy blocks × 4 calendars

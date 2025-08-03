from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.calendars.models import Calendar, CalendarAccount, Event, SyncLog


class CalendarAccountModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.profile = UserProfile.objects.create(user=self.user)

    def test_calendar_account_creation(self):
        """Test creating a calendar account"""
        account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="google123",
            email="calendar@gmail.com",
            access_token="encrypted_access_token",
            refresh_token="encrypted_refresh_token",
            token_expires_at=timezone.now() + timedelta(hours=1),
        )
        self.assertEqual(account.user, self.user)
        self.assertEqual(account.google_account_id, "google123")
        self.assertEqual(account.email, "calendar@gmail.com")
        self.assertTrue(account.is_active)

    def test_token_encryption_decryption(self):
        """Test token encryption and decryption"""
        account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="google123",
            email="calendar@gmail.com",
            access_token="",
            refresh_token="",
            token_expires_at=timezone.now() + timedelta(hours=1),
        )

        # Test access token
        test_token = "my_secret_access_token"
        account.set_access_token(test_token)
        self.assertNotEqual(account.access_token, test_token)  # Should be encrypted
        self.assertEqual(
            account.get_access_token(), test_token
        )  # Should decrypt correctly

        # Test refresh token
        refresh_token = "my_secret_refresh_token"
        account.set_refresh_token(refresh_token)
        self.assertNotEqual(account.refresh_token, refresh_token)  # Should be encrypted
        self.assertEqual(
            account.get_refresh_token(), refresh_token
        )  # Should decrypt correctly

    def test_token_expiry_check(self):
        """Test token expiry checking"""
        # Expired token
        account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="google123",
            email="calendar@gmail.com",
            access_token="token",
            refresh_token="refresh",
            token_expires_at=timezone.now() - timedelta(hours=1),
        )
        self.assertTrue(account.is_token_expired)

        # Valid token
        account.token_expires_at = timezone.now() + timedelta(hours=1)
        account.save()
        self.assertFalse(account.is_token_expired)

    def test_unique_constraint(self):
        """Test unique constraint on user and google_account_id"""
        CalendarAccount.objects.create(
            user=self.user,
            google_account_id="google123",
            email="calendar1@gmail.com",
            access_token="token1",
            refresh_token="refresh1",
            token_expires_at=timezone.now() + timedelta(hours=1),
        )

        # Try to create duplicate
        with self.assertRaises((ValidationError, Exception)):
            CalendarAccount.objects.create(
                user=self.user,
                google_account_id="google123",
                email="calendar2@gmail.com",
                access_token="token2",
                refresh_token="refresh2",
                token_expires_at=timezone.now() + timedelta(hours=1),
            )


class CalendarModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.profile = UserProfile.objects.create(user=self.user)
        self.account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="google123",
            email="calendar@gmail.com",
            access_token="token",
            refresh_token="refresh",
            token_expires_at=timezone.now() + timedelta(hours=1),
        )

    def test_calendar_creation(self):
        """Test creating a calendar"""
        calendar = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal123",
            name="Work Calendar",
            description="My work calendar",
            color="#0000FF",
            is_primary=True,
        )
        self.assertEqual(calendar.calendar_account, self.account)
        self.assertEqual(calendar.google_calendar_id, "cal123")
        self.assertEqual(calendar.name, "Work Calendar")
        self.assertTrue(calendar.is_primary)
        self.assertTrue(calendar.sync_enabled)

    def test_should_sync_property(self):
        """Test the should_sync property logic"""
        calendar = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal123",
            name="Work Calendar",
        )

        # All enabled - should sync
        self.assertTrue(calendar.should_sync)

        # Calendar sync disabled
        calendar.sync_enabled = False
        calendar.save()
        self.assertFalse(calendar.should_sync)

        # Account inactive
        calendar.sync_enabled = True
        calendar.save()
        self.account.is_active = False
        self.account.save()
        self.assertFalse(calendar.should_sync)

        # User profile sync disabled
        self.account.is_active = True
        self.account.save()
        self.profile.sync_enabled = False
        self.profile.save()
        self.assertFalse(calendar.should_sync)

    def test_unique_constraint(self):
        """Test unique constraint on calendar_account and google_calendar_id"""
        Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal123",
            name="Calendar 1",
        )

        # Try to create duplicate
        with self.assertRaises((ValidationError, Exception)):
            Calendar.objects.create(
                calendar_account=self.account,
                google_calendar_id="cal123",
                name="Calendar 2",
            )


class EventModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.profile = UserProfile.objects.create(user=self.user)
        self.account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="google123",
            email="calendar@gmail.com",
            access_token="token",
            refresh_token="refresh",
            token_expires_at=timezone.now() + timedelta(hours=1),
        )
        self.calendar = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal123",
            name="Work Calendar",
        )

    def test_event_creation(self):
        """Test creating a regular event"""
        start_time = timezone.now()
        end_time = start_time + timedelta(hours=1)

        event = Event.objects.create(
            calendar=self.calendar,
            google_event_id="event123",
            title="Team Meeting",
            description="Weekly team sync",
            start_time=start_time,
            end_time=end_time,
            is_all_day=False,
            is_busy_block=False,
        )

        self.assertEqual(event.calendar, self.calendar)
        self.assertEqual(event.title, "Team Meeting")
        self.assertFalse(event.is_busy_block)
        self.assertIsNotNone(event.event_hash)

    def test_event_validation(self):
        """Test event time validation"""
        start_time = timezone.now()

        # End time before start time should raise error
        with self.assertRaises(ValidationError):
            Event.objects.create(
                calendar=self.calendar,
                google_event_id="event123",
                title="Invalid Event",
                start_time=start_time,
                end_time=start_time - timedelta(hours=1),
            )

    def test_busy_block_creation(self):
        """Test creating a busy block from source event"""
        # Create source event
        start_time = timezone.now()
        end_time = start_time + timedelta(hours=1)

        source_event = Event.objects.create(
            calendar=self.calendar,
            google_event_id="event123",
            title="Team Meeting",
            start_time=start_time,
            end_time=end_time,
        )

        # Create target calendar
        target_calendar = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal456",
            name="Personal Calendar",
        )

        # Create busy block
        busy_block = Event.create_busy_block(source_event, target_calendar)
        self.assertTrue(busy_block.is_busy_block)
        self.assertEqual(busy_block.source_event, source_event)
        self.assertEqual(busy_block.calendar, target_calendar)
        self.assertIn("🔒 Busy -", busy_block.title)
        self.assertIn("CalSync [source:", busy_block.busy_block_tag)

    def test_event_hash_generation(self):
        """Test event content hash generation"""
        event = Event.objects.create(
            calendar=self.calendar,
            google_event_id="event123",
            title="Test Event",
            description="Test Description",
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1),
        )

        original_hash = event.event_hash
        self.assertIsNotNone(original_hash)

        # Change content and regenerate hash
        event.title = "Updated Title"
        new_hash = event.generate_content_hash()
        self.assertNotEqual(original_hash, new_hash)

    def test_system_busy_block_detection(self):
        """Test detection of system-created busy blocks"""
        self.assertTrue(Event.is_system_busy_block("🔒 Busy - CalSync"))
        self.assertTrue(Event.is_system_busy_block("Meeting CalSync [source:123:456]"))
        self.assertFalse(Event.is_system_busy_block("Regular Meeting"))


class SyncLogModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="google123",
            email="calendar@gmail.com",
            access_token="token",
            refresh_token="refresh",
            token_expires_at=timezone.now() + timedelta(hours=1),
        )

    def test_sync_log_creation(self):
        """Test creating a sync log"""
        sync_log = SyncLog.objects.create(
            calendar_account=self.account, sync_type="full", status="in_progress"
        )

        self.assertEqual(sync_log.calendar_account, self.account)
        self.assertEqual(sync_log.sync_type, "full")
        self.assertEqual(sync_log.status, "in_progress")
        self.assertIsNotNone(sync_log.started_at)
        self.assertIsNone(sync_log.completed_at)

    def test_mark_completed(self):
        """Test marking sync as completed"""
        sync_log = SyncLog.objects.create(
            calendar_account=self.account, sync_type="incremental"
        )

        # Mark as successful
        sync_log.mark_completed(status="success")
        self.assertEqual(sync_log.status, "success")
        self.assertIsNotNone(sync_log.completed_at)
        self.assertEqual(sync_log.error_message, "")

        # Test duration property
        duration = sync_log.duration
        self.assertIsNotNone(duration)
        self.assertGreater(duration, 0)

    def test_mark_completed_with_error(self):
        """Test marking sync as failed with error"""
        sync_log = SyncLog.objects.create(
            calendar_account=self.account, sync_type="full"
        )

        error_msg = "API rate limit exceeded"
        sync_log.mark_completed(status="error", error_message=error_msg)
        self.assertEqual(sync_log.status, "error")
        self.assertEqual(sync_log.error_message, error_msg)
        self.assertIsNotNone(sync_log.completed_at)

    def test_sync_statistics(self):
        """Test sync statistics tracking"""
        sync_log = SyncLog.objects.create(
            calendar_account=self.account,
            sync_type="full",
            events_processed=100,
            events_created=10,
            events_updated=20,
            events_deleted=5,
            busy_blocks_created=15,
            busy_blocks_updated=8,
            busy_blocks_deleted=3,
            api_calls_made=50,
        )

        self.assertEqual(sync_log.events_processed, 100)
        self.assertEqual(sync_log.events_created, 10)
        self.assertEqual(sync_log.busy_blocks_created, 15)
        self.assertEqual(sync_log.api_calls_made, 50)

    def test_cleanup_old_logs(self):
        """Test cleanup of old sync logs"""
        # Create old log
        old_log = SyncLog.objects.create(
            calendar_account=self.account, sync_type="full"
        )
        old_log.started_at = timezone.now() - timedelta(days=40)
        old_log.save()

        # Create recent log
        recent_log = SyncLog.objects.create(
            calendar_account=self.account, sync_type="incremental"
        )

        # Run cleanup for 30 days
        deleted_count = SyncLog.cleanup_old_logs(days_to_keep=30)

        self.assertEqual(deleted_count, 1)
        self.assertFalse(SyncLog.objects.filter(id=old_log.id).exists())
        self.assertTrue(SyncLog.objects.filter(id=recent_log.id).exists())

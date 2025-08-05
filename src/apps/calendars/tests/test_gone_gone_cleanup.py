"""
Test for 'Gone Gone' cleanup policy when toggling calendar sync off

Tests that the bidirectional cleanup completely removes all sync relationships.
"""

from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from apps.calendars.models import Calendar, CalendarAccount, EventState
from apps.calendars.services.calendar_service import CalendarService
from apps.accounts.models import UserProfile

User = get_user_model()


class GoneGoneCleanupTest(TestCase):
    """Test the 'Gone Gone' cleanup policy"""

    def setUp(self):
        """Set up test data with multiple calendars and cross-calendar busy blocks"""
        # Create test user
        self.user = User.objects.create_user(
            username="gonetest",
            email="gonetest@example.com", 
            password="testpass123"
        )
        
        # Create user profile
        self.profile = UserProfile.objects.create(
            user=self.user,
            sync_enabled=True,
        )
        
        # Create calendar account
        self.account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="gonetest@example.com",
            email="gonetest@example.com",
            access_token="encrypted_token",
            refresh_token="encrypted_refresh", 
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )
        
        # Create three calendars
        self.calendar1 = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal1_gone_test",
            name="Work Calendar",
            sync_enabled=True,
        )
        
        self.calendar2 = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal2_gone_test",
            name="Personal Calendar", 
            sync_enabled=True,
        )
        
        self.calendar3 = Calendar.objects.create(
            calendar_account=self.account,
            google_calendar_id="cal3_gone_test",
            name="Family Calendar",
            sync_enabled=True,
        )
        
        # Create test events and busy blocks
        self._create_test_events_and_busy_blocks()

    def _create_test_events_and_busy_blocks(self):
        """Create test events and cross-calendar busy blocks"""
        now = timezone.now()
        
        # Create user events in calendar1
        self.event1 = EventState.create_user_event(
            calendar=self.calendar1,
            google_event_id="event1_google_id",
            title="Work Meeting",
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
        )
        self.event1.mark_synced("event1_google_id")
        
        self.event2 = EventState.create_user_event(
            calendar=self.calendar1,
            google_event_id="event2_google_id",
            title="Project Review", 
            start_time=now + timedelta(hours=3),
            end_time=now + timedelta(hours=4),
        )
        self.event2.mark_synced("event2_google_id")
        
        # Create user event in calendar2
        self.event3 = EventState.create_user_event(
            calendar=self.calendar2,
            google_event_id="event3_google_id",
            title="Doctor Appointment",
            start_time=now + timedelta(hours=5),
            end_time=now + timedelta(hours=6),
        )
        self.event3.mark_synced("event3_google_id")
        
        # Create busy blocks: calendar1 events → calendar2 and calendar3
        self.busy_block1_in_cal2 = EventState.create_busy_block(
            target_calendar=self.calendar2,
            source_uuid=self.event1.uuid,
            title="Work Meeting",
        )
        self.busy_block1_in_cal2.mark_synced("busy1_cal2_google_id")
        
        self.busy_block1_in_cal3 = EventState.create_busy_block(
            target_calendar=self.calendar3,
            source_uuid=self.event1.uuid,
            title="Work Meeting",
        )
        self.busy_block1_in_cal3.mark_synced("busy1_cal3_google_id")
        
        self.busy_block2_in_cal2 = EventState.create_busy_block(
            target_calendar=self.calendar2,
            source_uuid=self.event2.uuid,
            title="Project Review",
        )
        self.busy_block2_in_cal2.mark_synced("busy2_cal2_google_id")
        
        self.busy_block2_in_cal3 = EventState.create_busy_block(
            target_calendar=self.calendar3,
            source_uuid=self.event2.uuid,
            title="Project Review",
        )
        self.busy_block2_in_cal3.mark_synced("busy2_cal3_google_id")
        
        # Create busy blocks: calendar2 events → calendar1 and calendar3
        self.busy_block3_in_cal1 = EventState.create_busy_block(
            target_calendar=self.calendar1,
            source_uuid=self.event3.uuid,
            title="Doctor Appointment",
        )
        self.busy_block3_in_cal1.mark_synced("busy3_cal1_google_id")
        
        self.busy_block3_in_cal3 = EventState.create_busy_block(
            target_calendar=self.calendar3,
            source_uuid=self.event3.uuid,
            title="Doctor Appointment",
        )
        self.busy_block3_in_cal3.mark_synced("busy3_cal3_google_id")

    def _analyze_sync_state(self, description):
        """Analyze and log current sync state"""
        cal1_user_events = self.calendar1.event_states.filter(is_busy_block=False).count()
        cal1_busy_blocks = self.calendar1.event_states.filter(is_busy_block=True).count()
        
        cal2_user_events = self.calendar2.event_states.filter(is_busy_block=False).count()
        cal2_busy_blocks = self.calendar2.event_states.filter(is_busy_block=True).count()
        
        cal3_user_events = self.calendar3.event_states.filter(is_busy_block=False).count()
        cal3_busy_blocks = self.calendar3.event_states.filter(is_busy_block=True).count()
        
        # Count outbound busy blocks from calendar1
        cal1_user_uuids = list(self.calendar1.event_states.filter(is_busy_block=False).values_list('uuid', flat=True))
        outbound_busy_blocks = EventState.objects.filter(
            calendar__in=[self.calendar2, self.calendar3],
            is_busy_block=True,
            source_uuid__in=cal1_user_uuids
        ).count()
        
        print(f"\n📊 {description}:")
        print(f"   Work Calendar: {cal1_user_events} user events, {cal1_busy_blocks} busy blocks")
        print(f"   Personal Calendar: {cal2_user_events} user events, {cal2_busy_blocks} busy blocks") 
        print(f"   Family Calendar: {cal3_user_events} user events, {cal3_busy_blocks} busy blocks")
        print(f"   Outbound busy blocks from Work Calendar: {outbound_busy_blocks}")
        
        return {
            'cal1_user_events': cal1_user_events,
            'cal1_busy_blocks': cal1_busy_blocks,
            'cal2_user_events': cal2_user_events,
            'cal2_busy_blocks': cal2_busy_blocks,
            'cal3_user_events': cal3_user_events,
            'cal3_busy_blocks': cal3_busy_blocks,
            'outbound_busy_blocks': outbound_busy_blocks,
        }

    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient')
    def test_gone_gone_cleanup_policy(self, mock_client_class):
        """Test complete 'Gone Gone' cleanup when calendar sync is toggled off"""
        print("\n🎯 TESTING 'Gone Gone' CLEANUP POLICY")
        print("=" * 50)
        
        # Setup mock client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.delete_event.return_value = True
        
        # Analyze initial state
        before_stats = self._analyze_sync_state("BEFORE CLEANUP")
        
        # Verify initial setup
        self.assertEqual(before_stats['cal1_user_events'], 2)  # event1, event2
        self.assertEqual(before_stats['cal1_busy_blocks'], 1)  # busy_block3_in_cal1
        self.assertEqual(before_stats['cal2_user_events'], 1)  # event3
        self.assertEqual(before_stats['cal2_busy_blocks'], 2)  # busy_block1_in_cal2, busy_block2_in_cal2
        self.assertEqual(before_stats['cal3_user_events'], 0)  # no user events
        self.assertEqual(before_stats['cal3_busy_blocks'], 3)  # all busy blocks
        self.assertEqual(before_stats['outbound_busy_blocks'], 4)  # 2 events × 2 target calendars
        
        # Toggle calendar1 sync OFF (triggers 'Gone Gone' cleanup)
        print(f"\n🚀 Toggling {self.calendar1.name} sync OFF...")
        service = CalendarService(user=self.user)
        result = service.toggle_calendar_sync(self.calendar1.id)
        
        # Verify toggle result
        self.assertFalse(result.sync_enabled)
        self.assertTrue(result.cleanup_pending)
        print(f"   ✅ Calendar sync disabled: {result.sync_enabled}")
        print(f"   ⏳ Calendar marked for cleanup: {result.cleanup_pending}")
        
        # Simulate async cleanup execution (what the cleanup command would do)
        print(f"   🔄 Running async cleanup...")
        service._execute_gone_gone_cleanup(result)
        
        # Verify Google Calendar deletions were called
        google_delete_calls = mock_client.delete_event.call_count
        print(f"   🗑️  Google Calendar delete_event called {google_delete_calls} times")
        
        # Analyze state after cleanup
        after_stats = self._analyze_sync_state("AFTER CLEANUP")
        
        # VERIFICATION: Gone Gone Policy Requirements
        print(f"\n🏆 GONE GONE POLICY VERIFICATION:")
        
        # Requirement 1: All EventState records removed from calendar1
        self.assertEqual(after_stats['cal1_user_events'], 0, 
                        "Calendar1 should have zero user events after cleanup")
        self.assertEqual(after_stats['cal1_busy_blocks'], 0,
                        "Calendar1 should have zero busy blocks after cleanup")
        print("   ✅ Local cleanup: All EventState records removed from toggled calendar")
        
        # Requirement 2: All outbound busy blocks removed from other calendars
        self.assertEqual(after_stats['outbound_busy_blocks'], 0,
                        "No busy blocks from calendar1 should remain in other calendars")
        print("   ✅ Outbound cleanup: All busy blocks removed from other calendars")
        
        # Requirement 3: Google Calendar deletions called for each outbound busy block
        expected_google_deletes = before_stats['outbound_busy_blocks']
        self.assertEqual(google_delete_calls, expected_google_deletes,
                        f"Expected {expected_google_deletes} Google deletions, got {google_delete_calls}")
        print(f"   ✅ Google cleanup: {google_delete_calls} busy blocks deleted from Google Calendar")
        
        # Requirement 4: Other calendars' user events preserved
        self.assertEqual(after_stats['cal2_user_events'], before_stats['cal2_user_events'],
                        "Calendar2 user events should be unchanged")
        self.assertEqual(after_stats['cal3_user_events'], before_stats['cal3_user_events'],
                        "Calendar3 user events should be unchanged")
        print("   ✅ Preservation: Other calendars' user events unchanged")
        
        # Requirement 5: Verify specific busy blocks were removed
        # Calendar2 should have lost 2 busy blocks (from calendar1)
        expected_cal2_busy_after = before_stats['cal2_busy_blocks'] - 2
        self.assertEqual(after_stats['cal2_busy_blocks'], expected_cal2_busy_after,
                        f"Calendar2 should have {expected_cal2_busy_after} busy blocks after cleanup")
        
        # Calendar3 should have lost 2 busy blocks (from calendar1)
        expected_cal3_busy_after = before_stats['cal3_busy_blocks'] - 2
        self.assertEqual(after_stats['cal3_busy_blocks'], expected_cal3_busy_after,
                        f"Calendar3 should have {expected_cal3_busy_after} busy blocks after cleanup")
        
        # Summary verification
        total_busy_blocks_removed = (before_stats['cal2_busy_blocks'] - after_stats['cal2_busy_blocks'] +
                                   before_stats['cal3_busy_blocks'] - after_stats['cal3_busy_blocks'])
        print(f"   📊 Summary: {total_busy_blocks_removed} busy blocks removed across other calendars")
        
        # Final validation: Calendar1 is completely isolated
        remaining_calendar1_relationships = EventState.objects.filter(
            calendar=self.calendar1
        ).count()
        self.assertEqual(remaining_calendar1_relationships, 0,
                        "Calendar1 should have no remaining EventState relationships")
        
        remaining_outbound_relationships = EventState.objects.filter(
            source_uuid__in=[self.event1.uuid, self.event2.uuid]
        ).count()
        self.assertEqual(remaining_outbound_relationships, 0,
                        "No EventState records should reference calendar1's events")
        
        print("\n" + "=" * 50)
        print("🎉 'GONE GONE' POLICY TEST: PASSED")
        print("✅ Complete bidirectional cleanup verified")
        print("✅ Calendar is completely isolated from sync system")
        print("✅ Ready for clean re-enablement")

    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient')
    def test_gone_gone_policy_isolation(self, mock_client_class):
        """Test that 'Gone Gone' cleanup creates complete isolation"""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.delete_event.return_value = True
        
        # Record original UUIDs
        original_event1_uuid = self.event1.uuid
        original_event2_uuid = self.event2.uuid
        
        # Toggle calendar1 off
        service = CalendarService(user=self.user)
        result = service.toggle_calendar_sync(self.calendar1.id)
        
        # Simulate async cleanup execution (what the cleanup command would do)
        service._execute_gone_gone_cleanup(result)
        
        # Verify complete isolation: No EventState records reference the original events
        orphaned_busy_blocks = EventState.objects.filter(
            source_uuid__in=[original_event1_uuid, original_event2_uuid]
        )
        self.assertEqual(orphaned_busy_blocks.count(), 0,
                        "No EventState records should reference deleted events")
        
        # Verify calendar1 has clean slate
        calendar1_events = EventState.objects.filter(calendar=self.calendar1)
        self.assertEqual(calendar1_events.count(), 0,
                        "Calendar1 should have completely clean EventState slate")
        
        print("✅ Complete isolation verified - calendar is 'gone gone'")

    @patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient')
    def test_gone_gone_preserves_other_relationships(self, mock_client_class):
        """Test that 'Gone Gone' cleanup preserves unrelated sync relationships"""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.delete_event.return_value = True
        
        # Record pre-cleanup state of calendar2 → calendar3 relationship
        cal2_to_cal3_busy_blocks_before = EventState.objects.filter(
            calendar=self.calendar3,
            source_uuid=self.event3.uuid,  # event3 is from calendar2
            is_busy_block=True
        ).count()
        
        # Toggle calendar1 off
        service = CalendarService(user=self.user)
        service.toggle_calendar_sync(self.calendar1.id)
        
        # Verify calendar2 → calendar3 relationship preserved
        cal2_to_cal3_busy_blocks_after = EventState.objects.filter(
            calendar=self.calendar3,
            source_uuid=self.event3.uuid,
            is_busy_block=True
        ).count()
        
        self.assertEqual(cal2_to_cal3_busy_blocks_before, cal2_to_cal3_busy_blocks_after,
                        "Calendar2 → Calendar3 relationship should be preserved")
        
        # Verify calendar2's user event is preserved
        cal2_user_events = EventState.objects.filter(
            calendar=self.calendar2,
            is_busy_block=False
        ).count()
        self.assertEqual(cal2_user_events, 1, "Calendar2 user events should be preserved")
        
        print("✅ Unrelated sync relationships preserved during cleanup")
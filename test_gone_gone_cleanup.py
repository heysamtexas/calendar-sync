#!/usr/bin/env python
"""
Test script for "Gone Gone" cleanup policy

Tests that toggling a calendar off completely removes all sync relationships:
1. Deletes all EventState records for the calendar
2. Removes busy blocks created by this calendar in other calendars
3. Deletes those busy blocks from Google Calendar
4. Verifies complete isolation from sync system
"""

import os
import sys
import django
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "calendar_bridge.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from unittest.mock import MagicMock, patch

from apps.calendars.models import Calendar, CalendarAccount, EventState
from apps.calendars.services.calendar_service import CalendarService
from apps.accounts.models import UserProfile

User = get_user_model()


def setup_test_data():
    """Set up test user with multiple calendars and events"""
    print("🔧 Setting up test data...")
    
    # Clean up any existing test data
    User.objects.filter(email="gonetest@example.com").delete()
    
    # Create test user
    user = User.objects.create_user(
        username="gonetest",
        email="gonetest@example.com",
        password="testpass123"
    )
    
    # Create user profile
    profile = UserProfile.objects.create(
        user=user,
        sync_enabled=True,
    )
    
    # Create calendar account
    account = CalendarAccount.objects.create(
        user=user,
        google_account_id="gonetest@example.com",
        email="gonetest@example.com",
        access_token="encrypted_token",
        refresh_token="encrypted_refresh",
        token_expires_at=timezone.now() + timedelta(hours=1),
        is_active=True,
    )
    
    # Create three calendars
    calendar1 = Calendar.objects.create(
        calendar_account=account,
        google_calendar_id="cal1_gone_test",
        name="Work Calendar",
        sync_enabled=True,
    )
    
    calendar2 = Calendar.objects.create(
        calendar_account=account,
        google_calendar_id="cal2_gone_test", 
        name="Personal Calendar",
        sync_enabled=True,
    )
    
    calendar3 = Calendar.objects.create(
        calendar_account=account,
        google_calendar_id="cal3_gone_test",
        name="Family Calendar", 
        sync_enabled=True,
    )
    
    return user, account, calendar1, calendar2, calendar3


def create_test_events(calendar1, calendar2, calendar3):
    """Create test events and busy blocks between calendars"""
    print("📅 Creating test events and busy blocks...")
    
    now = timezone.now()
    
    # Create user events in calendar1
    event1 = EventState.create_user_event(
        calendar=calendar1,
        google_event_id="event1_google_id",
        title="Work Meeting",
        start_time=now + timedelta(hours=1),
        end_time=now + timedelta(hours=2),
    )
    event1.mark_synced("event1_google_id")
    
    event2 = EventState.create_user_event(
        calendar=calendar1,
        google_event_id="event2_google_id", 
        title="Project Review",
        start_time=now + timedelta(hours=3),
        end_time=now + timedelta(hours=4),
    )
    event2.mark_synced("event2_google_id")
    
    # Create user events in calendar2
    event3 = EventState.create_user_event(
        calendar=calendar2,
        google_event_id="event3_google_id",
        title="Doctor Appointment",
        start_time=now + timedelta(hours=5),
        end_time=now + timedelta(hours=6),
    )
    event3.mark_synced("event3_google_id")
    
    # Create busy blocks: calendar1 events → calendar2 and calendar3
    busy_block1_in_cal2 = EventState.create_busy_block(
        target_calendar=calendar2,
        source_uuid=event1.uuid,
        title="Work Meeting",
    )
    busy_block1_in_cal2.mark_synced("busy1_cal2_google_id")
    
    busy_block1_in_cal3 = EventState.create_busy_block(
        target_calendar=calendar3,
        source_uuid=event1.uuid,
        title="Work Meeting",
    )
    busy_block1_in_cal3.mark_synced("busy1_cal3_google_id")
    
    busy_block2_in_cal2 = EventState.create_busy_block(
        target_calendar=calendar2,
        source_uuid=event2.uuid,
        title="Project Review",
    )
    busy_block2_in_cal2.mark_synced("busy2_cal2_google_id")
    
    busy_block2_in_cal3 = EventState.create_busy_block(
        target_calendar=calendar3,
        source_uuid=event2.uuid,
        title="Project Review", 
    )
    busy_block2_in_cal3.mark_synced("busy2_cal3_google_id")
    
    # Create busy blocks: calendar2 events → calendar1 and calendar3
    busy_block3_in_cal1 = EventState.create_busy_block(
        target_calendar=calendar1,
        source_uuid=event3.uuid,
        title="Doctor Appointment",
    )
    busy_block3_in_cal1.mark_synced("busy3_cal1_google_id")
    
    busy_block3_in_cal3 = EventState.create_busy_block(
        target_calendar=calendar3,
        source_uuid=event3.uuid,
        title="Doctor Appointment",
    )
    busy_block3_in_cal3.mark_synced("busy3_cal3_google_id")
    
    return [event1, event2, event3], [
        busy_block1_in_cal2, busy_block1_in_cal3,
        busy_block2_in_cal2, busy_block2_in_cal3,
        busy_block3_in_cal1, busy_block3_in_cal3
    ]


def analyze_before_cleanup(calendar1, calendar2, calendar3):
    """Analyze sync state before cleanup"""
    print("\n📊 BEFORE CLEANUP - Sync State Analysis:")
    
    # Count events in each calendar
    cal1_user_events = calendar1.event_states.filter(is_busy_block=False).count()
    cal1_busy_blocks = calendar1.event_states.filter(is_busy_block=True).count()
    
    cal2_user_events = calendar2.event_states.filter(is_busy_block=False).count()
    cal2_busy_blocks = calendar2.event_states.filter(is_busy_block=True).count()
    
    cal3_user_events = calendar3.event_states.filter(is_busy_block=False).count()
    cal3_busy_blocks = calendar3.event_states.filter(is_busy_block=True).count()
    
    print(f"   🗓️  {calendar1.name}: {cal1_user_events} user events, {cal1_busy_blocks} busy blocks")
    print(f"   🗓️  {calendar2.name}: {cal2_user_events} user events, {cal2_busy_blocks} busy blocks")
    print(f"   🗓️  {calendar3.name}: {cal3_user_events} user events, {cal3_busy_blocks} busy blocks")
    
    # Count busy blocks created by calendar1 in other calendars
    cal1_user_uuids = list(calendar1.event_states.filter(is_busy_block=False).values_list('uuid', flat=True))
    outbound_busy_blocks = EventState.objects.filter(
        calendar__in=[calendar2, calendar3],
        is_busy_block=True,
        source_uuid__in=cal1_user_uuids
    ).count()
    
    print(f"   🔗 Outbound busy blocks from {calendar1.name}: {outbound_busy_blocks}")
    
    return {
        'cal1_user_events': cal1_user_events,
        'cal1_busy_blocks': cal1_busy_blocks,
        'cal2_user_events': cal2_user_events,
        'cal2_busy_blocks': cal2_busy_blocks,
        'cal3_user_events': cal3_user_events,
        'cal3_busy_blocks': cal3_busy_blocks,
        'outbound_busy_blocks': outbound_busy_blocks,
    }


def test_gone_gone_cleanup(user, calendar1):
    """Test the 'Gone Gone' cleanup when toggling calendar off"""
    print(f"\n🚀 TESTING 'Gone Gone' cleanup for {calendar1.name}...")
    
    # Mock Google Calendar client to avoid API calls
    with patch('apps.calendars.services.google_calendar_client.GoogleCalendarClient') as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.delete_event.return_value = True  # Simulate successful deletion
        
        # Initialize service and toggle calendar off
        service = CalendarService(user=user)
        
        print(f"   ⚡ Toggling {calendar1.name} sync OFF...")
        result = service.toggle_calendar_sync(calendar1.id)
        
        print(f"   ✅ Toggle result: sync_enabled = {result.sync_enabled}")
        
        # Verify Google Calendar delete_event was called
        delete_calls = mock_client.delete_event.call_count
        print(f"   🗑️  Google Calendar delete_event called {delete_calls} times")
        
        return delete_calls


def analyze_after_cleanup(calendar1, calendar2, calendar3, before_stats):
    """Analyze sync state after cleanup"""
    print("\n📊 AFTER CLEANUP - Sync State Analysis:")
    
    # Refresh calendars from database
    calendar1.refresh_from_db()
    calendar2.refresh_from_db()
    calendar3.refresh_from_db()
    
    # Count events in each calendar
    cal1_user_events = calendar1.event_states.filter(is_busy_block=False).count()
    cal1_busy_blocks = calendar1.event_states.filter(is_busy_block=True).count()
    
    cal2_user_events = calendar2.event_states.filter(is_busy_block=False).count()
    cal2_busy_blocks = calendar2.event_states.filter(is_busy_block=True).count()
    
    cal3_user_events = calendar3.event_states.filter(is_busy_block=False).count()
    cal3_busy_blocks = calendar3.event_states.filter(is_busy_block=True).count()
    
    print(f"   🗓️  {calendar1.name}: {cal1_user_events} user events, {cal1_busy_blocks} busy blocks")
    print(f"   🗓️  {calendar2.name}: {cal2_user_events} user events, {cal2_busy_blocks} busy blocks")
    print(f"   🗓️  {calendar3.name}: {cal3_user_events} user events, {cal3_busy_blocks} busy blocks")
    
    # Count remaining busy blocks that were created by calendar1
    cal1_user_uuids = list(calendar1.event_states.filter(is_busy_block=False).values_list('uuid', flat=True))
    remaining_outbound = EventState.objects.filter(
        calendar__in=[calendar2, calendar3],
        is_busy_block=True,
        source_uuid__in=cal1_user_uuids
    ).count()
    
    print(f"   🔗 Remaining outbound busy blocks from {calendar1.name}: {remaining_outbound}")
    
    return {
        'cal1_user_events': cal1_user_events,
        'cal1_busy_blocks': cal1_busy_blocks,
        'cal2_user_events': cal2_user_events,
        'cal2_busy_blocks': cal2_busy_blocks,
        'cal3_user_events': cal3_user_events,
        'cal3_busy_blocks': cal3_busy_blocks,
        'remaining_outbound': remaining_outbound,
    }


def verify_gone_gone_policy(before_stats, after_stats, google_deletes):
    """Verify that 'Gone Gone' policy was properly executed"""
    print("\n🏆 GONE GONE POLICY VERIFICATION:")
    
    success = True
    
    # Check 1: Calendar1 should have zero events (local cleanup)
    if after_stats['cal1_user_events'] == 0 and after_stats['cal1_busy_blocks'] == 0:
        print("   ✅ Local cleanup: All EventState records removed from toggled calendar")
    else:
        print("   ❌ Local cleanup: EventState records still exist in toggled calendar")
        success = False
    
    # Check 2: No outbound busy blocks should remain (bidirectional cleanup)
    if after_stats['remaining_outbound'] == 0:
        print("   ✅ Outbound cleanup: All busy blocks removed from other calendars")
    else:
        print("   ❌ Outbound cleanup: Busy blocks still exist in other calendars")
        success = False
    
    # Check 3: Google Calendar deletes should have been called
    expected_deletes = before_stats['outbound_busy_blocks']
    if google_deletes == expected_deletes:
        print(f"   ✅ Google cleanup: {google_deletes} busy blocks deleted from Google Calendar")
    else:
        print(f"   ❌ Google cleanup: Expected {expected_deletes} deletes, got {google_deletes}")
        success = False
    
    # Check 4: Other calendars' user events should be unchanged
    if (after_stats['cal2_user_events'] == before_stats['cal2_user_events'] and
        after_stats['cal3_user_events'] == before_stats['cal3_user_events']):
        print("   ✅ Preservation: Other calendars' user events unchanged")
    else:
        print("   ❌ Preservation: Other calendars' user events were affected")
        success = False
        
    # Calculate busy blocks removed from cal2 and cal3
    cal2_busy_removed = before_stats['cal2_busy_blocks'] - after_stats['cal2_busy_blocks']
    cal3_busy_removed = before_stats['cal3_busy_blocks'] - after_stats['cal3_busy_blocks']
    total_busy_removed = cal2_busy_removed + cal3_busy_removed
    
    print(f"   📊 Summary: {total_busy_removed} busy blocks removed across other calendars")
    
    return success


def cleanup_test_data(user):
    """Clean up test data"""
    print("\n🧹 Cleaning up test data...")
    user.delete()
    print("   ✅ Test data cleaned up")


def main():
    """Main test execution"""
    print("🎯 TESTING 'Gone Gone' CLEANUP POLICY")
    print("=" * 50)
    
    try:
        # Setup test data
        user, account, calendar1, calendar2, calendar3 = setup_test_data()
        events, busy_blocks = create_test_events(calendar1, calendar2, calendar3)
        
        # Analyze before cleanup
        before_stats = analyze_before_cleanup(calendar1, calendar2, calendar3)
        
        # Execute 'Gone Gone' cleanup
        google_deletes = test_gone_gone_cleanup(user, calendar1)
        
        # Analyze after cleanup
        after_stats = analyze_after_cleanup(calendar1, calendar2, calendar3, before_stats)
        
        # Verify policy implementation
        policy_success = verify_gone_gone_policy(before_stats, after_stats, google_deletes)
        
        # Final verdict
        print("\n" + "=" * 50)
        if policy_success:
            print("🎉 'GONE GONE' POLICY TEST: PASSED")
            print("✅ Complete bidirectional cleanup verified")
            print("✅ Calendar is completely isolated from sync system")
            print("✅ Ready for clean re-enablement")
        else:
            print("❌ 'GONE GONE' POLICY TEST: FAILED")
            print("🚨 Cleanup implementation needs fixes")
        
        # Cleanup test data
        cleanup_test_data(user)
        
        return 0 if policy_success else 1
        
    except Exception as e:
        print(f"\n❌ TEST EXECUTION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
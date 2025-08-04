# TASK GT-02: Integration Tests First
## *"Integration tests catch real problems and guide architecture"*

### Priority: HIGH - CORE TESTING
### Estimated Time: 3-4 hours  
### Dependencies: GT-01 (Test Infrastructure Foundation)
### Status: Ready for Implementation

---

## Problem Statement

Our current approach writes unit tests first, then tries to piece together integration tests as an afterthought. This is backwards according to Guilfoyle principles:

**Current Broken Approach**:
1. Write unit tests with heavy mocking
2. Mock internal services and business logic
3. Integration tests become "more mocks glued together"
4. No confidence that the actual system works end-to-end

**Guilfoyle's Correct Approach**:
1. Integration tests first - they catch real problems
2. Test complete user workflows with real objects
3. Mock only external boundaries (Google APIs)
4. Build confidence in the actual business value

---

## Acceptance Criteria

- [ ] Webhook processing integration tests with real Django flow
- [ ] Calendar synchronization tests that actually sync data
- [ ] User workflow tests from login to calendar management
- [ ] Cross-calendar busy block creation tests
- [ ] Error handling tests with real error conditions
- [ ] Performance validation for critical integration paths
- [ ] All tests mock only external APIs (Google, not internal services)
- [ ] Tests verify actual business outcomes, not method calls

---

## Implementation Steps

### Step 1: Webhook Processing Integration Tests (60 minutes)

Create `tests/integration/test_webhook_processing.py`:

```python
"""
Webhook Processing Integration Tests
Tests the complete webhook flow: HTTP request → sync engine → database changes
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch

from apps.calendars.models import Calendar, CalendarAccount, Event
from apps.webhooks.models import WebhookRequest
from tests.conftest import BaseTestCase, create_google_event_data, create_webhook_headers

class WebhookProcessingIntegrationTest(BaseTestCase):
    """Test complete webhook processing flow"""
    
    def setUp(self):
        super().setUp()
        self.account = self.create_calendar_account()
        self.calendar = self.create_calendar(
            account=self.account,
            webhook_channel_id='test-webhook-channel-123'
        )
    
    @patch('googleapiclient.discovery.build')
    def test_webhook_creates_new_events(self, mock_build):
        """Test webhook processes new events from Google"""
        # Mock Google API response with new events
        mock_service = mock_build.return_value
        mock_service.events().list().execute.return_value = {
            'items': [
                create_google_event_data(
                    id='new_event_123',
                    summary='New Meeting',
                    start={'dateTime': '2023-06-01T10:00:00Z'},
                    end={'dateTime': '2023-06-01T11:00:00Z'}
                ),
                create_google_event_data(
                    id='new_event_456',
                    summary='Another Meeting',
                    start={'dateTime': '2023-06-01T14:00:00Z'},
                    end={'dateTime': '2023-06-01T15:00:00Z'}
                )
            ],
            'nextSyncToken': 'sync_token_abc'
        }
        
        # Simulate webhook from Google
        webhook_headers = create_webhook_headers(
            resource_id=self.calendar.google_calendar_id,
            channel_id='test-webhook-channel-123'
        )
        
        response = self.client.post(
            reverse('webhooks:google_webhook'),
            **webhook_headers
        )
        
        # Verify webhook processing succeeded
        self.assertEqual(response.status_code, 200)
        
        # Verify actual business outcomes
        self.assertEqual(Event.objects.count(), 2)
        
        new_event_1 = Event.objects.get(google_event_id='new_event_123')
        self.assertEqual(new_event_1.title, 'New Meeting')
        self.assertEqual(new_event_1.calendar, self.calendar)
        
        new_event_2 = Event.objects.get(google_event_id='new_event_456')
        self.assertEqual(new_event_2.title, 'Another Meeting')
        
        # Verify webhook was logged
        webhook_request = WebhookRequest.objects.get(
            resource_id=self.calendar.google_calendar_id
        )
        self.assertEqual(webhook_request.status, 'success')
        self.assertIsNotNone(webhook_request.processed_at)
    
    @patch('googleapiclient.discovery.build')
    def test_webhook_updates_existing_events(self, mock_build):
        """Test webhook updates events that already exist"""
        # Create existing event
        existing_event = self.create_event(
            calendar=self.calendar,
            google_event_id='existing_event_789',
            title='Old Title'
        )
        
        # Mock Google API response with updated event
        mock_service = mock_build.return_value
        mock_service.events().list().execute.return_value = {
            'items': [
                create_google_event_data(
                    id='existing_event_789',
                    summary='Updated Title',  # Changed title
                    description='Updated description'
                )
            ]
        }
        
        # Send webhook
        webhook_headers = create_webhook_headers(
            resource_id=self.calendar.google_calendar_id,
            channel_id='test-webhook-channel-123'
        )
        
        response = self.client.post(
            reverse('webhooks:google_webhook'),
            **webhook_headers
        )
        
        # Verify update succeeded
        self.assertEqual(response.status_code, 200)
        
        # Verify business outcome - event was updated
        existing_event.refresh_from_db()
        self.assertEqual(existing_event.title, 'Updated Title')
        self.assertEqual(existing_event.description, 'Updated description')
        
        # Should still be only one event
        self.assertEqual(Event.objects.count(), 1)
    
    @patch('googleapiclient.discovery.build')
    def test_webhook_handles_deleted_events(self, mock_build):
        """Test webhook handles events deleted in Google"""
        # Create existing events
        event_1 = self.create_event(
            calendar=self.calendar,
            google_event_id='event_to_keep',
            title='Keep This Event'
        )
        event_2 = self.create_event(
            calendar=self.calendar,
            google_event_id='event_to_delete',
            title='Delete This Event'
        )
        
        # Mock Google API - only returns one event (other was deleted)
        mock_service = mock_build.return_value
        mock_service.events().list().execute.return_value = {
            'items': [
                create_google_event_data(
                    id='event_to_keep',
                    summary='Keep This Event'
                )
            ]
        }
        
        # Send webhook
        webhook_headers = create_webhook_headers(
            resource_id=self.calendar.google_calendar_id,
            channel_id='test-webhook-channel-123'
        )
        
        response = self.client.post(
            reverse('webhooks:google_webhook'),
            **webhook_headers
        )
        
        # Verify processing succeeded
        self.assertEqual(response.status_code, 200)
        
        # Verify business outcomes
        event_1.refresh_from_db()
        self.assertFalse(event_1.is_deleted)  # Should still exist
        
        event_2.refresh_from_db()
        self.assertTrue(event_2.is_deleted)  # Should be marked deleted
        
        # Verify only active events are returned in queries
        active_events = Event.objects.active()
        self.assertEqual(active_events.count(), 1)
        self.assertEqual(active_events.first(), event_1)
    
    def test_webhook_rejects_invalid_requests(self):
        """Test webhook properly validates incoming requests"""
        # Test missing headers
        response = self.client.post(reverse('webhooks:google_webhook'))
        self.assertEqual(response.status_code, 400)
        
        # Test invalid resource ID
        invalid_headers = create_webhook_headers(
            resource_id='unknown_calendar',
            channel_id='test-webhook-channel-123'
        )
        
        response = self.client.post(
            reverse('webhooks:google_webhook'),
            **invalid_headers
        )
        
        # Should return 200 (webhooks never fail) but log error
        self.assertEqual(response.status_code, 200)
        
        # Verify no events were processed
        self.assertEqual(Event.objects.count(), 0)
    
    @patch('googleapiclient.discovery.build')
    def test_webhook_triggers_busy_block_creation(self, mock_build):
        """Test webhook triggers cross-calendar busy block creation"""
        # Create second calendar for same user
        second_calendar = self.create_calendar(
            account=self.account,
            google_calendar_id='second_calendar_456',
            name='Work Calendar'
        )
        
        # Mock Google API response with busy event
        mock_service = mock_build.return_value
        mock_service.events().list().execute.return_value = {
            'items': [
                create_google_event_data(
                    id='busy_meeting_123',
                    summary='Important Meeting',
                    start={'dateTime': '2023-06-01T10:00:00Z'},
                    end={'dateTime': '2023-06-01T11:00:00Z'}
                )
            ]
        }
        
        # Send webhook for first calendar
        webhook_headers = create_webhook_headers(
            resource_id=self.calendar.google_calendar_id,
            channel_id='test-webhook-channel-123'
        )
        
        response = self.client.post(
            reverse('webhooks:google_webhook'),
            **webhook_headers
        )
        
        # Verify webhook succeeded
        self.assertEqual(response.status_code, 200)
        
        # Verify original event was created
        original_event = Event.objects.get(google_event_id='busy_meeting_123')
        self.assertEqual(original_event.calendar, self.calendar)
        self.assertFalse(original_event.is_busy_block)
        
        # Verify busy block was created in second calendar
        busy_blocks = Event.objects.filter(is_busy_block=True)
        self.assertEqual(busy_blocks.count(), 1)
        
        busy_block = busy_blocks.first()
        self.assertEqual(busy_block.calendar, second_calendar)
        self.assertEqual(busy_block.title, 'Busy - Important Meeting')
        self.assertEqual(busy_block.start_time, original_event.start_time)
        self.assertEqual(busy_block.end_time, original_event.end_time)

@pytest.mark.django_db
class WebhookPerformanceIntegrationTest:
    """Test webhook processing performance"""
    
    def test_webhook_processes_large_event_list(self, calendar_account, calendar, mock_google_calendar_api):
        """Test webhook can handle large number of events efficiently"""
        import time
        
        # Mock large event list (100 events)
        large_event_list = []
        for i in range(100):
            large_event_list.append(
                create_google_event_data(
                    id=f'event_{i}',
                    summary=f'Event {i}',
                    start={'dateTime': f'2023-06-{i%30+1:02d}T{i%24:02d}:00:00Z'},
                    end={'dateTime': f'2023-06-{i%30+1:02d}T{(i%24)+1:02d}:00:00Z'}
                )
            )
        
        mock_google_calendar_api.events().list().execute.return_value = {
            'items': large_event_list
        }
        
        # Update calendar with webhook channel
        calendar.webhook_channel_id = 'performance-test-channel'
        calendar.save()
        
        # Time the webhook processing
        client = Client()
        webhook_headers = create_webhook_headers(
            resource_id=calendar.google_calendar_id,
            channel_id='performance-test-channel'
        )
        
        start_time = time.time()
        response = client.post('/webhooks/google/', **webhook_headers)
        end_time = time.time()
        
        # Verify performance
        processing_time = end_time - start_time
        assert processing_time < 5.0, f"Webhook took {processing_time:.2f}s, should be <5s"
        
        # Verify all events were processed
        assert response.status_code == 200
        assert Event.objects.count() == 100
```

### Step 2: Calendar Synchronization Integration Tests (60 minutes)

Create `tests/integration/test_calendar_sync.py`:

```python
"""
Calendar Synchronization Integration Tests
Tests the complete sync flow: trigger → Google API → database updates → cross-calendar busy blocks
"""

import pytest
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch

from apps.calendars.models import Calendar, CalendarAccount, Event, SyncLog
from apps.calendars.services.sync_engine import SyncEngine
from tests.conftest import BaseTestCase, create_google_event_data

class CalendarSyncIntegrationTest(BaseTestCase):
    """Test complete calendar synchronization flow"""
    
    def setUp(self):
        super().setUp()
        self.account = self.create_calendar_account()
        self.calendar = self.create_calendar(account=self.account)
    
    @patch('googleapiclient.discovery.build')
    def test_manual_sync_creates_events_and_busy_blocks(self, mock_build):
        """Test manual sync creates events and cross-calendar busy blocks"""
        # Create second calendar for busy blocks
        work_calendar = self.create_calendar(
            account=self.account,
            google_calendar_id='work_calendar_456',
            name='Work Calendar'
        )
        
        # Mock Google API responses for both calendars
        mock_service = mock_build.return_value
        
        def mock_list_events(*args, **kwargs):
            calendar_id = kwargs.get('calendarId')
            if calendar_id == self.calendar.google_calendar_id:
                return {
                    'items': [
                        create_google_event_data(
                            id='personal_meeting_123',
                            summary='Personal Appointment',
                            start={'dateTime': '2023-06-01T10:00:00Z'},
                            end={'dateTime': '2023-06-01T11:00:00Z'}
                        )
                    ]
                }
            elif calendar_id == work_calendar.google_calendar_id:
                return {
                    'items': [
                        create_google_event_data(
                            id='work_meeting_456',
                            summary='Team Standup',
                            start={'dateTime': '2023-06-01T09:00:00Z'},
                            end={'dateTime': '2023-06-01T09:30:00Z'}
                        )
                    ]
                }
            return {'items': []}
        
        mock_service.events().list().execute.side_effect = mock_list_events
        
        # Trigger manual sync
        sync_engine = SyncEngine()
        sync_results = sync_engine.sync_all_calendars_for_user(self.user)
        
        # Verify sync completed successfully
        self.assertTrue(sync_results['success'])
        self.assertEqual(sync_results['calendars_synced'], 2)
        
        # Verify events were created
        personal_event = Event.objects.get(google_event_id='personal_meeting_123')
        self.assertEqual(personal_event.calendar, self.calendar)
        self.assertEqual(personal_event.title, 'Personal Appointment')
        self.assertFalse(personal_event.is_busy_block)
        
        work_event = Event.objects.get(google_event_id='work_meeting_456')
        self.assertEqual(work_event.calendar, work_calendar)
        self.assertEqual(work_event.title, 'Team Standup')
        self.assertFalse(work_event.is_busy_block)
        
        # Verify cross-calendar busy blocks were created
        busy_blocks = Event.objects.filter(is_busy_block=True)
        self.assertEqual(busy_blocks.count(), 2)
        
        # Personal event should create busy block in work calendar
        personal_busy_block = busy_blocks.get(
            title='Busy - Personal Appointment',
            calendar=work_calendar
        )
        self.assertEqual(personal_busy_block.start_time, personal_event.start_time)
        self.assertEqual(personal_busy_block.end_time, personal_event.end_time)
        
        # Work event should create busy block in personal calendar
        work_busy_block = busy_blocks.get(
            title='Busy - Team Standup',
            calendar=self.calendar
        )
        self.assertEqual(work_busy_block.start_time, work_event.start_time)
        self.assertEqual(work_busy_block.end_time, work_event.end_time)
        
        # Verify sync logs were created
        sync_logs = SyncLog.objects.filter(calendar_account=self.account)
        self.assertEqual(sync_logs.count(), 2)
        
        for log in sync_logs:
            self.assertEqual(log.status, 'success')
            self.assertTrue(log.events_processed > 0)
    
    @patch('googleapiclient.discovery.build')
    def test_sync_handles_google_api_errors(self, mock_build):
        """Test sync gracefully handles Google API errors"""
        from googleapiclient.errors import HttpError
        from unittest.mock import Mock
        
        # Mock Google API to return rate limit error then success
        mock_service = mock_build.return_value
        mock_response = Mock()
        mock_response.status = 429
        
        mock_service.events().list().execute.side_effect = [
            HttpError(resp=mock_response, content=b'Rate limit exceeded'),
            {
                'items': [
                    create_google_event_data(
                        id='recovered_event_123',
                        summary='Event After Retry'
                    )
                ]
            }
        ]
        
        # Trigger sync
        sync_engine = SyncEngine()
        sync_results = sync_engine.sync_specific_calendar(self.calendar.id)
        
        # Verify sync eventually succeeded despite initial error
        self.assertTrue(sync_results['success'])
        
        # Verify event was created after retry
        recovered_event = Event.objects.get(google_event_id='recovered_event_123')
        self.assertEqual(recovered_event.title, 'Event After Retry')
        
        # Verify sync log shows retry occurred
        sync_log = SyncLog.objects.get(calendar_account=self.account)
        self.assertEqual(sync_log.status, 'success')
        self.assertIn('retry', sync_log.notes.lower())
    
    @patch('googleapiclient.discovery.build')
    def test_sync_preserves_user_modifications(self, mock_build):
        """Test sync doesn't overwrite user-modified events"""
        # Create event that exists both locally and in Google
        local_event = self.create_event(
            calendar=self.calendar,
            google_event_id='shared_event_123',
            title='User Modified Title',
            description='User added description',
            user_modified=True  # Flag indicating user changed this
        )
        
        # Mock Google API with different data
        mock_service = mock_build.return_value
        mock_service.events().list().execute.return_value = {
            'items': [
                create_google_event_data(
                    id='shared_event_123',
                    summary='Google Title',  # Different from user's version
                    description='Google description'
                )
            ]
        }
        
        # Trigger sync
        sync_engine = SyncEngine()
        sync_results = sync_engine.sync_specific_calendar(self.calendar.id)
        
        # Verify sync succeeded
        self.assertTrue(sync_results['success'])
        
        # Verify user modifications were preserved
        local_event.refresh_from_db()
        self.assertEqual(local_event.title, 'User Modified Title')
        self.assertEqual(local_event.description, 'User added description')
        self.assertTrue(local_event.user_modified)
        
        # Verify sync log indicates user modifications were preserved
        sync_log = SyncLog.objects.get(calendar_account=self.account)
        self.assertIn('preserved user modifications', sync_log.notes.lower())
    
    def test_sync_respects_calendar_settings(self):
        """Test sync respects individual calendar sync settings"""
        # Create calendar with sync disabled
        disabled_calendar = self.create_calendar(
            account=self.account,
            google_calendar_id='disabled_calendar_789',
            name='Disabled Calendar',
            sync_enabled=False
        )
        
        # Trigger sync for user
        sync_engine = SyncEngine()
        sync_results = sync_engine.sync_all_calendars_for_user(self.user)
        
        # Verify only enabled calendar was synced
        self.assertEqual(sync_results['calendars_synced'], 1)
        self.assertEqual(sync_results['calendars_skipped'], 1)
        
        # Verify no events were created for disabled calendar
        disabled_events = Event.objects.filter(calendar=disabled_calendar)
        self.assertEqual(disabled_events.count(), 0)
        
        # Verify sync log only exists for enabled calendar
        sync_logs = SyncLog.objects.filter(calendar_account=self.account)
        self.assertEqual(sync_logs.count(), 1)

@pytest.mark.django_db  
class CrossCalendarBusyBlockTest:
    """Test cross-calendar busy block creation logic"""
    
    def test_busy_blocks_respect_privacy_settings(self, calendar_account):
        """Test busy blocks respect calendar privacy settings"""
        # Create private and public calendars
        private_calendar = Calendar.objects.create(
            calendar_account=calendar_account,
            google_calendar_id='private_cal',
            name='Private Calendar',
            visibility='private',
            sync_enabled=True
        )
        
        public_calendar = Calendar.objects.create(
            calendar_account=calendar_account,
            google_calendar_id='public_cal', 
            name='Public Calendar',
            visibility='public',
            sync_enabled=True
        )
        
        # Create event in private calendar
        private_event = Event.objects.create(
            calendar=private_calendar,
            google_event_id='private_event_123',
            title='Confidential Meeting',
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=1)
        )
        
        # Trigger busy block creation
        from apps.calendars.services.busy_block_service import BusyBlockService
        busy_service = BusyBlockService()
        busy_service.create_cross_calendar_busy_blocks(calendar_account.user)
        
        # Verify busy block in public calendar shows generic title
        busy_block = Event.objects.get(
            calendar=public_calendar,
            is_busy_block=True
        )
        self.assertEqual(busy_block.title, 'Busy')  # Generic title for privacy
        self.assertEqual(busy_block.description, '')  # No description
        self.assertEqual(busy_block.start_time, private_event.start_time)
        self.assertEqual(busy_block.end_time, private_event.end_time)
```

### Step 3: User Workflow Integration Tests (90 minutes)

Create `tests/integration/test_user_workflows.py`:

```python
"""
Complete User Workflow Integration Tests
Tests entire user journeys from login to calendar management
"""

import pytest
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from unittest.mock import patch

from apps.calendars.models import CalendarAccount, Calendar, Event
from tests.conftest import create_webhook_headers

class UserWorkflowIntegrationTest(TestCase):
    """Test complete user workflows"""
    
    def test_complete_new_user_onboarding_flow(self):
        """Test complete flow: register → OAuth → calendars appear → sync works"""
        client = Client()
        
        # Step 1: User registers
        user = User.objects.create_user(
            username='newuser',
            email='newuser@example.com',
            password='newpass123'
        )
        
        # Step 2: User logs in
        login_success = client.login(username='newuser', password='newpass123')
        self.assertTrue(login_success)
        
        # Step 3: User sees dashboard with no calendars
        response = client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Connect New Account')
        self.assertNotContains(response, 'calendar-row')  # No calendars yet
        
        # Step 4: User initiates OAuth flow
        response = client.get(reverse('accounts:connect'))
        self.assertEqual(response.status_code, 302)  # Redirect to Google
        
        # Step 5: OAuth callback creates account (mocked)
        with patch('apps.accounts.views.GoogleCalendarClient') as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.get_user_info.return_value = {
                'id': 'google_user_123',
                'email': 'newuser@gmail.com',
                'name': 'New User'
            }
            mock_client.list_calendars.return_value = [
                {
                    'id': 'primary',
                    'summary': 'newuser@gmail.com',
                    'primary': True,
                    'backgroundColor': '#1f4788'
                },
                {
                    'id': 'work_cal_456',
                    'summary': 'Work Calendar',
                    'primary': False,
                    'backgroundColor': '#d50000'
                }
            ]
            
            # Simulate OAuth callback
            response = client.get(
                reverse('accounts:oauth_callback'),
                {
                    'code': 'mock_auth_code',
                    'state': 'mock_state'
                }
            )
            
            # Should redirect to dashboard
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.endswith('/dashboard/'))
        
        # Step 6: Verify account and calendars were created
        account = CalendarAccount.objects.get(user=user)
        self.assertEqual(account.email, 'newuser@gmail.com')
        self.assertTrue(account.is_active)
        
        calendars = Calendar.objects.filter(calendar_account=account)
        self.assertEqual(calendars.count(), 2)
        
        primary_cal = calendars.get(google_calendar_id='primary')
        self.assertTrue(primary_cal.is_primary)
        self.assertFalse(primary_cal.sync_enabled)  # Disabled by default
        
        work_cal = calendars.get(google_calendar_id='work_cal_456')
        self.assertEqual(work_cal.name, 'Work Calendar')
        
        # Step 7: User sees calendars on dashboard
        response = client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'newuser@gmail.com')
        self.assertContains(response, 'Work Calendar')
        self.assertContains(response, 'Sync Disabled')  # Shows current state
        
        # Step 8: User enables sync for work calendar
        response = client.post(
            reverse('dashboard:toggle_calendar_sync', args=[work_cal.id]),
            HTTP_HX_REQUEST='true'  # HTMX request
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify sync was enabled
        work_cal.refresh_from_db()
        self.assertTrue(work_cal.sync_enabled)
        
        # Step 9: Manual sync creates events (mocked Google API)
        with patch('googleapiclient.discovery.build') as mock_build:
            mock_service = mock_build.return_value
            mock_service.events().list().execute.return_value = {
                'items': [
                    {
                        'id': 'work_event_123',
                        'summary': 'Team Meeting',
                        'start': {'dateTime': '2023-06-01T10:00:00Z'},
                        'end': {'dateTime': '2023-06-01T11:00:00Z'},
                        'status': 'confirmed'
                    }
                ]
            }
            
            # Trigger manual sync
            response = client.post(reverse('dashboard:global_sync'))
            self.assertEqual(response.status_code, 302)  # Redirect after sync
        
        # Step 10: Verify events appear on dashboard
        response = client.get(reverse('dashboard:index'))
        self.assertEqual(response.status_code, 200)
        
        # Should show sync statistics
        self.assertContains(response, '1 event')  # Event count
        self.assertContains(response, 'Last synced')  # Sync timestamp
        
        # Verify event was actually created
        event = Event.objects.get(google_event_id='work_event_123')
        self.assertEqual(event.title, 'Team Meeting')
        self.assertEqual(event.calendar, work_cal)
    
    def test_existing_user_adds_second_account(self):
        """Test user with existing account adds a second Google account"""
        # Create user with existing calendar account
        user = User.objects.create_user(
            username='existinguser',
            password='pass123'
        )
        
        existing_account = CalendarAccount.objects.create(
            user=user,
            google_account_id='existing_account_123',
            email='existing@gmail.com',
            is_active=True
        )
        
        existing_calendar = Calendar.objects.create(
            calendar_account=existing_account,
            google_calendar_id='existing_cal_456',
            name='Existing Calendar',
            sync_enabled=True
        )
        
        client = Client()
        client.force_login(user)
        
        # User adds second account
        with patch('apps.accounts.views.GoogleCalendarClient') as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.get_user_info.return_value = {
                'id': 'second_google_account_789',
                'email': 'work@company.com',
                'name': 'Work Account'
            }
            mock_client.list_calendars.return_value = [
                {
                    'id': 'work_primary',
                    'summary': 'work@company.com',
                    'primary': True,
                    'backgroundColor': '#d50000'
                }
            ]
            
            # Initiate second OAuth flow
            response = client.get(reverse('accounts:connect'))
            self.assertEqual(response.status_code, 302)
            
            # Complete OAuth callback
            response = client.get(
                reverse('accounts:oauth_callback'),
                {'code': 'second_auth_code', 'state': 'second_state'}
            )
            self.assertEqual(response.status_code, 302)
        
        # Verify second account was added
        accounts = CalendarAccount.objects.filter(user=user)
        self.assertEqual(accounts.count(), 2)
        
        second_account = accounts.get(email='work@company.com')
        self.assertEqual(second_account.google_account_id, 'second_google_account_789')
        
        # Verify both accounts show on dashboard
        response = client.get(reverse('dashboard:index'))
        self.assertContains(response, 'existing@gmail.com')
        self.assertContains(response, 'work@company.com')
        self.assertContains(response, '2 accounts')  # Account count
    
    def test_user_disconnects_account_workflow(self):
        """Test complete account disconnection workflow"""
        # Setup user with calendar account and events
        user = User.objects.create_user(username='user', password='pass')
        account = CalendarAccount.objects.create(
            user=user,
            google_account_id='account_to_disconnect',
            email='disconnect@gmail.com',
            is_active=True
        )
        calendar = Calendar.objects.create(
            calendar_account=account,
            google_calendar_id='cal_to_disconnect',
            name='Calendar to Disconnect'
        )
        event = Event.objects.create(
            calendar=calendar,
            google_event_id='event_123',
            title='Event to be Removed'
        )
        
        client = Client()
        client.force_login(user)
        
        # User views account details
        response = client.get(
            reverse('dashboard:account_detail', args=[account.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'disconnect@gmail.com')
        self.assertContains(response, 'Disconnect Account')
        
        # User clicks disconnect (with confirmation)
        response = client.post(
            reverse('accounts:disconnect_account', args=[account.id])
        )
        self.assertEqual(response.status_code, 302)  # Redirect after disconnect
        
        # Verify account and related data were removed
        self.assertFalse(
            CalendarAccount.objects.filter(id=account.id).exists()
        )
        self.assertFalse(
            Calendar.objects.filter(id=calendar.id).exists()
        )
        self.assertFalse(
            Event.objects.filter(id=event.id).exists()
        )
        
        # User returns to dashboard
        response = client.get(reverse('dashboard:index'))
        self.assertNotContains(response, 'disconnect@gmail.com')
        self.assertContains(response, 'Connect New Account')  # No accounts left
```

### Step 4: Error Handling and Edge Cases (45 minutes)

Add error handling tests to the integration files:

```python
# Add to test_webhook_processing.py

class WebhookErrorHandlingTest(BaseTestCase):
    """Test webhook error handling in realistic scenarios"""
    
    @patch('googleapiclient.discovery.build')
    def test_webhook_handles_google_api_timeout(self, mock_build):
        """Test webhook gracefully handles Google API timeouts"""
        from requests.exceptions import Timeout
        
        # Mock timeout on first call, success on second
        mock_service = mock_build.return_value
        mock_service.events().list().execute.side_effect = [
            Timeout("Request timed out"),
            {'items': [create_google_event_data(id='recovered_event')]}
        ]
        
        calendar = self.create_calendar(webhook_channel_id='timeout-test')
        
        # Send webhook
        response = self.client.post(
            reverse('webhooks:google_webhook'),
            **create_webhook_headers(
                resource_id=calendar.google_calendar_id,
                channel_id='timeout-test'
            )
        )
        
        # Should return 200 (webhooks never fail outright)
        self.assertEqual(response.status_code, 200)
        
        # Should have retried and eventually succeeded
        self.assertEqual(Event.objects.count(), 1)
        event = Event.objects.first()
        self.assertEqual(event.google_event_id, 'recovered_event')
    
    def test_webhook_handles_database_constraint_violations(self):
        """Test webhook handles database integrity issues gracefully"""
        calendar = self.create_calendar(webhook_channel_id='constraint-test')
        
        # Create event that will cause constraint violation
        existing_event = self.create_event(
            calendar=calendar,
            google_event_id='duplicate_event_id'
        )
        
        with patch('googleapiclient.discovery.build') as mock_build:
            mock_service = mock_build.return_value
            mock_service.events().list().execute.return_value = {
                'items': [
                    create_google_event_data(
                        id='duplicate_event_id',  # Will conflict
                        summary='Updated Event'
                    )
                ]
            }
            
            # Send webhook
            response = self.client.post(
                reverse('webhooks:google_webhook'),
                **create_webhook_headers(
                    resource_id=calendar.google_calendar_id,
                    channel_id='constraint-test'
                )
            )
            
            # Should handle gracefully
            self.assertEqual(response.status_code, 200)
            
            # Should have updated existing event instead of creating duplicate
            self.assertEqual(Event.objects.count(), 1)
            existing_event.refresh_from_db()
            self.assertEqual(existing_event.title, 'Updated Event')
```

---

## Files to Create/Modify

### New Files:
- `tests/integration/test_webhook_processing.py` - Complete webhook flow tests
- `tests/integration/test_calendar_sync.py` - Synchronization integration tests  
- `tests/integration/test_user_workflows.py` - End-to-end user journey tests
- `tests/integration/__init__.py` - Package initialization

### Integration Test Structure:
```
tests/integration/
├── __init__.py
├── test_webhook_processing.py      # Webhook → sync → database
├── test_calendar_sync.py           # Manual sync → Google API → events
├── test_user_workflows.py          # Complete user journeys
└── test_error_scenarios.py         # Error handling integration
```

---

## Validation Steps

1. **Run Integration Tests**:
   ```bash
   cd src
   pytest tests/integration/ -v --tb=short
   ```

2. **Verify Business Outcomes**:
   ```bash
   pytest tests/integration/test_webhook_processing.py::WebhookProcessingIntegrationTest::test_webhook_creates_new_events -v
   ```

3. **Test Performance**:
   ```bash
   pytest tests/integration/ -k "performance" --durations=10
   ```

4. **Validate Error Handling**:
   ```bash
   pytest tests/integration/ -k "error" -v
   ```

---

## Success Criteria

- [ ] All integration tests verify actual business outcomes
- [ ] Tests mock only external APIs (Google), never internal services
- [ ] Webhook tests verify real HTTP → database flow
- [ ] Sync tests verify real Google API → event creation flow
- [ ] User workflow tests cover complete journeys
- [ ] Error handling tests use realistic failure scenarios
- [ ] Performance tests validate acceptable response times
- [ ] Tests would fail if core features were accidentally deleted

---

## Definition of Done

- [ ] Integration tests follow all Guilfoyle principles from manifesto
- [ ] Tests verify business value, not implementation details
- [ ] All critical user workflows are covered end-to-end
- [ ] Error scenarios test realistic failure conditions
- [ ] Performance benchmarks are established for key flows
- [ ] Tests use real Django mechanisms (HTTP, database, authentication)
- [ ] Mock setup is minimal and only at external boundaries
- [ ] Tests provide confidence that the system actually works

These integration tests form the foundation of confidence in the system. They catch real problems and guide architecture decisions, exactly as Guilfoyle intended.
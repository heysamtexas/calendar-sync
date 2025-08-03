"""Tests for Google Calendar API client"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from googleapiclient.errors import HttpError

from apps.accounts.models import UserProfile
from apps.calendars.models import CalendarAccount
from apps.calendars.services.google_calendar_client import (
    GoogleCalendarClient,
    get_google_calendar_client,
    test_connection,
)


@override_settings(
    GOOGLE_OAUTH_CLIENT_ID="test_client_id",
    GOOGLE_OAUTH_CLIENT_SECRET="test_client_secret",
)
class GoogleCalendarClientTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.profile = UserProfile.objects.create(user=self.user)
        self.account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="google123",
            email="test@gmail.com",
            access_token="",
            refresh_token="",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )
        # Set test tokens
        self.account.set_access_token("test_access_token")
        self.account.set_refresh_token("test_refresh_token")
        self.account.save()

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_client_initialization(self, mock_build):
        """Test client initialization and service creation"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        client = GoogleCalendarClient(self.account)

        # Service should not be created until first use
        self.assertIsNone(client._service)

        # First call should create service
        service = client._get_service()
        self.assertEqual(service, mock_service)
        self.assertEqual(client._service, mock_service)

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_list_calendars_success(self, mock_build):
        """Test successful calendar listing"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Mock calendar list response
        mock_calendars = [
            {"id": "primary", "summary": "Primary Calendar"},
            {"id": "calendar2", "summary": "Work Calendar"},
        ]
        mock_service.calendarList().list().execute.return_value = {
            "items": mock_calendars
        }

        client = GoogleCalendarClient(self.account)
        calendars = client.list_calendars()

        self.assertEqual(calendars, mock_calendars)
        mock_service.calendarList().list().execute.assert_called()

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_list_calendars_empty(self, mock_build):
        """Test calendar listing with no calendars"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Mock empty response
        mock_service.calendarList().list().execute.return_value = {}

        client = GoogleCalendarClient(self.account)
        calendars = client.list_calendars()

        self.assertEqual(calendars, [])

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_get_calendar_success(self, mock_build):
        """Test successful calendar retrieval"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_calendar = {"id": "cal123", "summary": "Test Calendar"}
        mock_service.calendars().get().execute.return_value = mock_calendar

        client = GoogleCalendarClient(self.account)
        calendar = client.get_calendar("cal123")

        self.assertEqual(calendar, mock_calendar)
        mock_service.calendars().get.assert_called_with(calendarId="cal123")

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_get_calendar_not_found(self, mock_build):
        """Test calendar retrieval when calendar doesn't exist"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Mock 404 error
        mock_response = MagicMock()
        mock_response.status = 404
        http_error = HttpError(mock_response, b"Not Found")
        mock_service.calendars().get().execute.side_effect = http_error

        client = GoogleCalendarClient(self.account)
        calendar = client.get_calendar("nonexistent")

        self.assertIsNone(calendar)

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_list_events_success(self, mock_build):
        """Test successful event listing"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_events = [
            {"id": "event1", "summary": "Meeting 1"},
            {"id": "event2", "summary": "Meeting 2"},
        ]
        mock_service.events().list().execute.return_value = {"items": mock_events}

        client = GoogleCalendarClient(self.account)
        events = client.list_events("cal123")

        self.assertEqual(events, mock_events)
        # Verify API call was made with correct parameters
        mock_service.events().list.assert_called()
        call_args = mock_service.events().list.call_args[1]
        self.assertEqual(call_args["calendarId"], "cal123")
        self.assertEqual(call_args["maxResults"], 250)
        self.assertEqual(call_args["singleEvents"], True)
        self.assertEqual(call_args["orderBy"], "startTime")

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_list_events_with_time_range(self, mock_build):
        """Test event listing with custom time range"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.events().list().execute.return_value = {"items": []}

        client = GoogleCalendarClient(self.account)

        start_time = timezone.now()
        end_time = start_time + timedelta(days=7)

        client.list_events(
            "cal123", time_min=start_time, time_max=end_time, max_results=100
        )

        call_args = mock_service.events().list.call_args[1]
        self.assertEqual(call_args["timeMin"], start_time.isoformat())
        self.assertEqual(call_args["timeMax"], end_time.isoformat())
        self.assertEqual(call_args["maxResults"], 100)

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_create_event_success(self, mock_build):
        """Test successful event creation"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_event = {"id": "new_event_id", "summary": "New Event"}
        mock_service.events().insert().execute.return_value = mock_event

        client = GoogleCalendarClient(self.account)

        event_data = {
            "summary": "Test Event",
            "start": {"dateTime": "2023-12-01T10:00:00Z"},
            "end": {"dateTime": "2023-12-01T11:00:00Z"},
        }

        result = client.create_event("cal123", event_data)

        self.assertEqual(result, mock_event)
        # Verify the insert method was called with correct parameters
        mock_service.events().insert.assert_called_with(
            calendarId="cal123", body=event_data
        )

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_update_event_success(self, mock_build):
        """Test successful event update"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_event = {"id": "event123", "summary": "Updated Event"}
        mock_service.events().update().execute.return_value = mock_event

        client = GoogleCalendarClient(self.account)

        event_data = {"summary": "Updated Event"}
        result = client.update_event("cal123", "event123", event_data)

        self.assertEqual(result, mock_event)
        mock_service.events().update.assert_called_with(
            calendarId="cal123", eventId="event123", body=event_data
        )

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_delete_event_success(self, mock_build):
        """Test successful event deletion"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        client = GoogleCalendarClient(self.account)
        result = client.delete_event("cal123", "event123")

        self.assertTrue(result)
        mock_service.events().delete.assert_called_with(
            calendarId="cal123", eventId="event123"
        )

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_delete_event_not_found(self, mock_build):
        """Test event deletion when event doesn't exist"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Mock 404 error
        mock_response = MagicMock()
        mock_response.status = 404
        http_error = HttpError(mock_response, b"Not Found")
        mock_service.events().delete().execute.side_effect = http_error

        client = GoogleCalendarClient(self.account)
        result = client.delete_event("cal123", "nonexistent")

        # Should return True (consider missing event as successfully deleted)
        self.assertTrue(result)

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_create_busy_block(self, mock_build):
        """Test busy block creation"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_event = {"id": "busy_block_id", "summary": "🔒 Busy - Meeting"}
        mock_service.events().insert().execute.return_value = mock_event

        client = GoogleCalendarClient(self.account)

        start_time = timezone.now()
        end_time = start_time + timedelta(hours=1)

        result = client.create_busy_block(
            "cal123",
            "🔒 Busy - Meeting",
            start_time,
            end_time,
            "CalSync [source:cal1:event123]",
        )

        self.assertEqual(result, mock_event)

        # Verify the event data structure
        call_args = mock_service.events().insert.call_args[1]
        event_data = call_args["body"]
        self.assertEqual(event_data["summary"], "🔒 Busy - Meeting")
        self.assertEqual(event_data["description"], "CalSync [source:cal1:event123]")
        self.assertEqual(event_data["transparency"], "opaque")
        self.assertEqual(event_data["visibility"], "private")

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_find_system_events(self, mock_build):
        """Test finding system-created events"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_events = [
            {
                "id": "event1",
                "summary": "Regular Meeting",
                "description": "Normal event",
            },
            {"id": "event2", "summary": "🔒 Busy - CalSync Meeting", "description": ""},
            {
                "id": "event3",
                "summary": "Another Meeting",
                "description": "CalSync [source:cal1:event123]",
            },
            {"id": "event4", "summary": "Personal Event", "description": ""},
        ]
        mock_service.events().list().execute.return_value = {"items": mock_events}

        client = GoogleCalendarClient(self.account)
        system_events = client.find_system_events("cal123", "CalSync")

        # Should find events 2 and 3 (system-created)
        self.assertEqual(len(system_events), 2)
        system_event_ids = [event["id"] for event in system_events]
        self.assertIn("event2", system_event_ids)
        self.assertIn("event3", system_event_ids)

    @patch("apps.calendars.services.google_calendar_client.build")
    def test_batch_delete_events(self, mock_build):
        """Test batch deletion of multiple events"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        client = GoogleCalendarClient(self.account)
        event_ids = ["event1", "event2", "event3"]

        results = client.batch_delete_events("cal123", event_ids)

        # Should attempt to delete all events
        self.assertEqual(len(results), 3)
        for event_id in event_ids:
            self.assertTrue(results[event_id])

        # Verify correct number of delete calls
        self.assertEqual(mock_service.events().delete.call_count, 3)

    def test_factory_function(self):
        """Test factory function for creating client"""
        client = get_google_calendar_client(self.account)
        self.assertIsInstance(client, GoogleCalendarClient)
        self.assertEqual(client.account, self.account)

    @patch(
        "apps.calendars.services.google_calendar_client.GoogleCalendarClient.list_calendars"
    )
    def test_connection_test_success(self, mock_list_calendars):
        """Test successful connection testing"""
        mock_list_calendars.return_value = [{"id": "primary", "summary": "Primary"}]

        result = test_connection(self.account)
        self.assertTrue(result)
        mock_list_calendars.assert_called()

    @patch(
        "apps.calendars.services.google_calendar_client.GoogleCalendarClient.list_calendars"
    )
    def test_connection_test_failure(self, mock_list_calendars):
        """Test connection test failure"""
        mock_list_calendars.side_effect = Exception("Connection failed")

        result = test_connection(self.account)
        self.assertFalse(result)

    def test_invalid_credentials(self):
        """Test client behavior with invalid credentials"""
        # Create account with no tokens
        invalid_account = CalendarAccount.objects.create(
            user=self.user,
            google_account_id="invalid123",
            email="invalid@gmail.com",
            access_token="",
            refresh_token="",
            token_expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        client = GoogleCalendarClient(invalid_account)

        with self.assertRaises(Exception) as context:
            client._get_service()

        self.assertIn("No valid credentials", str(context.exception))

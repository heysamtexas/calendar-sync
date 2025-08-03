"""OAuth authentication views for Google Calendar integration"""

from datetime import timedelta
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from google_auth_oauthlib.flow import Flow

from apps.calendars.models import CalendarAccount


logger = logging.getLogger(__name__)

# OAuth 2.0 scope for Google Calendar
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_oauth_flow(request: HttpRequest) -> Flow:
    """Create OAuth flow with proper redirect URI"""
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [request.build_absolute_uri(reverse("accounts:auth_callback"))],
            }
        },
        scopes=SCOPES,
    )
    flow.redirect_uri = request.build_absolute_uri(reverse("accounts:auth_callback"))
    return flow


@login_required
def oauth_initiate(request: HttpRequest) -> HttpResponse:
    """Initiate OAuth flow for Google Calendar"""
    try:
        flow = get_oauth_flow(request)

        # Generate authorization URL
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",  # Force consent to get refresh token
        )

        # Store state in session for security
        request.session["oauth_state"] = state

        logger.info(f"Starting OAuth flow for user {request.user.username}")
        return redirect(authorization_url)

    except Exception as e:
        logger.error(f"OAuth initiation failed for user {request.user.username}: {e!s}")
        messages.error(
            request,
            "Unable to connect to Google Calendar. Please check your internet connection and try again. "
            "If the problem persists, verify your Google OAuth credentials in the .env file.",
        )
        return redirect("dashboard:index")


@login_required
def oauth_callback(request: HttpRequest) -> HttpResponse:
    """Handle OAuth callback from Google"""
    try:
        # Verify state parameter for security
        stored_state = request.session.get("oauth_state")
        received_state = request.GET.get("state")

        if not stored_state or stored_state != received_state:
            logger.warning(f"OAuth state mismatch for user {request.user.username}")
            messages.error(
                request,
                "Authentication failed due to a security verification error. Please try connecting your calendar again.",
            )
            # Clean up invalid state
            request.session.pop("oauth_state", None)
            return redirect("dashboard:index")

        # Check for error in callback
        if "error" in request.GET:
            error = request.GET.get("error")
            logger.warning(f"OAuth error for user {request.user.username}: {error}")
            messages.error(
                request,
                f"Google Calendar authentication was denied or failed: {error}. "
                "Please ensure you grant calendar permissions and try again.",
            )
            # Clean up session on error
            request.session.pop("oauth_state", None)
            return redirect("dashboard:index")

        # Exchange authorization code for tokens
        flow = get_oauth_flow(request)
        flow.fetch_token(authorization_response=request.build_absolute_uri())

        credentials = flow.credentials

        # Get user info from Google
        from googleapiclient.discovery import build

        service = build("calendar", "v3", credentials=credentials)

        # Get the user's primary calendar to obtain account info
        calendars_result = service.calendarList().list(maxResults=1).execute()
        calendars = calendars_result.get("items", [])

        if not calendars:
            logger.error(f"No calendars found for user {request.user.username}")
            messages.error(
                request,
                "No calendars were found in your Google account. Please ensure you have at least one calendar "
                "and that this application has permission to access your Google Calendar.",
            )
            return redirect("dashboard:index")

        # Extract account information
        primary_calendar = calendars[0]
        google_account_id = credentials.client_id  # Use client_id as account identifier
        email = primary_calendar.get("summary", "Unknown")  # Calendar name as fallback

        # Try to get actual email from calendar service
        try:
            settings_result = (
                service.settings().get(setting="primaryCalendar").execute()
            )
            email = settings_result.get("value", email)
        except Exception:
            pass  # Use fallback email

        # Calculate token expiry
        expires_at = timezone.now() + timedelta(
            seconds=credentials.expiry.timestamp() - timezone.now().timestamp()
        )

        # Create or update calendar account
        account, created = CalendarAccount.objects.update_or_create(
            user=request.user,
            google_account_id=google_account_id,
            defaults={
                "email": email,
                "token_expires_at": expires_at,
                "is_active": True,
            },
        )

        # Set encrypted tokens
        account.set_access_token(credentials.token)
        if credentials.refresh_token:
            account.set_refresh_token(credentials.refresh_token)
        account.save()

        # Clean up session
        request.session.pop("oauth_state", None)

        action = "connected" if created else "updated"
        logger.info(
            f"Successfully {action} Google account {email} for user {request.user.username}"
        )
        messages.success(
            request, f"Successfully {action} Google Calendar account: {email}"
        )

        return redirect("dashboard:index")

    except Exception as e:
        logger.error(f"OAuth callback failed for user {request.user.username}: {e!s}")
        messages.error(
            request,
            "Failed to complete Google Calendar authentication. This could be due to a network issue "
            "or invalid credentials. Please check your internet connection and try again.",
        )
        # Clean up session on exception
        request.session.pop("oauth_state", None)
        return redirect("dashboard:index")


@login_required
def disconnect_account(request: HttpRequest, account_id: int) -> HttpResponse:
    """Disconnect a Google Calendar account"""
    try:
        account = CalendarAccount.objects.get(id=account_id, user=request.user)

        email = account.email
        account.delete()

        logger.info(
            f"Disconnected Google account {email} for user {request.user.username}"
        )
        messages.success(request, f"Disconnected Google Calendar account: {email}")

    except CalendarAccount.DoesNotExist:
        logger.warning(
            f"Attempted to disconnect non-existent account {account_id} for user {request.user.username}"
        )
        messages.error(
            request,
            "The calendar account you're trying to disconnect was not found. It may have already been removed.",
        )

    except Exception as e:
        logger.error(
            f"Failed to disconnect account {account_id} for user {request.user.username}: {e!s}"
        )
        messages.error(
            request,
            "Failed to disconnect the calendar account. Please refresh the page and try again. "
            "If the problem persists, the account may need to be disconnected from your Google account settings.",
        )

    return redirect("dashboard:index")

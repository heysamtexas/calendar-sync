"""OAuth authentication views for Google Calendar integration"""

import logging
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from google_auth_oauthlib.flow import Flow

from .services import OAuthService
from apps.calendars.services import ResourceNotFoundError, ExternalServiceError

# Allow insecure transport for local development (HTTP instead of HTTPS)
if settings.DEBUG:
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

logger = logging.getLogger(__name__)

# OAuth 2.0 scopes for Google Calendar and user profile
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
]


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
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception details: {str(e)}")
        messages.error(
            request,
            f"Unable to connect to Google Calendar. Error: {str(e)}. "
            "Please verify your Google OAuth credentials and redirect URI configuration.",
        )
        return redirect("dashboard:index")


@login_required
def oauth_callback(request: HttpRequest) -> HttpResponse:
    """Handle OAuth callback from Google using service layer"""
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

        # Get user info from Google (get actual email address)
        from googleapiclient.discovery import build
        
        try:
            # Use OAuth2 API to get user profile information
            oauth2_service = build("oauth2", "v2", credentials=credentials)
            user_profile = oauth2_service.userinfo().get().execute()
            user_email = user_profile.get("email", "Unknown")
            
            # Fallback: try to get primary calendar email if OAuth2 API fails
            if user_email == "Unknown":
                calendar_service = build("calendar", "v3", credentials=credentials)
                calendars_result = calendar_service.calendarList().list().execute()
                calendars = calendars_result.get("items", [])
                
                # Find the primary calendar
                for calendar in calendars:
                    if calendar.get("primary", False):
                        user_email = calendar.get("id", "Unknown")  # Calendar ID is usually the email
                        break
                
                # Final fallback: use first calendar ID
                if user_email == "Unknown" and calendars:
                    user_email = calendars[0].get("id", "Unknown")
            
            user_info = {"email": user_email}
            
        except Exception as e:
            logger.warning(f"Failed to get user email: {e}")
            user_info = {"email": "Unknown"}

        # Use OAuth service for business logic
        oauth_service = OAuthService(request.user)
        result = oauth_service.process_oauth_callback(credentials, user_info)

        # Clean up session
        request.session.pop("oauth_state", None)

        if result["success"]:
            messages.success(request, result["message"])
            return redirect("dashboard:account_detail", account_id=result["account"].id)
        else:
            messages.error(request, result["message"])
            return redirect("dashboard:index")

    except Exception as e:
        logger.error(f"OAuth callback failed for user {request.user.username}: {e}")
        messages.error(
            request,
            "Failed to complete Google Calendar authentication. Please check your internet connection and try again.",
        )
        # Clean up session on exception
        request.session.pop("oauth_state", None)
        return redirect("dashboard:index")


@login_required
def disconnect_account(request: HttpRequest, account_id: int) -> HttpResponse:
    """Disconnect a Google Calendar account using service layer"""
    try:
        oauth_service = OAuthService(request.user)
        result = oauth_service.disconnect_account(account_id)
        
        if result["success"]:
            messages.success(request, result["message"])
        else:
            messages.error(request, result.get("message", "Failed to disconnect account"))
            
    except ResourceNotFoundError:
        messages.error(
            request,
            "The calendar account you're trying to disconnect was not found. It may have already been removed.",
        )
    except ExternalServiceError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.error(f"Unexpected error disconnecting account {account_id}: {e}")
        messages.error(
            request,
            "An unexpected error occurred. Please try again or contact support if the problem persists.",
        )

    return redirect("dashboard:index")



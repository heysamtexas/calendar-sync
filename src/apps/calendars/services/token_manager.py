"""Simplified token management for single-user calendar sync application"""

from datetime import timedelta
import logging
import time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from apps.calendars.models import CalendarAccount


logger = logging.getLogger(__name__)


class TokenManager:
    """Simple token management for single-user app - no enterprise complexity"""

    def __init__(self, calendar_account: CalendarAccount):
        self.account = calendar_account

    def get_valid_credentials(self) -> Credentials | None:
        """Get valid credentials, refreshing if needed"""
        if not self.account.is_active:
            logger.warning(f"Account {self.account.email} is inactive")
            return None

        # Create credentials object
        credentials = self._build_credentials()
        if not credentials:
            return None

        # Check if refresh needed (5 minute buffer)
        if self._needs_refresh():
            logger.info(f"Refreshing token for {self.account.email}")
            if not self._refresh_token_simple(credentials):
                return None

        return credentials

    def _build_credentials(self) -> Credentials | None:
        """Build credentials object from stored tokens"""
        try:
            access_token = self.account.get_access_token()
            refresh_token = self.account.get_refresh_token()

            if not access_token or not refresh_token:
                logger.error(f"Missing tokens for account {self.account.email}")
                return None

            credentials = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", ""),
                client_secret=getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", ""),
                scopes=["https://www.googleapis.com/auth/calendar"],
            )

            # Handle timezone for credentials.expiry (Google's library expects UTC naive)
            if self.account.token_expires_at:
                if self.account.token_expires_at.tzinfo is not None:
                    # Convert timezone-aware to UTC naive
                    credentials.expiry = self.account.token_expires_at.astimezone(
                        ZoneInfo("UTC")
                    ).replace(tzinfo=None)
                else:
                    credentials.expiry = self.account.token_expires_at

            return credentials

        except Exception as e:
            logger.error(f"Failed to build credentials for {self.account.email}: {e}")
            return None

    def _needs_refresh(self) -> bool:
        """Check if token needs refresh (5 minute buffer)"""
        if not self.account.token_expires_at:
            return True

        buffer_time = timedelta(minutes=5)
        return timezone.now() + buffer_time >= self.account.token_expires_at

    def _refresh_token_simple(self, credentials: Credentials) -> bool:
        """Simple token refresh with basic retry (no complex backoff)"""
        if not credentials.refresh_token:
            logger.error(f"No refresh token for account {self.account.email}")
            self._deactivate_account("No refresh token available")
            return False

        # Simple retry: 3 attempts with 2-second wait
        for attempt in range(3):
            try:
                logger.info(
                    f"Token refresh attempt {attempt + 1} for {self.account.email}"
                )

                request = Request()
                credentials.refresh(request)

                # Save new tokens with proper timezone handling
                self.account.set_access_token(credentials.token)

                # Ensure expiry is timezone-aware
                if credentials.expiry:
                    if credentials.expiry.tzinfo is None:
                        # If timezone-naive, assume UTC and make it timezone-aware
                        expiry_aware = timezone.make_aware(
                            credentials.expiry, ZoneInfo("UTC")
                        )
                    else:
                        expiry_aware = credentials.expiry
                    self.account.token_expires_at = expiry_aware

                self.account.save()

                logger.info(f"Successfully refreshed token for {self.account.email}")
                return True

            except RefreshError as e:
                # Check for permanent errors (don't retry these)
                if "invalid_grant" in str(e) or "unauthorized_client" in str(e):
                    logger.error(f"Permanent token error for {self.account.email}: {e}")
                    break

                logger.warning(f"Refresh attempt {attempt + 1} failed: {e}")
                if attempt < 2:  # Don't sleep on last attempt
                    time.sleep(2)  # Simple 2-second wait

            except Exception as e:
                logger.warning(
                    f"Unexpected refresh error for {self.account.email}: {e}"
                )
                if attempt < 2:
                    time.sleep(2)

        # All attempts failed
        logger.error(f"Token refresh failed for {self.account.email} after 3 attempts")
        self._deactivate_account("Token refresh failed")
        return False

    def _deactivate_account(self, reason: str):
        """Deactivate account when token refresh fails"""
        logger.error(f"Deactivating account {self.account.email}: {reason}")
        self.account.is_active = False
        self.account.save()

    def revoke_token(self) -> bool:
        """Revoke OAuth tokens (simplified - just clear local tokens)"""
        try:
            # For single-user app, just clear local tokens
            # Google tokens will expire naturally in 1 hour
            logger.info(f"Clearing tokens for {self.account.email}")

            # Clear tokens and deactivate
            self.account.set_access_token("")
            self.account.set_refresh_token("")
            self.account.is_active = False
            self.account.save()
            return True

        except Exception as e:
            logger.error(f"Token clearing failed for {self.account.email}: {e}")
            # Still try to deactivate
            self.account.is_active = False
            self.account.save()
            return False


# Utility functions for backward compatibility with existing code
def get_valid_credentials(account: CalendarAccount) -> Credentials | None:
    """Backward compatibility function"""
    manager = TokenManager(account)
    return manager.get_valid_credentials()


def revoke_token(account: CalendarAccount) -> bool:
    """Backward compatibility function"""
    manager = TokenManager(account)
    return manager.revoke_token()


def validate_all_accounts() -> dict:
    """Simple validation of all active accounts"""
    active_accounts = CalendarAccount.objects.filter(is_active=True)
    successful = 0
    failed = 0
    deactivated = []

    for account in active_accounts:
        try:
            manager = TokenManager(account)
            credentials = manager.get_valid_credentials()
            if credentials:
                successful += 1
            else:
                failed += 1
                deactivated.append(account.email)
        except Exception as e:
            logger.error(f"Error validating account {account.email}: {e}")
            failed += 1

    return {
        "total_accounts": active_accounts.count(),
        "successful_refreshes": successful,
        "failed_refreshes": failed,
        "deactivated_accounts": deactivated,
        "errors": [],
    }

"""Token management service for Google OAuth tokens"""

import logging

from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from apps.calendars.models import CalendarAccount


logger = logging.getLogger(__name__)


class TokenManager:
    """Manages OAuth token refresh and validation"""

    @staticmethod
    def get_valid_credentials(account: CalendarAccount) -> Credentials | None:
        """Get valid credentials for a calendar account, refreshing if needed"""
        try:
            # Create credentials object
            credentials = Credentials(
                token=account.get_access_token(),
                refresh_token=account.get_refresh_token(),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
                scopes=["https://www.googleapis.com/auth/calendar"],
            )

            # Set expiry time
            credentials.expiry = account.token_expires_at

            # Check if token needs refresh
            if account.is_token_expired:
                logger.info(f"Refreshing expired token for account {account.email}")

                if not credentials.refresh_token:
                    logger.error(
                        f"No refresh token available for account {account.email}"
                    )
                    account.is_active = False
                    account.save()
                    return None

                # Refresh the token
                request = Request()
                credentials.refresh(request)

                # Update stored tokens
                account.set_access_token(credentials.token)
                account.token_expires_at = credentials.expiry
                account.save()

                logger.info(f"Successfully refreshed token for account {account.email}")

            return credentials

        except Exception as e:
            logger.error(f"Token refresh failed for account {account.email}: {e!s}")
            # Deactivate account on token refresh failure
            account.is_active = False
            account.save()
            return None

    @staticmethod
    def validate_all_accounts():
        """Validate and refresh tokens for all active accounts"""
        active_accounts = CalendarAccount.objects.filter(is_active=True)

        for account in active_accounts:
            logger.info(f"Validating tokens for account {account.email}")
            credentials = TokenManager.get_valid_credentials(account)

            if not credentials:
                logger.warning(
                    f"Failed to get valid credentials for account {account.email}"
                )
            else:
                logger.info(f"Credentials valid for account {account.email}")

    @staticmethod
    def revoke_token(account: CalendarAccount) -> bool:
        """Revoke OAuth tokens for an account"""
        try:
            credentials = Credentials(
                token=account.get_access_token(),
                refresh_token=account.get_refresh_token(),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
            )

            # Revoke the credentials
            request = Request()
            credentials.revoke(request)

            logger.info(f"Successfully revoked tokens for account {account.email}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to revoke tokens for account {account.email}: {e!s}"
            )
            return False

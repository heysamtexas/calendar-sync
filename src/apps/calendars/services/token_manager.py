"""Token management service for Google OAuth tokens"""

from datetime import timedelta
import logging
import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from apps.calendars.constants import TokenConstants
from apps.calendars.models import CalendarAccount


logger = logging.getLogger(__name__)


class TokenRefreshError(Exception):
    """Exception raised when token refresh fails"""


class TokenManager:
    """Manages OAuth token refresh and validation with enhanced error handling"""

    @staticmethod
    def should_refresh_token(account: CalendarAccount) -> bool:
        """Check if token should be refreshed proactively"""
        if not account.token_expires_at:
            return True

        buffer_time = timedelta(minutes=TokenConstants.REFRESH_BUFFER_MINUTES)
        return timezone.now() + buffer_time >= account.token_expires_at

    @staticmethod
    def get_valid_credentials(account: CalendarAccount) -> Credentials | None:
        """Get valid credentials for a calendar account, refreshing if needed"""
        if not account.is_active:
            logger.warning(
                f"Account {account.email} is inactive, skipping credential validation"
            )
            return None

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

            # Check if token needs refresh (proactive refresh)
            if TokenManager.should_refresh_token(account):
                logger.info(f"Token for account {account.email} needs refresh")
                return TokenManager._refresh_token_with_retry(account, credentials)

            return credentials

        except Exception as e:
            logger.error(
                f"Failed to create credentials for account {account.email}: {e!s}"
            )
            return None

    @staticmethod
    @transaction.atomic
    def _refresh_token_with_retry(
        account: CalendarAccount, credentials: Credentials
    ) -> Credentials | None:
        """Refresh token with retry logic and exponential backoff"""
        if not credentials.refresh_token:
            logger.error(f"No refresh token available for account {account.email}")
            TokenManager._handle_refresh_failure(account, "No refresh token available")
            return None

        last_exception = None

        for attempt in range(TokenConstants.MAX_RETRY_ATTEMPTS):
            try:
                logger.info(
                    f"Token refresh attempt {attempt + 1} for account {account.email}"
                )

                # Calculate delay for exponential backoff
                if attempt > 0:
                    delay = min(
                        TokenConstants.BASE_RETRY_DELAY * (2 ** (attempt - 1)),
                        TokenConstants.MAX_RETRY_DELAY,
                    )
                    logger.info(f"Waiting {delay} seconds before retry...")
                    time.sleep(delay)

                # Attempt token refresh
                request = Request()
                credentials.refresh(request)

                # Update stored tokens with thread safety
                account.refresh_from_db()  # Get latest state
                account.set_access_token(credentials.token)
                account.token_expires_at = credentials.expiry
                account.save()

                logger.info(f"Successfully refreshed token for account {account.email}")
                return credentials

            except RefreshError as e:
                last_exception = e
                logger.warning(
                    f"Token refresh attempt {attempt + 1} failed for account {account.email}: {e}"
                )

                # If this is a permanent error, don't retry
                if "invalid_grant" in str(e) or "unauthorized_client" in str(e):
                    logger.error(
                        f"Permanent token refresh error for account {account.email}: {e}"
                    )
                    break

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Unexpected error during token refresh attempt {attempt + 1} for account {account.email}: {e}"
                )

        # All retry attempts failed
        error_msg = f"Token refresh failed after {TokenConstants.MAX_RETRY_ATTEMPTS} attempts: {last_exception}"
        logger.error(error_msg)
        TokenManager._handle_refresh_failure(account, error_msg)
        return None

    @staticmethod
    def _handle_refresh_failure(account: CalendarAccount, error_message: str):
        """Handle token refresh failure with proper cleanup and notifications"""
        logger.error(
            f"Handling refresh failure for account {account.email}: {error_message}"
        )

        # Deactivate account to prevent further API calls
        account.is_active = False
        account.save()

        # TODO: Add user notification system
        # This would integrate with Django messages or email notifications
        if TokenConstants.NOTIFY_ON_ACCOUNT_DEACTIVATION:
            logger.info(
                f"Account {account.email} deactivated due to token refresh failure"
            )
            # Future enhancement: Send notification to user

    @staticmethod
    def proactive_refresh_check(account: CalendarAccount) -> bool:
        """Check if account needs proactive token refresh and perform if needed"""
        if not account.is_active:
            return False

        if TokenManager.should_refresh_token(account):
            logger.info(
                f"Performing proactive token refresh for account {account.email}"
            )
            credentials = TokenManager.get_valid_credentials(account)
            return credentials is not None

        return True

    @staticmethod
    def validate_all_accounts() -> dict:
        """Validate and refresh tokens for all active accounts"""
        active_accounts = CalendarAccount.objects.filter(is_active=True)
        results = {
            "total_accounts": active_accounts.count(),
            "successful_refreshes": 0,
            "failed_refreshes": 0,
            "deactivated_accounts": [],
            "errors": [],
        }

        logger.info(
            f"Starting token validation for {results['total_accounts']} active accounts"
        )

        for account in active_accounts:
            try:
                logger.info(f"Validating tokens for account {account.email}")

                # Check if proactive refresh is needed
                if TokenManager.should_refresh_token(account):
                    credentials = TokenManager.get_valid_credentials(account)

                    if credentials:
                        results["successful_refreshes"] += 1
                        logger.info(
                            f"Successfully validated/refreshed credentials for account {account.email}"
                        )
                    else:
                        results["failed_refreshes"] += 1
                        results["deactivated_accounts"].append(account.email)
                        logger.warning(
                            f"Failed to validate credentials for account {account.email}"
                        )
                else:
                    logger.info(f"Token for account {account.email} is still valid")

            except Exception as e:
                error_msg = f"Unexpected error validating account {account.email}: {e}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
                results["failed_refreshes"] += 1

        logger.info(
            f"Token validation complete: {results['successful_refreshes']} successful, {results['failed_refreshes']} failed"
        )
        return results

    @staticmethod
    def background_token_refresh():
        """Background task method for proactive token refresh"""
        logger.info("Starting background token refresh task")

        # Get accounts that need proactive refresh
        buffer_time = timedelta(minutes=TokenConstants.REFRESH_BUFFER_MINUTES)
        cutoff_time = timezone.now() + buffer_time

        accounts_needing_refresh = CalendarAccount.objects.filter(
            is_active=True, token_expires_at__lte=cutoff_time
        )

        refresh_count = 0
        for account in accounts_needing_refresh:
            try:
                logger.info(f"Background refresh for account {account.email}")
                if TokenManager.proactive_refresh_check(account):
                    refresh_count += 1
                    logger.info(
                        f"Successfully refreshed token for account {account.email}"
                    )
                else:
                    logger.warning(
                        f"Background refresh failed for account {account.email}"
                    )

            except Exception as e:
                logger.error(
                    f"Error during background refresh for account {account.email}: {e}"
                )

        logger.info(
            f"Background token refresh complete: {refresh_count} tokens refreshed"
        )
        return refresh_count

    @staticmethod
    def revoke_token(account: CalendarAccount) -> bool:
        """Revoke OAuth tokens for an account with enhanced error handling"""
        try:
            access_token = account.get_access_token()
            refresh_token = account.get_refresh_token()

            if not access_token and not refresh_token:
                logger.warning(f"No tokens to revoke for account {account.email}")
                return True  # Consider this successful since there's nothing to revoke

            credentials = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
                client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
            )

            # Attempt to revoke the credentials
            request = Request()
            credentials.revoke(request)

            logger.info(f"Successfully revoked tokens for account {account.email}")

            # Clear stored tokens after successful revocation
            account.set_access_token("")
            account.set_refresh_token("")
            account.is_active = False
            account.save()

            return True

        except Exception as e:
            logger.error(f"Failed to revoke tokens for account {account.email}: {e!s}")
            # Even if revocation fails, we should clear local tokens for security
            account.set_access_token("")
            account.set_refresh_token("")
            account.is_active = False
            account.save()
            return False

    @staticmethod
    def get_token_status_summary() -> dict:
        """Get summary of token status across all accounts"""
        all_accounts = CalendarAccount.objects.all()
        active_accounts = all_accounts.filter(is_active=True)

        buffer_time = timedelta(minutes=TokenConstants.REFRESH_BUFFER_MINUTES)
        cutoff_time = timezone.now() + buffer_time

        tokens_expiring_soon = active_accounts.filter(token_expires_at__lte=cutoff_time)
        expired_tokens = active_accounts.filter(token_expires_at__lte=timezone.now())

        return {
            "total_accounts": all_accounts.count(),
            "active_accounts": active_accounts.count(),
            "inactive_accounts": all_accounts.filter(is_active=False).count(),
            "tokens_expiring_soon": tokens_expiring_soon.count(),
            "expired_tokens": expired_tokens.count(),
            "healthy_tokens": active_accounts.filter(
                token_expires_at__gt=cutoff_time
            ).count(),
        }

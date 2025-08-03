"""OAuth business logic service"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.calendars.models import CalendarAccount
from apps.calendars.services.base import (
    BaseService,
    ExternalServiceError,
    ResourceNotFoundError,
)


class OAuthService(BaseService):
    """Service for OAuth business operations"""

    def process_oauth_callback(self, credentials, user_info):
        """Process OAuth callback with transaction safety"""
        try:
            with transaction.atomic():
                # Extract account information safely
                email = self._extract_email_safely(user_info)
                expires_at = self._calculate_token_expiry(credentials)

                # Use email as the unique identifier for the Google account
                # This ensures each Google account creates a separate CalendarAccount record
                google_account_id = email

                # Create or update account
                account, created = CalendarAccount.objects.update_or_create(
                    user=self.user,
                    google_account_id=google_account_id,
                    defaults={
                        "email": email,
                        "token_expires_at": expires_at,
                        "is_active": True,
                    },
                )

                # Set encrypted tokens
                account.set_access_token(credentials.token)
                if hasattr(credentials, "refresh_token") and credentials.refresh_token:
                    account.set_refresh_token(credentials.refresh_token)
                account.save()

                # Discover calendars safely
                calendar_stats = self._discover_calendars_safely(account, credentials)

                # Log successful operation
                self._log_operation(
                    "oauth_callback_success",
                    account_id=account.id,
                    email=email,
                    created=created,
                    **calendar_stats,
                )

                # Prepare user message
                action = "connected" if created else "updated"
                if calendar_stats["calendars_created"] > 0:
                    message = (
                        f"Successfully {action} {email} and discovered "
                        f"{calendar_stats['calendars_created']} calendars. "
                        "Sync is disabled by default - enable it for calendars you want to sync."
                    )
                else:
                    message = f"Successfully {action} {email}. No calendars found."

                return {
                    "success": True,
                    "account": account,
                    "message": message,
                    "created": created,
                    **calendar_stats,
                }

        except Exception as e:
            self._handle_error(
                e, "oauth_callback", email=email if "email" in locals() else "unknown"
            )
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to connect Google Calendar account. Please try again.",
            }

    def _extract_email_safely(self, user_info):
        """Extract email from user info with fallbacks"""
        if isinstance(user_info, dict):
            return user_info.get("email", "Unknown Email")
        # Handle other user info formats
        return getattr(user_info, "email", "Unknown Email")

    def _calculate_token_expiry(self, credentials):
        """Calculate token expiry with timezone handling"""
        try:
            if hasattr(credentials, "expiry") and credentials.expiry:
                # Ensure it's a datetime object (not a mock)
                from datetime import datetime

                if isinstance(credentials.expiry, datetime):
                    if credentials.expiry.tzinfo is None:
                        # Convert naive UTC to timezone-aware
                        import zoneinfo

                        expiry_aware = timezone.make_aware(
                            credentials.expiry, zoneinfo.ZoneInfo("UTC")
                        )
                    else:
                        expiry_aware = credentials.expiry
                    return expiry_aware
        except (AttributeError, TypeError, ValueError):
            # Handle mock objects or invalid datetime values
            pass

        # Default to 1 hour from now
        return timezone.now() + timedelta(hours=1)

    def _discover_calendars_safely(self, account, credentials):
        """Discover calendars with safe defaults and error handling"""
        try:
            from googleapiclient.discovery import build

            service = build("calendar", "v3", credentials=credentials)

            all_calendars_result = service.calendarList().list().execute()
            all_calendars = all_calendars_result.get("items", [])

            # Use Calendar model for calendar creation
            from apps.calendars.models import Calendar

            calendars_created = 0
            for cal_item in all_calendars:
                calendar, cal_created = Calendar.objects.update_or_create(
                    calendar_account=account,
                    google_calendar_id=cal_item["id"],
                    defaults={
                        "name": cal_item.get("summary", "Unnamed Calendar"),
                        "is_primary": cal_item.get("primary", False),
                        "description": cal_item.get("description", ""),
                        "color": cal_item.get("backgroundColor", ""),
                        "sync_enabled": False,  # SAFE DEFAULT - require explicit opt-in
                    },
                )
                if cal_created:
                    calendars_created += 1

            return {
                "calendars_found": len(all_calendars),
                "calendars_created": calendars_created,
            }

        except Exception as e:
            self.logger.error(f"Calendar discovery failed for {account.email}: {e}")
            return {
                "calendars_found": 0,
                "calendars_created": 0,
                "discovery_error": str(e),
            }

    def disconnect_account(self, account_id):
        """Safely disconnect an OAuth account"""
        try:
            account = CalendarAccount.objects.get(id=account_id, user=self.user)

            email = account.email
            calendar_count = account.calendars.count()

            with transaction.atomic():
                # Deactivate first, then delete
                account.is_active = False
                account.save()
                account.delete()

            self._log_operation(
                "account_disconnect",
                account_id=account_id,
                email=email,
                calendar_count=calendar_count,
            )

            return {
                "success": True,
                "message": f"Disconnected {email} and removed {calendar_count} calendars.",
            }

        except CalendarAccount.DoesNotExist:
            raise ResourceNotFoundError(f"Account {account_id} not found")
        except Exception as e:
            self._handle_error(e, "account_disconnect", account_id=account_id)
            raise ExternalServiceError(f"Failed to disconnect account: {e!s}")

    def refresh_account_token(self, account_id):
        """Refresh OAuth token for an account"""
        try:
            account = CalendarAccount.objects.get(id=account_id, user=self.user)

            # Use existing token manager
            from apps.calendars.services.token_manager import TokenManager

            token_manager = TokenManager()
            success = token_manager.refresh_token(account)

            if success:
                self._log_operation(
                    "token_refresh_success",
                    account_id=account.id,
                    email=account.email,
                )
                return {"success": True, "message": "Token refreshed successfully"}
            else:
                self._log_operation(
                    "token_refresh_failed",
                    account_id=account.id,
                    email=account.email,
                )
                return {"success": False, "message": "Token refresh failed"}

        except CalendarAccount.DoesNotExist:
            raise ResourceNotFoundError(f"Account {account_id} not found")
        except Exception as e:
            self._handle_error(e, "token_refresh", account_id=account_id)
            raise ExternalServiceError(f"Token refresh failed: {e!s}")

    def get_account_status(self, account_id):
        """Get comprehensive account status information"""
        try:
            account = CalendarAccount.objects.select_related("user").get(
                id=account_id, user=self.user
            )

            status = {
                "account": account,
                "is_active": account.is_active,
                "is_token_expired": account.is_token_expired,
                "needs_refresh": getattr(
                    account, "needs_token_refresh", lambda: False
                )(),
                "calendar_count": account.calendars.count(),
                "sync_enabled_count": account.calendars.filter(
                    sync_enabled=True
                ).count(),
                "last_sync": account.sync_logs.filter(status="success")
                .order_by("-completed_at")
                .first(),
            }

            return status

        except CalendarAccount.DoesNotExist:
            raise ResourceNotFoundError(f"Account {account_id} not found")

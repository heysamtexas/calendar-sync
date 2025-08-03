"""Calendar business logic service"""

from django.db import transaction, models
from django.core.exceptions import ValidationError
from .base import BaseService, ResourceNotFoundError, BusinessLogicError, ExternalServiceError
from ..models import Calendar, CalendarAccount


class CalendarService(BaseService):
    """Service for calendar business operations"""

    def toggle_calendar_sync(self, calendar_id):
        """Toggle sync status for a calendar"""
        try:
            calendar = Calendar.objects.select_related("calendar_account").get(
                id=calendar_id
            )

            # Validate user permission
            self._validate_user_permission(calendar, "calendar_account__user")

            # Perform toggle operation
            old_status = calendar.sync_enabled
            calendar.sync_enabled = not calendar.sync_enabled
            calendar.save(update_fields=["sync_enabled"])

            # Log operation
            self._log_operation(
                "calendar_sync_toggle",
                calendar_id=calendar.id,
                calendar_name=calendar.name,
                old_status=old_status,
                new_status=calendar.sync_enabled,
            )

            return calendar

        except Calendar.DoesNotExist:
            raise ResourceNotFoundError(f"Calendar {calendar_id} not found")

    def bulk_toggle_calendars(self, calendar_ids, enable=True):
        """Toggle multiple calendars efficiently"""
        calendars = Calendar.objects.filter(
            id__in=calendar_ids, calendar_account__user=self.user
        ).select_related("calendar_account")

        if not calendars.exists():
            raise ResourceNotFoundError("No accessible calendars found")

        with transaction.atomic():
            updated_calendars = []
            for calendar in calendars:
                if calendar.sync_enabled != enable:
                    calendar.sync_enabled = enable
                    calendar.save(update_fields=["sync_enabled"])
                    updated_calendars.append(calendar)

            self._log_operation(
                "bulk_calendar_toggle",
                calendar_count=len(updated_calendars),
                enabled=enable,
            )

            return updated_calendars

    def get_user_calendar_stats(self):
        """Get calendar statistics for user"""
        stats = CalendarAccount.objects.filter(user=self.user).aggregate(
            total_accounts=models.Count("id"),
            active_accounts=models.Count("id", filter=models.Q(is_active=True)),
            total_calendars=models.Count("calendars"),
            sync_enabled_calendars=models.Count(
                "calendars", filter=models.Q(calendars__sync_enabled=True)
            ),
        )

        return stats

    def refresh_calendar_list(self, account_id):
        """Refresh calendar list for an account"""
        try:
            account = CalendarAccount.objects.get(id=account_id, user=self.user)

            if not account.is_active:
                raise BusinessLogicError("Cannot refresh calendars for inactive account")

            # Use existing GoogleCalendarClient
            from .google_calendar_client import GoogleCalendarClient

            client = GoogleCalendarClient(account)

            try:
                calendars_data = client.list_calendars()
            except Exception as e:
                raise ExternalServiceError(f"Failed to fetch calendars: {str(e)}")

            with transaction.atomic():
                calendars_created = 0
                calendars_updated = 0

                for cal_item in calendars_data:
                    calendar, created = Calendar.objects.update_or_create(
                        calendar_account=account,
                        google_calendar_id=cal_item["id"],
                        defaults={
                            "name": cal_item.get("summary", "Unnamed Calendar"),
                            "is_primary": cal_item.get("primary", False),
                            "description": cal_item.get("description", ""),
                            "color": cal_item.get("backgroundColor", ""),
                        },
                    )

                    if created:
                        calendar.sync_enabled = False  # Safe default
                        calendar.save(update_fields=["sync_enabled"])
                        calendars_created += 1
                    else:
                        calendars_updated += 1

                self._log_operation(
                    "calendar_refresh",
                    account_id=account.id,
                    calendars_found=len(calendars_data),
                    calendars_created=calendars_created,
                    calendars_updated=calendars_updated,
                )

                return {
                    "calendars_found": len(calendars_data),
                    "calendars_created": calendars_created,
                    "calendars_updated": calendars_updated,
                }

        except CalendarAccount.DoesNotExist:
            raise ResourceNotFoundError(f"Account {account_id} not found")
        except (BusinessLogicError, ExternalServiceError):
            raise
        except Exception as e:
            self._handle_error(e, "calendar_refresh", account_id=account_id)
            raise ExternalServiceError(f"Calendar refresh failed: {str(e)}")

    def get_calendar_with_stats(self, calendar_id):
        """Get calendar with event statistics"""
        try:
            calendar = (
                Calendar.objects.select_related("calendar_account")
                .annotate(
                    event_count=models.Count("events"),
                    busy_block_count=models.Count(
                        "events", filter=models.Q(events__is_busy_block=True)
                    ),
                )
                .get(id=calendar_id)
            )

            # Validate user permission
            self._validate_user_permission(calendar, "calendar_account__user")

            return calendar

        except Calendar.DoesNotExist:
            raise ResourceNotFoundError(f"Calendar {calendar_id} not found")

    def get_user_calendars_optimized(self):
        """Get all user calendars with optimized queries"""
        return (
            Calendar.objects.filter(calendar_account__user=self.user)
            .select_related("calendar_account")
            .annotate(
                event_count=models.Count("events"),
                busy_block_count=models.Count(
                    "events", filter=models.Q(events__is_busy_block=True)
                ),
            )
            .order_by("calendar_account__email", "name")
        )

    def validate_calendar_sync_requirements(self, calendar):
        """Validate if calendar can be synced"""
        if not calendar.calendar_account.is_active:
            return False, "Account is inactive"

        if calendar.calendar_account.is_token_expired:
            return False, "Token has expired"

        if not calendar.sync_enabled:
            return False, "Sync is disabled for this calendar"

        return True, "Calendar is ready for sync"
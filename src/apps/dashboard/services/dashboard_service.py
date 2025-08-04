"""Dashboard business logic service"""

from django.db import models

from apps.calendars.models import CalendarAccount, SyncLog
from apps.calendars.services.base import BaseService


class DashboardService(BaseService):
    """Service for dashboard data aggregation and business logic"""

    def get_dashboard_data(self):
        """Get all dashboard data in optimized queries"""
        # Get user profile
        from apps.accounts.models import UserProfile

        profile, created = UserProfile.objects.get_or_create(user=self.user)

        # Get calendar accounts with optimized queries
        calendar_accounts_queryset = (
            CalendarAccount.objects.filter(user=self.user)
            .select_related("user")
            .prefetch_related("sync_logs")
            .annotate(
                calendar_count=models.Count("calendars"),
                active_calendar_count=models.Count(
                    "calendars", filter=models.Q(calendars__sync_enabled=True)
                ),
            )
            .order_by("email")
        )

        # Convert to list and add last_sync for each account
        calendar_accounts = []
        for account in calendar_accounts_queryset:
            # Get the last successful sync for this account
            last_sync = account.get_last_successful_sync()
            account.last_sync = last_sync.completed_at if last_sync else None
            calendar_accounts.append(account)

        # Get recent sync logs
        recent_syncs = (
            SyncLog.objects.filter(calendar_account__user=self.user)
            .select_related("calendar_account")
            .order_by("-started_at")[:10]
        )

        # Calculate aggregated statistics
        total_calendars = sum(account.calendar_count for account in calendar_accounts)
        active_accounts = sum(1 for account in calendar_accounts if account.is_active)

        # Log dashboard access
        self._log_operation(
            "dashboard_access",
            total_accounts=len(calendar_accounts),
            total_calendars=total_calendars,
            active_accounts=active_accounts,
        )

        return {
            "profile": profile,
            "calendar_accounts": calendar_accounts,
            "recent_syncs": recent_syncs,
            "total_calendars": total_calendars,
            "active_accounts": active_accounts,
            "sync_enabled": profile.sync_enabled,
        }

    def get_account_detail_data(self, account_id):
        """Get account detail data with optimized queries"""
        from apps.calendars.models import Calendar
        from apps.calendars.services.base import ResourceNotFoundError

        try:
            # Get account with prefetched data
            account = (
                CalendarAccount.objects.select_related("user")
                .prefetch_related("sync_logs")
                .prefetch_related(
                    models.Prefetch(
                        "calendars",
                        queryset=Calendar.objects.annotate(
                            event_count=models.Count("events"),
                            busy_block_count=models.Count(
                                "events", filter=models.Q(events__is_busy_block=True)
                            ),
                        ).order_by("name"),
                    )
                )
                .get(id=account_id, user=self.user)
            )
            
            # Add last_sync attribute for template compatibility
            last_sync = account.get_last_successful_sync()
            account.last_sync = last_sync.completed_at if last_sync else None
        except CalendarAccount.DoesNotExist:
            raise ResourceNotFoundError(f"Account {account_id} not found")

        # Get sync logs for this account
        sync_logs = account.sync_logs.order_by("-started_at")[:20]

        # Access calendars from prefetched data
        calendars = account.calendars.all()

        # Log account detail access
        self._log_operation(
            "account_detail_access",
            account_id=account.id,
            calendar_count=len(calendars),
        )

        return {
            "account": account,
            "calendars": calendars,
            "sync_logs": sync_logs,
        }

    def get_sync_statistics(self):
        """Get comprehensive sync statistics for the user"""
        stats = {}

        # Recent sync activity
        recent_syncs = SyncLog.objects.filter(
            calendar_account__user=self.user
        ).order_by("-started_at")[:50]

        # Success rate calculation
        total_syncs = recent_syncs.count()
        successful_syncs = recent_syncs.filter(status="success").count()
        success_rate = (successful_syncs / total_syncs * 100) if total_syncs > 0 else 0

        # Activity by status
        status_counts = recent_syncs.values("status").annotate(count=models.Count("id"))

        # Calendar activity
        calendar_stats = CalendarAccount.objects.filter(user=self.user).aggregate(
            total_accounts=models.Count("id"),
            active_accounts=models.Count("id", filter=models.Q(is_active=True)),
            total_calendars=models.Count("calendars"),
            sync_enabled_calendars=models.Count(
                "calendars", filter=models.Q(calendars__sync_enabled=True)
            ),
        )

        stats.update(
            {
                "recent_syncs": recent_syncs[:10],  # Limit for display
                "total_syncs": total_syncs,
                "success_rate": round(success_rate, 1),
                "status_distribution": {
                    item["status"]: item["count"] for item in status_counts
                },
                **calendar_stats,
            }
        )

        return stats

    def get_health_check_data(self):
        """Get system health check information"""
        health_data = {}
        issues = []

        # Check for inactive accounts
        inactive_accounts = CalendarAccount.objects.filter(
            user=self.user, is_active=False
        ).count()
        if inactive_accounts > 0:
            issues.append(f"{inactive_accounts} inactive account(s) need attention")

        # Check for expired tokens
        expired_tokens = CalendarAccount.objects.filter(user=self.user, is_active=True)
        expired_count = sum(1 for account in expired_tokens if account.is_token_expired)
        if expired_count > 0:
            issues.append(f"{expired_count} account(s) have expired tokens")

        # Check for recent sync failures
        recent_failures = (
            SyncLog.objects.filter(calendar_account__user=self.user, status="error")
            .order_by("-started_at")[:5]
            .count()
        )
        if recent_failures > 0:
            issues.append(f"{recent_failures} recent sync failure(s)")

        # Check for calendars with sync enabled but account inactive
        orphaned_calendars = CalendarAccount.objects.filter(
            user=self.user, is_active=False
        ).aggregate(
            orphaned=models.Count(
                "calendars", filter=models.Q(calendars__sync_enabled=True)
            )
        )["orphaned"]
        if orphaned_calendars > 0:
            issues.append(
                f"{orphaned_calendars} calendar(s) enabled but account inactive"
            )

        health_data.update(
            {
                "status": "healthy" if not issues else "needs_attention",
                "issues": issues,
                "inactive_accounts": inactive_accounts,
                "expired_tokens": expired_count,
                "recent_failures": recent_failures,
                "orphaned_calendars": orphaned_calendars,
            }
        )

        return health_data

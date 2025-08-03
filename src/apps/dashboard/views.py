"""Dashboard views for calendar sync management"""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from apps.accounts.models import UserProfile
from apps.calendars.models import Calendar, CalendarAccount, SyncLog


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """Main dashboard showing connected accounts and sync status"""
    # Get or create user profile
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    # Get all calendar accounts for this user
    calendar_accounts = CalendarAccount.objects.filter(user=request.user).order_by(
        "email"
    )

    # Get recent sync logs
    recent_syncs = SyncLog.objects.filter(calendar_account__user=request.user).order_by(
        "-started_at"
    )[:10]

    # Calculate statistics
    total_calendars = Calendar.objects.filter(
        calendar_account__user=request.user
    ).count()
    active_accounts = calendar_accounts.filter(is_active=True).count()

    context = {
        "profile": profile,
        "calendar_accounts": calendar_accounts,
        "recent_syncs": recent_syncs,
        "total_calendars": total_calendars,
        "active_accounts": active_accounts,
        "sync_enabled": profile.sync_enabled,
    }

    return render(request, "dashboard/index.html", context)


@login_required
def account_detail(request: HttpRequest, account_id: int) -> HttpResponse:
    """Detailed view of a specific calendar account"""
    account = get_object_or_404(CalendarAccount, id=account_id, user=request.user)

    # Get calendars for this account
    calendars = account.calendars.all().order_by("name")

    # Get sync logs for this account
    sync_logs = account.sync_logs.order_by("-started_at")[:20]

    context = {
        "account": account,
        "calendars": calendars,
        "sync_logs": sync_logs,
    }

    return render(request, "dashboard/account_detail.html", context)

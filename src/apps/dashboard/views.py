"""Dashboard views for calendar sync management"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from apps.accounts.models import UserProfile
from apps.calendars.models import Calendar, CalendarAccount, SyncLog
from apps.calendars.services.google_calendar_client import GoogleCalendarClient

logger = logging.getLogger(__name__)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """Main dashboard showing connected accounts and sync status"""
    # Get or create user profile
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    # Get all calendar accounts with optimized queries (Query 1)
    calendar_accounts = list(
        CalendarAccount.objects.filter(user=request.user)
        .select_related("user")  # Avoid extra user query
        .annotate(
            calendar_count=models.Count("calendars"),
            active_calendar_count=models.Count(
                "calendars", filter=models.Q(calendars__sync_enabled=True)
            ),
        )
        .order_by("email")
    )

    # Get recent sync logs with calendar account data (Query 2)
    recent_syncs = (
        SyncLog.objects.filter(calendar_account__user=request.user)
        .select_related("calendar_account")  # Avoid N+1 on calendar account
        .order_by("-started_at")[:10]
    )

    # Calculate aggregated statistics using the already-fetched data
    total_calendars = sum(account.calendar_count for account in calendar_accounts)
    active_accounts = sum(1 for account in calendar_accounts if account.is_active)

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
    # Get account with prefetched data (Query 1)
    account = get_object_or_404(
        CalendarAccount.objects.select_related("user")
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
        ),
        id=account_id,
        user=request.user,
    )

    # Get sync logs for this account (Query 2)
    sync_logs = account.sync_logs.order_by("-started_at")[:20]

    # Access calendars from prefetched data (no additional query)
    calendars = account.calendars.all()

    context = {
        "account": account,
        "calendars": calendars,
        "sync_logs": sync_logs,
    }

    return render(request, "dashboard/account_detail.html", context)


@login_required
def refresh_calendars(request: HttpRequest, account_id: int) -> HttpResponse:
    """Refresh calendar list for a specific account"""
    account = get_object_or_404(CalendarAccount, id=account_id, user=request.user)
    
    if not account.is_active:
        messages.error(request, f"Cannot refresh calendars for inactive account: {account.email}")
        return redirect("dashboard:account_detail", account_id=account.id)
    
    try:
        # Create Google Calendar client
        client = GoogleCalendarClient(account)
        
        # Get all calendars from Google using the client's method
        calendars_data = client.list_calendars()
        
        if not calendars_data:
            messages.warning(request, f"No calendars found for account: {account.email}")
            return redirect("dashboard:account_detail", account_id=account.id)
        
        # Track statistics
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
                    # Keep existing sync_enabled setting, defaults applied below for new calendars
                },
            )
            
            if created:
                calendar.sync_enabled = False  # SAFE DEFAULT - require explicit opt-in
                calendar.save()
                calendars_created += 1
            else:
                calendars_updated += 1
        
        # Log the refresh operation
        logger.info(
            f"Calendar refresh for {account.email}: "
            f"{len(calendars_data)} total, {calendars_created} created, {calendars_updated} updated"
        )
        
        # Success message
        if calendars_created > 0:
            messages.success(
                request,
                f"Refreshed calendars for {account.email}: "
                f"found {len(calendars_data)} calendars, {calendars_created} new calendars added."
            )
        else:
            messages.success(
                request,
                f"Refreshed calendars for {account.email}: {len(calendars_data)} calendars found, all up to date."
            )
            
    except Exception as e:
        logger.error(f"Failed to refresh calendars for {account.email}: {e}")
        messages.error(
            request,
            f"Failed to refresh calendars for {account.email}. "
            "Please check your internet connection and try again."
        )
    
    return redirect("dashboard:account_detail", account_id=account.id)


@login_required
@require_POST
@csrf_protect
def toggle_calendar_sync(request: HttpRequest, calendar_id: int) -> HttpResponse:
    """Toggle sync status for a specific calendar"""
    # Get calendar and verify ownership - get_object_or_404 handles the 404 response
    calendar = get_object_or_404(
        Calendar, 
        id=calendar_id, 
        calendar_account__user=request.user
    )
    
    # Toggle sync status
    calendar.sync_enabled = not calendar.sync_enabled
    calendar.save(update_fields=['sync_enabled'])
    
    action = "enabled" if calendar.sync_enabled else "disabled"
    logger.info(f"Sync {action} for calendar {calendar.name} by user {request.user.username}")
    
    # Return updated sync status partial
    context = {"calendar": calendar}
    return render(request, "dashboard/partials/calendar_sync_status.html", context)

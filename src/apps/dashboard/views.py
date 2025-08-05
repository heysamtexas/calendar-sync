"""Dashboard views for calendar sync management"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from apps.calendars.services import (
    BusinessLogicError,
    CalendarService,
    ExternalServiceError,
    ResourceNotFoundError,
)

from .services import DashboardService


logger = logging.getLogger(__name__)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    """Main dashboard showing connected accounts and sync status"""
    dashboard_service = DashboardService(request.user)
    context = dashboard_service.get_dashboard_data()
    return render(request, "dashboard/index.html", context)


@login_required
def account_detail(request: HttpRequest, account_id: int) -> HttpResponse:
    """Detailed view of a specific calendar account"""
    try:
        dashboard_service = DashboardService(request.user)
        context = dashboard_service.get_account_detail_data(account_id)
        return render(request, "dashboard/account_detail.html", context)
    except ResourceNotFoundError:
        messages.error(request, "Account not found.")
        return redirect("dashboard:index")
    except PermissionDenied:
        messages.error(request, "Access denied.")
        return redirect("dashboard:index")


@login_required
def refresh_calendars(request: HttpRequest, account_id: int) -> HttpResponse:
    """Refresh calendar list for a specific account"""
    try:
        calendar_service = CalendarService(request.user)
        result = calendar_service.refresh_calendar_list(account_id)

        # Add user message based on results
        if result["calendars_created"] > 0:
            messages.success(
                request,
                f"Refreshed calendars: found {result['calendars_found']}, "
                f"added {result['calendars_created']} new calendars.",
            )
        else:
            messages.success(
                request,
                f"Refreshed calendars: {result['calendars_found']} calendars found, all up to date.",
            )

        return redirect("dashboard:account_detail", account_id=account_id)

    except ResourceNotFoundError:
        messages.error(request, "Account not found.")
        return redirect("dashboard:index")
    except BusinessLogicError as e:
        messages.error(request, str(e))
        return redirect("dashboard:account_detail", account_id=account_id)
    except ExternalServiceError as e:
        messages.error(request, f"Failed to refresh calendars: {e!s}")
        return redirect("dashboard:account_detail", account_id=account_id)


@login_required
@require_POST
@csrf_protect
def toggle_calendar_sync(request: HttpRequest, calendar_id: int) -> HttpResponse:
    """Toggle sync status for a specific calendar"""
    try:
        calendar_service = CalendarService(request.user)
        calendar = calendar_service.toggle_calendar_sync(calendar_id)

        # Return updated sync status partial
        return render(
            request,
            "dashboard/partials/calendar_sync_status.html",
            {"calendar": calendar},
        )

    except ResourceNotFoundError:
        return HttpResponse("Calendar not found", status=404)
    except PermissionDenied:
        return HttpResponse("Access denied", status=403)
    except Exception as e:
        logger.error(f"Toggle failed for calendar {calendar_id}: {e}")
        return HttpResponse("Internal error", status=500)


@login_required
@require_POST
def global_manual_sync(request: HttpRequest) -> HttpResponse:
    """Manually trigger sync for all user's calendars"""
    from apps.calendars.services.uuid_sync_engine import sync_calendar_yolo

    try:
        # Run UUID correlation sync for all user's calendars
        from apps.calendars.models import Calendar

        user_calendars = Calendar.objects.filter(
            calendar_account__user=request.user,
            sync_enabled=True,
            calendar_account__is_active=True
        )

        total_calendars = 0
        total_errors = 0

        for calendar in user_calendars:
            try:
                sync_calendar_yolo(calendar)
                total_calendars += 1
            except Exception as e:
                total_errors += 1
                logger.error(f"Manual sync failed for calendar {calendar.name}: {e}")

        if total_errors > 0:
            messages.warning(
                request,
                f"Sync completed with {total_errors} errors. Check the sync logs for details.",
            )
        else:
            messages.success(
                request,
                f"Successfully triggered sync for {total_calendars} calendars.",
            )

        return redirect("dashboard:index")

    except Exception as e:
        logger.error(f"Global manual sync failed: {e}")
        messages.error(request, "Sync failed. Please try again or check the logs.")
        return redirect("dashboard:index")

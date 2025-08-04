"""URL configuration for dashboard app"""

from django.urls import path

from . import views


app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard, name="index"),
    path("account/<int:account_id>/", views.account_detail, name="account_detail"),
    path(
        "account/<int:account_id>/refresh/",
        views.refresh_calendars,
        name="refresh_calendars",
    ),
    path(
        "calendar/<int:calendar_id>/toggle/",
        views.toggle_calendar_sync,
        name="toggle_calendar_sync",
    ),
    path("sync/", views.global_manual_sync, name="global_sync"),
]

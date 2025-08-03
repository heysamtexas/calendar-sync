"""URL configuration for dashboard app"""

from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard, name="index"),
    path("account/<int:account_id>/", views.account_detail, name="account_detail"),
]

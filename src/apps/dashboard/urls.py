"""URL configuration for dashboard app"""

from django.urls import path

from . import views


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("account/<int:account_id>/", views.account_detail, name="account_detail"),
]

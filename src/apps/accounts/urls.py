"""URL configuration for accounts app (OAuth flows)"""

from django.urls import path

from . import views


app_name = "accounts"

urlpatterns = [
    path("connect/", views.oauth_initiate, name="connect"),
    path("auth/initiate/", views.oauth_initiate, name="oauth_initiate"),
    path("auth/callback/", views.oauth_callback, name="auth_callback"),
    path(
        "auth/disconnect/<int:account_id>/",
        views.disconnect_account,
        name="disconnect_account",
    ),
]

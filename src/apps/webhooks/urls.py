from django.urls import path
from . import views

app_name = 'webhooks'

urlpatterns = [
    # Simplified webhook endpoint - receives Google Calendar notifications
    path('google/', views.GoogleWebhookView.as_view(), name='google_webhook'),
]
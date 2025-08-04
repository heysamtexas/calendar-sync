"""Django admin configuration for accounts app"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html


# Enhance the default User admin with calendar-specific info
class CalendarUserAdmin(BaseUserAdmin):
    """Enhanced User admin showing calendar sync info"""

    def get_calendar_accounts(self, obj):
        from apps.calendars.models import CalendarAccount

        accounts = CalendarAccount.objects.filter(user=obj)
        if accounts.exists():
            account_list = []
            for account in accounts:
                status = "✓ Active" if account.is_active else "✗ Inactive"
                account_list.append(f"{account.email} ({status})")
            return format_html("<br>".join(account_list))
        return "No calendar accounts"

    get_calendar_accounts.short_description = "Calendar Accounts"

    def get_sync_enabled_calendars(self, obj):
        from apps.calendars.models import Calendar

        calendars = Calendar.objects.filter(
            calendar_account__user=obj, sync_enabled=True
        )
        return calendars.count()

    get_sync_enabled_calendars.short_description = "Sync-Enabled Calendars"

    # Add calendar info to the user list view
    list_display = BaseUserAdmin.list_display + ("get_sync_enabled_calendars",)

    # Add calendar info to the user detail view
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Calendar Sync Info",
            {"fields": ("get_calendar_accounts",), "classes": ("collapse",)},
        ),
    )

    readonly_fields = BaseUserAdmin.readonly_fields + ("get_calendar_accounts",)


# Unregister the default User admin and register our enhanced version
admin.site.unregister(User)
admin.site.register(User, CalendarUserAdmin)

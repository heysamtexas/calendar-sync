"""Django admin configuration for calendar sync models"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import CalendarAccount, Calendar, Event, SyncLog


@admin.register(CalendarAccount)
class CalendarAccountAdmin(admin.ModelAdmin):
    list_display = ('email', 'user', 'is_active', 'token_expires_at', 'get_last_sync', 'created_at')
    list_filter = ('is_active', 'created_at', 'token_expires_at')
    search_fields = ('email', 'user__username', 'google_account_id')
    readonly_fields = ('google_account_id', 'created_at', 'updated_at', 'access_token', 'refresh_token', 'get_last_sync', 'get_sync_summary')
    
    fieldsets = (
        ('Account Info', {
            'fields': ('user', 'email', 'google_account_id', 'is_active')
        }),
        ('Token Info', {
            'fields': ('access_token', 'refresh_token', 'token_expires_at'),
            'classes': ('collapse',)
        }),
        ('Sync Status', {
            'fields': ('get_last_sync', 'get_sync_summary')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_last_sync(self, obj):
        from .models import SyncLog
        last_sync = SyncLog.objects.filter(calendar_account=obj).order_by('-started_at').first()
        if last_sync:
            return f"{last_sync.started_at} ({last_sync.status})"
        return "No syncs yet"
    get_last_sync.short_description = 'Last Sync'
    
    def get_sync_summary(self, obj):
        from .models import Calendar
        calendars = Calendar.objects.filter(calendar_account=obj)
        sync_enabled = calendars.filter(sync_enabled=True).count()
        total = calendars.count()
        return f"{sync_enabled}/{total} calendars sync-enabled"
    get_sync_summary.short_description = 'Sync Summary'


@admin.register(Calendar)
class CalendarAdmin(admin.ModelAdmin):
    list_display = ('name', 'calendar_account_email', 'sync_enabled', 'webhook_status', 'webhook_expires_at', 'created_at')
    list_filter = ('sync_enabled', 'created_at', 'calendar_account__is_active')
    search_fields = ('name', 'google_calendar_id', 'calendar_account__email')
    readonly_fields = ('google_calendar_id', 'created_at', 'updated_at', 'webhook_info_display')
    
    fieldsets = (
        ('Calendar Info', {
            'fields': ('name', 'google_calendar_id', 'calendar_account', 'sync_enabled')
        }),
        ('Webhook Info', {
            'fields': ('webhook_channel_id', 'webhook_expires_at', 'webhook_last_setup', 'webhook_info_display'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def calendar_account_email(self, obj):
        return obj.calendar_account.email
    calendar_account_email.short_description = 'Account Email'
    
    def webhook_status(self, obj):
        if obj.has_active_webhook():
            return format_html('<span style="color: green;">✓ Active</span>')
        elif obj.webhook_channel_id:
            return format_html('<span style="color: red;">✗ Expired</span>')
        else:
            return format_html('<span style="color: gray;">No webhook</span>')
    webhook_status.short_description = 'Webhook Status'
    
    def webhook_info_display(self, obj):
        if obj.webhook_channel_id:
            return format_html(
                '<strong>Channel:</strong> {}<br>'
                '<strong>Expires:</strong> {}<br>'
                '<strong>Last Setup:</strong> {}<br>'
                '<strong>Status:</strong> {}',
                obj.webhook_channel_id,
                obj.webhook_expires_at or 'Unknown',
                obj.webhook_last_setup or 'Unknown',
                obj.get_webhook_status()
            )
        return 'No webhook configured'
    webhook_info_display.short_description = 'Webhook Details'


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title_short', 'calendar_name', 'is_busy_block', 'is_meeting_invite', 'start_time', 'end_time', 'created_at')
    list_filter = ('is_busy_block', 'is_meeting_invite', 'is_all_day', 'calendar__name', 'created_at')
    search_fields = ('title', 'description', 'google_event_id', 'calendar__name')
    readonly_fields = ('google_event_id', 'created_at', 'updated_at', 'source_event_link', 'busy_block_tag')
    date_hierarchy = 'start_time'
    
    fieldsets = (
        ('Event Info', {
            'fields': ('title', 'description', 'calendar', 'google_event_id')
        }),
        ('Timing', {
            'fields': ('start_time', 'end_time', 'is_all_day')
        }),
        ('Type & Status', {
            'fields': ('is_busy_block', 'is_meeting_invite', 'busy_block_tag')
        }),
        ('Relationships', {
            'fields': ('source_event', 'source_event_link'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def title_short(self, obj):
        return obj.title[:50] + '...' if len(obj.title) > 50 else obj.title
    title_short.short_description = 'Title'
    
    def calendar_name(self, obj):
        return obj.calendar.name
    calendar_name.short_description = 'Calendar'
    
    def source_event_link(self, obj):
        if obj.source_event:
            url = reverse('admin:calendars_event_change', args=[obj.source_event.id])
            return format_html('<a href="{}">View Source Event</a>', url)
        return 'No source event'
    source_event_link.short_description = 'Source Event'


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ('started_at', 'calendar_account_email', 'sync_type', 'status', 'events_processed', 'duration', 'busy_blocks_summary')
    list_filter = ('sync_type', 'status', 'started_at', 'calendar_account__email')
    search_fields = ('calendar_account__email', 'error_message')
    readonly_fields = ('started_at', 'completed_at', 'duration_display', 'stats_display')
    date_hierarchy = 'started_at'
    
    fieldsets = (
        ('Sync Info', {
            'fields': ('calendar_account', 'sync_type', 'status', 'started_at', 'completed_at', 'duration_display')
        }),
        ('Statistics', {
            'fields': ('events_processed', 'stats_display')
        }),
        ('Error Info', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
    )
    
    def calendar_account_email(self, obj):
        return obj.calendar_account.email
    calendar_account_email.short_description = 'Account Email'
    
    def duration(self, obj):
        if obj.completed_at and obj.started_at:
            delta = obj.completed_at - obj.started_at
            return f"{delta.total_seconds():.1f}s"
        return 'In progress' if obj.status == 'in_progress' else 'Unknown'
    duration.short_description = 'Duration'
    
    def busy_blocks_summary(self, obj):
        return f"C:{obj.busy_blocks_created} U:{obj.busy_blocks_updated} D:{obj.busy_blocks_deleted}"
    busy_blocks_summary.short_description = 'Busy Blocks (C/U/D)'
    
    def duration_display(self, obj):
        return self.duration(obj)
    duration_display.short_description = 'Duration'
    
    def stats_display(self, obj):
        return format_html(
            '<strong>Events:</strong> Created: {}, Updated: {}, Deleted: {}<br>'
            '<strong>Busy Blocks:</strong> Created: {}, Updated: {}, Deleted: {}<br>'
            '<strong>API Calls:</strong> {}',
            obj.events_created, obj.events_updated, obj.events_deleted,
            obj.busy_blocks_created, obj.busy_blocks_updated, obj.busy_blocks_deleted,
            obj.api_calls_made
        )
    stats_display.short_description = 'Detailed Statistics'

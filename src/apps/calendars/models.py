import hashlib
import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator
from django.db import models
from django.utils import timezone

from .constants import BusyBlock, SyncConstants


logger = logging.getLogger(__name__)


class ActiveCalendarAccountManager(models.Manager):
    """Manager for active calendar accounts with complex queries"""

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)

    def with_calendar_stats(self):
        """Get accounts with calendar statistics annotated"""
        return self.get_queryset().annotate(
            calendar_count=models.Count("calendars"),
            sync_enabled_count=models.Count(
                "calendars", filter=models.Q(calendars__sync_enabled=True)
            ),
            primary_calendar_count=models.Count(
                "calendars", filter=models.Q(calendars__is_primary=True)
            ),
        )

    def requiring_token_refresh(self, buffer_minutes=5):
        """Get accounts that need token refresh"""
        from datetime import timedelta

        buffer_time = timezone.now() + timedelta(minutes=buffer_minutes)
        return self.get_queryset().filter(token_expires_at__lte=buffer_time)

    def with_recent_sync_failures(self, hours=24, failure_threshold=3):
        """Get accounts with recent sync failures"""
        cutoff_time = timezone.now() - timezone.timedelta(hours=hours)
        return (
            self.get_queryset()
            .annotate(
                recent_failures=models.Count(
                    "sync_logs",
                    filter=models.Q(
                        sync_logs__status="error",
                        sync_logs__started_at__gte=cutoff_time,
                    ),
                )
            )
            .filter(recent_failures__gte=failure_threshold)
        )


class SyncEnabledCalendarManager(models.Manager):
    """Manager for calendars that are enabled for synchronization"""

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                sync_enabled=True,
                calendar_account__is_active=True,
            )
        )

    def with_event_stats(self):
        """Get sync-enabled calendars with event statistics"""
        return self.get_queryset().annotate(
            total_events=models.Count("events"),
            busy_blocks=models.Count(
                "events", filter=models.Q(events__is_busy_block=True)
            ),
            regular_events=models.Count(
                "events", filter=models.Q(events__is_busy_block=False)
            ),
        )

    def ready_for_sync(self):
        """Get calendars that are ready for synchronization"""
        return (
            self.get_queryset()
            .filter(calendar_account__token_expires_at__gt=timezone.now())
            .select_related("calendar_account__user")
        )

    def with_recent_activity(self, days=7):
        """Get calendars with recent activity"""
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        return (
            self.get_queryset().filter(events__updated_at__gte=cutoff_date).distinct()
        )


class CalendarAccount(models.Model):
    """OAuth credentials and account info for each Google account"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_accounts",
    )
    google_account_id = models.CharField(
        max_length=100, help_text="Google account unique identifier"
    )
    email = models.EmailField(help_text="Google account email address")
    access_token = models.TextField(help_text="Encrypted OAuth access token")
    refresh_token = models.TextField(help_text="Encrypted OAuth refresh token")
    token_expires_at = models.DateTimeField(help_text="When the access token expires")
    is_active = models.BooleanField(
        default=True, help_text="Enable/disable sync for this account"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom managers
    objects = models.Manager()  # Default manager
    active = ActiveCalendarAccountManager()  # Active accounts only

    class Meta:
        unique_together = ["user", "google_account_id"]
        verbose_name = "Calendar Account"
        verbose_name_plural = "Calendar Accounts"

    def __str__(self):
        return f"{self.email} ({self.user.username})"

    @property
    def is_token_expired(self):
        """Check if access token is expired"""
        return timezone.now() >= self.token_expires_at

    def set_access_token(self, token):
        """Set encrypted access token"""
        from .services.encryption import encrypt_token

        if token:
            self.access_token = encrypt_token({"token": token})
        else:
            self.access_token = ""

    def get_access_token(self):
        """Get decrypted access token"""
        from .services.encryption import CredentialsError, decrypt_token

        if not self.access_token:
            return ""
        try:
            token_data = decrypt_token(self.access_token)
            return token_data.get("token", "")
        except CredentialsError:
            logger.error(f"Failed to decrypt access token for account {self.email}")
            return ""

    def set_refresh_token(self, token):
        """Set encrypted refresh token"""
        from .services.encryption import encrypt_token

        if token:
            self.refresh_token = encrypt_token({"token": token})
        else:
            self.refresh_token = ""

    def get_refresh_token(self):
        """Get decrypted refresh token"""
        from .services.encryption import CredentialsError, decrypt_token

        if not self.refresh_token:
            return ""
        try:
            token_data = decrypt_token(self.refresh_token)
            return token_data.get("token", "")
        except CredentialsError:
            logger.error(f"Failed to decrypt refresh token for account {self.email}")
            return ""

    def needs_token_refresh(self, buffer_minutes=5):
        """Check if token needs refresh with buffer time"""
        if not self.token_expires_at:
            return True

        from datetime import timedelta

        buffer_time = timedelta(minutes=buffer_minutes)
        return timezone.now() + buffer_time >= self.token_expires_at

    def get_calendar_stats(self):
        """Get statistics for this account's calendars"""
        from django.db import models

        stats = self.calendars.aggregate(
            total_calendars=models.Count("id"),
            sync_enabled_calendars=models.Count(
                "id", filter=models.Q(sync_enabled=True)
            ),
            primary_calendars=models.Count("id", filter=models.Q(is_primary=True)),
        )

        return {
            "total_calendars": stats["total_calendars"] or 0,
            "sync_enabled_calendars": stats["sync_enabled_calendars"] or 0,
            "primary_calendars": stats["primary_calendars"] or 0,
        }

    def get_last_successful_sync(self):
        """Get the most recent successful sync for this account"""
        return self.sync_logs.filter(status="success").order_by("-completed_at").first()

    def get_sync_health_status(self):
        """Get comprehensive sync health status"""
        if not self.is_active:
            return {
                "status": "inactive",
                "message": "Account is inactive",
                "can_sync": False,
            }

        if self.is_token_expired:
            return {
                "status": "expired",
                "message": "Token has expired and needs refresh",
                "can_sync": False,
            }

        if self.needs_token_refresh():
            return {
                "status": "refresh_needed",
                "message": "Token will expire soon and should be refreshed",
                "can_sync": True,
            }

        # Check for recent sync failures
        recent_failures = self.sync_logs.filter(
            status="error",
            started_at__gte=timezone.now() - timezone.timedelta(hours=24),
        ).count()

        if recent_failures > 3:
            return {
                "status": "failing",
                "message": f"{recent_failures} sync failures in the last 24 hours",
                "can_sync": True,
            }

        return {
            "status": "healthy",
            "message": "Account is ready for sync",
            "can_sync": True,
        }

    def has_valid_credentials(self):
        """Check if account has valid credentials"""
        return (
            self.is_active
            and bool(self.get_access_token())
            and bool(self.get_refresh_token())
            and not self.is_token_expired
        )

    def get_calendars_for_sync(self):
        """Get calendars that are enabled for synchronization"""
        return self.calendars.filter(sync_enabled=True)

    def deactivate_with_reason(self, reason="Manual deactivation"):
        """Deactivate account with logging"""
        self.is_active = False
        self.save(update_fields=["is_active"])

        logger.info(f"Deactivated account {self.email}: {reason}")
        return True


class Calendar(models.Model):
    """Individual calendar configuration"""

    calendar_account = models.ForeignKey(
        CalendarAccount, on_delete=models.CASCADE, related_name="calendars"
    )
    google_calendar_id = models.CharField(
        max_length=200, help_text="Google Calendar unique identifier"
    )
    name = models.CharField(
        max_length=200,
        validators=[MinLengthValidator(1)],
        help_text="Calendar display name",
    )
    description = models.TextField(blank=True, help_text="Calendar description")
    color = models.CharField(max_length=10, blank=True, help_text="Calendar color code")
    is_primary = models.BooleanField(
        default=False, help_text="Is this the primary calendar for the account"
    )
    sync_enabled = models.BooleanField(
        default=True, help_text="Enable/disable sync for this calendar"
    )
    last_sync_token = models.CharField(
        max_length=500, blank=True, help_text="Token for incremental sync"
    )
    last_synced_at = models.DateTimeField(
        null=True, blank=True, help_text="Last successful sync timestamp"
    )

    # Webhook fields (Guilfoyle's minimalist approach - no separate model)
    webhook_channel_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Google webhook channel ID for this calendar",
    )
    webhook_expires_at = models.DateTimeField(
        null=True, blank=True, help_text="When the webhook subscription expires"
    )
    webhook_last_setup = models.DateTimeField(
        null=True, blank=True, help_text="When webhook was last registered with Google"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom managers
    objects = models.Manager()  # Default manager
    sync_ready = SyncEnabledCalendarManager()  # Sync-enabled calendars only

    class Meta:
        unique_together = ["calendar_account", "google_calendar_id"]
        verbose_name = "Calendar"
        verbose_name_plural = "Calendars"
        indexes = [
            models.Index(fields=["last_synced_at"]),
            models.Index(fields=["sync_enabled"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.calendar_account.email})"

    def save(self, *args, **kwargs):
        """Save with validation"""
        self.full_clean()
        if self.name:
            self.name = self.name.strip()
        super().save(*args, **kwargs)

    def clean(self):
        """Validate calendar data"""
        if self.name and not self.name.strip():
            raise ValidationError({"name": "Calendar name cannot be empty"})

        # Check for duplicate names per account
        if (
            self.name
            and Calendar.objects.filter(
                calendar_account=self.calendar_account, name__iexact=self.name.strip()
            )
            .exclude(pk=self.pk)
            .exists()
        ):
            raise ValidationError({"name": "Calendar name must be unique per account"})

    @property
    def should_sync(self):
        """Check if this calendar should be synced"""
        return (
            self.sync_enabled
            and self.calendar_account.is_active
            and self.calendar_account.user.profile.sync_enabled
        )

    def toggle_sync(self):
        """Toggle sync status - business logic in model"""
        self.sync_enabled = not self.sync_enabled
        self.save(update_fields=["sync_enabled"])
        return self.sync_enabled

    def can_sync(self):
        """Check if calendar can be synced with detailed reason"""
        if not self.calendar_account.is_active:
            return False, "Account is inactive"

        if self.calendar_account.is_token_expired:
            return False, "Token has expired"

        if not self.sync_enabled:
            return False, "Sync is disabled for this calendar"

        try:
            if not self.calendar_account.user.profile.sync_enabled:
                return False, "Global sync is disabled for user"
        except AttributeError:
            # Handle missing user profile
            return False, "User profile not configured"

        return True, "Calendar is ready for sync"

    def get_sync_status_display(self):
        """Human-readable sync status"""
        can_sync, reason = self.can_sync()
        if can_sync:
            return "Sync Enabled"
        return reason

    def get_last_sync_time(self):
        """Get last successful sync time for this calendar's account"""
        last_sync = (
            self.calendar_account.sync_logs.filter(status="success")
            .order_by("-completed_at")
            .first()
        )

        return last_sync.completed_at if last_sync else None

    def get_event_counts(self):
        """Get event statistics for this calendar"""
        from django.db import models

        stats = self.events.aggregate(
            total_events=models.Count("id"),
            busy_blocks=models.Count("id", filter=models.Q(is_busy_block=True)),
            regular_events=models.Count("id", filter=models.Q(is_busy_block=False)),
        )

        return {
            "total": stats["total_events"] or 0,
            "busy_blocks": stats["busy_blocks"] or 0,
            "regular_events": stats["regular_events"] or 0,
        }

    def has_active_webhook(self, buffer_hours=24):
        """Check if calendar has an active webhook that hasn't expired"""
        if not self.webhook_channel_id or not self.webhook_expires_at:
            return False

        # Check if webhook expires within buffer time
        buffer_time = timezone.now() + timezone.timedelta(hours=buffer_hours)
        return self.webhook_expires_at > buffer_time

    def needs_webhook_renewal(self, buffer_hours=24):
        """Check if webhook needs renewal (expires within buffer time)"""
        if not self.webhook_channel_id or not self.webhook_expires_at:
            return True  # No webhook or expiration info

        buffer_time = timezone.now() + timezone.timedelta(hours=buffer_hours)
        return self.webhook_expires_at <= buffer_time

    def update_webhook_info(self, channel_id, expires_at):
        """Update webhook information after successful registration"""
        self.webhook_channel_id = channel_id
        self.webhook_expires_at = expires_at
        self.webhook_last_setup = timezone.now()
        self.save(
            update_fields=[
                "webhook_channel_id",
                "webhook_expires_at",
                "webhook_last_setup",
            ]
        )

    def clear_webhook_info(self):
        """Clear webhook information when webhook is deactivated"""
        self.webhook_channel_id = None
        self.webhook_expires_at = None
        self.save(update_fields=["webhook_channel_id", "webhook_expires_at"])

    def get_webhook_status(self):
        """Get human-readable webhook status"""
        if not self.webhook_channel_id:
            return "No webhook registered"

        if not self.webhook_expires_at:
            return "Webhook registered (no expiration info)"

        if self.webhook_expires_at <= timezone.now():
            return "Webhook expired"

        if self.needs_webhook_renewal():
            hours_left = int(
                (self.webhook_expires_at - timezone.now()).total_seconds() / 3600
            )
            return f"Webhook expires in {hours_left} hours"

        return "Webhook active"

    def has_recent_activity(self, days=7):
        """Check if calendar has recent activity"""
        from datetime import timedelta

        from django.utils import timezone

        cutoff_date = timezone.now() - timedelta(days=days)
        return self.events.filter(updated_at__gte=cutoff_date).exists()

    def validate_for_sync(self):
        """Validate calendar is ready for synchronization"""
        can_sync, reason = self.can_sync()
        if not can_sync:
            from django.core.exceptions import ValidationError

            raise ValidationError(f"Calendar cannot be synced: {reason}")
        return True


class Event(models.Model):
    """Calendar events and system-created busy blocks"""

    calendar = models.ForeignKey(
        Calendar, on_delete=models.CASCADE, related_name="events"
    )
    google_event_id = models.CharField(
        max_length=200, help_text="Google Calendar event unique identifier"
    )
    title = models.CharField(
        max_length=SyncConstants.MAX_TITLE_LENGTH,
        validators=[MinLengthValidator(1)],
        help_text="Event title/summary",
    )
    description = models.TextField(blank=True, help_text="Event description")
    start_time = models.DateTimeField(help_text="Event start datetime (UTC)")
    end_time = models.DateTimeField(help_text="Event end datetime (UTC)")
    is_all_day = models.BooleanField(default=False, help_text="All-day event flag")
    is_busy_block = models.BooleanField(
        default=False, help_text="System-created busy block flag"
    )
    source_event = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="busy_blocks",
        help_text="Source event for busy blocks",
    )
    busy_block_tag = models.CharField(
        max_length=200, blank=True, help_text="Unique tag for busy block identification"
    )
    event_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="Hash of event content for change detection",
    )
    # Privacy-first meeting detection (no attendee details stored)
    is_meeting_invite = models.BooleanField(
        default=False,
        help_text="Whether this event is a meeting invite (has attendees)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["calendar", "google_event_id"]
        verbose_name = "Event"
        verbose_name_plural = "Events"
        ordering = ["start_time"]
        indexes = [
            models.Index(fields=["start_time", "end_time"]),
            models.Index(fields=["is_busy_block"]),
            models.Index(fields=["source_event"]),
            models.Index(fields=["updated_at"]),
        ]

    def __str__(self):
        block_indicator = " [BUSY BLOCK]" if self.is_busy_block else ""
        return f"{self.title} ({self.start_time}){block_indicator}"

    def save(self, *args, **kwargs):
        """Save with validation"""
        self.full_clean()
        if self.title:
            self.title = self.title.strip()
        # Generate event hash for change detection
        if not self.event_hash:
            self.event_hash = self.generate_content_hash()
        super().save(*args, **kwargs)

    def clean(self):
        """Validate event data"""
        if self.title and not self.title.strip():
            raise ValidationError({"title": "Event title cannot be empty"})

        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": "End time must be after start time"})

        # Validate busy block has source event
        if self.is_busy_block and not self.source_event:
            raise ValidationError(
                {"source_event": "Busy blocks must have a source event"}
            )

    def generate_content_hash(self):
        """Generate hash of event content for change detection"""
        content = f"{self.title}{self.start_time}{self.end_time}{self.description}"
        return hashlib.md5(content.encode()).hexdigest()

    def generate_busy_block_tag(self):
        """Generate unique tag for busy block identification"""
        if self.source_event and self.calendar:
            return BusyBlock.generate_tag(self.calendar.id, self.source_event.id)
        return ""

    @classmethod
    def create_busy_block(cls, source_event, target_calendar):
        """Create a busy block from a source event in target calendar"""
        busy_block = cls(
            calendar=target_calendar,
            google_event_id=f"busy_{source_event.id}_{target_calendar.id}",
            title=BusyBlock.generate_title(source_event.title),
            description=f"Busy block created from: {source_event.calendar.name}",
            start_time=source_event.start_time,
            end_time=source_event.end_time,
            is_all_day=source_event.is_all_day,
            is_busy_block=True,
            source_event=source_event,
        )
        busy_block.busy_block_tag = busy_block.generate_busy_block_tag()
        return busy_block

    @classmethod
    def is_system_busy_block(cls, event_title):
        """Check if an event is a system-created busy block by title"""
        return BusyBlock.is_system_busy_block(event_title)

    def get_meeting_type_display(self):
        """Get human-readable meeting type"""
        if self.is_busy_block:
            if self.source_event and self.source_event.is_meeting_invite:
                return "🔒 Meeting"
            else:
                return "🔒 Busy"
        elif self.is_meeting_invite:
            return "Meeting Invite"
        else:
            return "Personal Event"


class SyncLog(models.Model):
    """Track sync operations and errors"""

    SYNC_TYPES = [
        ("full", "Full Sync"),
        ("incremental", "Incremental Sync"),
        ("manual", "Manual Sync"),
    ]

    STATUS_CHOICES = [
        ("success", "Success"),
        ("error", "Error"),
        ("partial", "Partial Success"),
        ("in_progress", "In Progress"),
    ]

    calendar_account = models.ForeignKey(
        CalendarAccount, on_delete=models.CASCADE, related_name="sync_logs"
    )
    sync_type = models.CharField(
        max_length=20, choices=SYNC_TYPES, default="incremental"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="in_progress"
    )
    events_processed = models.PositiveIntegerField(
        default=0, help_text="Total events processed"
    )
    events_created = models.PositiveIntegerField(
        default=0, help_text="New events created"
    )
    events_updated = models.PositiveIntegerField(default=0, help_text="Events updated")
    events_deleted = models.PositiveIntegerField(default=0, help_text="Events deleted")
    busy_blocks_created = models.PositiveIntegerField(
        default=0, help_text="Busy blocks created"
    )
    busy_blocks_updated = models.PositiveIntegerField(
        default=0, help_text="Busy blocks updated"
    )
    busy_blocks_deleted = models.PositiveIntegerField(
        default=0, help_text="Busy blocks deleted"
    )
    error_message = models.TextField(
        blank=True, help_text="Error details if sync failed"
    )
    api_calls_made = models.PositiveIntegerField(
        default=0, help_text="Number of Google API calls made"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        null=True, blank=True, help_text="When sync completed (success or failure)"
    )

    class Meta:
        verbose_name = "Sync Log"
        verbose_name_plural = "Sync Logs"
        ordering = ["-started_at"]

    def __str__(self):
        duration = ""
        if self.completed_at:
            delta = self.completed_at - self.started_at
            duration = f" ({delta.total_seconds():.1f}s)"
        return f"{self.sync_type} sync for {self.calendar_account.email} - {self.status}{duration}"

    def mark_completed(self, status="success", error_message=""):
        """Mark sync as completed with status"""
        self.status = status
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save()

    @property
    def duration(self):
        """Get sync duration in seconds"""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @classmethod
    def cleanup_old_logs(cls, days_to_keep=30):
        """Remove sync logs older than specified days"""
        cutoff_date = timezone.now() - timezone.timedelta(days=days_to_keep)
        deleted_count = cls.objects.filter(started_at__lt=cutoff_date).delete()[0]
        return deleted_count

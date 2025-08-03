import hashlib
import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator
from django.db import models
from django.utils import timezone

from .constants import BusyBlock, SyncConstants


logger = logging.getLogger(__name__)


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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

        if self.start_time and self.end_time:
            if self.start_time >= self.end_time:
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

"""Constants for calendar sync application"""


class SyncConstants:
    """Constants for sync operations"""

    DEFAULT_RETRY_DELAY = 60  # seconds
    RECENT_EVENTS_LIMIT = 5
    MAX_EMAIL_LENGTH = 255
    MAX_TITLE_LENGTH = 500
    MAX_DESCRIPTION_LENGTH = 2000
    BATCH_SIZE = 100
    MAX_SYNC_DAYS_AHEAD = 90
    MAX_SYNC_DAYS_BEHIND = 30

    # Sync intervals
    INCREMENTAL_SYNC_INTERVAL = 300  # 5 minutes
    FULL_SYNC_INTERVAL = 86400  # 24 hours

    # Rate limiting
    API_CALLS_PER_MINUTE = 50
    API_RETRY_ATTEMPTS = 3
    EXPONENTIAL_BACKOFF_BASE = 2


class OAuth:
    """OAuth configuration constants"""

    SCOPES: list[str] = ["https://www.googleapis.com/auth/calendar"]
    REDIRECT_PATH = "/auth/callback/"
    STATE_LENGTH = 32

    # Token expiry buffer (refresh tokens before they expire)
    TOKEN_REFRESH_BUFFER_MINUTES = 10


class TokenConstants:
    """Token management configuration"""

    # Buffer time before token expiration to trigger refresh (minutes)
    REFRESH_BUFFER_MINUTES = 10

    # Maximum retry attempts for token refresh
    MAX_RETRY_ATTEMPTS = 3

    # Base delay for exponential backoff (seconds)
    BASE_RETRY_DELAY = 1

    # Maximum delay between retries (seconds)
    MAX_RETRY_DELAY = 60

    # Default token expiry duration (hours) - Google tokens typically last 1 hour
    DEFAULT_TOKEN_EXPIRY_HOURS = 1

    # Notification settings
    NOTIFY_ON_REFRESH_FAILURE = True
    NOTIFY_ON_ACCOUNT_DEACTIVATION = True


class BusyBlock:
    """Busy block configuration"""

    TITLE_PREFIX = "🔒 Busy - "
    TAG_PREFIX = "CalSync [source:"
    TAG_SUFFIX = "]"

    @staticmethod
    def generate_title(source_title: str) -> str:
        """Generate busy block title from source event"""
        return f"{BusyBlock.TITLE_PREFIX}{source_title}"

    @staticmethod
    def generate_tag(calendar_id: int, event_id: int) -> str:
        """Generate busy block tag"""
        return (
            f"{BusyBlock.TAG_PREFIX}{calendar_id}:event{event_id}{BusyBlock.TAG_SUFFIX}"
        )

    @staticmethod
    def is_system_busy_block(title: str) -> bool:
        """Check if title indicates system-created busy block"""
        return BusyBlock.TITLE_PREFIX in title or BusyBlock.TAG_PREFIX in title


class DatabaseConstants:
    """Database-related constants"""

    MAX_VARCHAR_LENGTH = 255
    MAX_TEXT_LENGTH = 2000

    # Index names (for migrations)
    INDEX_CALENDAR_SYNC_TIME = "idx_calendar_last_synced"
    INDEX_EVENT_TIME_RANGE = "idx_event_time_range"
    INDEX_SYNC_LOG_ACCOUNT_TIME = "idx_sync_log_account_time"


class LoggingConstants:
    """Logging configuration"""

    DEFAULT_LOG_LEVEL = "INFO"
    SYNC_LOG_RETENTION_DAYS = 30
    DEBUG_LOG_MAX_SIZE = 10 * 1024 * 1024  # 10MB

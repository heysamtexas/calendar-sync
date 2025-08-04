# Event State Model Design

## 🎯 Purpose

Create new database model to track event correlation IDs and lifecycle states, enabling bulletproof identification of system-created vs user-created events.

## 📋 EventState Model Specification

### Core Model Structure

```python
from django.db import models
import uuid

class EventState(models.Model):
    """
    Tracks event correlation IDs and lifecycle states for bulletproof event identification.
    
    This model serves as the authoritative source for determining:
    - Which events were created by our system vs users
    - Parent-child relationships between events and busy blocks
    - Event lifecycle states (creating → created → synced)
    """
    
    # Primary correlation identifier
    correlation_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique correlation ID embedded in Google Calendar extendedProperties"
    )
    
    # Calendar relationship
    calendar = models.ForeignKey(
        'Calendar',
        on_delete=models.CASCADE,
        related_name='event_states',
        help_text="Calendar where this event exists"
    )
    
    # Google Calendar integration
    google_event_id = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text="Google Calendar event ID (set after creation)"
    )
    
    # Event classification
    event_type = models.CharField(
        max_length=20,
        choices=[
            ('user_event', 'User Event'),
            ('busy_block', 'Busy Block'),
        ],
        help_text="Type of event"
    )
    
    # Creation tracking
    created_by_us = models.BooleanField(
        help_text="True if this event was created by our system"
    )
    
    # Parent-child relationships
    source_correlation_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Correlation ID of the source event (for busy blocks)"
    )
    
    # Lifecycle tracking
    status = models.CharField(
        max_length=20,
        choices=[
            ('creating', 'Creating'),     # Database record created, Google event pending
            ('created', 'Created'),       # Google event created, ID assigned
            ('synced', 'Synced'),        # Fully synchronized across calendars
            ('deleted', 'Deleted'),      # Marked for deletion
        ],
        default='creating',
        help_text="Event lifecycle status"
    )
    
    # Additional metadata
    title = models.CharField(
        max_length=500,
        blank=True,
        help_text="Event title for debugging and display"
    )
    
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this event was seen in Google Calendar"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Event State"
        verbose_name_plural = "Event States"
        indexes = [
            models.Index(fields=['calendar', 'google_event_id']),
            models.Index(fields=['calendar', 'created_by_us']),
            models.Index(fields=['source_correlation_id']),
            models.Index(fields=['status']),
            models.Index(fields=['last_seen_at']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(
                    models.Q(event_type='user_event', source_correlation_id__isnull=True) |
                    models.Q(event_type='busy_block', source_correlation_id__isnull=False)
                ),
                name='source_correlation_id_constraint'
            )
        ]
    
    def __str__(self):
        return f"{self.event_type}: {self.title} ({self.correlation_id})"
    
    @property
    def is_busy_block(self):
        """Check if this is a busy block"""
        return self.event_type == 'busy_block'
    
    @property
    def is_user_event(self):
        """Check if this is a user event"""
        return self.event_type == 'user_event'
    
    def get_source_event(self):
        """Get the source event for busy blocks"""
        if self.source_correlation_id:
            return EventState.objects.filter(
                correlation_id=self.source_correlation_id
            ).first()
        return None
    
    def get_busy_blocks(self):
        """Get all busy blocks created from this event"""
        if self.is_user_event:
            return EventState.objects.filter(
                source_correlation_id=self.correlation_id,
                event_type='busy_block'
            )
        return EventState.objects.none()
    
    def mark_created(self, google_event_id):
        """Mark event as created in Google Calendar"""
        self.google_event_id = google_event_id
        self.status = 'created'
        self.save(update_fields=['google_event_id', 'status', 'updated_at'])
    
    def mark_synced(self):
        """Mark event as fully synced"""
        self.status = 'synced'
        self.last_seen_at = timezone.now()
        self.save(update_fields=['status', 'last_seen_at', 'updated_at'])
    
    def mark_seen(self):
        """Update last seen timestamp"""
        self.last_seen_at = timezone.now()
        self.save(update_fields=['last_seen_at', 'updated_at'])
```

## 🔍 Relationship with Existing Models

### Integration with Current Event Model

The new `EventState` model complements the existing `Event` model:

```python
class Event(models.Model):
    # Existing fields...
    
    # NEW: Link to correlation tracking
    correlation_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="Correlation ID for state tracking"
    )
    
    def get_event_state(self):
        """Get associated EventState record"""
        if self.correlation_id:
            return EventState.objects.filter(
                correlation_id=self.correlation_id
            ).first()
        return None
    
    @property
    def created_by_us(self):
        """Check if this event was created by our system"""
        state = self.get_event_state()
        return state.created_by_us if state else False
```

### Manager Methods

```python
class EventStateManager(models.Manager):
    """Custom manager for EventState operations"""
    
    def our_events(self, calendar=None):
        """Get events created by our system"""
        queryset = self.filter(created_by_us=True)
        if calendar:
            queryset = queryset.filter(calendar=calendar)
        return queryset
    
    def user_events(self, calendar=None):
        """Get events created by users"""
        queryset = self.filter(created_by_us=False)
        if calendar:
            queryset = queryset.filter(calendar=calendar)
        return queryset
    
    def busy_blocks(self, calendar=None):
        """Get busy blocks"""
        queryset = self.filter(event_type='busy_block')
        if calendar:
            queryset = queryset.filter(calendar=calendar)
        return queryset
    
    def pending_creation(self):
        """Get events that are still being created"""
        return self.filter(status='creating')
    
    def for_google_event(self, google_event_id):
        """Find EventState by Google event ID"""
        return self.filter(google_event_id=google_event_id).first()
    
    def by_correlation_id(self, correlation_id):
        """Find EventState by correlation ID"""
        return self.filter(correlation_id=correlation_id).first()

# Add custom manager to model
EventState.objects = EventStateManager()
```

## 🔄 Migration Strategy

### Phase 1: Add EventState Model

```python
# migrations/0001_add_event_state.py
from django.db import migrations, models
import uuid

class Migration(migrations.Migration):
    dependencies = [
        ('calendars', '0010_previous_migration'),
    ]
    
    operations = [
        migrations.CreateModel(
            name='EventState',
            fields=[
                ('correlation_id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)),
                ('calendar', models.ForeignKey('Calendar', on_delete=models.CASCADE, related_name='event_states')),
                ('google_event_id', models.CharField(max_length=200, null=True, blank=True)),
                ('event_type', models.CharField(max_length=20, choices=[('user_event', 'User Event'), ('busy_block', 'Busy Block')])),
                ('created_by_us', models.BooleanField()),
                ('source_correlation_id', models.UUIDField(null=True, blank=True)),
                ('status', models.CharField(max_length=20, choices=[('creating', 'Creating'), ('created', 'Created'), ('synced', 'Synced'), ('deleted', 'Deleted')], default='creating')),
                ('title', models.CharField(max_length=500, blank=True)),
                ('last_seen_at', models.DateTimeField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Event State',
                'verbose_name_plural': 'Event States',
            },
        ),
        # Add indexes
        migrations.AddIndex(
            model_name='eventstate',
            index=models.Index(fields=['calendar', 'google_event_id'], name='eventstate_calendar_google_idx'),
        ),
        migrations.AddIndex(
            model_name='eventstate',
            index=models.Index(fields=['calendar', 'created_by_us'], name='eventstate_calendar_created_idx'),
        ),
        migrations.AddIndex(
            model_name='eventstate',
            index=models.Index(fields=['source_correlation_id'], name='eventstate_source_correlation_idx'),
        ),
        migrations.AddIndex(
            model_name='eventstate',
            index=models.Index(fields=['status'], name='eventstate_status_idx'),
        ),
    ]
```

### Phase 2: Add Correlation ID to Event Model

```python
# migrations/0002_add_correlation_id_to_event.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('calendars', '0001_add_event_state'),
    ]
    
    operations = [
        migrations.AddField(
            model_name='event',
            name='correlation_id',
            field=models.UUIDField(null=True, blank=True, help_text='Correlation ID for state tracking'),
        ),
        migrations.AddIndex(
            model_name='event',
            index=models.Index(fields=['correlation_id'], name='event_correlation_id_idx'),
        ),
    ]
```

### Phase 3: Data Migration for Existing Events

```python
# migrations/0003_migrate_existing_events.py
from django.db import migrations
import uuid

def migrate_existing_events(apps, schema_editor):
    Event = apps.get_model('calendars', 'Event')
    EventState = apps.get_model('calendars', 'EventState')
    
    for event in Event.objects.all():
        # Generate correlation ID for existing event
        correlation_id = uuid.uuid4()
        
        # Update Event model
        event.correlation_id = correlation_id
        event.save()
        
        # Create EventState record
        EventState.objects.create(
            correlation_id=correlation_id,
            calendar=event.calendar,
            google_event_id=event.google_event_id,
            event_type='busy_block' if event.is_busy_block else 'user_event',
            created_by_us=event.is_busy_block,  # Assume busy blocks were created by us
            status='synced',  # Existing events are already synced
            title=event.title,
            last_seen_at=event.updated_at,
        )

def reverse_migration(apps, schema_editor):
    EventState = apps.get_model('calendars', 'EventState')
    EventState.objects.all().delete()

class Migration(migrations.Migration):
    dependencies = [
        ('calendars', '0002_add_correlation_id_to_event'),
    ]
    
    operations = [
        migrations.RunPython(migrate_existing_events, reverse_migration),
    ]
```

## 🧪 Usage Examples

### Creating New User Event State

```python
def handle_new_user_event(calendar, google_event):
    """Create EventState for newly discovered user event"""
    correlation_id = uuid.uuid4()
    
    # Create state tracking
    EventState.objects.create(
        correlation_id=correlation_id,
        calendar=calendar,
        google_event_id=google_event['id'],
        event_type='user_event',
        created_by_us=False,
        status='synced',
        title=google_event.get('summary', ''),
        last_seen_at=timezone.now()
    )
    
    # Update Google event with correlation ID
    update_google_event_correlation_id(google_event['id'], correlation_id)
    
    return correlation_id
```

### Creating Busy Block State

```python
def create_busy_block_state(target_calendar, source_correlation_id, title):
    """Create EventState for new busy block before Google creation"""
    correlation_id = uuid.uuid4()
    
    # Create state FIRST
    state = EventState.objects.create(
        correlation_id=correlation_id,
        calendar=target_calendar,
        event_type='busy_block',
        created_by_us=True,
        source_correlation_id=source_correlation_id,
        status='creating',
        title=title
    )
    
    return state
```

### Checking Event Ownership

```python
def is_our_event(google_event):
    """Perfect detection using correlation ID"""
    # Extract correlation ID from extendedProperties
    extended = google_event.get('extendedProperties', {})
    calsync_id = extended.get('private', {}).get('calsync_id')
    
    if calsync_id:
        # Check if we created this event
        return EventState.objects.filter(
            correlation_id=calsync_id,
            created_by_us=True
        ).exists()
    
    return False
```

## 📊 Performance Considerations

### Database Performance

1. **Indexes**: Strategic indexes on high-query fields
2. **UUID Performance**: UUIDs as primary keys are efficient for lookups
3. **Foreign Key Relationships**: Proper relationships enable efficient joins

### Query Optimization

```python
# Efficient bulk operations
def get_our_events_in_calendar(calendar):
    """Get all our events in a calendar with minimal queries"""
    return EventState.objects.select_related('calendar').filter(
        calendar=calendar,
        created_by_us=True
    )

# Efficient relationship queries
def get_busy_blocks_for_event(source_correlation_id):
    """Get all busy blocks for a source event"""
    return EventState.objects.filter(
        source_correlation_id=source_correlation_id,
        event_type='busy_block'
    )
```

## 🔐 Data Integrity

### Constraints and Validation

1. **Check Constraints**: Ensure data consistency at database level
2. **Foreign Key Integrity**: Proper cascade behaviors
3. **UUID Uniqueness**: Globally unique correlation IDs

### Cleanup Operations

```python
def cleanup_orphaned_states():
    """Remove EventState records for events that no longer exist in Google"""
    from django.utils import timezone
    from datetime import timedelta
    
    # Find events not seen recently
    stale_cutoff = timezone.now() - timedelta(days=7)
    
    stale_events = EventState.objects.filter(
        last_seen_at__lt=stale_cutoff,
        status__in=['created', 'synced']
    )
    
    # Verify they don't exist in Google before deletion
    for state in stale_events:
        if not google_event_exists(state.calendar, state.google_event_id):
            state.status = 'deleted'
            state.save()
```

This EventState model provides the foundation for bulletproof event tracking and perfect cascade prevention through UUID correlation.
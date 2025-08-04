# UUID Correlation Architecture - Overview

## 🎯 Problem Analysis

### Current State: Fragile Text-Based Detection
Our current system attempts to identify system-created busy blocks through:
- **Emoji prefixes**: `🔒 Busy - ` in event titles
- **Text parsing**: `CalSync [source:...]` in descriptions
- **String matching**: Fragile detection that can be broken by user edits

### Root Cause of Webhook Cascades
1. **User creates event** in Calendar A
2. **We create busy block** in Calendar B with text markers
3. **Google sends webhook** for Calendar B: "something changed"
4. **We fetch all events** from Calendar B (including our busy block)
5. **Detection fails** - our text markers aren't recognized properly
6. **We process our own busy block** as a new user event
7. **Cascade begins** - creates more busy blocks → more webhooks → infinite loop

### Evidence from Webhook Data
- Message numbers jumping by ~20,000 in 20 seconds
- Consistent `events_created: 1, events_updated: 1` patterns
- Multiple calendars affected simultaneously
- Current detection showing `"cross_calendar_policy": "Disabled"` but cascades continue

## 🔧 Solution: UUID Correlation Architecture

### Core Principle
**Replace fragile text detection with bulletproof UUID correlation IDs embedded invisibly in Google Calendar events.**

### Key Components

#### 1. Unique Correlation IDs
```python
# Generate UUID for every event we create or process
correlation_id = str(uuid.uuid4())  # e.g., "550e8400-e29b-41d4-a716-446655440000"
```

#### 2. Google Calendar ExtendedProperties
```python
# Embed tracking data invisibly in Google events
event_data = {
    'summary': 'Busy - Important Meeting',  # Clean, emoji-free
    'description': 'Meeting details...',
    'extendedProperties': {
        'private': {
            'calsync_id': correlation_id,
            'calsync_type': 'busy_block',
            'calsync_source': source_correlation_id
        }
    }
}
```

**Why ExtendedProperties are perfect:**
- **Invisible to users** - can't accidentally edit or break
- **Preserved by Google** - never lost or modified
- **Structured data** - no text parsing required
- **Private scope** - only our app can access them

#### 3. Database State Management
```python
class EventState(models.Model):
    correlation_id = models.UUIDField(unique=True, primary_key=True)
    calendar = models.ForeignKey(Calendar)
    google_event_id = models.CharField(null=True)  # Set after creation
    event_type = models.CharField(choices=[
        ('user_event', 'User Event'),
        ('busy_block', 'Busy Block')
    ])
    created_by_us = models.BooleanField()
    source_correlation_id = models.UUIDField(null=True)  # For busy blocks
    status = models.CharField(choices=[
        ('creating', 'Creating'),
        ('created', 'Created'),
        ('synced', 'Synced')
    ])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### Perfect Cascade Prevention

#### Before (Fragile):
```python
def is_our_busy_block(google_event):
    title = google_event.get('summary', '')
    description = google_event.get('description', '')
    
    # Fragile text parsing
    return '🔒 Busy - ' in title or 'CalSync [source:' in description
```

#### After (Bulletproof):
```python
def is_our_event(google_event):
    extended = google_event.get('extendedProperties', {})
    calsync_id = extended.get('private', {}).get('calsync_id')
    
    if calsync_id:
        # Perfect UUID match - no parsing, no guessing
        return EventState.objects.filter(
            correlation_id=calsync_id,
            created_by_us=True
        ).exists()
    
    return False  # No correlation ID = not ours
```

## 🔄 Complete Flow Redesign

### Current Flow (Problematic)
```
User Event → Text-Tagged Busy Block → Webhook → Fetch All → Failed Detection → Process Own Event → CASCADE
```

### New Flow (Bulletproof)
```
User Event → UUID-Tagged Busy Block → Webhook → Fetch All → UUID Match → Skip Own Event → NO CASCADE
```

### Detailed New Flow

#### 1. User Event Detection
```python
# Webhook arrives: "Calendar changed"
google_events = fetch_all_events(calendar)

for google_event in google_events:
    correlation_id = get_correlation_id(google_event)
    
    if correlation_id and is_our_event(correlation_id):
        # Skip - this is our event
        continue
    
    if not correlation_id:
        # New user event - assign correlation ID and process
        new_correlation_id = str(uuid.uuid4())
        EventState.objects.create(
            correlation_id=new_correlation_id,
            calendar=calendar,
            google_event_id=google_event['id'],
            event_type='user_event',
            created_by_us=False,
            status='synced'
        )
        
        # Create busy blocks in other calendars
        create_busy_blocks_for(google_event, new_correlation_id)
```

#### 2. Busy Block Creation
```python
def create_busy_blocks_for(source_event, source_correlation_id):
    for target_calendar in get_sync_targets():
        # Generate unique correlation ID for busy block
        busy_block_correlation_id = str(uuid.uuid4())
        
        # Create database state FIRST
        EventState.objects.create(
            correlation_id=busy_block_correlation_id,
            calendar=target_calendar,
            event_type='busy_block',
            created_by_us=True,
            source_correlation_id=source_correlation_id,
            status='creating'
        )
        
        # Create in Google with correlation ID
        google_event = client.create_busy_block(
            calendar_id=target_calendar.google_calendar_id,
            title='Busy - ' + source_event['summary'],
            start_time=source_event['start'],
            end_time=source_event['end'],
            extended_properties={
                'private': {
                    'calsync_id': busy_block_correlation_id,
                    'calsync_type': 'busy_block',
                    'calsync_source': source_correlation_id
                }
            }
        )
        
        # Update database with Google's event ID
        state = EventState.objects.get(correlation_id=busy_block_correlation_id)
        state.google_event_id = google_event['id']
        state.status = 'created'
        state.save()
```

#### 3. Webhook Processing
```python
def handle_webhook(calendar):
    google_events = fetch_all_events(calendar)
    
    for google_event in google_events:
        # Check for our correlation ID
        extended = google_event.get('extendedProperties', {})
        calsync_id = extended.get('private', {}).get('calsync_id')
        
        if calsync_id:
            # This has our tracking - check if we created it
            our_event = EventState.objects.filter(
                correlation_id=calsync_id,
                created_by_us=True
            ).first()
            
            if our_event:
                # This is our event - skip processing
                continue
        
        # No correlation ID or not created by us = real user event
        process_user_event(google_event)
```

## 🚀 Benefits

### 1. **Perfect Cascade Prevention**
- Never process our own events because UUID matching is bulletproof
- No reliance on user-editable text
- Immune to formatting changes or user modifications

### 2. **Reliable Detection**
- ExtendedProperties are invisible and tamper-proof
- Structured data instead of text parsing
- No emoji encoding issues

### 3. **Complete Audit Trail**
- Every event has unique correlation ID
- Perfect parent-child relationships tracked
- Full lifecycle visibility from creation to sync

### 4. **Future-Proof Architecture**
- UUIDs are globally unique and collision-free
- Extensible metadata system in ExtendedProperties
- Database-first approach enables complex logic

## 🎯 Success Metrics

### Before Implementation
- Webhook cascades every few minutes
- Message numbers jumping by thousands
- Events "blinking on/off"
- Unreliable sync state

### After Implementation
- Zero webhook cascades
- Stable message number progression
- Consistent event state
- Bulletproof sync operations

## 📋 Implementation Phases

1. **Infrastructure** - EventState model and UUID system
2. **Integration** - ExtendedProperties and Google Calendar API
3. **Engine** - Sync engine redesign with UUID detection
4. **Migration** - Existing events to correlation ID system
5. **Testing** - Comprehensive validation and monitoring

This architecture eliminates the fundamental flaw in our current system by replacing fragile text detection with bulletproof UUID correlation that Google cannot interfere with.
# Event Change Processing - Implementation Task

## Objective

Implement comprehensive event change processing for incremental sync, handling all event lifecycle operations (create, update, delete) with proper cross-calendar propagation.

## Background

Google Calendar incremental sync returns three types of changes:
- **New events**: `status: "confirmed"` (first appearance)
- **Updated events**: `status: "confirmed"` (modified since last sync)
- **Deleted events**: `status: "cancelled"` (marked for deletion)

## Event Change Processing Requirements

### 1. New Event Processing

#### Enhanced SyncEngine Integration
```python
def _process_incremental_events(self, calendar: Calendar, events: list[dict]):
    """Process incremental event changes with change type detection"""
    
    for google_event in events:
        event_id = google_event.get('id')
        event_status = google_event.get('status', 'confirmed')
        
        try:
            if event_status == 'cancelled':
                self._process_deleted_event(calendar, google_event)
            else:
                # Check if this is new or updated
                existing_event = Event.objects.filter(
                    calendar=calendar,
                    google_event_id=event_id
                ).first()
                
                if existing_event:
                    self._process_updated_event(calendar, existing_event, google_event)
                else:
                    self._process_new_event(calendar, google_event)
                    
        except Exception as e:
            logger.error(f"Failed to process event change {event_id}: {e}")
            # Continue processing other events rather than failing entire sync
```

#### New Event Creation with Cross-Calendar Impact
```python
def _process_new_event(self, calendar: Calendar, google_event: dict):
    """Process new event with immediate busy block propagation"""
    
    # Skip system-created busy blocks
    if BusyBlock.is_system_busy_block(google_event.get('summary', '')):
        return
    
    # Extract and validate event data
    event_data = self._extract_event_data(google_event)
    
    # Skip declined meetings
    if event_data.get('user_declined', False):
        logger.debug(f"Skipping declined meeting: {event_data['title']}")
        return
    
    # Create the event
    event_data_to_store = {k: v for k, v in event_data.items() if k != 'user_declined'}
    
    event = Event.objects.create(
        calendar=calendar,
        google_event_id=google_event.get('id'),
        **event_data_to_store
    )
    
    logger.info(f"Created new event: {event.title}")
    self.sync_results['events_created'] += 1
    
    # Immediate busy block propagation for new events
    self._propagate_event_to_target_calendars(event, action='create')
```

### 2. Updated Event Processing

#### Change Detection and Propagation
```python
def _process_updated_event(self, calendar: Calendar, existing_event: Event, google_event: dict):
    """Process updated event with change impact analysis"""
    
    # Extract new event data
    new_event_data = self._extract_event_data(google_event)
    
    # Skip declined meetings (may have changed to declined)
    if new_event_data.get('user_declined', False):
        logger.debug(f"Event now declined, removing: {existing_event.title}")
        self._process_deleted_event(calendar, google_event, existing_event=existing_event)
        return
    
    # Clean data for storage
    new_data_to_store = {k: v for k, v in new_event_data.items() if k != 'user_declined'}
    
    # Detect what changed
    changes = self._detect_event_changes(existing_event, new_data_to_store)
    
    if changes:
        # Update the event
        for field, new_value in new_data_to_store.items():
            setattr(existing_event, field, new_value)
        existing_event.save()
        
        logger.info(f"Updated event: {existing_event.title} - Changes: {list(changes.keys())}")
        self.sync_results['events_updated'] += 1
        
        # Propagate changes to busy blocks
        self._propagate_event_changes(existing_event, changes)
    else:
        logger.debug(f"No changes detected for event: {existing_event.title}")

def _detect_event_changes(self, event: Event, new_data: dict) -> dict:
    """Detect specific changes between existing and new event data"""
    changes = {}
    
    for field, new_value in new_data.items():
        old_value = getattr(event, field)
        if old_value != new_value:
            changes[field] = {'old': old_value, 'new': new_value}
    
    return changes

def _propagate_event_changes(self, event: Event, changes: dict):
    """Propagate event changes to all target calendars"""
    
    # Determine if busy blocks need updates
    time_changed = 'start_time' in changes or 'end_time' in changes
    title_changed = 'title' in changes
    
    if time_changed or title_changed:
        # Update all busy blocks for this event
        self._propagate_event_to_target_calendars(event, action='update', changes=changes)
```

### 3. Deleted Event Processing

#### Comprehensive Deletion with Cross-Calendar Cleanup
```python
def _process_deleted_event(self, calendar: Calendar, google_event: dict, existing_event: Event = None):
    """Process deleted event with comprehensive busy block cleanup"""
    
    event_id = google_event.get('id')
    
    # Find the event to delete
    if not existing_event:
        existing_event = Event.objects.filter(
            calendar=calendar,
            google_event_id=event_id
        ).first()
    
    if not existing_event:
        logger.debug(f"Event {event_id} already deleted or never existed")
        return
    
    logger.info(f"Processing deletion of event: {existing_event.title}")
    
    # Remove all busy blocks created from this source event
    self._remove_busy_blocks_for_source_event(existing_event)
    
    # Delete the event itself
    existing_event.delete()
    self.sync_results['events_deleted'] += 1

def _remove_busy_blocks_for_source_event(self, source_event: Event):
    """Remove all busy blocks created from a source event across all calendars"""
    
    # Find all busy blocks that reference this source event
    busy_blocks = Event.objects.filter(
        source_event=source_event,
        is_busy_block=True
    ).select_related('calendar', 'calendar__calendar_account')
    
    removed_count = 0
    
    for busy_block in busy_blocks:
        try:
            # Delete from Google Calendar
            client = GoogleCalendarClient(busy_block.calendar.calendar_account)
            client.delete_event(busy_block.calendar.google_calendar_id, busy_block.google_event_id)
            
            # Delete from database
            busy_block.delete()
            removed_count += 1
            
        except Exception as e:
            logger.warning(f"Failed to delete busy block {busy_block.google_event_id}: {e}")
    
    if removed_count > 0:
        logger.info(f"Removed {removed_count} busy blocks for deleted event: {source_event.title}")
        self.sync_results['busy_blocks_deleted'] += removed_count
```

### 4. Cross-Calendar Event Propagation

#### Immediate Propagation System
```python
def _propagate_event_to_target_calendars(self, source_event: Event, action: str, changes: dict = None):
    """Propagate event changes to all target calendars immediately"""
    
    # Get all calendars for the same user (cross-account sync)
    target_calendars = Calendar.objects.filter(
        calendar_account__user=source_event.calendar.calendar_account.user,
        sync_enabled=True,
        calendar_account__is_active=True
    ).exclude(id=source_event.calendar.id).select_related('calendar_account')
    
    for target_calendar in target_calendars:
        try:
            if action == 'create':
                self._create_busy_block_for_event(source_event, target_calendar)
            elif action == 'update':
                self._update_busy_block_for_event(source_event, target_calendar, changes)
            elif action == 'delete':
                self._remove_busy_block_for_event(source_event, target_calendar)
                
        except Exception as e:
            logger.error(f"Failed to propagate {action} to calendar {target_calendar.name}: {e}")

def _create_busy_block_for_event(self, source_event: Event, target_calendar: Calendar):
    """Create single busy block for specific event in target calendar"""
    
    client = GoogleCalendarClient(target_calendar.calendar_account)
    
    # Generate busy block details
    busy_block_title = BusyBlock.generate_title(source_event.title)
    busy_block_description = (
        f"CalSync [source:{source_event.calendar.calendar_account.email}:"
        f"{source_event.calendar.google_calendar_id}:{source_event.google_event_id}]"
    )
    
    # Create in Google Calendar
    google_event = client.create_busy_block(
        target_calendar.google_calendar_id,
        busy_block_title,
        source_event.start_time,
        source_event.end_time,
        busy_block_description
    )
    
    # Save in database
    busy_block_tag = BusyBlock.generate_tag(target_calendar.id, source_event.id)
    
    Event.objects.create(
        calendar=target_calendar,
        google_event_id=google_event['id'],
        title=busy_block_title,
        description=busy_block_description,
        start_time=source_event.start_time,
        end_time=source_event.end_time,
        is_busy_block=True,
        is_meeting_invite=source_event.is_meeting_invite,
        source_event=source_event,
        busy_block_tag=busy_block_tag
    )
    
    self.sync_results['busy_blocks_created'] += 1

def _update_busy_block_for_event(self, source_event: Event, target_calendar: Calendar, changes: dict):
    """Update existing busy block for changed source event"""
    
    # Find existing busy block
    busy_block = Event.objects.filter(
        calendar=target_calendar,
        source_event=source_event,
        is_busy_block=True
    ).first()
    
    if not busy_block:
        # No existing busy block, create new one
        self._create_busy_block_for_event(source_event, target_calendar)
        return
    
    client = GoogleCalendarClient(target_calendar.calendar_account)
    
    # Update busy block data
    busy_block.title = BusyBlock.generate_title(source_event.title)
    busy_block.start_time = source_event.start_time
    busy_block.end_time = source_event.end_time
    busy_block.is_meeting_invite = source_event.is_meeting_invite
    
    # Update in Google Calendar
    event_data = {
        'summary': busy_block.title,
        'start': {'dateTime': source_event.start_time.isoformat()},
        'end': {'dateTime': source_event.end_time.isoformat()},
        'description': busy_block.description
    }
    
    client.update_event(target_calendar.google_calendar_id, busy_block.google_event_id, event_data)
    
    # Save database changes
    busy_block.save()
    self.sync_results['busy_blocks_updated'] += 1
```

## Error Handling and Recovery

### 1. Partial Sync Failure Recovery
```python
def _handle_event_processing_error(self, calendar: Calendar, event_data: dict, error: Exception):
    """Handle individual event processing errors without failing entire sync"""
    
    event_id = event_data.get('id', 'unknown')
    error_msg = f"Failed to process event {event_id} in calendar {calendar.name}: {error}"
    
    logger.error(error_msg)
    
    # Record the error but continue processing
    self.sync_results['errors'].append(error_msg)
    
    # Optionally: Mark this event for retry in next sync
    # Could implement a failed_events tracking system
```

### 2. Cross-Calendar Consistency Validation
```python
def _validate_cross_calendar_consistency(self, source_event: Event):
    """Validate that busy blocks exist in all target calendars"""
    
    target_calendars = Calendar.objects.filter(
        calendar_account__user=source_event.calendar.calendar_account.user,
        sync_enabled=True,
        calendar_account__is_active=True
    ).exclude(id=source_event.calendar.id)
    
    inconsistencies = []
    
    for target_calendar in target_calendars:
        busy_block_exists = Event.objects.filter(
            calendar=target_calendar,
            source_event=source_event,
            is_busy_block=True
        ).exists()
        
        if not busy_block_exists:
            inconsistencies.append(target_calendar.name)
    
    if inconsistencies:
        logger.warning(f"Missing busy blocks for event {source_event.title} in calendars: {inconsistencies}")
        # Trigger repair process
        self._repair_missing_busy_blocks(source_event, inconsistencies)

def _repair_missing_busy_blocks(self, source_event: Event, missing_calendar_names: list[str]):
    """Repair missing busy blocks for consistency"""
    
    missing_calendars = Calendar.objects.filter(
        name__in=missing_calendar_names,
        calendar_account__user=source_event.calendar.calendar_account.user
    )
    
    for target_calendar in missing_calendars:
        try:
            self._create_busy_block_for_event(source_event, target_calendar)
            logger.info(f"Repaired missing busy block in {target_calendar.name}")
        except Exception as e:
            logger.error(f"Failed to repair busy block in {target_calendar.name}: {e}")
```

## Performance Optimizations

### 1. Batch Processing for Large Change Sets
```python
def _process_incremental_events_batch(self, calendar: Calendar, events: list[dict]):
    """Process incremental events in batches for better performance"""
    
    BATCH_SIZE = 50  # Process in chunks to avoid memory issues
    
    for i in range(0, len(events), BATCH_SIZE):
        batch = events[i:i + BATCH_SIZE]
        
        logger.debug(f"Processing batch {i//BATCH_SIZE + 1} of {len(batch)} events")
        
        with transaction.atomic():  # Ensure batch consistency
            for google_event in batch:
                try:
                    self._process_single_incremental_event(calendar, google_event)
                except Exception as e:
                    logger.error(f"Failed to process event in batch: {e}")
                    # Log error but continue with batch
```

### 2. Database Query Optimization
```python
def _bulk_update_busy_blocks(self, updates: list[dict]):
    """Bulk update busy blocks for better performance"""
    
    # Group updates by calendar for efficient processing
    updates_by_calendar = {}
    for update in updates:
        calendar_id = update['calendar_id']
        if calendar_id not in updates_by_calendar:
            updates_by_calendar[calendar_id] = []
        updates_by_calendar[calendar_id].append(update)
    
    for calendar_id, calendar_updates in updates_by_calendar.items():
        try:
            calendar = Calendar.objects.get(id=calendar_id)
            client = GoogleCalendarClient(calendar.calendar_account)
            
            # Batch update Google Calendar events
            for update in calendar_updates:
                # Update logic here
                pass
                
        except Exception as e:
            logger.error(f"Failed to bulk update calendar {calendar_id}: {e}")
```

## Testing Requirements

### 1. Event Change Processing Tests
```python
def test_new_event_creates_busy_blocks():
    """Test that new events create busy blocks in all target calendars"""

def test_updated_event_propagates_changes():
    """Test that event updates propagate to all busy blocks"""

def test_deleted_event_removes_busy_blocks():
    """Test that deleted events remove all associated busy blocks"""

def test_declined_meeting_handling():
    """Test that declined meetings are properly filtered"""

def test_cross_calendar_consistency():
    """Test that busy blocks remain consistent across calendars"""
```

### 2. Error Recovery Tests
```python
def test_partial_sync_failure_recovery():
    """Test recovery from individual event processing failures"""

def test_cross_calendar_propagation_failure():
    """Test handling of busy block creation failures"""

def test_consistency_validation_and_repair():
    """Test detection and repair of inconsistent states"""
```

## Success Criteria

### Technical Success
- ✅ All event change types processed correctly (create, update, delete)
- ✅ Immediate cross-calendar propagation working
- ✅ Zero orphaned busy blocks after event deletions
- ✅ Performance improvement over full-sync approach

### Operational Success
- ✅ Error handling prevents sync failures
- ✅ Consistency validation catches and repairs issues
- ✅ Performance monitoring shows improvement
- ✅ User experience remains seamless

This event change processing system ensures that incremental sync maintains the same reliability as full sync while providing significant performance improvements.
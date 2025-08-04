# Cross-Calendar Impact Analysis - Implementation Task

## Objective

Analyze and implement solutions for cross-calendar busy block management in incremental sync, ensuring proper propagation of changes while maintaining data consistency and preventing orphaned busy blocks.

## Problem Statement

The current full-sync approach ensures cross-calendar consistency by completely rebuilding all busy blocks every sync cycle. Incremental sync introduces complexity:

- **Source-Target Relationships**: Changes in Calendar A must propagate to busy blocks in Calendars B, C, D
- **Deletion Propagation**: When events are deleted, corresponding busy blocks across all calendars must be removed
- **Update Propagation**: Time/title changes must update all related busy blocks
- **Cross-Account Sync**: Events from different Google accounts must sync to each other's calendars

## Current Architecture Analysis

### Existing Cross-Calendar Logic
```python
# From sync_engine.py:312-341
def _create_cross_account_busy_blocks(self, source_calendar: Calendar, target_calendar: Calendar):
    # Enhanced tag pattern includes source account email
    tag_pattern = f"CalSync [source:{source_calendar.calendar_account.email}:{source_calendar.google_calendar_id}:"
    
    # Problem: Full cleanup + recreation approach
    # Solution needed: Incremental updates based on actual changes
```

### Tag System Analysis
```python
# Current tagging system in constants.py
busy_block_description = (
    f"CalSync [source:{source_calendar.calendar_account.email}:"
    f"{source_calendar.google_calendar_id}:{event.google_event_id}]"
)

# Issues:
# 1. 200-character truncation in busy_block_tag field
# 2. Complex parsing required for cleanup operations
# 3. No version tracking for incremental updates
```

## Enhanced Cross-Calendar Implementation

### 1. Improved Busy Block Tracking System

#### Enhanced Database Schema Considerations
```python
# Potential Calendar model enhancements (evaluate need)
class Calendar(models.Model):
    # ... existing fields ...
    
    # Track cross-calendar relationships more efficiently
    busy_block_generation = models.PositiveIntegerField(
        default=1, 
        help_text="Generation counter for busy block versioning"
    )
    
    def increment_busy_block_generation(self):
        """Increment generation for change tracking"""
        self.busy_block_generation += 1
        self.save(update_fields=['busy_block_generation'])
```

#### Enhanced Event Model for Cross-Calendar Tracking
```python
# Potential Event model enhancements
class Event(models.Model):
    # ... existing fields ...
    
    # Enhanced source tracking for better cross-calendar management
    source_calendar_email = models.EmailField(
        blank=True,
        help_text="Email of source calendar account for busy blocks"
    )
    source_calendar_generation = models.PositiveIntegerField(
        default=0,
        help_text="Generation when this busy block was created"
    )
    
    @classmethod
    def create_enhanced_busy_block(cls, source_event, target_calendar):
        """Create busy block with enhanced tracking"""
        busy_block = cls.create_busy_block(source_event, target_calendar)
        
        # Add enhanced tracking
        busy_block.source_calendar_email = source_event.calendar.calendar_account.email
        busy_block.source_calendar_generation = source_event.calendar.busy_block_generation
        
        return busy_block
```

### 2. Cross-Calendar Change Propagation System

#### Real-Time Propagation Engine
```python
class CrossCalendarPropagationEngine:
    """Handles real-time propagation of changes across calendars"""
    
    def __init__(self):
        self.propagation_results = {
            'calendars_updated': 0,
            'busy_blocks_created': 0,
            'busy_blocks_updated': 0,
            'busy_blocks_deleted': 0,
            'errors': []
        }
    
    def propagate_event_change(self, source_event: Event, change_type: str, changes: dict = None):
        """Propagate event changes to all target calendars immediately"""
        
        target_calendars = self._get_target_calendars(source_event)
        
        for target_calendar in target_calendars:
            try:
                if change_type == 'create':
                    self._propagate_new_event(source_event, target_calendar)
                elif change_type == 'update':
                    self._propagate_updated_event(source_event, target_calendar, changes)
                elif change_type == 'delete':
                    self._propagate_deleted_event(source_event, target_calendar)
                    
            except Exception as e:
                error_msg = f"Failed to propagate {change_type} to {target_calendar.name}: {e}"
                logger.error(error_msg)
                self.propagation_results['errors'].append(error_msg)
    
    def _get_target_calendars(self, source_event: Event) -> list[Calendar]:
        """Get all calendars that should receive busy blocks from source event"""
        
        return Calendar.objects.filter(
            calendar_account__user=source_event.calendar.calendar_account.user,
            sync_enabled=True,
            calendar_account__is_active=True
        ).exclude(
            id=source_event.calendar.id
        ).select_related('calendar_account')
    
    def _propagate_new_event(self, source_event: Event, target_calendar: Calendar):
        """Create new busy block in target calendar"""
        
        # Check if busy block already exists (avoid duplicates)
        existing_busy_block = Event.objects.filter(
            calendar=target_calendar,
            source_event=source_event,
            is_busy_block=True
        ).first()
        
        if existing_busy_block:
            logger.debug(f"Busy block already exists in {target_calendar.name}")
            return
        
        # Create the busy block
        busy_block = self._create_busy_block_with_tracking(source_event, target_calendar)
        
        logger.info(f"Created busy block in {target_calendar.name} for new event: {source_event.title}")
        self.propagation_results['busy_blocks_created'] += 1
    
    def _propagate_updated_event(self, source_event: Event, target_calendar: Calendar, changes: dict):
        """Update existing busy block or create if missing"""
        
        existing_busy_block = Event.objects.filter(
            calendar=target_calendar,
            source_event=source_event,
            is_busy_block=True
        ).first()
        
        if not existing_busy_block:
            # Missing busy block - create it
            logger.warning(f"Missing busy block in {target_calendar.name}, creating")
            self._propagate_new_event(source_event, target_calendar)
            return
        
        # Determine what needs updating
        needs_google_update = self._busy_block_needs_google_update(changes)
        
        if needs_google_update:
            # Update in Google Calendar
            self._update_busy_block_in_google(existing_busy_block, source_event, target_calendar)
        
        # Always update database record
        self._update_busy_block_in_database(existing_busy_block, source_event)
        
        logger.info(f"Updated busy block in {target_calendar.name} for event: {source_event.title}")
        self.propagation_results['busy_blocks_updated'] += 1
    
    def _propagate_deleted_event(self, source_event: Event, target_calendar: Calendar):
        """Remove busy block from target calendar"""
        
        busy_blocks = Event.objects.filter(
            calendar=target_calendar,
            source_event=source_event,
            is_busy_block=True
        )
        
        for busy_block in busy_blocks:
            try:
                # Delete from Google Calendar
                client = GoogleCalendarClient(target_calendar.calendar_account)
                success = client.delete_event(
                    target_calendar.google_calendar_id, 
                    busy_block.google_event_id
                )
                
                if success:
                    # Delete from database
                    busy_block.delete()
                    self.propagation_results['busy_blocks_deleted'] += 1
                    logger.info(f"Removed busy block from {target_calendar.name}")
                
            except Exception as e:
                logger.error(f"Failed to delete busy block {busy_block.google_event_id}: {e}")
    
    def _busy_block_needs_google_update(self, changes: dict) -> bool:
        """Determine if busy block needs Google Calendar update"""
        
        google_relevant_changes = ['title', 'start_time', 'end_time', 'description']
        return any(field in changes for field in google_relevant_changes)
    
    def _update_busy_block_in_google(self, busy_block: Event, source_event: Event, target_calendar: Calendar):
        """Update busy block in Google Calendar"""
        
        client = GoogleCalendarClient(target_calendar.calendar_account)
        
        event_data = {
            'summary': BusyBlock.generate_title(source_event.title),
            'start': {'dateTime': source_event.start_time.isoformat()},
            'end': {'dateTime': source_event.end_time.isoformat()},
            'description': busy_block.description  # Keep original description with tracking info
        }
        
        client.update_event(
            target_calendar.google_calendar_id,
            busy_block.google_event_id,
            event_data
        )
    
    def _update_busy_block_in_database(self, busy_block: Event, source_event: Event):
        """Update busy block record in database"""
        
        busy_block.title = BusyBlock.generate_title(source_event.title)
        busy_block.start_time = source_event.start_time
        busy_block.end_time = source_event.end_time
        busy_block.is_meeting_invite = source_event.is_meeting_invite
        busy_block.save()
    
    def _create_busy_block_with_tracking(self, source_event: Event, target_calendar: Calendar) -> Event:
        """Create busy block with enhanced tracking information"""
        
        client = GoogleCalendarClient(target_calendar.calendar_account)
        
        # Generate enhanced description with tracking
        busy_block_title = BusyBlock.generate_title(source_event.title)
        busy_block_description = self._generate_enhanced_description(source_event)
        
        # Create in Google Calendar
        google_event = client.create_busy_block(
            target_calendar.google_calendar_id,
            busy_block_title,
            source_event.start_time,
            source_event.end_time,
            busy_block_description
        )
        
        # Create in database with enhanced tracking
        busy_block = Event.objects.create(
            calendar=target_calendar,
            google_event_id=google_event['id'],
            title=busy_block_title,
            description=busy_block_description,
            start_time=source_event.start_time,
            end_time=source_event.end_time,
            is_busy_block=True,
            is_meeting_invite=source_event.is_meeting_invite,
            source_event=source_event,
            busy_block_tag=BusyBlock.generate_tag(target_calendar.id, source_event.id),
            source_calendar_email=source_event.calendar.calendar_account.email,
            source_calendar_generation=source_event.calendar.busy_block_generation
        )
        
        return busy_block
    
    def _generate_enhanced_description(self, source_event: Event) -> str:
        """Generate enhanced description with better tracking"""
        
        # Include timestamp and generation for better tracking
        timestamp = timezone.now().isoformat()
        generation = source_event.calendar.busy_block_generation
        
        return (
            f"CalSync [source:{source_event.calendar.calendar_account.email}:"
            f"{source_event.calendar.google_calendar_id}:{source_event.google_event_id}:"
            f"gen:{generation}:ts:{timestamp}]"
        )
```

### 3. Orphaned Busy Block Detection and Cleanup

#### Orphan Detection System
```python
class OrphanedBusyBlockDetector:
    """Detects and cleans up orphaned busy blocks"""
    
    def detect_orphaned_busy_blocks(self, calendar: Calendar = None) -> dict:
        """Detect busy blocks that no longer have valid source events"""
        
        query = Event.objects.filter(is_busy_block=True)
        if calendar:
            query = query.filter(calendar=calendar)
        
        orphaned_blocks = []
        
        for busy_block in query.select_related('source_event', 'calendar'):
            if self._is_orphaned(busy_block):
                orphaned_blocks.append(busy_block)
        
        return {
            'orphaned_count': len(orphaned_blocks),
            'orphaned_blocks': orphaned_blocks,
            'calendars_affected': len(set(b.calendar.id for b in orphaned_blocks))
        }
    
    def _is_orphaned(self, busy_block: Event) -> bool:
        """Check if a busy block is orphaned"""
        
        # No source event reference
        if not busy_block.source_event:
            return True
        
        # Source event deleted
        if not Event.objects.filter(id=busy_block.source_event.id).exists():
            return True
        
        # Source calendar no longer sync enabled
        if not busy_block.source_event.calendar.sync_enabled:
            return True
        
        # Source account deactivated
        if not busy_block.source_event.calendar.calendar_account.is_active:
            return True
        
        return False
    
    def cleanup_orphaned_busy_blocks(self, orphaned_blocks: list[Event]) -> dict:
        """Clean up orphaned busy blocks"""
        
        cleanup_results = {
            'google_deleted': 0,
            'database_deleted': 0,
            'errors': []
        }
        
        # Group by calendar for efficient client usage
        blocks_by_calendar = {}
        for block in orphaned_blocks:
            calendar_id = block.calendar.id
            if calendar_id not in blocks_by_calendar:
                blocks_by_calendar[calendar_id] = []
            blocks_by_calendar[calendar_id].append(block)
        
        for calendar_id, blocks in blocks_by_calendar.items():
            try:
                calendar = Calendar.objects.get(id=calendar_id)
                client = GoogleCalendarClient(calendar.calendar_account)
                
                for block in blocks:
                    try:
                        # Delete from Google Calendar
                        success = client.delete_event(
                            calendar.google_calendar_id,
                            block.google_event_id
                        )
                        
                        if success:
                            cleanup_results['google_deleted'] += 1
                        
                        # Delete from database regardless
                        block.delete()
                        cleanup_results['database_deleted'] += 1
                        
                    except Exception as e:
                        error_msg = f"Failed to delete orphaned block {block.google_event_id}: {e}"
                        logger.error(error_msg)
                        cleanup_results['errors'].append(error_msg)
                
            except Exception as e:
                error_msg = f"Failed to process calendar {calendar_id}: {e}"
                logger.error(error_msg)
                cleanup_results['errors'].append(error_msg)
        
        return cleanup_results
```

### 4. Cross-Calendar Consistency Validation

#### Consistency Checker
```python
class CrossCalendarConsistencyChecker:
    """Validates and maintains cross-calendar consistency"""
    
    def validate_consistency(self, user_id: int = None) -> dict:
        """Validate cross-calendar busy block consistency"""
        
        # Get all sync-enabled calendars for user(s)
        calendar_query = Calendar.objects.filter(
            sync_enabled=True,
            calendar_account__is_active=True
        ).select_related('calendar_account')
        
        if user_id:
            calendar_query = calendar_query.filter(calendar_account__user_id=user_id)
        
        calendars = list(calendar_query)
        inconsistencies = []
        
        # Check each source calendar's events
        for source_calendar in calendars:
            source_events = Event.objects.filter(
                calendar=source_calendar,
                is_busy_block=False,  # Only check real events
                start_time__gte=timezone.now(),  # Future events only
                end_time__lte=timezone.now() + timedelta(days=90)
            )
            
            for source_event in source_events:
                target_calendars = [c for c in calendars if c.id != source_calendar.id 
                                 and c.calendar_account.user_id == source_calendar.calendar_account.user_id]
                
                for target_calendar in target_calendars:
                    busy_block_exists = Event.objects.filter(
                        calendar=target_calendar,
                        source_event=source_event,
                        is_busy_block=True
                    ).exists()
                    
                    if not busy_block_exists:
                        inconsistencies.append({
                            'source_event_id': source_event.id,
                            'source_calendar': source_calendar.name,
                            'target_calendar': target_calendar.name,
                            'missing_busy_block': True
                        })
        
        return {
            'consistent': len(inconsistencies) == 0,
            'inconsistencies': inconsistencies,
            'calendars_checked': len(calendars)
        }
    
    def repair_inconsistencies(self, inconsistencies: list[dict]) -> dict:
        """Repair detected inconsistencies"""
        
        repair_results = {
            'repaired': 0,
            'failed': 0,
            'errors': []
        }
        
        propagation_engine = CrossCalendarPropagationEngine()
        
        for inconsistency in inconsistencies:
            try:
                source_event = Event.objects.get(id=inconsistency['source_event_id'])
                target_calendar = Calendar.objects.get(name=inconsistency['target_calendar'])
                
                # Create missing busy block
                propagation_engine._propagate_new_event(source_event, target_calendar)
                repair_results['repaired'] += 1
                
            except Exception as e:
                error_msg = f"Failed to repair inconsistency {inconsistency}: {e}"
                logger.error(error_msg)
                repair_results['errors'].append(error_msg)
                repair_results['failed'] += 1
        
        return repair_results
```

### 5. Integration with Incremental Sync

#### Modified SyncEngine Integration
```python
class SyncEngine:
    def __init__(self):
        # ... existing initialization ...
        self.propagation_engine = CrossCalendarPropagationEngine()
        self.orphan_detector = OrphanedBusyBlockDetector()
        self.consistency_checker = CrossCalendarConsistencyChecker()
    
    def _process_incremental_events(self, calendar: Calendar, events: list[dict]):
        """Enhanced incremental processing with cross-calendar propagation"""
        
        for google_event in events:
            event_id = google_event.get('id')
            event_status = google_event.get('status', 'confirmed')
            
            try:
                if event_status == 'cancelled':
                    self._process_deleted_event_with_propagation(calendar, google_event)
                else:
                    existing_event = Event.objects.filter(
                        calendar=calendar,
                        google_event_id=event_id
                    ).first()
                    
                    if existing_event:
                        changes = self._process_updated_event_with_propagation(
                            calendar, existing_event, google_event
                        )
                    else:
                        self._process_new_event_with_propagation(calendar, google_event)
                        
            except Exception as e:
                logger.error(f"Failed to process event change {event_id}: {e}")
    
    def _process_new_event_with_propagation(self, calendar: Calendar, google_event: dict):
        """Process new event with immediate cross-calendar propagation"""
        
        # Create the event (existing logic)
        event = self._create_event_from_google_data(calendar, google_event)
        
        if event:
            # Immediate propagation to other calendars
            self.propagation_engine.propagate_event_change(event, 'create')
    
    def _process_updated_event_with_propagation(self, calendar: Calendar, existing_event: Event, google_event: dict):
        """Process updated event with cross-calendar change propagation"""
        
        # Detect changes (existing logic)
        changes = self._detect_and_apply_changes(existing_event, google_event)
        
        if changes:
            # Propagate changes to busy blocks
            self.propagation_engine.propagate_event_change(existing_event, 'update', changes)
        
        return changes
    
    def _process_deleted_event_with_propagation(self, calendar: Calendar, google_event: dict):
        """Process deleted event with cross-calendar cleanup"""
        
        event_id = google_event.get('id')
        existing_event = Event.objects.filter(
            calendar=calendar,
            google_event_id=event_id
        ).first()
        
        if existing_event:
            # Propagate deletion to all busy blocks
            self.propagation_engine.propagate_event_change(existing_event, 'delete')
            
            # Delete the source event
            existing_event.delete()
            self.sync_results['events_deleted'] += 1
    
    def _post_sync_consistency_check(self, calendar: Calendar):
        """Run consistency check after incremental sync"""
        
        # Check for orphaned busy blocks
        orphan_results = self.orphan_detector.detect_orphaned_busy_blocks(calendar)
        
        if orphan_results['orphaned_count'] > 0:
            logger.warning(f"Found {orphan_results['orphaned_count']} orphaned busy blocks")
            
            # Clean up orphans
            cleanup_results = self.orphan_detector.cleanup_orphaned_busy_blocks(
                orphan_results['orphaned_blocks']
            )
            
            logger.info(f"Cleaned up {cleanup_results['database_deleted']} orphaned busy blocks")
        
        # Validate consistency
        consistency_results = self.consistency_checker.validate_consistency(
            calendar.calendar_account.user_id
        )
        
        if not consistency_results['consistent']:
            logger.warning(f"Found {len(consistency_results['inconsistencies'])} consistency issues")
            
            # Attempt repairs
            repair_results = self.consistency_checker.repair_inconsistencies(
                consistency_results['inconsistencies']
            )
            
            logger.info(f"Repaired {repair_results['repaired']} consistency issues")
```

## Success Criteria

### Technical Success
- ✅ Real-time cross-calendar propagation working
- ✅ Zero orphaned busy blocks after 24-hour period
- ✅ Consistency validation catches all edge cases
- ✅ Performance better than full-sync approach

### Operational Success  
- ✅ Cross-account sync maintains reliability
- ✅ Error recovery prevents cascade failures
- ✅ Monitoring detects propagation issues
- ✅ User experience remains seamless across calendars

This cross-calendar impact system maintains the reliability of full-sync while enabling the performance benefits of incremental sync.
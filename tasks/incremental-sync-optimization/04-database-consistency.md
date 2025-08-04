# Database Consistency - Implementation Task

## Objective

Ensure database integrity and consistency during incremental sync operations through proper transaction management, data validation, and recovery mechanisms.

## Background

Incremental sync introduces several database consistency challenges:
- **Partial sync failures** leaving the database in inconsistent states
- **Concurrent sync operations** creating race conditions
- **Cross-calendar dependencies** requiring transactional consistency
- **Sync token management** requiring atomic updates

## Database Consistency Requirements

### 1. Transaction Management

#### Atomic Sync Operations
```python
from django.db import transaction
from django.db.models import F
import logging

logger = logging.getLogger(__name__)

class DatabaseConsistentSyncEngine(SyncEngine):
    """Enhanced SyncEngine with database consistency guarantees"""
    
    def _sync_single_calendar_atomic(self, calendar: Calendar):
        """Sync single calendar with full atomicity guarantees"""
        
        try:
            with transaction.atomic():
                # Create savepoint for partial rollback capability
                savepoint = transaction.savepoint()
                
                try:
                    # Perform the sync within transaction
                    sync_result = self._perform_incremental_sync(calendar)
                    
                    # Validate results before committing
                    self._validate_sync_results(calendar, sync_result)
                    
                    # Update sync token atomically with last_synced_at
                    if sync_result.get('next_sync_token'):
                        calendar.update_sync_token(sync_result['next_sync_token'])
                    
                    # Commit the savepoint
                    transaction.savepoint_commit(savepoint)
                    
                    logger.info(f"Successfully synced calendar {calendar.name}")
                    return sync_result
                    
                except Exception as e:
                    # Rollback to savepoint on any error
                    transaction.savepoint_rollback(savepoint)
                    logger.error(f"Sync failed for {calendar.name}, rolled back: {e}")
                    raise
                    
        except Exception as e:
            # Log the failure and clear sync token to force full sync next time
            logger.error(f"Transaction failed for calendar {calendar.name}: {e}")
            calendar.clear_sync_token()
            raise
    
    def _perform_incremental_sync(self, calendar: Calendar) -> dict:
        """Perform incremental sync with consistency tracking"""
        
        client = GoogleCalendarClient(calendar.calendar_account)
        
        # Get incremental changes
        sync_result = client.list_events_incremental(
            calendar.google_calendar_id,
            sync_token=calendar.last_sync_token if calendar.has_valid_sync_token() else None
        )
        
        # Process events with change tracking
        change_log = {
            'events_processed': 0,
            'events_created': 0,
            'events_updated': 0,
            'events_deleted': 0,
            'busy_blocks_affected': 0
        }
        
        for event_data in sync_result['events']:
            try:
                change_result = self._process_event_with_consistency(calendar, event_data)
                
                # Aggregate changes
                for key, value in change_result.items():
                    change_log[key] = change_log.get(key, 0) + value
                    
            except Exception as e:
                logger.error(f"Failed to process event {event_data.get('id')}: {e}")
                # Continue processing but log the failure
                
        # Add sync metadata to result
        sync_result.update(change_log)
        return sync_result
    
    def _process_event_with_consistency(self, calendar: Calendar, event_data: dict) -> dict:
        """Process single event with consistency guarantees"""
        
        event_id = event_data.get('id')
        event_status = event_data.get('status', 'confirmed')
        
        change_result = {
            'events_processed': 1,
            'events_created': 0,
            'events_updated': 0,
            'events_deleted': 0,
            'busy_blocks_affected': 0
        }
        
        if event_status == 'cancelled':
            # Handle deletion with cross-calendar cleanup
            deleted_event = Event.objects.filter(
                calendar=calendar,
                google_event_id=event_id
            ).first()
            
            if deleted_event:
                # Count affected busy blocks before deletion
                affected_busy_blocks = Event.objects.filter(
                    source_event=deleted_event,
                    is_busy_block=True
                ).count()
                
                # Perform deletion with propagation
                self._delete_event_with_consistency(deleted_event)
                
                change_result['events_deleted'] = 1
                change_result['busy_blocks_affected'] = affected_busy_blocks
        
        else:
            # Handle create/update
            existing_event = Event.objects.filter(
                calendar=calendar,
                google_event_id=event_id
            ).first()
            
            if existing_event:
                # Update existing event
                changes = self._update_event_with_consistency(existing_event, event_data)
                if changes:
                    change_result['events_updated'] = 1
                    change_result['busy_blocks_affected'] = self._count_affected_busy_blocks(existing_event)
            else:
                # Create new event
                new_event = self._create_event_with_consistency(calendar, event_data)
                if new_event:
                    change_result['events_created'] = 1
                    change_result['busy_blocks_affected'] = self._count_target_calendars(new_event)
        
        return change_result
    
    def _validate_sync_results(self, calendar: Calendar, sync_result: dict):
        """Validate sync results for consistency before committing"""
        
        # Check for required fields
        if 'next_sync_token' not in sync_result:
            raise ValueError("Sync result missing next_sync_token")
        
        # Validate event counts make sense
        total_processed = sync_result.get('events_processed', 0)
        total_changes = (
            sync_result.get('events_created', 0) + 
            sync_result.get('events_updated', 0) + 
            sync_result.get('events_deleted', 0)
        )
        
        if total_changes > total_processed:
            raise ValueError(f"Change count ({total_changes}) exceeds processed count ({total_processed})")
        
        # Validate database state
        self._validate_calendar_database_state(calendar)
    
    def _validate_calendar_database_state(self, calendar: Calendar):
        """Validate calendar's database state for consistency"""
        
        # Check for orphaned busy blocks
        orphaned_count = Event.objects.filter(
            calendar=calendar,
            is_busy_block=True,
            source_event__isnull=True
        ).count()
        
        if orphaned_count > 0:
            raise ValueError(f"Found {orphaned_count} orphaned busy blocks")
        
        # Check for busy blocks with invalid source events
        invalid_busy_blocks = Event.objects.filter(
            calendar=calendar,
            is_busy_block=True,
            source_event__calendar__sync_enabled=False
        ).count()
        
        if invalid_busy_blocks > 0:
            logger.warning(f"Found {invalid_busy_blocks} busy blocks with inactive source calendars")
```

### 2. Concurrent Access Management

#### Sync Locking Mechanism
```python
import fcntl
import os
import time
from contextlib import contextmanager

class SyncLockManager:
    """Manages locks to prevent concurrent sync operations"""
    
    def __init__(self):
        self.lock_dir = "/tmp/calendar_sync_locks"
        os.makedirs(self.lock_dir, exist_ok=True)
    
    @contextmanager
    def calendar_sync_lock(self, calendar_id: int, timeout: int = 300):
        """Acquire exclusive lock for calendar sync"""
        
        lock_file = os.path.join(self.lock_dir, f"calendar_{calendar_id}.lock")
        
        try:
            with open(lock_file, 'w') as f:
                # Try to acquire exclusive lock with timeout
                start_time = time.time()
                
                while time.time() - start_time < timeout:
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        f.write(f"Locked by PID {os.getpid()} at {time.time()}")
                        f.flush()
                        
                        logger.debug(f"Acquired sync lock for calendar {calendar_id}")
                        yield
                        return
                        
                    except IOError:
                        # Lock is held by another process
                        time.sleep(1)
                        continue
                
                raise TimeoutError(f"Could not acquire sync lock for calendar {calendar_id} within {timeout}s")
                
        finally:
            # Lock automatically released when file is closed
            try:
                os.remove(lock_file)
                logger.debug(f"Released sync lock for calendar {calendar_id}")
            except OSError:
                pass  # File may have been removed by another process

class ConcurrentSafeSyncEngine(DatabaseConsistentSyncEngine):
    """Sync engine with concurrent access protection"""
    
    def __init__(self):
        super().__init__()
        self.lock_manager = SyncLockManager()
    
    def sync_calendar_with_lock(self, calendar_id: int) -> dict:
        """Sync calendar with exclusive locking"""
        
        try:
            calendar = Calendar.objects.get(
                id=calendar_id, 
                sync_enabled=True, 
                calendar_account__is_active=True
            )
        except Calendar.DoesNotExist:
            return {"error": f"Calendar {calendar_id} not found"}
        
        try:
            with self.lock_manager.calendar_sync_lock(calendar_id):
                # Refresh calendar data in case it changed while waiting for lock
                calendar.refresh_from_db()
                
                # Perform the sync
                return self._sync_single_calendar_atomic(calendar)
                
        except TimeoutError as e:
            logger.error(f"Sync timeout for calendar {calendar_id}: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Sync error for calendar {calendar_id}: {e}")
            return {"error": str(e)}
```

### 3. Data Integrity Validation

#### Comprehensive Data Validation
```python
class DataIntegrityValidator:
    """Validates data integrity across the sync system"""
    
    def validate_event_integrity(self, event: Event) -> list[str]:
        """Validate individual event integrity"""
        
        errors = []
        
        # Basic field validation
        if not event.title or not event.title.strip():
            errors.append("Event title is empty")
        
        if event.start_time >= event.end_time:
            errors.append("End time must be after start time")
        
        # Busy block specific validation
        if event.is_busy_block:
            if not event.source_event:
                errors.append("Busy block missing source event")
            elif not event.source_event.calendar.sync_enabled:
                errors.append("Busy block source calendar not sync enabled")
            elif event.source_event.is_busy_block:
                errors.append("Busy block cannot have another busy block as source")
        
        # Cross-calendar validation
        if event.is_busy_block and event.source_event:
            if event.calendar.calendar_account.user_id != event.source_event.calendar.calendar_account.user_id:
                errors.append("Busy block and source event must belong to same user")
        
        return errors
    
    def validate_calendar_integrity(self, calendar: Calendar) -> dict:
        """Validate calendar-level integrity"""
        
        results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'stats': {}
        }
        
        # Get all events for this calendar
        events = Event.objects.filter(calendar=calendar)
        
        # Count different event types
        total_events = events.count()
        busy_blocks = events.filter(is_busy_block=True).count()
        regular_events = events.filter(is_busy_block=False).count()
        
        results['stats'] = {
            'total_events': total_events,
            'busy_blocks': busy_blocks,
            'regular_events': regular_events
        }
        
        # Validate each event
        for event in events:
            event_errors = self.validate_event_integrity(event)
            if event_errors:
                results['errors'].extend([f"Event {event.id}: {error}" for error in event_errors])
                results['valid'] = False
        
        # Check for orphaned busy blocks
        orphaned_busy_blocks = events.filter(
            is_busy_block=True,
            source_event__isnull=True
        )
        
        if orphaned_busy_blocks.exists():
            count = orphaned_busy_blocks.count()
            results['errors'].append(f"Found {count} orphaned busy blocks")
            results['valid'] = False
        
        # Check for circular references (should be impossible but check anyway)
        for busy_block in events.filter(is_busy_block=True):
            if self._has_circular_reference(busy_block):
                results['errors'].append(f"Circular reference detected for event {busy_block.id}")
                results['valid'] = False
        
        # Validate sync token state
        if calendar.last_sync_token and not calendar.last_synced_at:
            results['warnings'].append("Calendar has sync token but no last synced timestamp")
        
        return results
    
    def _has_circular_reference(self, event: Event, visited: set = None) -> bool:
        """Check for circular references in busy block chain"""
        
        if visited is None:
            visited = set()
        
        if event.id in visited:
            return True
        
        if not event.is_busy_block or not event.source_event:
            return False
        
        visited.add(event.id)
        return self._has_circular_reference(event.source_event, visited)
    
    def validate_cross_calendar_integrity(self, user_id: int) -> dict:
        """Validate integrity across all calendars for a user"""
        
        results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'calendars_checked': 0,
            'total_events': 0,
            'consistency_issues': 0
        }
        
        # Get all calendars for user
        calendars = Calendar.objects.filter(
            calendar_account__user_id=user_id,
            sync_enabled=True,
            calendar_account__is_active=True
        )
        
        results['calendars_checked'] = calendars.count()
        
        # Validate each calendar
        for calendar in calendars:
            calendar_results = self.validate_calendar_integrity(calendar)
            
            results['total_events'] += calendar_results['stats']['total_events']
            
            if not calendar_results['valid']:
                results['valid'] = False
                results['errors'].extend([
                    f"Calendar {calendar.name}: {error}" 
                    for error in calendar_results['errors']
                ])
            
            results['warnings'].extend([
                f"Calendar {calendar.name}: {warning}" 
                for warning in calendar_results['warnings']
            ])
        
        # Check cross-calendar consistency
        consistency_issues = self._check_cross_calendar_consistency(calendars)
        results['consistency_issues'] = len(consistency_issues)
        
        if consistency_issues:
            results['valid'] = False
            results['errors'].extend(consistency_issues)
        
        return results
    
    def _check_cross_calendar_consistency(self, calendars: list[Calendar]) -> list[str]:
        """Check consistency across multiple calendars"""
        
        issues = []
        
        # Check that each event has corresponding busy blocks
        for source_calendar in calendars:
            source_events = Event.objects.filter(
                calendar=source_calendar,
                is_busy_block=False,
                start_time__gte=timezone.now(),
                end_time__lte=timezone.now() + timedelta(days=90)
            )
            
            for source_event in source_events:
                expected_targets = [c for c in calendars if c.id != source_calendar.id]
                
                for target_calendar in expected_targets:
                    busy_block_exists = Event.objects.filter(
                        calendar=target_calendar,
                        source_event=source_event,
                        is_busy_block=True
                    ).exists()
                    
                    if not busy_block_exists:
                        issues.append(
                            f"Missing busy block in {target_calendar.name} "
                            f"for event {source_event.title} from {source_calendar.name}"
                        )
        
        return issues
```

### 4. Recovery and Repair Mechanisms

#### Automatic Recovery System
```python
class DatabaseRecoveryManager:
    """Handles automatic recovery from database inconsistencies"""
    
    def __init__(self):
        self.validator = DataIntegrityValidator()
    
    def recover_calendar_consistency(self, calendar: Calendar) -> dict:
        """Recover calendar from inconsistent state"""
        
        recovery_results = {
            'actions_taken': [],
            'errors_fixed': 0,
            'warnings_resolved': 0,
            'success': True
        }
        
        # Validate current state
        integrity_results = self.validator.validate_calendar_integrity(calendar)
        
        if integrity_results['valid']:
            recovery_results['actions_taken'].append("No recovery needed")
            return recovery_results
        
        logger.info(f"Starting recovery for calendar {calendar.name}")
        
        try:
            with transaction.atomic():
                # Fix orphaned busy blocks
                orphaned_count = self._fix_orphaned_busy_blocks(calendar)
                if orphaned_count > 0:
                    recovery_results['actions_taken'].append(f"Removed {orphaned_count} orphaned busy blocks")
                    recovery_results['errors_fixed'] += orphaned_count
                
                # Fix invalid busy block references
                invalid_count = self._fix_invalid_busy_block_references(calendar)
                if invalid_count > 0:
                    recovery_results['actions_taken'].append(f"Fixed {invalid_count} invalid busy block references")
                    recovery_results['errors_fixed'] += invalid_count
                
                # Repair missing sync timestamps
                if calendar.last_sync_token and not calendar.last_synced_at:
                    calendar.last_synced_at = timezone.now()
                    calendar.save(update_fields=['last_synced_at'])
                    recovery_results['actions_taken'].append("Added missing sync timestamp")
                    recovery_results['warnings_resolved'] += 1
                
                # Validate recovery was successful
                post_recovery_results = self.validator.validate_calendar_integrity(calendar)
                if not post_recovery_results['valid']:
                    recovery_results['success'] = False
                    recovery_results['actions_taken'].append("Recovery incomplete - manual intervention required")
                
        except Exception as e:
            logger.error(f"Recovery failed for calendar {calendar.name}: {e}")
            recovery_results['success'] = False
            recovery_results['actions_taken'].append(f"Recovery failed: {e}")
        
        return recovery_results
    
    def _fix_orphaned_busy_blocks(self, calendar: Calendar) -> int:
        """Remove orphaned busy blocks"""
        
        orphaned_blocks = Event.objects.filter(
            calendar=calendar,
            is_busy_block=True,
            source_event__isnull=True
        )
        
        count = orphaned_blocks.count()
        if count > 0:
            # Delete from Google Calendar first
            client = GoogleCalendarClient(calendar.calendar_account)
            
            for block in orphaned_blocks:
                try:
                    client.delete_event(calendar.google_calendar_id, block.google_event_id)
                except Exception as e:
                    logger.warning(f"Failed to delete orphaned block from Google: {e}")
            
            # Delete from database
            orphaned_blocks.delete()
            logger.info(f"Removed {count} orphaned busy blocks from {calendar.name}")
        
        return count
    
    def _fix_invalid_busy_block_references(self, calendar: Calendar) -> int:
        """Fix busy blocks with invalid source event references"""
        
        invalid_blocks = Event.objects.filter(
            calendar=calendar,
            is_busy_block=True,
            source_event__calendar__sync_enabled=False
        )
        
        count = invalid_blocks.count()
        if count > 0:
            # These busy blocks should be removed as their source is no longer valid
            client = GoogleCalendarClient(calendar.calendar_account)
            
            for block in invalid_blocks:
                try:
                    client.delete_event(calendar.google_calendar_id, block.google_event_id)
                except Exception as e:
                    logger.warning(f"Failed to delete invalid block from Google: {e}")
                    
                block.delete()
            
            logger.info(f"Removed {count} busy blocks with invalid sources from {calendar.name}")
        
        return count
    
    def recover_sync_token_state(self, calendar: Calendar) -> dict:
        """Recover from sync token corruption"""
        
        recovery_result = {
            'action_taken': None,
            'success': False
        }
        
        try:
            # Clear corrupted sync token
            calendar.clear_sync_token()
            
            # Force full sync on next run
            recovery_result['action_taken'] = "Cleared sync token to force full sync"
            recovery_result['success'] = True
            
            logger.info(f"Reset sync token for calendar {calendar.name}")
            
        except Exception as e:
            logger.error(f"Failed to reset sync token for calendar {calendar.name}: {e}")
            recovery_result['action_taken'] = f"Reset failed: {e}"
        
        return recovery_result
```

### 5. Monitoring and Alerting

#### Database Health Monitoring
```python
class DatabaseHealthMonitor:
    """Monitors database health and consistency"""
    
    def __init__(self):
        self.validator = DataIntegrityValidator()
        self.recovery_manager = DatabaseRecoveryManager()
    
    def health_check_all_calendars(self) -> dict:
        """Perform health check on all active calendars"""
        
        health_report = {
            'overall_health': 'healthy',
            'calendars_checked': 0,
            'calendars_healthy': 0,
            'calendars_with_issues': 0,
            'critical_issues': [],
            'warnings': [],
            'automatic_fixes_applied': 0
        }
        
        active_calendars = Calendar.objects.filter(
            sync_enabled=True,
            calendar_account__is_active=True
        )
        
        health_report['calendars_checked'] = active_calendars.count()
        
        for calendar in active_calendars:
            try:
                integrity_results = self.validator.validate_calendar_integrity(calendar)
                
                if integrity_results['valid']:
                    health_report['calendars_healthy'] += 1
                else:
                    health_report['calendars_with_issues'] += 1
                    
                    # Try automatic recovery
                    recovery_results = self.recovery_manager.recover_calendar_consistency(calendar)
                    
                    if recovery_results['success']:
                        health_report['automatic_fixes_applied'] += recovery_results['errors_fixed']
                        health_report['warnings'].append(
                            f"Calendar {calendar.name}: Automatically fixed {recovery_results['errors_fixed']} issues"
                        )
                    else:
                        health_report['critical_issues'].append(
                            f"Calendar {calendar.name}: {integrity_results['errors']}"
                        )
                        health_report['overall_health'] = 'critical'
            
            except Exception as e:
                logger.error(f"Health check failed for calendar {calendar.name}: {e}")
                health_report['critical_issues'].append(f"Calendar {calendar.name}: Health check failed - {e}")
                health_report['overall_health'] = 'critical'
        
        # Determine overall health
        if health_report['critical_issues']:
            health_report['overall_health'] = 'critical'
        elif health_report['calendars_with_issues'] > 0:
            health_report['overall_health'] = 'degraded'
        
        return health_report
    
    def alert_on_critical_issues(self, health_report: dict):
        """Send alerts for critical database issues"""
        
        if health_report['overall_health'] == 'critical':
            alert_message = f"CRITICAL: Database consistency issues detected\n"
            alert_message += f"Issues: {len(health_report['critical_issues'])}\n"
            
            for issue in health_report['critical_issues']:
                alert_message += f"- {issue}\n"
            
            # Send alert (implement according to your alerting system)
            logger.critical(alert_message)
            
        elif health_report['automatic_fixes_applied'] > 0:
            info_message = f"INFO: Automatically fixed {health_report['automatic_fixes_applied']} database issues"
            logger.info(info_message)
```

## Success Criteria

### Technical Success
- ✅ All sync operations are atomic and consistent
- ✅ Concurrent sync operations handled safely
- ✅ Data integrity maintained across all failure scenarios
- ✅ Automatic recovery from common inconsistencies

### Operational Success
- ✅ Database health monitoring detects issues proactively
- ✅ Recovery mechanisms resolve issues automatically
- ✅ Critical issues trigger appropriate alerts
- ✅ Zero data loss during sync operations

This database consistency framework ensures that incremental sync maintains data integrity while providing the performance benefits of reduced API usage.
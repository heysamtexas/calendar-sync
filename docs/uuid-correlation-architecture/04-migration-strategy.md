# Migration Strategy for UUID Correlation Architecture

## 🎯 Migration Overview

This document outlines the strategy for migrating from the current fragile text-based event detection to the bulletproof UUID correlation architecture while maintaining zero downtime and data integrity.

## 📋 Migration Phases

### Phase 1: Infrastructure Setup
**Goal**: Establish database schema and core infrastructure without disrupting current system

#### 1.1 Database Schema Migration
```bash
# Create migrations
python manage.py makemigrations calendars --name add_event_state_model
python manage.py makemigrations calendars --name add_correlation_id_to_event
python manage.py makemigrations calendars --name migrate_existing_events_data

# Apply migrations
python manage.py migrate
```

#### 1.2 Deploy Code Infrastructure
- Deploy EventState model
- Deploy CalSyncProperties helper class
- Deploy EventCorrelationManager
- Keep existing sync engine as default

**Success Criteria**:
- [ ] EventState model created successfully
- [ ] All existing Event records have correlation_id populated
- [ ] EventState records created for all existing events
- [ ] No disruption to current sync operations

### Phase 2: Google Calendar Integration
**Goal**: Add ExtendedProperties support and correlation ID tracking to Google Calendar

#### 2.1 Enhanced Google Calendar Client
```python
# Deploy enhanced client with ExtendedProperties support
class GoogleCalendarClient:
    # Add correlation ID methods
    def create_event_with_correlation(self, ...): pass
    def update_event_correlation(self, ...): pass
    def list_events_with_correlation_data(self, ...): pass
```

#### 2.2 Add Correlation IDs to Existing Google Events
```bash
# Run migration command to add correlation IDs to Google Calendar
python manage.py migrate_google_events_correlation_ids --dry-run
python manage.py migrate_google_events_correlation_ids
```

**Migration Command Implementation**:
```python
# management/commands/migrate_google_events_correlation_ids.py
from django.core.management.base import BaseCommand
from apps.calendars.models import Calendar, Event, EventState
from apps.calendars.services.google_calendar_client import GoogleCalendarClient

class Command(BaseCommand):
    help = 'Add correlation IDs to existing Google Calendar events'
    
    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--calendar-id', type=int, help='Specific calendar only')
        parser.add_argument('--batch-size', type=int, default=50, help='Batch size for API calls')
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        calendar_id = options.get('calendar_id')
        batch_size = options['batch_size']
        
        if dry_run:
            self.stdout.write("DRY RUN - No changes will be made")
        
        # Get calendars to migrate
        if calendar_id:
            calendars = Calendar.objects.filter(id=calendar_id, sync_enabled=True)
        else:
            calendars = Calendar.objects.filter(sync_enabled=True, calendar_account__is_active=True)
        
        total_events = 0
        total_updated = 0
        total_errors = 0
        
        for calendar in calendars:
            self.stdout.write(f"Processing calendar: {calendar.name}")
            
            try:
                client = GoogleCalendarClient(calendar.calendar_account)
                
                # Get events that need correlation IDs
                events_needing_correlation = Event.objects.filter(
                    calendar=calendar,
                    correlation_id__isnull=False  # We have correlation ID in DB
                ).select_related('calendar')
                
                # Batch process events
                batch = []
                for event in events_needing_correlation:
                    # Check if Google event already has correlation ID
                    try:
                        google_event = client.get_event(calendar.google_calendar_id, event.google_event_id)
                        
                        if not google_event:
                            self.stdout.write(f"  Event {event.google_event_id} not found in Google Calendar")
                            continue
                        
                        # Check if already has correlation ID
                        from apps.calendars.constants import CalSyncProperties
                        existing_correlation = CalSyncProperties.extract_correlation_id(google_event)
                        
                        if existing_correlation:
                            self.stdout.write(f"  Event {event.google_event_id} already has correlation ID")
                            continue
                        
                        # Add to batch for correlation ID update
                        batch.append({
                            'event_id': event.google_event_id,
                            'correlation_id': str(event.correlation_id),
                            'event_type': 'busy_block' if event.is_busy_block else 'user_event'
                        })
                        
                        # Process batch when it reaches batch_size
                        if len(batch) >= batch_size:
                            self._process_batch(client, calendar, batch, dry_run)
                            total_updated += len(batch)
                            batch = []
                    
                    except Exception as e:
                        self.stdout.write(f"  Error processing event {event.google_event_id}: {e}")
                        total_errors += 1
                    
                    total_events += 1
                
                # Process remaining batch
                if batch:
                    self._process_batch(client, calendar, batch, dry_run)
                    total_updated += len(batch)
                
            except Exception as e:
                self.stdout.write(f"Error processing calendar {calendar.name}: {e}")
                total_errors += 1
        
        # Summary
        self.stdout.write(f"\nMigration Summary:")
        self.stdout.write(f"  Total events processed: {total_events}")
        self.stdout.write(f"  Events updated: {total_updated}")
        self.stdout.write(f"  Errors: {total_errors}")
        
        if dry_run:
            self.stdout.write("DRY RUN completed - use without --dry-run to execute")
    
    def _process_batch(self, client, calendar, batch, dry_run):
        """Process a batch of correlation ID updates"""
        
        if dry_run:
            self.stdout.write(f"  Would update {len(batch)} events with correlation IDs")
            return
        
        try:
            results = client.bulk_add_correlation_ids(calendar.google_calendar_id, batch)
            
            successful = sum(1 for r in results if r['success'])
            failed = len(results) - successful
            
            self.stdout.write(f"  Updated {successful} events, {failed} failed")
            
            # Log failures
            for result in results:
                if not result['success']:
                    self.stdout.write(f"    Failed: {result['event_id']} - {result['error']}")
        
        except Exception as e:
            self.stdout.write(f"  Batch update failed: {e}")
```

**Success Criteria**:
- [ ] All existing Google Calendar events have correlation IDs in ExtendedProperties
- [ ] EventState records match Google Calendar state
- [ ] No events lost or corrupted during migration
- [ ] Current sync operations continue working

### Phase 3: Hybrid Sync Engine Deployment
**Goal**: Deploy new UUID-based sync engine alongside existing engine with feature flag

#### 3.1 Feature Flag Implementation
```python
# settings.py
USE_UUID_CORRELATION_SYNC = os.environ.get('USE_UUID_CORRELATION_SYNC', 'false').lower() == 'true'

# Deploy hybrid sync engine
class HybridSyncEngine:
    def __init__(self):
        self.use_uuid_correlation = settings.USE_UUID_CORRELATION_SYNC
        self.uuid_engine = UUIDCorrelationSyncEngine()
        self.legacy_engine = SyncEngine()
    
    def sync_calendar(self, calendar, webhook_triggered=False):
        if self.use_uuid_correlation:
            return self.uuid_engine.sync_calendar_webhook(calendar)
        else:
            return self.legacy_engine.sync_specific_calendar(calendar.id, webhook_triggered)
```

#### 3.2 Gradual Rollout Plan
```bash
# Stage 1: Deploy code with feature flag OFF
# Verify hybrid engine works in legacy mode
USE_UUID_CORRELATION_SYNC=false

# Stage 2: Enable for single test calendar
# Test UUID correlation on one calendar
python manage.py test_uuid_sync --calendar-id=1

# Stage 3: Enable for small percentage of calendars
# Gradual rollout with monitoring
USE_UUID_CORRELATION_SYNC=true
UUID_SYNC_CALENDAR_PERCENTAGE=10

# Stage 4: Full rollout
USE_UUID_CORRELATION_SYNC=true
UUID_SYNC_CALENDAR_PERCENTAGE=100
```

**Success Criteria**:
- [ ] Hybrid engine deployed successfully
- [ ] Feature flag controls sync engine selection
- [ ] UUID correlation sync works on test calendars
- [ ] No increase in webhook cascade incidents
- [ ] Performance metrics remain stable

### Phase 4: Full Migration and Legacy Cleanup
**Goal**: Complete migration to UUID correlation and remove legacy code

#### 4.1 Full UUID Correlation Rollout
```bash
# Enable UUID correlation for all calendars
USE_UUID_CORRELATION_SYNC=true

# Monitor for 48 hours to ensure stability
# Check metrics:
# - Webhook cascade incidents: 0
# - Sync success rate: >99%
# - Performance degradation: <10%
```

#### 4.2 Legacy Code Removal
```python
# Remove legacy sync engine code
# Remove text-based detection methods
# Remove emoji-based busy block titles
# Clean up legacy constants

# Update BusyBlock constants
class BusyBlock:
    TITLE_PREFIX = "Busy - "  # Clean, no emoji
    
    @staticmethod
    def generate_title(source_title: str) -> str:
        return f"Busy - {source_title}"
    
    @staticmethod
    def is_system_busy_block(google_event: Dict[str, Any]) -> bool:
        # Use UUID correlation only
        from apps.calendars.constants import CalSyncProperties
        return CalSyncProperties.is_busy_block(google_event)
```

**Success Criteria**:
- [ ] All calendars using UUID correlation sync
- [ ] Zero webhook cascade incidents for 7 days
- [ ] Legacy sync engine code removed
- [ ] Clean, maintainable codebase

## 🔄 Rollback Strategy

### Emergency Rollback Procedures

#### Level 1: Feature Flag Rollback
```bash
# Immediate rollback to legacy sync engine
USE_UUID_CORRELATION_SYNC=false

# Monitor for stability return
# Usually resolves issues within 5 minutes
```

#### Level 2: Code Rollback
```bash
# Git rollback to previous stable version
git revert <uuid-correlation-commits>
python manage.py migrate <previous-migration>

# Redeploy previous version
# Database schema changes are backward compatible
```

#### Level 3: Database Rollback
```sql
-- Only if database corruption occurs
-- EventState table can be dropped without affecting Event table
DROP TABLE calendars_eventstate;

-- correlation_id field in Event table can be set to NULL
UPDATE calendars_event SET correlation_id = NULL;
```

### Rollback Decision Criteria

**Trigger Level 1 Rollback if**:
- Webhook cascade incidents increase >50%
- Sync failure rate >5%
- Response time degradation >100%

**Trigger Level 2 Rollback if**:
- Database errors or corruption detected
- Level 1 rollback doesn't resolve issues within 30 minutes
- Data integrity issues found

**Trigger Level 3 Rollback if**:
- Severe database corruption
- Complete system failure
- Data loss detected

## 🧪 Testing Strategy

### Pre-Migration Testing

#### 1. Database Migration Testing
```python
# Test migration on copy of production database
python manage.py test_migrations
python manage.py validate_event_state_migration

# Verify data integrity
python manage.py check_correlation_id_consistency
```

#### 2. Google Calendar Integration Testing
```python
# Test ExtendedProperties functionality
class TestExtendedProperties(TestCase):
    def test_create_event_with_correlation(self):
        # Test correlation ID embedding
        pass
    
    def test_extract_correlation_id(self):
        # Test correlation ID extraction
        pass
    
    def test_bulk_correlation_update(self):
        # Test batch correlation ID updates
        pass
```

#### 3. Sync Engine Testing
```python
# Test UUID correlation sync engine
class TestUUIDCorrelationSync(TestCase):
    def test_webhook_cascade_prevention(self):
        # Verify no cascades with UUID correlation
        pass
    
    def test_user_event_detection(self):
        # Verify proper user event detection
        pass
    
    def test_busy_block_creation(self):
        # Verify correlation ID tracking in busy blocks
        pass
```

### Post-Migration Monitoring

#### 1. Real-time Metrics Dashboard
```python
# Monitor key metrics during migration
metrics = {
    'webhook_cascade_incidents': 0,  # Must remain 0
    'sync_success_rate': 99.5,      # Must stay >99%
    'avg_webhook_processing_time': 2.5,  # Should improve
    'events_stuck_creating': 0,     # Should be 0
    'correlation_id_coverage': 100, # Should be 100%
}
```

#### 2. Automated Alerts
```python
# Set up alerts for migration issues
alerts = [
    {'metric': 'webhook_cascade_incidents', 'threshold': 1, 'action': 'immediate_alert'},
    {'metric': 'sync_success_rate', 'threshold': 95, 'action': 'warning_alert'},
    {'metric': 'events_stuck_creating', 'threshold': 5, 'action': 'investigation_alert'},
]
```

## 📊 Migration Timeline

### Week 1: Infrastructure Preparation
- **Day 1-2**: Database schema migrations
- **Day 3-4**: Deploy EventState model and infrastructure
- **Day 5-7**: Testing and validation of database changes

### Week 2: Google Calendar Integration
- **Day 1-3**: Deploy ExtendedProperties support
- **Day 4-5**: Run correlation ID migration for Google Calendar events
- **Day 6-7**: Validation and testing of Google integration

### Week 3: Hybrid Engine Deployment
- **Day 1-2**: Deploy hybrid sync engine with feature flag OFF
- **Day 3-4**: Enable UUID correlation for test calendars
- **Day 5-7**: Gradual rollout to 50% of calendars

### Week 4: Full Migration
- **Day 1-2**: Enable UUID correlation for all calendars
- **Day 3-5**: Monitor stability and performance
- **Day 6-7**: Remove legacy code and finalize migration

## 🔒 Risk Mitigation

### High-Risk Areas

#### 1. Google API Rate Limits
**Risk**: Migration may trigger rate limits during bulk correlation ID updates

**Mitigation**:
- Implement exponential backoff
- Batch operations with delays
- Monitor API quota usage
- Prepare rate limit override requests

#### 2. Database Performance
**Risk**: New EventState queries may impact performance

**Mitigation**:
- Add strategic database indexes
- Monitor query performance
- Implement connection pooling
- Cache correlation ID lookups

#### 3. Data Consistency
**Risk**: Mismatch between EventState and Google Calendar state

**Mitigation**:
- Implement consistency checks
- Add data validation commands
- Monitor sync discrepancies
- Automated cleanup procedures

### Low-Risk Areas

#### 1. Webhook Processing
**Risk**: UUID correlation may affect webhook processing time

**Mitigation**:
- Performance testing shows minimal impact
- UUID lookups are O(1) operations
- Database indexes optimize queries

#### 2. User Experience
**Risk**: Users may notice busy block title changes (no emojis)

**Mitigation**:
- Title changes are cosmetic only
- "Busy - " prefix remains clear
- Functionality is identical

## ✅ Success Criteria

### Technical Success Metrics
- [ ] Zero webhook cascade incidents for 7 consecutive days
- [ ] Sync success rate >99.5%
- [ ] Webhook processing time <3 seconds average
- [ ] 100% correlation ID coverage for all events
- [ ] Zero data integrity issues

### Operational Success Metrics
- [ ] Zero production incidents during migration
- [ ] Successful rollback capability demonstrated
- [ ] Team trained on new architecture
- [ ] Documentation updated and complete
- [ ] Monitoring and alerting operational

### Business Success Metrics
- [ ] User-reported sync issues reduced by >90%
- [ ] Support tickets related to sync problems <5/week
- [ ] System reliability >99.9% uptime
- [ ] Customer satisfaction scores maintain or improve

This migration strategy ensures a safe, monitored transition to the UUID correlation architecture while maintaining system stability and data integrity throughout the process.
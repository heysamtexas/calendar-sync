# Sync Token Foundation - Implementation Task

## Objective

Modify the GoogleCalendarClient to support incremental sync using Google Calendar sync tokens, with robust error handling and fallback mechanisms.

## Background

Google Calendar API supports incremental sync via sync tokens:
- **First sync:** `events().list()` returns all events + `nextSyncToken`
- **Subsequent syncs:** `events().list(syncToken=lastToken)` returns only changes + new `nextSyncToken`
- **Token lifespan:** ~7 days of inactivity, invalidated by major changes

## Implementation Requirements

### 1. GoogleCalendarClient Modifications

#### Current Method Signature
```python
def list_events(self, calendar_id: str, time_min: datetime, time_max: datetime, max_results: int = 250) -> list[dict]
```

#### New Method Required
```python
def list_events_incremental(
    self, 
    calendar_id: str, 
    sync_token: str = None,
    time_min: datetime = None,
    time_max: datetime = None
) -> dict[str, any]:
    """
    List events incrementally using sync tokens
    
    Returns:
    {
        'events': [list of event objects],
        'next_sync_token': 'token_for_next_sync',
        'is_full_sync': True/False,
        'total_events': int
    }
    """
```

#### Implementation Logic Flow

```python
def list_events_incremental(self, calendar_id, sync_token=None, time_min=None, time_max=None):
    service = self._get_service()
    
    try:
        if sync_token:
            # Incremental sync
            request_params = {
                'calendarId': calendar_id,
                'syncToken': sync_token,
                'maxResults': 2500,  # Higher limit for bulk changes
                'singleEvents': True
            }
            is_full_sync = False
        else:
            # Full sync (first time or fallback)
            request_params = {
                'calendarId': calendar_id,
                'timeMin': time_min.isoformat() if time_min else None,
                'timeMax': time_max.isoformat() if time_max else None,
                'maxResults': 250,
                'singleEvents': True,
                'orderBy': 'startTime'
            }
            is_full_sync = True
            
        # Execute API call with pagination support
        all_events = []
        page_token = None
        
        while True:
            if page_token:
                request_params['pageToken'] = page_token
                
            response = service.events().list(**request_params).execute()
            events = response.get('items', [])
            all_events.extend(events)
            
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        
        return {
            'events': all_events,
            'next_sync_token': response.get('nextSyncToken'),
            'is_full_sync': is_full_sync,
            'total_events': len(all_events)
        }
        
    except HttpError as e:
        # Handle sync token errors
        if e.resp.status == 410:  # Gone - sync token expired
            logger.warning(f"Sync token expired for calendar {calendar_id}, falling back to full sync")
            return self.list_events_incremental(calendar_id, sync_token=None, time_min=time_min, time_max=time_max)
        elif e.resp.status == 400:  # Bad Request - invalid sync token
            logger.warning(f"Invalid sync token for calendar {calendar_id}, falling back to full sync")
            return self.list_events_incremental(calendar_id, sync_token=None, time_min=time_min, time_max=time_max)
        else:
            logger.error(f"Failed to list events for calendar {calendar_id}: {e}")
            raise
```

### 2. Calendar Model Token Management

#### Update Calendar Model Methods
```python
class Calendar(models.Model):
    # ... existing fields
    last_sync_token = models.CharField(max_length=500, blank=True, help_text="Token for incremental sync")
    
    def update_sync_token(self, new_token: str):
        """Safely update sync token with validation"""
        if new_token and len(new_token.strip()) > 0:
            self.last_sync_token = new_token.strip()
            self.last_synced_at = timezone.now()
            self.save(update_fields=['last_sync_token', 'last_synced_at'])
            logger.debug(f"Updated sync token for calendar {self.name}: {new_token[:20]}...")
        else:
            logger.warning(f"Attempted to save empty sync token for calendar {self.name}")
    
    def clear_sync_token(self):
        """Clear sync token to force full sync"""
        self.last_sync_token = ""
        self.save(update_fields=['last_sync_token'])
        logger.info(f"Cleared sync token for calendar {self.name} - will do full sync next time")
    
    def has_valid_sync_token(self) -> bool:
        """Check if calendar has a potentially valid sync token"""
        return bool(self.last_sync_token and self.last_sync_token.strip())
```

### 3. SyncEngine Integration

#### Modify _sync_single_calendar Method
```python
def _sync_single_calendar(self, calendar: Calendar):
    """Sync events for a single calendar using incremental sync"""
    client = GoogleCalendarClient(calendar.calendar_account)
    
    try:
        # Attempt incremental sync if token available
        if calendar.has_valid_sync_token():
            logger.info(f"Performing incremental sync for calendar {calendar.name}")
            sync_result = client.list_events_incremental(
                calendar.google_calendar_id,
                sync_token=calendar.last_sync_token
            )
        else:
            logger.info(f"Performing full sync for calendar {calendar.name} (no sync token)")
            # Get time range for full sync
            time_min = timezone.now() - timedelta(days=30)
            time_max = timezone.now() + timedelta(days=90)
            
            sync_result = client.list_events_incremental(
                calendar.google_calendar_id,
                sync_token=None,
                time_min=time_min,
                time_max=time_max
            )
        
        # Process the events
        events = sync_result['events']
        is_full_sync = sync_result['is_full_sync']
        next_sync_token = sync_result['next_sync_token']
        
        logger.info(f"Retrieved {len(events)} events ({'full' if is_full_sync else 'incremental'} sync) for {calendar.name}")
        
        # Process events (existing logic adapted for incremental)
        if is_full_sync:
            self._process_full_sync_events(calendar, events)
        else:
            self._process_incremental_events(calendar, events)
        
        # Update sync token for next time
        if next_sync_token:
            calendar.update_sync_token(next_sync_token)
        else:
            logger.warning(f"No sync token returned for calendar {calendar.name}")
            
    except Exception as e:
        logger.error(f"Sync failed for calendar {calendar.name}: {e}")
        # Clear sync token on persistent errors to force full sync next time
        calendar.clear_sync_token()
        raise
```

## Error Handling Strategy

### 1. Sync Token Expiration (410 Gone)
- **Trigger:** Token older than ~7 days
- **Response:** Automatic fallback to full sync
- **Recovery:** Generate new token from full sync
- **Logging:** Warning level (expected scenario)

### 2. Invalid Sync Token (400 Bad Request)
- **Trigger:** Corrupted or invalid token
- **Response:** Clear token, fallback to full sync
- **Recovery:** Generate new token from full sync  
- **Logging:** Warning level (recoverable error)

### 3. Rate Limiting (429 Too Many Requests)
- **Trigger:** API quota exceeded
- **Response:** Exponential backoff retry
- **Recovery:** Retry after delay, then fail if persistent
- **Logging:** Error level (needs attention)

### 4. Network/Service Errors (5xx)
- **Trigger:** Google service unavailable
- **Response:** Retry with backoff
- **Recovery:** Fail after max retries, preserve sync token
- **Logging:** Error level (temporary issue)

## Testing Requirements

### 1. Unit Tests
```python
def test_incremental_sync_with_valid_token():
    """Test incremental sync returns only changed events"""
    
def test_incremental_sync_token_expired():
    """Test graceful fallback when sync token expires"""
    
def test_incremental_sync_invalid_token():
    """Test recovery from corrupted sync token"""
    
def test_sync_token_storage_and_retrieval():
    """Test database operations for sync tokens"""
```

### 2. Integration Tests
```python
def test_end_to_end_incremental_sync():
    """Test complete sync cycle with token management"""
    
def test_fallback_to_full_sync():
    """Test fallback behavior under various error conditions"""
    
def test_concurrent_sync_token_updates():
    """Test race conditions in token updates"""
```

### 3. Performance Tests
- Measure API call reduction (target: >80%)
- Validate sync completion time improvement
- Test with large change sets (100+ events)
- Verify memory usage with paginated results

## Migration Strategy

### Phase 1: Implementation
1. Add new `list_events_incremental` method
2. Update Calendar model methods
3. Add comprehensive error handling
4. Create unit tests

### Phase 2: Integration
1. Modify SyncEngine to use incremental method
2. Add incremental event processing logic
3. Implement fallback mechanisms
4. Add integration tests

### Phase 3: Deployment
1. Deploy with feature flag (disabled)
2. Validate in development environment
3. Enable for single test calendar
4. Gradual rollout to all calendars

## Monitoring and Alerts

### Key Metrics
- **Sync token expiration rate** (target: <5% per day)
- **Full sync fallback rate** (target: <10% of syncs)
- **API call reduction** (target: >80% reduction)
- **Sync completion time** (target: <30 seconds)

### Alert Conditions
- High sync token expiration rate (>10% per hour)
- Persistent API errors (>5% error rate)
- Performance degradation (sync time >60 seconds)
- Fallback rate spike (>20% fallbacks)

## Dependencies

### Code Dependencies
- Existing GoogleCalendarClient class
- Calendar model with last_sync_token field
- SyncEngine event processing logic
- Error logging infrastructure

### External Dependencies
- Google Calendar API v3
- Stable network connectivity
- Database transaction support
- Feature flag system (optional)

## Success Criteria

### Technical Success
- ✅ Sync token storage and rotation working reliably
- ✅ Graceful error handling for all identified scenarios
- ✅ API call reduction >80% in normal operation
- ✅ Zero data loss during incremental sync
- ✅ Performance improvement in sync completion time

### Operational Success
- ✅ Monitoring dashboard showing sync health
- ✅ Alert system for sync failures
- ✅ Documentation for troubleshooting
- ✅ Rollback procedure tested and verified

This foundation enables the incremental sync system while maintaining reliability through comprehensive error handling and fallback mechanisms.
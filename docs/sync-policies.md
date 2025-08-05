# Calendar Sync Policies

This document defines the behavioral policies for calendar synchronization in the Calendar Bridge system.

## "Gone Gone" Toggle Policy

### Overview

The "Gone Gone" policy ensures that when a calendar's sync is disabled, it is **completely removed** from the sync ecosystem, providing intuitive user experience and clean testing capabilities.

### User Mental Model

- **Sync OFF** = "Remove this calendar from all sync relationships"
- **Sync ON** = "Start fresh sync based on current reality"

This matches user expectations: toggling sync off should make the calendar "gone gone" from the sync system.

## Toggle OFF Behavior ("Gone Gone")

When a calendar's sync is **disabled**, the system performs complete cleanup:

### 1. Local Database Cleanup
- Delete **all EventState records** for this calendar
- Removes both user events and busy blocks from local database
- Clears sync history and UUID correlations

### 2. Outbound Cleanup (This Calendar → Others)
- Find all busy blocks in **other calendars** that were created from this calendar's events
- Delete those busy blocks from other calendars' **Google Calendars**
- Delete those busy block **EventState records** from database
- Complete removal of this calendar's "footprint" in other calendars

### 3. Google Calendar Cleanup
- Delete busy blocks from Google Calendar using Google Calendar API
- Ensures visual calendar view is cleaned up
- Maintains consistency between database and Google Calendar

### 4. Complete Isolation
- Calendar becomes completely isolated from sync system
- No traces remain in any other calendar
- Clean slate for potential re-enabling

## Toggle ON Behavior ("Current Reality Resurrection")

When a calendar's sync is **enabled**, the system starts fresh:

### 1. Fresh Event Discovery
- Scan calendar's **current Google Calendar events** (ignore history)
- Process events through normal UUID correlation sync engine
- Create new EventState records for current events

### 2. Outbound Sync
- Create busy blocks in **other sync-enabled calendars**
- Based only on events that currently exist in Google Calendar
- Uses fresh UUID correlation (no memory of previous state)

### 3. Inbound Sync  
- Scan **other calendars' current events**
- Create busy blocks in this calendar from other calendars' current events
- Fresh start, no memory of what busy blocks used to exist

### 4. No Historical Memory
- System ignores any previous sync state
- Only deals with "current reality" as seen in Google Calendar
- Avoids complex conflict resolution scenarios

## Policy Benefits

### User Experience
- ✅ **Intuitive behavior** matches user mental model
- ✅ **Predictable results** - toggle off means "gone", toggle on means "fresh start"
- ✅ **No mysterious artifacts** from previous sync states
- ✅ **Clear cause and effect** relationship

### Technical Benefits
- ✅ **Perfect testing environment** - toggle off/on gives clean test cases
- ✅ **No database pollution** from old sync relationships
- ✅ **Simple conflict resolution** - users see conflicts immediately
- ✅ **Easier debugging** - clean state transitions

### Architectural Compatibility
- ✅ **Maintains UUID correlation** for active syncs
- ✅ **Database-first approach** preserved
- ✅ **Cascade prevention** through UUID identification during cleanup
- ✅ **Guilfoyle's YOLO principles** maintained

## Edge Cases Handled

### Time-Based Scenarios
- **Event deleted while sync off**: No busy block created when toggled on ✅
- **Event added while sync off**: Busy block created when toggled on ✅  
- **Recurring events**: Current instances get busy blocks ✅

### Conflict Scenarios
- **Double-booking conflicts**: User sees conflicts immediately and resolves manually ✅
- **Cross-calendar dependencies**: Based on current reality only ✅

### Data Integrity
- **Orphaned busy blocks**: Prevented by bidirectional cleanup ✅
- **UUID correlation**: Maintains integrity for active relationships ✅
- **Audit trail**: Preserved for active events, cleaned for disabled calendars ✅

## Implementation Notes

### Cleanup Order
1. **Database cleanup** first (EventState records)
2. **Google Calendar cleanup** second (visual calendar)
3. **Cross-calendar cleanup** third (other calendars' busy blocks)

### Error Handling
- Cleanup operations are **transactional** where possible
- Google Calendar API failures don't prevent database cleanup
- Partial cleanup is logged for troubleshooting

### Performance Considerations
- Cleanup is performed **synchronously** during toggle operation
- May cause brief delay for calendars with many events
- Acceptable trade-off for clean user experience

## Alternative Policies Considered

### "Lightweight Toggle" (Previous Behavior)
- Only flip `sync_enabled` flag
- Keep all EventState records intact
- **Rejected**: Confusing user experience, poor testing

### "Pause Mode"
- Disable sync but keep relationships for quick resume
- **Rejected**: Complex state management, unclear user benefit

### "Selective Cleanup"
- Allow user to choose cleanup level
- **Rejected**: Too complex for typical use cases

## Configuration

The "Gone Gone" policy is the default behavior. For advanced use cases, it can be controlled via:

```python
# settings.py
CALENDAR_SYNC_TOGGLE_OFF_CLEANUP = True  # Default: "Gone Gone" mode
```

Set to `False` for lightweight toggle behavior (not recommended for production).

---

**Policy Established**: 2025-08-05  
**Implementation Status**: In Development  
**Approval**: Guilfoyle's YOLO Principles Compliant ✅
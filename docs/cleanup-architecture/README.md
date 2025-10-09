# Cleanup Architecture

This folder documents the async cleanup patterns and implementations used throughout the Calendar Bridge system.

## Overview

The Calendar Bridge system implements a "Gone Gone" policy - when sync is disabled, all traces should be completely removed from both the local system and Google Calendar. This requires careful async cleanup operations to handle external API calls and data consistency.

## Core Principles

1. **Immediate User Feedback** - Users see instant response (account disabled, etc.)
2. **Security First** - Revoke tokens/permissions immediately when disconnecting
3. **Async Processing** - Use background commands for Google Calendar API cleanup
4. **Graceful Failure** - Continue operations even if some cleanup steps fail
5. **Reuse Proven Patterns** - Leverage existing cleanup logic where possible

## Cleanup Patterns

### Pattern 1: Bulk Calendar Cleanup with Deferred Account Deletion
**Used for:** Account disconnection
**Documentation:** [01-account-disconnection-fix.md](01-account-disconnection-fix.md)

**Flow:**
1. Immediate security action (revoke tokens)
2. Immediate UX feedback (mark account inactive) 
3. Mark all related calendars for async cleanup (`cleanup_pending=True`)
4. Background command processes calendar cleanups
5. When all calendars cleaned up → delete account

**Key Benefits:**
- Reuses existing calendar cleanup logic
- No new state machines or coordination complexity
- Clear failure modes and recovery paths

### Pattern 2: Individual Calendar Toggle Cleanup
**Used for:** Individual calendar sync disable
**Implementation:** Existing `cleanup_pending` system

**Flow:**
1. Set `sync_enabled=False, cleanup_pending=True`  
2. Background command processes cleanup (removes busy blocks from Google Calendar)
3. Clear `cleanup_pending=False` when complete

## Commands and Scheduling

### `cleanup_disabled_calendars` 
**Schedule:** Every 15 minutes
**Purpose:** Process both individual calendar cleanups and account deletions
**Location:** `src/apps/calendars/management/commands/cleanup_disabled_calendars.py`

**Recommended Cron:**
```bash
*/15 * * * * cd /path/to/project && uv run python src/manage.py cleanup_disabled_calendars
```

## Implementation History

- **2025-08-12** - Account disconnection fix implemented
  - Problem: Account deletion left orphaned busy blocks in Google Calendar
  - Solution: Bulk calendar cleanup with deferred account deletion
  - Result: **FAILED** - Implementation had critical timing flaw

- **2025-08-12** - Production failure and architectural pivot  
  - Issue: OAuth tokens revoked before Google cleanup completed
  - Root cause: Premature account deletion in cleanup cycle
  - Guilfoyle consultation: "Stop making async operations appear synchronous"
  - New approach: Account-level state machine with background processing

## Future Patterns

This architecture provides a foundation for other async cleanup operations:
- Webhook cleanup during account deletion
- Token cleanup during security incidents  
- Bulk operations for calendar management
- Event cleanup during calendar resets

## Related Documentation

- **[sync-policies.md](../sync-policies.md)** - "Gone Gone" policy definition
- **[uuid-correlation-architecture/](../uuid-correlation-architecture/)** - Core sync patterns
- **[testing-architecture/](../testing-architecture/)** - Testing patterns for cleanup operations
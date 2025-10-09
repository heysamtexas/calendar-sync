# Fix Account Disconnection - Gone Gone Policy Implementation

## Problem Statement

Account disconnection currently does immediate `account.delete()` which CASCADE deletes local database records but **leaves orphaned busy blocks in Google Calendar**. This violates our "Gone Gone" principle where disabled sync should completely remove all traces from the sync ecosystem.

**Current Flow (BROKEN):**
1. User clicks "Disconnect Account"
2. `oauth_service.disconnect_account()` calls `account.delete()`
3. CASCADE delete removes all local data instantly
4. **Google Calendar still contains "Busy - Event Title" blocks** ❌
5. No way to track or clean up these orphaned blocks

**Inconsistency:**
- Individual calendar toggle: Uses "Gone Gone" async cleanup via `cleanup_pending=True`
- Account disconnect: Immediate deletion, no Google cleanup

## Solution (Guilfoyle-Approved)

Implement account disconnection as **"bulk calendar cleanup with deferred account deletion"** - reusing existing proven patterns instead of complex state management.

**New Flow (FIXED):**
1. User clicks "Disconnect Account"
2. Revoke OAuth tokens immediately (security)
3. Set `is_active=False` (immediate UX feedback)
4. Mark ALL account calendars with `sync_enabled=False, cleanup_pending=True`
5. User sees "Account disconnected, cleanup in progress"
6. Cleanup command (runs every 15 minutes) processes calendar cleanups
7. When ALL account calendars have `cleanup_pending=False`, delete the account
8. Result: Complete "Gone Gone" cleanup with no orphaned blocks ✅

## Implementation Tasks

### TASK-1: Modify OAuth Service (HIGH PRIORITY)
**File:** `/src/apps/accounts/services/oauth_service.py`
**Current:** `disconnect_account()` does immediate `account.delete()`
**New:** Use bulk calendar cleanup pattern

**Changes:**
```python
def disconnect_account(self, account_id):
    try:
        account = CalendarAccount.objects.get(id=account_id, user=self.user)
        
        # 1. Security first - revoke tokens immediately
        from apps.calendars.services.token_manager import revoke_token
        revoke_token(account)
        
        # 2. User feedback - mark as inactive immediately  
        account.is_active = False
        account.save(update_fields=['is_active'])
        
        # 3. Bulk calendar cleanup - use existing proven logic
        calendars_marked = 0
        for calendar in account.calendars.filter(sync_enabled=True):
            calendar.sync_enabled = False
            calendar.cleanup_pending = True
            calendar.cleanup_requested_at = timezone.now()
            calendar.save(update_fields=['sync_enabled', 'cleanup_pending', 'cleanup_requested_at'])
            calendars_marked += 1
        
        return {
            "success": True,
            "message": f"Account {account.email} disconnected. Cleanup of {calendars_marked} calendars in progress - busy blocks will be removed within 30 minutes."
        }
        
    except CalendarAccount.DoesNotExist:
        raise ResourceNotFoundError(f"Account {account_id} not found")
```

**Key Benefits:**
- Reuses existing `cleanup_pending` logic (proven and tested)
- Immediate security (tokens revoked)
- Immediate UX feedback (account appears disconnected)
- No new database fields or state machines needed

### TASK-2: Enhance Cleanup Command (MEDIUM PRIORITY)
**File:** `/src/apps/calendars/management/commands/cleanup_disabled_calendars.py`
**Current:** Only processes individual calendars
**New:** Add account deletion check after calendar cleanup

**Changes:**
```python
def handle(self, *args, **options):
    # Existing calendar cleanup logic...
    self._process_calendar_cleanups()
    
    # NEW: Check for accounts ready for deletion
    self._process_account_deletions()

def _process_account_deletions(self):
    """Delete inactive accounts where all calendars have completed cleanup"""
    from apps.calendars.models import CalendarAccount
    
    # Find inactive accounts with no pending calendar cleanups
    ready_accounts = CalendarAccount.objects.filter(
        is_active=False
    ).annotate(
        pending_calendars=Count('calendars', filter=Q(calendars__cleanup_pending=True))
    ).filter(pending_calendars=0)
    
    deleted_count = 0
    for account in ready_accounts:
        try:
            # Cancel any remaining webhooks before deletion
            self._cancel_account_webhooks(account)
            
            email = account.email
            calendar_count = account.calendars.count()
            
            account.delete()  # CASCADE handles the rest
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Deleted account {email} ({calendar_count} calendars cleaned up)"
                )
            )
            deleted_count += 1
            
        except Exception as e:
            self.logger.error(f"Failed to delete account {account.id}: {e}")
    
    if deleted_count > 0:
        self.stdout.write(f"Deleted {deleted_count} completed account disconnections")

def _cancel_account_webhooks(self, account):
    """Cancel webhooks for account before deletion"""
    # Implementation for webhook cancellation
    pass
```

### TASK-3: Reconnection Prevention (LOW PRIORITY)
**File:** `/src/apps/accounts/services/oauth_service.py`
**Current:** No prevention during cleanup
**New:** Block reconnection while `is_active=False`

**Changes:**
```python
def _check_existing_account(self, google_account_id):
    """Check if account already exists and handle reconnection"""
    try:
        existing_account = CalendarAccount.objects.get(
            user=self.user,
            google_account_id=google_account_id
        )
        
        if not existing_account.is_active:
            # Account is being disconnected - prevent reconnection
            return {
                "exists": True,
                "can_reconnect": False,
                "message": "This account is being disconnected. Please wait for cleanup to complete before reconnecting."
            }
            
        return {
            "exists": True, 
            "can_reconnect": True,
            "account": existing_account
        }
        
    except CalendarAccount.DoesNotExist:
        return {"exists": False}
```

### TASK-4: UI Updates (MEDIUM PRIORITY)
**File:** `/src/templates/dashboard/account_detail.html`
**Current:** Shows binary Active/Inactive
**New:** Show disconnection status

**Changes:**
```html
<!-- Account status display -->
{% if account.is_active %}
    <span class="badge bg-success">Active</span>
{% else %}
    {% if account.calendars.all|length > 0 %}
        {% with pending_count=account.calendars.all|pending_cleanup_count %}
        {% if pending_count > 0 %}
            <span class="badge bg-warning">Disconnecting ({{ pending_count }} calendars cleaning up)</span>
        {% else %}
            <span class="badge bg-secondary">Disconnected (cleanup complete)</span>
        {% endif %}
        {% endwith %}
    {% else %}
        <span class="badge bg-secondary">Disconnected</span>
    {% endif %}
{% endif %}
```

### TASK-5: Cron Schedule Documentation (LOW PRIORITY)
**File:** `/CLAUDE.md`
**Current:** No cleanup command in cron
**New:** Document 15-minute cleanup schedule

**Changes:**
```bash
# Add to existing cron setup
*/15 * * * * cd /home/user/src/calendar-bridge-clone && uv run python src/manage.py cleanup_disabled_calendars
```

## Progress Tracking

- [ ] **TASK-1**: OAuth service bulk cleanup (HIGH) - **IN PROGRESS**
- [ ] **TASK-2**: Enhanced cleanup command (MEDIUM) 
- [ ] **TASK-3**: Reconnection prevention (LOW)
- [ ] **TASK-4**: UI status updates (MEDIUM)
- [ ] **TASK-5**: Cron documentation (LOW)

## Testing Requirements

### Happy Path Test
1. Connect account with 2-3 calendars
2. Create events in calendars (generate busy blocks in other calendars)
3. Disconnect account
4. Verify account shows as "Disconnecting" 
5. Wait for cleanup command (or run manually)
6. Verify all busy blocks removed from Google Calendar
7. Verify account deleted from database

### Edge Cases
1. **Reconnection during cleanup**: Should be blocked with clear message
2. **Cleanup command failure**: Account should remain inactive, retry next cycle
3. **Webhook cancellation failure**: Should log error but continue with deletion
4. **Partial calendar cleanup**: Some calendars clean up, others fail

## Implementation Notes

**Why This Approach Works:**
- **Single Source of Truth**: Calendar cleanup state is the only state that matters
- **Reuses Proven Logic**: Leverages existing calendar cleanup that already works  
- **Simple Failure Modes**: Failed calendar cleanups already have retry logic
- **No State Coordination**: No complex async coordination between account and calendar state

**Guilfoyle's Seal of Approval:**
> "Your proposed solution works but creates unnecessary complexity. Use bulk calendar disconnection with deferred account cleanup. Keep the state model simple and reuse existing proven logic. The best engineering solution is often the boring one that reuses working patterns."

## Success Criteria

✅ **No orphaned busy blocks** - Account disconnection removes all traces from Google Calendar  
✅ **Consistent behavior** - Same "Gone Gone" policy as individual calendar toggles  
✅ **Simple state management** - Reuses existing `cleanup_pending` logic  
✅ **User-friendly experience** - Clear status and timing expectations  
✅ **Robust error handling** - Graceful degradation when cleanup fails  

---

**Last Updated:** 2025-08-12  
**Status:** Implementation in progress  
**Estimated Completion:** 2-3 hours implementation + testing
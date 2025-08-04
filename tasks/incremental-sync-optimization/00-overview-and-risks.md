# Incremental Sync Optimization - Overview and Risk Analysis

## Executive Summary

The Calendar Sync Tool currently uses **naive full-sync polling** that creates and deletes identical busy blocks every 15 minutes, resulting in ~26,000 Google Calendar API calls per day. This document outlines implementing **incremental sync** using Google Calendar sync tokens to reduce API usage by 90%+ while maintaining reliability.

## Current State Analysis

### Polling-Based Architecture Problems
- **136 busy blocks created + 136 deleted = 272 API calls per sync**
- **96 syncs per day (every 15 minutes) = 26,112 API calls/day**
- **Pure waste:** Recreating identical busy blocks continuously
- **API limit risk:** Already at 3% of daily quota with single user
- **Scalability crisis:** 10 users would consume 26% of daily quota

### Existing Infrastructure (Ready for Incremental)
- ✅ `last_sync_token` field exists in Calendar model (unused)
- ✅ GoogleCalendarClient has event CRUD operations
- ✅ Cross-calendar busy block system established
- ✅ Error handling and logging framework in place

## Incremental Sync Benefits

### API Usage Reduction
- **Current:** 26,112 calls/day (272 per sync × 96 syncs)
- **Projected:** 1,920 calls/day (20 per sync × 96 syncs)
- **Reduction:** 92% fewer API calls
- **Scalability:** Can support 50+ users within same quota

### Performance Improvements
- **Faster syncs:** Only process actual changes
- **Reduced load:** Less database operations
- **Better UX:** Near real-time updates instead of batch processing
- **Lower costs:** Reduced server resources and API quota usage

## Critical Edge Cases and Risks

### 🚨 **Risk Category 1: Cross-Calendar Dependencies**

**Problem:** Calendar A changes → Must update busy blocks in Calendars B, C, D
**Current Solution:** Full cleanup/recreation ensures consistency
**Incremental Challenge:** How to propagate changes across calendar boundaries?

**Specific Scenarios:**
1. **Event deleted in Calendar A** → Busy blocks in B, C, D become orphaned
2. **Event time changed in Calendar A** → Busy blocks in B, C, D show wrong times
3. **New event in Calendar A** → No busy blocks created in B, C, D

**Mitigation Strategy:**
- Track source-target relationships in busy block metadata
- Implement change propagation system
- Add periodic orphan cleanup as safety net

### 🚨 **Risk Category 2: Sync Token Fragility**

**Google Calendar Sync Token Limitations:**
- **Expire after ~7 days** of inactivity
- **Invalidated by "too many changes"** (undefined threshold)
- **Network issues** can corrupt token state
- **Account changes** can reset token validity

**Failure Scenarios:**
1. Token expires → API returns 410 Gone → Must do full sync
2. Invalid token → API returns 400 Bad Request → Must reset and full sync
3. Rate limiting during incremental → Partial sync state corruption

**Mitigation Strategy:**
- Graceful fallback to full sync on token errors
- Implement token refresh/validation logic
- Add sync state validation and recovery

### 🚨 **Risk Category 3: Event Deletion Complexity**

**Google Calendar Deletion Behavior:**
- Deleted events return as `status: "cancelled"` in incremental sync
- Need to find ALL corresponding busy blocks across ALL calendars
- Current tag system has 200-character truncation issues

**Complex Scenarios:**
1. **Recurring event series deleted** → Multiple busy blocks across multiple calendars
2. **Event exception deleted** → Partial series cleanup needed
3. **Tag truncation** → Cannot find all related busy blocks

**Mitigation Strategy:**
- Enhance busy block tagging system for better tracking
- Implement robust cleanup queries
- Add validation for incomplete cleanup operations

### 🚨 **Risk Category 4: Race Conditions and Concurrency**

**Current Architecture Assumptions:**
- Sequential calendar processing
- No concurrent modifications during sync
- Single-threaded busy block creation

**Incremental Sync Challenges:**
1. **Multiple calendars sync independently** → Timing dependencies broken
2. **User makes changes during sync** → Incremental state corruption
3. **Multiple sync processes** → Database consistency issues

**Mitigation Strategy:**
- Implement proper database transactions
- Add sync state locking mechanisms
- Design atomic operations for critical paths

### 🚨 **Risk Category 5: Data Integrity and Consistency**

**Current Safety Mechanisms:**
- Full cleanup ensures no orphaned data
- Complete recreation guarantees consistency
- Time-bounded sync windows (30 days past, 90 days future)

**Incremental Risks:**
1. **Partial sync failures** → Inconsistent state across calendars
2. **Database corruption** → Sync tokens out of sync with reality
3. **Time window violations** → Processing irrelevant old changes

**Mitigation Strategy:**
- Add comprehensive data validation
- Implement consistency check procedures
- Design rollback mechanisms for failed syncs

## Success Criteria

### Phase 1 (Foundation)
- ✅ Sync token storage and rotation working
- ✅ Graceful fallback to full sync on errors
- ✅ API call reduction >80% in normal operation

### Phase 2 (Reliability)
- ✅ Cross-calendar change propagation working
- ✅ Zero orphaned busy blocks after 24 hours
- ✅ Handles all deletion scenarios correctly

### Phase 3 (Production Ready)
- ✅ Multi-user operation without race conditions
- ✅ Recovery from all identified failure scenarios
- ✅ Performance monitoring and alerting

## Implementation Approach

### Phased Rollout Strategy
1. **Development implementation** with extensive testing
2. **Single-user deployment** with monitoring
3. **Gradual expansion** to multiple users
4. **Full production deployment** with fallback capability

### Rollback Plan
- Feature flag to disable incremental sync
- Immediate fallback to current full-sync polling
- Data integrity validation tools
- Emergency full-sync trigger capability

## Next Steps

This overview provides the foundation for detailed implementation tasks:
1. **Sync Token Foundation** (01-sync-token-foundation.md)
2. **Event Change Processing** (02-event-change-processing.md)
3. **Cross-Calendar Impact** (03-cross-calendar-impact.md)
4. **Database Consistency** (04-database-consistency.md)
5. **Testing Strategy** (05-testing-strategy.md)

## Review Requirements

### Technical Review (Guilfoyle)
- Architectural soundness of incremental approach
- Code complexity analysis and optimization opportunities
- Performance implications and bottleneck identification
- Security considerations for sync token handling

### Documentation Review (Copywriter)
- Clarity of technical concepts for future developers
- Completeness of edge case documentation
- Standardization of terminology and format
- User-facing impact documentation
# Core Models & Authentication Tasks

## Overview
Implement the core data models and Google OAuth authentication system.

## Priority: HIGH (Required for all sync functionality)

---

## TASK-008: User Model Extension
**Status:** Not Started  
**Estimated Time:** 30 minutes  
**Dependencies:** TASK-004 (Django Settings)  

### Description
Extend Django's default User model for calendar sync specific needs.

### Acceptance Criteria
- [ ] Custom User model created (if needed) or profile model
- [ ] User model supports multiple calendar accounts
- [ ] Database migration created and applied
- [ ] Admin interface configured for user management
- [ ] Basic user authentication working

### Implementation Notes
- Consider using Django's default User model with a Profile model
- Plan for future user preferences and settings
- Ensure compatibility with Django admin

---

## TASK-009: CalendarAccount Model
**Status:** Not Started  
**Estimated Time:** 60 minutes  
**Dependencies:** TASK-008  

### Description
Create the CalendarAccount model to store OAuth credentials per Google account.

### Acceptance Criteria
- [ ] CalendarAccount model created with fields:
  - [ ] `user` - ForeignKey to User
  - [ ] `google_account_id` - Unique Google account identifier
  - [ ] `email` - Google account email
  - [ ] `access_token` - Encrypted OAuth access token
  - [ ] `refresh_token` - Encrypted OAuth refresh token
  - [ ] `token_expires_at` - Token expiration timestamp
  - [ ] `is_active` - Boolean for enabling/disabling sync
  - [ ] `created_at`, `updated_at` - Timestamps
- [ ] Model includes token encryption/decryption methods
- [ ] Database migration created and applied
- [ ] Admin interface configured
- [ ] Model validation and constraints added

### Implementation Notes
- Use Django's encryption utilities for token storage
- Ensure tokens are never logged or exposed
- Add proper indexes for performance
- Include methods for token refresh logic

---

## TASK-010: Calendar Model
**Status:** Not Started  
**Estimated Time:** 45 minutes  
**Dependencies:** TASK-009  

### Description
Create the Calendar model to represent individual Google calendars.

### Acceptance Criteria
- [ ] Calendar model created with fields:
  - [ ] `calendar_account` - ForeignKey to CalendarAccount
  - [ ] `google_calendar_id` - Google's calendar ID
  - [ ] `name` - Calendar display name
  - [ ] `description` - Calendar description
  - [ ] `color` - Calendar color
  - [ ] `is_primary` - Boolean for primary calendar
  - [ ] `sync_enabled` - Boolean for enabling sync
  - [ ] `created_at`, `updated_at` - Timestamps
- [ ] Database migration created and applied
- [ ] Admin interface configured
- [ ] Unique constraints added
- [ ] String representation method

### Implementation Notes
- Ensure unique constraint on (calendar_account, google_calendar_id)
- Add methods for sync management
- Consider caching frequently accessed calendars

---

## TASK-011: Event Model with Tagging
**Status:** Not Started  
**Estimated Time:** 90 minutes  
**Dependencies:** TASK-010  

### Description
Create the Event model to represent both real events and system-created busy blocks.

### Acceptance Criteria
- [ ] Event model created with fields:
  - [ ] `calendar` - ForeignKey to Calendar
  - [ ] `google_event_id` - Google's event ID
  - [ ] `title` - Event title
  - [ ] `description` - Event description
  - [ ] `start_time` - Event start datetime
  - [ ] `end_time` - Event end datetime
  - [ ] `is_all_day` - Boolean for all-day events
  - [ ] `is_busy_block` - Boolean to identify system-created blocks
  - [ ] `source_event` - ForeignKey to source Event (for busy blocks)
  - [ ] `busy_block_tag` - Unique tag for safe identification
  - [ ] `created_at`, `updated_at` - Timestamps
- [ ] Model validation for time ranges
- [ ] Busy block tagging system implemented
- [ ] Database migration created and applied
- [ ] Admin interface configured

### Implementation Notes
- Implement busy block tag format: "CalSync [source:cal123:event456]"
- Add validation to prevent time conflicts
- Include methods for busy block creation and identification
- Ensure proper indexing for time-based queries

---

## TASK-012: SyncLog Model
**Status:** Not Started  
**Estimated Time:** 30 minutes  
**Dependencies:** TASK-010  

### Description
Create the SyncLog model to track sync operations and errors.

### Acceptance Criteria
- [ ] SyncLog model created with fields:
  - [ ] `calendar_account` - ForeignKey to CalendarAccount
  - [ ] `sync_type` - CharField (full, incremental, manual)
  - [ ] `status` - CharField (success, error, partial)
  - [ ] `events_processed` - Integer count
  - [ ] `events_created` - Integer count
  - [ ] `events_updated` - Integer count
  - [ ] `events_deleted` - Integer count
  - [ ] `error_message` - TextField (nullable)
  - [ ] `started_at` - Sync start time
  - [ ] `completed_at` - Sync completion time
- [ ] Database migration created and applied
- [ ] Admin interface configured
- [ ] Cleanup method for old logs

### Implementation Notes
- Include performance metrics for monitoring
- Add log retention policy (e.g., keep 30 days)
- Ensure sensitive information is not logged

---

## TASK-013: OAuth Flow Implementation
**Status:** Not Started  
**Estimated Time:** 120 minutes  
**Dependencies:** TASK-009, TASK-005 (Google Console setup)  

### Description
Implement Google OAuth 2.0 authentication flow for calendar access.

### Acceptance Criteria
- [ ] OAuth views created:
  - [ ] `initiate_oauth` - Start OAuth flow
  - [ ] `oauth_callback` - Handle OAuth callback
  - [ ] `oauth_disconnect` - Remove account access
- [ ] OAuth state parameter validation
- [ ] Error handling for OAuth failures
- [ ] Token storage using CalendarAccount model
- [ ] Automatic token refresh mechanism
- [ ] Proper scope requesting (Google Calendar access)
- [ ] Security measures (CSRF protection, state validation)

### Implementation Notes
- Use Google's official OAuth libraries
- Implement proper error handling and user feedback
- Ensure tokens are stored securely
- Add rate limiting for OAuth endpoints
- Test with multiple Google accounts

---

## TASK-014: Token Refresh System
**Status:** Not Started  
**Estimated Time:** 60 minutes  
**Dependencies:** TASK-013  

### Description
Implement automatic OAuth token refresh functionality.

### Acceptance Criteria
- [ ] Token refresh method in CalendarAccount model
- [ ] Automatic refresh before token expiration
- [ ] Error handling for refresh failures
- [ ] Background task for proactive token refresh
- [ ] Logging for token refresh operations
- [ ] Fallback for expired refresh tokens
- [ ] User notification for auth failures

### Implementation Notes
- Refresh tokens before they expire (5-10 minutes buffer)
- Handle cases where refresh token is invalid
- Implement retry logic with exponential backoff
- Ensure thread safety for concurrent access

---

## TASK-015: Model Tests
**Status:** Not Started  
**Estimated Time:** 90 minutes  
**Dependencies:** TASK-014  

### Description
Create comprehensive tests for all models and authentication.

### Acceptance Criteria
- [ ] Test cases for CalendarAccount model:
  - [ ] Token encryption/decryption
  - [ ] Token refresh functionality
  - [ ] Model validation
- [ ] Test cases for Calendar model:
  - [ ] Unique constraints
  - [ ] Sync enable/disable
- [ ] Test cases for Event model:
  - [ ] Busy block tagging
  - [ ] Time validation
  - [ ] Source event relationships
- [ ] Test cases for SyncLog model
- [ ] OAuth flow integration tests
- [ ] Token refresh tests
- [ ] All tests passing with good coverage

### Implementation Notes
- Use Django's TestCase class
- Mock external API calls
- Test both success and failure scenarios
- Ensure tests are fast and reliable

---

## Summary
Total estimated time: **8.5 hours**  
Critical path: TASK-008 → TASK-009 → TASK-010 → TASK-011 → TASK-013 → TASK-014  
Parallel work: TASK-012 and TASK-015 can be done alongside other tasks
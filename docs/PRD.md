# Calendar Sync Tool - Product Requirements Document

## Executive Summary

**Product Name:** Calendar Sync Tool  
**Version:** MVP 1.0  
**Target:** Personal calendar synchronization for individual users  

**Problem:** Users with multiple Google Calendar accounts experience double-bookings because events in one calendar don't block availability in others.

**Solution:** Self-hosted Django application that automatically syncs events across multiple Google Calendar accounts by creating "busy" blocks, preventing scheduling conflicts.

## Market Analysis

**Existing Solutions:**
- **OneCal:** $60+/year, focused on teams, over-featured for individual use
- **CalendarBridge:** Premium pricing, includes AI features not needed for basic sync
- **OGCS:** Free but Windows-only, requires app to stay running

**Market Gap:** No affordable, simple, self-hosted solution for individual users who just want basic calendar sync without ongoing subscription costs.

## Product Vision

Enable individuals to seamlessly manage multiple Google Calendar accounts without double-booking conflicts through automated, bi-directional synchronization.

## User Personas

**Primary User:** Individual professional with multiple Google Calendar accounts (work, personal, side projects) who experiences scheduling conflicts and needs a simple, cost-effective sync solution.

## Core User Flows

### Setup Flow
1. User deploys application via Docker
2. User connects first Google Calendar account via OAuth
3. User connects second Google Calendar account
4. User selects which calendars to sync with each other
5. System begins automatic bi-directional syncing

### Daily Usage Flow
1. User creates event in Calendar A
2. System detects new event within 5 minutes
3. System automatically creates "busy" block in Calendar B
4. External scheduling tools see both calendars as unavailable
5. Double-booking is prevented

### Management Flow
1. User accesses web dashboard
2. User views sync status and recent activity
3. User can pause/resume sync for specific calendars
4. User can perform reset operations when needed

## Functional Requirements

### Must Have (MVP)
- **Google OAuth Integration:** Secure authentication with multiple Google accounts
- **Bi-directional Calendar Sync:** Events in Calendar A create busy blocks in Calendar B, and vice versa
- **Automatic Polling:** Check for new/updated/deleted events every 5 minutes
- **Busy Block Management:** Create, update, and delete busy blocks automatically
- **Web Dashboard:** Simple interface for setup, monitoring, and management
- **Reset Functionality:** Remove all system-created busy blocks safely
- **Docker Deployment:** Single-command deployment and management

### Should Have (Phase 2)
- **Multiple Calendar Support:** Sync across 3+ calendars simultaneously
- **Selective Sync Rules:** Choose which types of events to sync
- **Manual Sync Trigger:** Force immediate sync when needed
- **Enhanced Dashboard:** Better sync status monitoring and logs

### Could Have (Future)
- **Microsoft Outlook Support:** Extend to Outlook calendars
- **iCloud Support:** Support for Apple Calendar via CalDAV
- **Scheduling Page:** Public page showing combined availability
- **Custom Busy Block Titles:** Personalize busy block appearance

## Technical Requirements

### Architecture
- **Framework:** Django web application
- **Task Processing:** Simple Django management command run on external schedule (cron/systemd timer)
- **Authentication:** Google OAuth 2.0
- **Database:** SQLite (sufficient for single-user application)
- **Deployment:** Docker containerization
- **Sync Frequency:** 5-minute polling intervals

### Provider Support Strategy
- **Phase 1:** Google Calendar only
- **Future:** Extensible architecture supporting multiple calendar providers
- **Provider Abstraction:** Design allows adding Outlook and iCloud without architectural changes

## Sync Logic & Conflict Resolution

### Sync Strategy
- **Source of Truth:** Each calendar owns its original events
- **Sync Direction:** Bi-directional (events in any calendar create busy blocks in all others)
- **Busy Block Identification:** System-generated events tagged with unique identifiers
- **Conflict Resolution:** Busy blocks can overlap, no complex conflict resolution needed

### Edge Cases
- **Duplicate Events:** Sync from first detected calendar only
- **Rate Limiting:** Implement exponential backoff for API limits
- **Sync Failures:** Log errors, retry on next cycle, don't break other syncs
- **Network Issues:** Graceful degradation and automatic recovery

## Reset & Cleanup Functionality

### Reset Options
1. **Soft Reset:** Pause sync, leave existing busy blocks
2. **Clean Calendar:** Remove all system-created busy blocks from selected calendar
3. **Complete Reset:** Remove all busy blocks, reset all sync relationships

### Safety Features
- **Busy Block Tagging:** All auto-created events identifiable by system markers
- **User Confirmation:** Multi-step confirmation for destructive actions
- **Audit Trail:** Track which events were created by the system
- **Selective Operations:** Reset specific calendars without affecting others

## Success Metrics & Acceptance Criteria

### MVP Launch Criteria
- Single user can connect 2+ Google Calendar accounts
- Bi-directional sync works (Calendar A ↔ Calendar B)
- User can pause/resume sync per calendar
- User can perform clean reset without deleting real events
- Basic web dashboard functional
- Docker deployment works on fresh system

### Success Validation
- Events successfully create corresponding busy blocks
- System operates for 7+ days without manual intervention
- Reset functions only remove system-created events
- OAuth integration handles token refresh automatically

## Development Phases

### Phase 1: MVP (2-3 weeks)
- Google OAuth integration
- Basic bi-directional sync between 2 calendars
- Simple web dashboard
- Core reset functionality
- Docker deployment configuration

### Phase 2: Enhancement (1-2 weeks)
- Support for 3+ calendars
- Enhanced dashboard with sync monitoring
- Improved error handling and logging
- Advanced reset options

### Phase 3: Future Expansion
- Microsoft Outlook calendar support
- iCloud calendar support via CalDAV
- Public scheduling pages
- Advanced sync rules and filtering

## Risks & Mitigation

### Technical Risks
- **Google API Rate Limits:** Mitigate with exponential backoff and efficient polling
- **Token Expiration:** Implement automatic refresh token handling
- **Data Loss:** Comprehensive tagging system prevents accidental deletion of user events

### Product Risks
- **User Adoption:** Simple setup flow and clear value proposition
- **Scope Creep:** Strict MVP focus, defer advanced features to later phases

## Dependencies

### External Services
- Google Calendar API
- Google OAuth 2.0 service

### Technical Stack
- Django framework
- External scheduling (cron/systemd timer)
- SQLite database
- Docker containerization

## Conclusion

This Calendar Sync Tool addresses a clear market gap for individual users seeking affordable, self-hosted calendar synchronization. The MVP focuses on core functionality with Google Calendar, while the architecture supports future expansion to additional providers. The bi-directional sync approach and robust reset capabilities ensure users can safely manage their calendar ecosystem without fear of data loss or scheduling conflicts.
# Technical Context & Research Findings

## Google Calendar API Research

### Rate Limits
- **Google Calendar API:** Generous quotas per project/user per minute
- **Best Practices:** Use exponential backoff, randomize sync timing across users
- **Polling Strategy:** 5-minute intervals are well within safe limits

### Authentication
- **OAuth 2.0 Flow:** Standard Google OAuth with refresh tokens
- **Scopes Needed:** `https://www.googleapis.com/auth/calendar` (read/write access)
- **Token Management:** Automatic refresh token handling required

### Python Libraries
- **google-auth:** For OAuth handling
- **google-auth-oauthlib:** For OAuth flow
- **google-auth-httplib2:** For HTTP transport
- **google-api-python-client:** For Calendar API calls

## Architecture Decisions

### Why Django Management Command + Cron
- **Simplicity:** No additional infrastructure (Redis/Celery)
- **Debuggability:** Easy to run manually, clear logs
- **Deployment:** Single container, external cron handles scheduling
- **Example:** `*/5 * * * * docker exec app python manage.py sync_calendars`

### Why SQLite
- **Single User:** No concurrency concerns
- **Low Volume:** Sync every 5 minutes, minimal writes
- **Deployment:** No separate DB container needed
- **Migration Path:** Django ORM makes switching to Postgres trivial later

### Provider Abstraction Strategy
- **Abstract Base Class:** CalendarProviderClient with common interface
- **Provider-Specific Implementations:** GoogleCalendarClient, etc.
- **Data Models:** Provider-agnostic Event/Calendar models
- **Future-Proofing:** Add Outlook/iCloud without architectural changes

## Key Technical Requirements

### Busy Block Identification
- **Tagging Strategy:** Unique identifier in event title/description
- **Example:** "🔒 Busy - CalSync [source:cal123:event456]"
- **Safety:** Only delete events with our specific tags

### Sync Logic
- **Bi-directional:** Events in any calendar create busy blocks in all others
- **Event Mapping:** Track source event → busy block relationships
- **Conflict Resolution:** Allow overlaps, no complex merging

### Error Handling
- **Rate Limits:** Exponential backoff with jitter
- **Network Failures:** Retry on next cycle, don't cascade failures
- **Auth Failures:** Clear error messages, re-auth flow

## Development Environment

### Required Environment Variables
```
# Using django-environ for environment management
GOOGLE_OAUTH_CLIENT_ID=your_client_id
GOOGLE_OAUTH_CLIENT_SECRET=your_client_secret
SECRET_KEY=your_secret_key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

### Docker Strategy
- **Single Container:** Django app with SQLite
- **Volume Mounts:** Persist database and logs
- **Port Mapping:** 8000:8000 for web interface
- **External Cron:** Host system schedules sync command

### Project Structure
```
calendar-sync/
├── docs/
│   ├── PRD.md
│   └── TECHNICAL_CONTEXT.md
├── src/
│   ├── calendar_sync/          # Django project
│   ├── apps/
│   │   ├── calendars/          # Calendar models and sync logic
│   │   ├── accounts/           # User authentication
│   │   └── dashboard/          # Web interface
│   └── Dockerfile
├── pyproject.toml              # Dependencies and tool configuration
└── docker-compose.yml
```

## Next Steps for Implementation

1. **Django Project Setup:** Create basic project structure
2. **Google OAuth Integration:** Implement authentication flow
3. **Calendar Models:** Create provider-agnostic data models
4. **Google Calendar Client:** Implement API wrapper
5. **Sync Command:** Create management command for syncing
6. **Web Dashboard:** Basic interface for setup and monitoring
7. **Docker Configuration:** Containerize application

## Testing Strategy

### Manual Testing
- Connect 2 Google accounts with multiple calendars
- Create events in Calendar A, verify busy blocks in Calendar B
- Test reset functionality with real data
- Verify OAuth token refresh works

### Edge Cases to Test
- Rate limiting scenarios
- Network connectivity issues
- Simultaneous events across calendars
- Large calendar with many events
- Token expiration and refresh

## Security Considerations

- **Token Storage:** Encrypt OAuth tokens in database
- **Scope Minimization:** Only request necessary Google Calendar permissions
- **Input Validation:** Sanitize all calendar data
- **HTTPS Only:** Force SSL in production
- **Secret Management:** Use environment variables for sensitive data

## Performance Considerations

- **Incremental Sync:** Only fetch events modified since last sync
- **Batch Operations:** Group API calls where possible
- **Database Indexing:** Index frequently queried fields
- **Logging:** Structured logging for monitoring and debugging
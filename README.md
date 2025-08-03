# Calendar Sync Tool

A self-hosted Django application for syncing events across multiple Google Calendar accounts to prevent double-booking.

## Quick Overview

**Problem:** Multiple Google Calendar accounts causing double-booking conflicts  
**Solution:** Bi-directional sync creating "busy" blocks across calendars  
**Scope:** Single-user, self-hosted, Google Calendar only (MVP)

## Key Features

- **Multi-Account Support:** Connect multiple Google Calendar accounts via OAuth
- **Bi-directional Sync:** Events in Calendar A automatically create busy blocks in Calendar B
- **Automatic Operation:** 5-minute polling via external cron job
- **Web Dashboard:** Simple interface for setup and monitoring
- **Safe Reset:** Only removes system-created busy blocks, never user events
- **Docker Ready:** Single-command deployment

## Quick Start

1. **Prerequisites:** Python 3.11+, Docker (optional)
2. **Setup:** Follow the [Getting Started Guide](docs/GETTING_STARTED.md)
3. **Deploy:** Use Docker or run locally with uv

## Technical Stack

- **Framework:** Django 4.2+
- **Database:** SQLite (sufficient for single-user)
- **Authentication:** Google OAuth 2.0
- **Scheduling:** External cron + Django management command
- **Deployment:** Docker container

## Documentation

### Getting Started
- **[Getting Started Guide](docs/GETTING_STARTED.md)** - Step-by-step setup instructions
- **[Product Requirements](docs/PRD.md)** - Complete product specification
- **[Technical Context](docs/TECHNICAL_CONTEXT.md)** - Architecture decisions and API research

### For AI Development
- **[CLAUDE.md](CLAUDE.md)** - AI agent command guidelines and development protocols
- **[Task Overview](tasks/00-task-overview.md)** - Detailed development task breakdown

## How It Works

1. **Connect:** Authenticate with multiple Google accounts via OAuth
2. **Sync:** Events created in any connected calendar automatically create "busy" blocks in all other calendars
3. **Prevent:** Double-booking is prevented because all calendars show your actual availability
4. **Manage:** Web dashboard lets you monitor sync status and manage connections

## Installation

### Prerequisites
- Python 3.11 or higher
- Google Cloud Console account
- Docker (optional, for deployment)

### Basic Setup
```bash
# Clone and navigate to project
git clone <repository-url>
cd calendar-sync-tool

# Install dependencies with uv
uv sync --all-extras

# Set up environment variables
cp .env.example .env
# Edit .env with your Google OAuth credentials

# Run migrations and start server
cd src/
uv run python manage.py migrate
uv run python manage.py runserver
```

For detailed setup instructions, see [Getting Started Guide](docs/GETTING_STARTED.md).

## Basic Usage

1. **Connect Accounts:** Visit the web dashboard and connect your Google Calendar accounts
2. **Automatic Sync:** Events sync every 5 minutes automatically via cron job
3. **Monitor:** Check sync status and logs in the dashboard
4. **Reset:** Use reset functionality to clean system-created busy blocks if needed

## Common Commands

```bash
# Run sync manually
uv run python manage.py sync_calendars

# Reset a specific calendar (removes only system-created blocks)
uv run python manage.py reset_calendar --calendar-id=<id>

# Run tests
uv run python manage.py test

# Start development server
uv run python manage.py runserver
```

## Architecture Overview

### Why This Approach?
- **Simple:** No Redis/Celery complexity - just Django + SQLite + cron
- **Reliable:** External cron scheduling is battle-tested and debuggable
- **Safe:** Tagged busy blocks prevent accidental deletion of real events
- **Extensible:** Provider-agnostic design supports future Outlook/iCloud integration

### Key Design Decisions
- **Provider-agnostic data models** for future calendar service support
- **Explicit busy block tagging** enables safe cleanup operations
- **OAuth token management** with automatic refresh handling
- **Fail-safe reset operations** that never touch user's real events

## Development Phases

### Phase 1: Foundation
- Django project setup and basic models
- Google OAuth authentication flow
- Core data structures for calendar sync

### Phase 2: Core Sync Logic
- Google Calendar API integration
- Bi-directional sync engine implementation
- Management commands for automated syncing

### Phase 3: Web Interface & Deployment
- Web dashboard for monitoring and management
- Docker containerization
- Production deployment configuration

## Troubleshooting

### Common Issues
- **OAuth Problems:** Check redirect URI in Google Console matches exactly
- **Sync Not Working:** Run `python manage.py sync_calendars --verbose` for detailed logs
- **Rate Limiting:** Check sync logs for exponential backoff implementation
- **Docker Database:** Ensure SQLite file is in mounted volume for persistence

### Getting Help
- Check the [Getting Started Guide](docs/GETTING_STARTED.md) for detailed setup
- Review [Technical Context](docs/TECHNICAL_CONTEXT.md) for architecture decisions
- See task files in `tasks/` directory for detailed implementation guidance

## License

[Add your license information here]
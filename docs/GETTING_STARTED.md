# Getting Started Guide

This guide will walk you through setting up the Calendar Sync Tool from scratch.

## Prerequisites

Before you begin, ensure you have:

- **Python 3.11 or higher** - Check with `python --version`
- **uv package manager** - Install from [docs.astral.sh/uv](https://docs.astral.sh/uv/)
- **Google Cloud Console account** - For OAuth credentials
- **Git** - For version control
- **Docker** (optional) - For containerized deployment

## System Requirements

- Operating System: Linux, macOS, or Windows
- Memory: 512MB RAM minimum
- Storage: 100MB for application + dependencies
- Network: Internet connection for Google Calendar API access

## Google Cloud Console Setup

You need to create OAuth credentials for Google Calendar API access.

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Create Project"
3. Name it something like "calendar-sync-tool"
4. Click "Create"

### Step 2: Enable Google Calendar API

1. In your new project, go to **APIs & Services > Library**
2. Search for "Google Calendar API"
3. Click on it and click **Enable**

### Step 3: Create OAuth Credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth 2.0 Client ID**
3. If prompted, configure the OAuth consent screen:
   - User Type: External (for personal use)
   - App name: "Calendar Sync Tool"
   - User support email: Your email
   - Developer contact: Your email
4. Create the OAuth client ID:
   - Application type: **Web application**
   - Name: "Calendar Sync OAuth Client"
   - Authorized redirect URIs: `http://localhost:8000/auth/callback/`
   
   **Important:** The redirect URI must match exactly including the trailing slash.

5. Click **Create**
6. **Save the Client ID and Client Secret** - you'll need these for the application setup

### Step 4: Note Your Credentials

Write down or save these values:
- Client ID (starts with something like `123456789-abc...googleusercontent.com`)
- Client Secret (random string of characters)

You'll add these to your `.env` file in the next section.

## Project Setup

Now let's set up the Calendar Sync Tool on your local machine.

### Step 1: Download and Install Dependencies

```bash
# Clone the repository (or navigate to your project directory)
git clone <repository-url>
cd calendar-sync-tool

# Install dependencies with uv
uv sync --all-extras
```

This will:
- Create a virtual environment in `.venv/`
- Install all Python dependencies from `pyproject.toml`
- Set up development tools (ruff, coverage, etc.)

### Step 2: Create Environment Configuration

Create a `.env` file with your Google OAuth credentials:

```bash
# Navigate to the source directory
cd src/

# Create environment file
cp .env.example .env
```

Edit the `.env` file and add your Google OAuth credentials:

```
DEBUG=True
SECRET_KEY=your-secret-key-here
GOOGLE_OAUTH_CLIENT_ID=your-google-client-id-from-step-above
GOOGLE_OAUTH_CLIENT_SECRET=your-google-client-secret-from-step-above
ALLOWED_HOSTS=localhost,127.0.0.1
```

**Generate a secure SECRET_KEY:**
```bash
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the generated key and replace `your-secret-key-here` in your `.env` file.

### Step 3: Initialize the Database

Set up Django and create the database:

```bash
# Run database migrations
uv run python manage.py migrate

# Create a superuser account (optional, for admin access)
uv run python manage.py createsuperuser
```

### Step 4: Test the Setup

Verify everything is working:

```bash
# Run the development server
uv run python manage.py runserver
```

Open your browser and go to `http://localhost:8000`. You should see the Calendar Sync Tool dashboard.

### Step 5: Connect Your First Calendar

1. Click "Connect Google Calendar Account" in the dashboard
2. You'll be redirected to Google for authentication
3. Grant the necessary permissions
4. You'll be redirected back to the dashboard with your account connected

Repeat this process to connect additional Google accounts.

## Setting Up Automatic Sync

Once you have calendars connected, you'll want to set up automatic syncing.

### Manual Sync

Test the sync functionality manually:

```bash
# Run sync once
uv run python manage.py sync_calendars

# Run sync with verbose output
uv run python manage.py sync_calendars --verbose
```

### Automated Sync with Cron

For production use, set up a cron job to sync every 5 minutes:

```bash
# Open crontab
crontab -e

# Add this line (adjust path as needed)
*/5 * * * * cd /path/to/calendar-sync-tool/src && /path/to/uv run python manage.py sync_calendars
```

### Docker Deployment (Optional)

If you prefer to run in Docker:

```bash
# Build and start the container
docker-compose up -d

# Set up cron job for Docker
*/5 * * * * docker exec calendar-sync python manage.py sync_calendars
```

## Testing Your Setup

### Manual Testing

Test that the basic functionality works:

#### 1. Connect Your Calendars
1. Visit the dashboard at `http://localhost:8000`
2. Click "Connect Google Calendar Account"
3. Complete the OAuth flow for your first account
4. Repeat for a second Google account

#### 2. Test Sync Functionality
```bash
# Run sync manually to test
uv run python manage.py sync_calendars --verbose
```

#### 3. Verify Busy Blocks
1. Create an event in one of your connected Google Calendar accounts
2. Wait 5 minutes or run the sync command manually
3. Check your other connected calendars - you should see a "busy" block created

### Running Tests

Test the application code:

```bash
# Run the test suite
uv run python manage.py test

# Run tests with coverage
uv run coverage run manage.py test
uv run coverage report
```

### Code Quality Checks

```bash
# Check code formatting
uv run ruff check .

# Auto-format code
uv run ruff format .

# Fix auto-fixable issues
uv run ruff check --fix .
```

## Troubleshooting

### Common Issues

#### OAuth Authentication Problems
- **"Invalid redirect URI"** - Check that your Google Console redirect URI exactly matches `http://localhost:8000/auth/callback/`
- **"Token expired"** - The app should automatically refresh tokens, but you may need to reconnect accounts if refresh tokens expire

#### Sync Not Working
- **No busy blocks appearing** - Check that:
  - Both accounts are connected and active
  - The sync command runs without errors: `uv run python manage.py sync_calendars --verbose`
  - Events exist in the source calendar
- **Rate limiting errors** - The app implements backoff, but if you see rate limit errors, wait a few minutes before retrying

#### Development Server Issues
- **Port 8000 in use** - Stop any existing servers or use a different port: `uv run python manage.py runserver 8001`
- **Database errors** - Try running migrations again: `uv run python manage.py migrate`

### Getting Help

If you encounter issues:

1. Check the Django logs for error messages
2. Run sync with verbose output: `uv run python manage.py sync_calendars --verbose`
3. Verify your `.env` file has the correct OAuth credentials
4. Ensure your Google Cloud Console project has the Calendar API enabled

### Development Workflow

For ongoing development:

1. Make changes to code
2. Run tests: `uv run python manage.py test`
3. Check code quality: `uv run ruff check .`
4. Test manually with sync command
5. Commit changes when tests pass

## Next Steps

Once you have the basic setup working:

1. **Set up automatic syncing** - Add a cron job to run sync every 5 minutes
2. **Monitor performance** - Check logs regularly for errors or rate limiting
3. **Customize settings** - Adjust sync frequency or add additional features
4. **Deploy to production** - Use Docker or your preferred deployment method

## Additional Resources

- [Google Calendar API Documentation](https://developers.google.com/calendar/api)
- [Django Documentation](https://docs.djangoproject.com/)
- [uv Documentation](https://docs.astral.sh/uv/)

This guide should get you from zero to a working calendar sync tool. The application provides a solid foundation that you can extend with additional features as needed.
# Setup & Infrastructure Tasks

## Overview
Foundation tasks for setting up the development environment and basic Django project structure.

## Priority: CRITICAL (Must complete before other development)

## AI Agent Execution Guidelines

### Prerequisites Validation (MANDATORY)
**AI agents MUST run these commands before starting ANY task:**
```bash
# Validate environment
pwd  # Expected: /home/sheraz/src/calendar-bridge-clone
python --version  # Expected: Python 3.11+
uv --version  # Expected: uv version info
ls pyproject.toml CLAUDE.md  # Expected: Both files exist

# Verify network connectivity for package downloads
ping -c 1 pypi.org > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "SUCCESS: Network connectivity verified"
else
    echo "WARNING: Network connectivity issue - package downloads may fail"
fi

echo "Prerequisites validated - ready for task execution"
```

### Safety Protocol for AI Agents
**CRITICAL CONSTRAINTS:**
- **NEVER** proceed if any prerequisite validation fails
- **ALWAYS** run tests after each task completion
- **MANDATORY** use the exact command patterns provided
- **REQUIRED** validate success after each command
- **ESSENTIAL** stop immediately on any failure and report status

---

## TASK-001: Project Initialization
**Status:** Not Started  
**Estimated Time:** 30 minutes  
**Dependencies:** None  

### Description
Initialize the project using uv and create the basic directory structure.

### AI Agent Prerequisites Check
**MANDATORY: Run before starting task:**
```bash
# Step 1: Validate working directory
if [ "$(pwd)" != "/home/sheraz/src/calendar-bridge-clone" ]; then
    echo "FAILED: Wrong working directory"
    exit 1
fi

# Step 2: Check if already initialized
if [ -d ".venv" ]; then
    echo "INFO: Project already initialized"
    echo "DECISION: Skip to validation steps"
else
    echo "INFO: Project needs initialization"
    echo "DECISION: Proceed with initialization"
fi
```

### AI Agent Execution Pattern
**Follow this exact sequence:**
```bash
# STEP 1: Project Initialization
echo "Starting TASK-001: Project Initialization"

if [ -d ".venv" ]; then
    echo "INFO: Virtual environment exists, skipping uv init"
else
    echo "Running uv init..."
    uv init
    if [ $? -eq 0 ]; then
        echo "SUCCESS: uv init completed"
    else
        echo "FAILED: uv init failed"
        exit 1
    fi
fi

# STEP 2: Install Dependencies
echo "Installing dependencies with uv sync..."
uv sync --all-extras
if [ $? -eq 0 ]; then
    echo "SUCCESS: Dependencies installed"
else
    echo "FAILED: Dependency installation failed"
    exit 1
fi

# STEP 3: Validate Installation
echo "Validating installation..."
# Check virtual environment exists
if [ -d ".venv" ]; then
    echo "SUCCESS: Virtual environment created"
else
    echo "FAILED: Virtual environment not found"
    exit 1
fi

# Check Python version in virtual environment
uv run python --version
if [ $? -eq 0 ]; then
    echo "SUCCESS: Python accessible through uv"
else
    echo "FAILED: Python not accessible"
    exit 1
fi

# Verify dependencies
uv run python -c "import django; print(f'Django {django.VERSION}')"
if [ $? -eq 0 ]; then
    echo "SUCCESS: Django imported successfully"
else
    echo "FAILED: Django import failed"
    exit 1
fi

echo "SUCCESS: TASK-001 completed successfully"
```

### Acceptance Criteria (AI Agent Validation)
**Each criterion must be programmatically verified:**

- [ ] **uv init executed successfully**
  ```bash
  # Validation command:
  ls .venv/pyvenv.cfg
  if [ $? -eq 0 ]; then echo "SUCCESS: uv init completed"; else echo "FAILED: uv init incomplete"; exit 1; fi
  ```

- [ ] **Dependencies installed successfully**
  ```bash
  # Validation command:
  uv run python -c "import django, google.auth, coverage, ruff"
  if [ $? -eq 0 ]; then echo "SUCCESS: All dependencies installed"; else echo "FAILED: Missing dependencies"; exit 1; fi
  ```

- [ ] **Python 3.11+ verified**
  ```bash
  # Validation command:
  uv run python -c "import sys; assert sys.version_info >= (3, 11), f'Need Python 3.11+, got {sys.version_info}'"
  if [ $? -eq 0 ]; then echo "SUCCESS: Python version valid"; else echo "FAILED: Python version invalid"; exit 1; fi
  ```

- [ ] **Virtual environment functional**
  ```bash
  # Validation command:
  uv run python -c "import sys; print(f'Virtual env: {sys.prefix}')"
  if [ $? -eq 0 ]; then echo "SUCCESS: Virtual environment working"; else echo "FAILED: Virtual environment broken"; exit 1; fi
  ```

- [ ] **All dependencies from pyproject.toml installed**
  ```bash
  # Validation command:
  uv pip list | grep -E "(django|google-api-python-client|ruff|coverage)"
  if [ $? -eq 0 ]; then echo "SUCCESS: Core dependencies found"; else echo "FAILED: Missing core dependencies"; exit 1; fi
  ```

### Implementation Notes (AI Agent Guidelines)
- **Follow CLAUDE.md setup instructions exactly** - Reference specific sections for validation
- **Ensure pyproject.toml is working correctly** - Dependencies must match file specifications
- **Test that `uv run` commands work** - All subsequent commands depend on this functionality
- **Verify Python version compatibility** - Must be Python 3.11+ as specified in CLAUDE.md
- **Check network connectivity** - uv sync requires internet access for package downloads
- **Monitor disk space** - Virtual environments require substantial storage space
- **Document any deviations** - Report unexpected behavior immediately

### Recovery Procedures (AI Agent Error Handling)
**If any step fails:**
1. **STOP immediately** - Do not continue to dependent tasks
2. **Capture error output** - Save full error message for troubleshooting
3. **Check common issues:**
   - Network connectivity for downloads
   - Disk space for virtual environment
   - Permission issues in directory
4. **Escalate to human** - If recovery steps don't resolve the issue

### Success Indicators (AI Agent Verification)
**Task is complete when ALL of these are true:**
- Virtual environment directory `.venv` exists
- `uv run python --version` returns Python 3.11+
- `uv run python -c "import django"` succeeds without error
- `uv pip list` shows expected dependencies
- No error messages in command output

---

## TASK-002: Django Project Creation
**Status:** Not Started  
**Estimated Time:** 45 minutes  
**Dependencies:** TASK-001  

### Description
Create the Django project structure and required apps using proper directory layout.

### AI Agent Prerequisites Check
**MANDATORY: Verify TASK-001 completion:**
```bash
# Validate TASK-001 completion
echo "Checking TASK-001 completion..."
if [ ! -d ".venv" ]; then
    echo "FAILED: TASK-001 incomplete - virtual environment missing"
    exit 1
fi

uv run python -c "import django"
if [ $? -ne 0 ]; then
    echo "FAILED: TASK-001 incomplete - Django not available"
    exit 1
fi

# Verify we're in correct working directory
if [ "$(pwd)" != "/home/sheraz/src/calendar-bridge-clone" ]; then
    echo "FAILED: Wrong working directory. Expected: /home/sheraz/src/calendar-bridge-clone"
    exit 1
fi

echo "SUCCESS: TASK-001 verified complete"
```

### AI Agent Execution Pattern
**Follow this exact sequence:**
```bash
# STEP 1: Create proper directory structure
echo "Starting TASK-002: Django Project Creation"

# Guilfoyle's Fix: Create src/ directory first to avoid nested mess
if [ ! -d "src" ]; then
    echo "Creating src/ directory..."
    mkdir src
    if [ $? -eq 0 ]; then
        echo "SUCCESS: src/ directory created"
    else
        echo "FAILED: Could not create src/ directory"
        exit 1
    fi
else
    echo "INFO: src/ directory already exists"
fi

# STEP 2: Create Django project with proper structure
if [ -f "src/manage.py" ]; then
    echo "INFO: Django project already exists"
    echo "DECISION: Skip to app creation"
else
    echo "Creating Django project with proper structure..."
    # Guilfoyle's Fix: Create project directly in src/ without nested calendar_sync/
    cd src/
    uv run django-admin startproject calendar_sync .
    
    if [ $? -eq 0 ]; then
        echo "SUCCESS: Django project created in src/"
        # Verify critical files exist
        if [ -f "manage.py" ] && [ -f "calendar_sync/settings.py" ]; then
            echo "SUCCESS: Django project structure validated"
        else
            echo "FAILED: Django project creation incomplete"
            echo "DEBUG: Contents of src/:"
            ls -la
            exit 1
        fi
    else
        echo "FAILED: Django project creation failed"
        exit 1
    fi
    
    echo "INFO: Working directory is now: $(pwd)"
fi

# Ensure we're in src/ directory for app creation
if [ "$(basename $(pwd))" != "src" ]; then
    cd src/
    echo "INFO: Navigated to src/ directory: $(pwd)"
fi

# STEP 3: Create apps/ directory structure
echo "Creating apps/ directory structure..."
if [ ! -d "apps" ]; then
    mkdir apps
    if [ $? -eq 0 ]; then
        echo "SUCCESS: apps/ directory created"
        # Create __init__.py to make it a Python package
        touch apps/__init__.py
        echo "SUCCESS: apps/__init__.py created"
    else
        echo "FAILED: Could not create apps/ directory"
        exit 1
    fi
else
    echo "INFO: apps/ directory already exists"
fi

# STEP 4: Create Django apps in apps/ directory
echo "Creating Django applications in apps/ directory..."

# Create calendars app
if [ -d "apps/calendars" ]; then
    echo "INFO: calendars app already exists"
else
    uv run python manage.py startapp calendars apps/calendars
    if [ $? -eq 0 ]; then
        echo "SUCCESS: calendars app created"
        if [ ! -f "apps/calendars/models.py" ]; then
            echo "FAILED: calendars app creation incomplete"
            exit 1
        fi
    else
        echo "FAILED: calendars app creation failed"
        exit 1
    fi
fi

# Create accounts app
if [ -d "apps/accounts" ]; then
    echo "INFO: accounts app already exists"
else
    uv run python manage.py startapp accounts apps/accounts
    if [ $? -eq 0 ]; then
        echo "SUCCESS: accounts app created"
        if [ ! -f "apps/accounts/models.py" ]; then
            echo "FAILED: accounts app creation incomplete"
            exit 1
        fi
    else
        echo "FAILED: accounts app creation failed"
        exit 1
    fi
fi

# Create dashboard app
if [ -d "apps/dashboard" ]; then
    echo "INFO: dashboard app already exists"
else
    uv run python manage.py startapp dashboard apps/dashboard
    if [ $? -eq 0 ]; then
        echo "SUCCESS: dashboard app created"
        if [ ! -f "apps/dashboard/views.py" ]; then
            echo "FAILED: dashboard app creation incomplete"
            exit 1
        fi
    else
        echo "FAILED: dashboard app creation failed"
        exit 1
    fi
fi

# STEP 5: Validate Django project structure
echo "Validating Django project structure..."
uv run python manage.py check
if [ $? -eq 0 ]; then
    echo "SUCCESS: Django project structure valid"
else
    echo "WARNING: Django project has configuration issues (expected - apps not yet registered)"
    echo "INFO: This will be resolved in TASK-003"
fi

echo "SUCCESS: TASK-002 completed successfully"
```

### Acceptance Criteria (AI Agent Validation)
**Each criterion must be programmatically verified:**

- [ ] **Django project created with proper structure**
  ```bash
  # Validation command:
  ls src/manage.py src/calendar_sync/settings.py
  if [ $? -eq 0 ]; then echo "SUCCESS: Django project exists with proper structure"; else echo "FAILED: Django project missing or malformed"; exit 1; fi
  ```

- [ ] **Apps directory structure created**
  ```bash
  # Validation command:
  ls src/apps/__init__.py
  if [ $? -eq 0 ]; then echo "SUCCESS: apps/ directory structure created"; else echo "FAILED: apps/ directory missing"; exit 1; fi
  ```

- [ ] **calendars app created in apps/ directory**
  ```bash
  # Validation command:
  ls src/apps/calendars/models.py src/apps/calendars/views.py src/apps/calendars/apps.py
  if [ $? -eq 0 ]; then echo "SUCCESS: calendars app created"; else echo "FAILED: calendars app incomplete"; exit 1; fi
  ```

- [ ] **accounts app created in apps/ directory**
  ```bash
  # Validation command:
  ls src/apps/accounts/models.py src/apps/accounts/views.py src/apps/accounts/apps.py
  if [ $? -eq 0 ]; then echo "SUCCESS: accounts app created"; else echo "FAILED: accounts app incomplete"; exit 1; fi
  ```

- [ ] **dashboard app created in apps/ directory**
  ```bash
  # Validation command:
  ls src/apps/dashboard/models.py src/apps/dashboard/views.py src/apps/dashboard/apps.py
  if [ $? -eq 0 ]; then echo "SUCCESS: dashboard app created"; else echo "FAILED: dashboard app incomplete"; exit 1; fi
  ```

- [ ] **Working directory management correct**
  ```bash
  # Validation command:
  cd src/
  if [ "$(basename $(pwd))" = "src" ] && [ -f "manage.py" ]; then
      echo "SUCCESS: Working directory management correct"
  else
      echo "FAILED: Working directory or file structure incorrect"
      exit 1
  fi
  ```

- [ ] **Basic Django structure functional**
  ```bash
  # Validation command:
  cd src/ && uv run python manage.py check --deploy
  if [ $? -eq 0 ]; then 
      echo "SUCCESS: Django configuration valid"
  else 
      echo "WARNING: Django deployment checks failed (expected until apps registered)"
  fi
  ```

### Implementation Notes (AI Agent Guidelines)
- **Navigate to correct directories** - All Django commands must run from `src/` directory
- **Verify each app creation** - Check for expected files after each `startapp` command
- **Use project-relative paths** - All subsequent development assumes `src/` as working directory
- **Test basic Django functionality** - Ensure `manage.py` commands work before proceeding
- **Handle existing directories** - Check for partial completion before running startproject/startapp
- **Validate app structure** - Each Django app must have models.py, views.py, apps.py at minimum
- **Test initial migration** - Run initial migration to verify database connectivity works

### Recovery Procedures (AI Agent Error Handling)
**If any step fails:**
1. **Check working directory** - Ensure commands run from correct location
2. **Verify permissions** - Check file creation permissions
3. **Clean partial creation** - Remove incomplete directories if needed
4. **Re-run from clean state** - Start over if corruption detected
5. **Escalate to human** - If repeated failures occur

---

## TASK-003: Environment Configuration
**Status:** Not Started  
**Estimated Time:** 30 minutes  
**Dependencies:** TASK-002  

### Description
Set up environment variables and django-environ configuration with secure SECRET_KEY generation.

### AI Agent Prerequisites Check
**MANDATORY: Verify TASK-002 completion:**
```bash
# Validate TASK-002 completion
echo "Checking TASK-002 completion..."
if [ ! -f "src/manage.py" ]; then
    echo "FAILED: TASK-002 incomplete - manage.py missing"
    exit 1
fi

if [ ! -f "src/calendar_sync/settings.py" ]; then
    echo "FAILED: TASK-002 incomplete - Django settings missing"
    exit 1
fi

if [ ! -d "src/apps" ]; then
    echo "FAILED: TASK-002 incomplete - apps/ directory missing"
    exit 1
fi

# Verify we're in correct working directory
if [ "$(pwd)" != "/home/sheraz/src/calendar-bridge-clone" ]; then
    echo "FAILED: Wrong working directory. Expected: /home/sheraz/src/calendar-bridge-clone"
    exit 1
fi

echo "SUCCESS: TASK-002 verified complete"
```

### AI Agent Execution Pattern
**Follow this exact sequence:**
```bash
# STEP 1: Generate secure SECRET_KEY using Guilfoyle's method
echo "Starting TASK-003: Environment Configuration"

# Ensure we're in project root directory
cd /home/sheraz/src/calendar-bridge-clone

# Guilfoyle's Fix: Use secrets.token_urlsafe(50) for secure generation
echo "Generating cryptographically secure SECRET_KEY..."
SECRET_KEY=$(uv run python -c "import secrets; print(secrets.token_urlsafe(50))")
if [ $? -eq 0 ] && [ ! -z "$SECRET_KEY" ]; then
    echo "SUCCESS: Secure SECRET_KEY generated (length: ${#SECRET_KEY})"
    if [ ${#SECRET_KEY} -lt 50 ]; then
        echo "WARNING: SECRET_KEY shorter than recommended 50 characters"
    fi
else
    echo "FAILED: SECRET_KEY generation failed"
    echo "Attempting fallback method..."
    SECRET_KEY=$(uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
    if [ $? -eq 0 ] && [ ! -z "$SECRET_KEY" ]; then
        echo "SUCCESS: SECRET_KEY generated using fallback method (length: ${#SECRET_KEY})"
    else
        echo "FAILED: All SECRET_KEY generation methods failed"
        exit 1
    fi
fi

# STEP 2: Create .env file
echo "Creating .env file..."
if [ -f ".env" ]; then
    echo "INFO: .env file already exists, creating backup"
    cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
fi

cat > .env << EOF
# Django Configuration
DEBUG=True
SECRET_KEY=${SECRET_KEY}

# Google OAuth Configuration (placeholder values)
GOOGLE_OAUTH_CLIENT_ID=your-google-client-id-here
GOOGLE_OAUTH_CLIENT_SECRET=your-google-client-secret-here

# Host Configuration
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Configuration - Guilfoyle's Fix: Explicit SQLite path for Docker compatibility
DATABASE_URL=sqlite:///./db.sqlite3
EOF

if [ $? -eq 0 ]; then
    echo "SUCCESS: .env file created"
else
    echo "FAILED: .env file creation failed"
    exit 1
fi

# STEP 3: Create .env.example template
echo "Creating .env.example template..."
cat > .env.example << EOF
# Django Configuration
DEBUG=True
SECRET_KEY=your-secret-key-here

# Google OAuth Configuration
GOOGLE_OAUTH_CLIENT_ID=your-google-client-id-here
GOOGLE_OAUTH_CLIENT_SECRET=your-google-client-secret-here

# Host Configuration
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Configuration - Docker compatible path
DATABASE_URL=sqlite:///./db.sqlite3
EOF

if [ $? -eq 0 ]; then
    echo "SUCCESS: .env.example created"
else
    echo "FAILED: .env.example creation failed"
    exit 1
fi

# STEP 4: Update .gitignore to exclude .env
echo "Updating .gitignore..."
if [ -f ".gitignore" ]; then
    # Check if .env is already in .gitignore
    if grep -q "^\.env$" .gitignore; then
        echo "INFO: .env already in .gitignore"
    else
        echo ".env" >> .gitignore
        echo "SUCCESS: .env added to .gitignore"
    fi
else
    # Create .gitignore with .env entry
    echo ".env" > .gitignore
    echo "SUCCESS: .gitignore created with .env entry"
fi

# STEP 5: Configure django-environ in settings.py
echo "Configuring django-environ in settings.py..."
cd src/

# Backup original settings.py
cp calendar_sync/settings.py calendar_sync/settings.py.backup

# Create the new settings.py with django-environ integration
cat > calendar_sync/settings.py << 'EOF'
"""
Django settings for calendar_sync project.

Generated by 'django-admin startproject' using Django 4.2.
"""

import environ
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize django-environ
env = environ.Env(
    # Cast and default values
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)

# Read .env file from project root (one level up from src/)
environ.Env.read_env(BASE_DIR.parent / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = env('ALLOWED_HOSTS')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Guilfoyle's Fix: Proper app registration with apps/ directory structure
    'apps.calendars',
    'apps.accounts', 
    'apps.dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'calendar_sync.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'calendar_sync.wsgi.application'

# Database - Guilfoyle's Fix: Explicit SQLite configuration for Docker compatibility
DATABASES = {
    'default': env.db(default='sqlite:///./db.sqlite3')
}

# Ensure database directory exists
import os
db_path = DATABASES['default']['NAME']
if db_path and db_path != ':memory:':
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise configuration
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Google OAuth Configuration
GOOGLE_OAUTH_CLIENT_ID = env('GOOGLE_OAUTH_CLIENT_ID', default='')
GOOGLE_OAUTH_CLIENT_SECRET = env('GOOGLE_OAUTH_CLIENT_SECRET', default='')
EOF

if [ $? -eq 0 ]; then
    echo "SUCCESS: settings.py configured with django-environ"
else
    echo "FAILED: settings.py configuration failed"
    exit 1
fi

# STEP 6: Test environment configuration
echo "Testing environment configuration..."
uv run python manage.py check
if [ $? -eq 0 ]; then
    echo "SUCCESS: Django configuration valid with environment variables"
else
    echo "FAILED: Django configuration invalid"
    exit 1
fi

# Test environment variable loading
uv run python -c "
import os
import sys
sys.path.append('.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'calendar_sync.settings')
import django
django.setup()
from django.conf import settings
print(f'DEBUG: {settings.DEBUG}')
print(f'SECRET_KEY length: {len(settings.SECRET_KEY)}')
print(f'ALLOWED_HOSTS: {settings.ALLOWED_HOSTS}')
assert settings.SECRET_KEY != 'your-secret-key-here', 'SECRET_KEY not properly loaded'
assert len(settings.SECRET_KEY) >= 50, 'SECRET_KEY too short'
print('SUCCESS: All environment variables loaded correctly')
"
if [ $? -eq 0 ]; then
    echo "SUCCESS: Environment variables loading correctly"
else
    echo "FAILED: Environment variable loading failed"
    exit 1
fi

echo "SUCCESS: TASK-003 completed successfully"
```

### Acceptance Criteria (AI Agent Validation)
**Each criterion must be programmatically verified:**

- [ ] **.env file created with secure SECRET_KEY**
  ```bash
  # Validation command:
  if [ -f ".env" ]; then
      SECRET_LENGTH=$(grep "SECRET_KEY=" .env | cut -d'=' -f2 | wc -c)
      if [ $SECRET_LENGTH -gt 50 ]; then
          echo "SUCCESS: .env file with secure SECRET_KEY exists"
      else
          echo "FAILED: SECRET_KEY too short or missing"
          exit 1
      fi
  else
      echo "FAILED: .env file missing"
      exit 1
  fi
  ```

- [ ] **Required environment variables present**
  ```bash
  # Validation command:
  required_vars="DEBUG SECRET_KEY GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET ALLOWED_HOSTS"
  for var in $required_vars; do
      if grep -q "^${var}=" .env; then
          echo "SUCCESS: $var found in .env"
      else
          echo "FAILED: $var missing from .env"
          exit 1
      fi
  done
  ```

- [ ] **django-environ integrated in settings.py**
  ```bash
  # Validation command:
  cd src/
  if grep -q "import environ" calendar_sync/settings.py && grep -q "env(" calendar_sync/settings.py; then
      echo "SUCCESS: django-environ integrated"
  else
      echo "FAILED: django-environ not properly integrated"
      exit 1
  fi
  ```

- [ ] **Environment variables loading correctly**
  ```bash
  # Validation command:
  cd src/
  uv run python -c "
  import os
  os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'calendar_sync.settings')
  import django
  django.setup()
  from django.conf import settings
  assert settings.DEBUG == True, 'DEBUG not loaded correctly'
  assert len(settings.SECRET_KEY) >= 50, 'SECRET_KEY not loaded correctly'
  assert 'localhost' in settings.ALLOWED_HOSTS, 'ALLOWED_HOSTS not loaded correctly'
  print('SUCCESS: Environment variables verified')
  "
  if [ $? -eq 0 ]; then
      echo "SUCCESS: Environment variables loading correctly"
  else
      echo "FAILED: Environment variable loading failed"
      exit 1
  fi
  ```

- [ ] **.env added to .gitignore**
  ```bash
  # Validation command:
  if grep -q "^\.env$" .gitignore; then
      echo "SUCCESS: .env in .gitignore"
  else
      echo "FAILED: .env not in .gitignore"
      exit 1
  fi
  ```

- [ ] **.env.example template created**
  ```bash
  # Validation command:
  if [ -f ".env.example" ] && grep -q "your-secret-key-here" .env.example; then
      echo "SUCCESS: .env.example template exists"
  else
      echo "FAILED: .env.example template missing or invalid"
      exit 1
  fi
  ```

- [ ] **WhiteNoise configured for static files**
  ```bash
  # Validation command:
  cd src/
  if grep -q "whitenoise" calendar_sync/settings.py; then
      echo "SUCCESS: WhiteNoise configured"
  else
      echo "FAILED: WhiteNoise not configured"
      exit 1
  fi
  ```

- [ ] **Django apps properly registered with apps/ prefix**
  ```bash
  # Validation command:
  cd src/
  apps_to_check="apps.calendars apps.accounts apps.dashboard"
  for app in $apps_to_check; do
      if grep -q "'${app}'" calendar_sync/settings.py; then
          echo "SUCCESS: $app registered in INSTALLED_APPS"
      else
          echo "FAILED: $app not registered in INSTALLED_APPS"
          exit 1
      fi
  done
  ```

### Implementation Notes (AI Agent Guidelines)
- **Security Priority**: Use `secrets.token_urlsafe(50)` for cryptographically secure SECRET_KEY generation (Guilfoyle's Fix)
- **Path Management**: Ensure .env file is in project root, not src/ directory
- **Database Configuration**: Use explicit SQLite path `sqlite:///./db.sqlite3` for Docker compatibility (Guilfoyle's Fix)
- **App Registration**: Register apps with `apps.` prefix to match directory structure (Guilfoyle's Fix)
- **Backup Strategy**: Create backup of original settings.py before modification
- **Environment Isolation**: Use django-environ for all configuration, not hardcoded values
- **Static Files**: Configure WhiteNoise for production-ready static file serving
- **Working Directory**: All Django commands must run from `src/` directory (Guilfoyle's Fix)

### Recovery Procedures (AI Agent Error Handling)
**If SECRET_KEY generation fails:**
1. Check Python access: `uv run python --version`
2. Test Django import: `uv run python -c "import django"`
3. Manual fallback: Use Python's secrets module as alternative
4. Escalate if cryptographic functions unavailable

**If .env file creation fails:**
1. Check write permissions in project directory
2. Verify disk space availability
3. Check for conflicting processes holding file locks
4. Try alternative path or temporary file approach

**If settings.py configuration fails:**
1. Restore from backup: `cp calendar_sync/settings.py.backup calendar_sync/settings.py`
2. Verify django-environ is installed: `uv pip list | grep django-environ`
3. Check for syntax errors in generated settings.py
4. Escalate if backup restoration fails

### Success Indicators (AI Agent Verification)
**Task is complete when ALL of these are true:**
- `.env` file exists with SECRET_KEY ≥50 characters
- `.env.example` template file exists
- `.env` is listed in `.gitignore`
- `settings.py` imports and uses django-environ
- `uv run python manage.py check` passes without errors
- Environment variables load correctly in Django
- All required apps are registered in INSTALLED_APPS
- WhiteNoise middleware is configured

---

## TASK-004: Database Setup and Initial Migration
**Status:** Not Started  
**Estimated Time:** 30 minutes  
**Dependencies:** TASK-003  

### Description
Initialize the database and run initial Django migrations to ensure the database layer is functional.

### AI Agent Prerequisites Check
**MANDATORY: Verify TASK-003 completion:**
```bash
# Validate TASK-003 completion
echo "Checking TASK-003 completion..."
if [ ! -f ".env" ]; then
    echo "FAILED: TASK-003 incomplete - .env file missing"
    exit 1
fi

if [ ! -f "src/calendar_sync/settings.py" ]; then
    echo "FAILED: TASK-003 incomplete - settings.py missing"
    exit 1
fi

# Verify we're in correct working directory
if [ "$(pwd)" != "/home/sheraz/src/calendar-bridge-clone" ]; then
    echo "FAILED: Wrong working directory. Expected: /home/sheraz/src/calendar-bridge-clone"
    exit 1
fi

# Test Django configuration
cd src/
uv run python manage.py check
if [ $? -ne 0 ]; then
    echo "FAILED: TASK-003 incomplete - Django configuration invalid"
    exit 1
fi

echo "SUCCESS: TASK-003 verified complete"
```

### AI Agent Execution Pattern
**Follow this exact sequence:**
```bash
# STEP 1: Navigate to Django project directory
echo "Starting TASK-004: Database Setup and Initial Migration"
cd /home/sheraz/src/calendar-bridge-clone/src/

# STEP 2: Run Django system checks
echo "Running Django system checks..."
uv run python manage.py check --deploy
if [ $? -eq 0 ]; then
    echo "SUCCESS: Django system checks passed"
else
    echo "WARNING: Some deployment checks failed (may be expected in development)"
    # Run basic checks only
    uv run python manage.py check
    if [ $? -eq 0 ]; then
        echo "SUCCESS: Basic Django checks passed"
    else
        echo "FAILED: Django configuration has errors"
        exit 1
    fi
fi

# STEP 3: Create initial database migrations
echo "Creating initial database migrations..."
uv run python manage.py makemigrations
if [ $? -eq 0 ]; then
    echo "SUCCESS: Initial migrations created"
else
    echo "WARNING: No migrations to create (expected for new project)"
fi

# STEP 4: Apply database migrations
echo "Applying database migrations..."
uv run python manage.py migrate
if [ $? -eq 0 ]; then
    echo "SUCCESS: Database migrations applied"
    # Verify database was created
    if [ -f "db.sqlite3" ]; then
        echo "SUCCESS: SQLite database file created"
    else
        echo "WARNING: Database file not found at expected location"
    fi
else
    echo "FAILED: Database migration failed"
    exit 1
fi

# STEP 5: Collect static files
echo "Collecting static files..."
uv run python manage.py collectstatic --noinput
if [ $? -eq 0 ]; then
    echo "SUCCESS: Static files collected"
else
    echo "WARNING: Static file collection failed (may be environment-specific)"
fi

# STEP 6: Test database connectivity
echo "Testing database connectivity..."
uv run python -c "
import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'calendar_sync.settings')
django.setup()

from django.db import connection
try:
    cursor = connection.cursor()
    cursor.execute('SELECT 1;')
    result = cursor.fetchone()
    if result[0] == 1:
        print('SUCCESS: Database connectivity verified')
    else:
        print('FAILED: Database query returned unexpected result')
        exit(1)
except Exception as e:
    print(f'FAILED: Database connectivity test failed: {e}')
    exit(1)
"
if [ $? -eq 0 ]; then
    echo "SUCCESS: Database connectivity confirmed"
else
    echo "FAILED: Database connectivity test failed"
    exit 1
fi

echo "SUCCESS: TASK-004 completed successfully"
```

### Acceptance Criteria (AI Agent Validation)
**Each criterion must be programmatically verified:**

- [ ] **Django migrations applied successfully**
  ```bash
  # Validation command:
  cd src/
  uv run python manage.py showmigrations
  if [ $? -eq 0 ]; then echo "SUCCESS: Migrations status accessible"; else echo "FAILED: Cannot access migrations"; exit 1; fi
  ```

- [ ] **Database file created**
  ```bash
  # Validation command:
  cd src/
  if [ -f "db.sqlite3" ]; then echo "SUCCESS: Database file exists"; else echo "FAILED: Database file missing"; exit 1; fi
  ```

- [ ] **Database connectivity working**
  ```bash
  # Validation command:
  cd src/
  uv run python manage.py shell -c "from django.db import connection; cursor = connection.cursor(); cursor.execute('SELECT 1'); print('Database OK')"
  if [ $? -eq 0 ]; then echo "SUCCESS: Database connectivity working"; else echo "FAILED: Database connection failed"; exit 1; fi
  ```

- [ ] **Apps properly loaded**
  ```bash
  # Validation command:
  cd src/
  uv run python manage.py check apps.calendars apps.accounts apps.dashboard
  if [ $? -eq 0 ]; then echo "SUCCESS: All apps loaded properly"; else echo "FAILED: App loading issues"; exit 1; fi
  ```

- [ ] **Static files configuration working**
  ```bash
  # Validation command:
  cd src/
  if [ -d "staticfiles" ]; then echo "SUCCESS: Static files directory exists"; else echo "INFO: Static files not collected yet"; fi
  ```

### Implementation Notes (AI Agent Guidelines)
- **Working Directory**: All commands must run from `src/` directory
- **Database Path**: SQLite database will be created in `src/db.sqlite3`
- **Migration Handling**: Initial migrations may not exist for custom apps yet
- **Static Files**: collectstatic may fail in development but shouldn't block progress
- **Error Tolerance**: Some warnings are acceptable in development environment

---

## TASK-005: Basic URL Configuration  
**Status:** Not Started  
**Estimated Time:** 30 minutes  
**Dependencies:** TASK-004  

### Description
Set up basic URL routing for the Django project to enable web interface access.

### AI Agent Prerequisites Check
**MANDATORY: Verify TASK-004 completion:**
```bash
# Validate TASK-004 completion
echo "Checking TASK-004 completion..."
if [ ! -f "src/db.sqlite3" ]; then
    echo "FAILED: TASK-004 incomplete - database missing"
    exit 1
fi

# Verify we're in correct working directory
if [ "$(pwd)" != "/home/sheraz/src/calendar-bridge-clone" ]; then
    echo "FAILED: Wrong working directory. Expected: /home/sheraz/src/calendar-bridge-clone"
    exit 1
fi

# Test Django functionality
cd src/
uv run python manage.py check
if [ $? -ne 0 ]; then
    echo "FAILED: TASK-004 incomplete - Django configuration issues"
    exit 1
fi

echo "SUCCESS: TASK-004 verified complete"
```

### AI Agent Execution Pattern
**Follow this exact sequence:**
```bash
# STEP 1: Navigate to Django project directory
echo "Starting TASK-005: Basic URL Configuration"
cd /home/sheraz/src/calendar-bridge-clone/src/

# STEP 2: Create basic URLs for each app
echo "Creating basic URL configurations for apps..."

# Create calendars app URLs
echo "Creating calendars app URLs..."
cat > apps/calendars/urls.py << 'EOF'
"""
URL configuration for calendars app.
"""
from django.urls import path
from . import views

app_name = 'calendars'

urlpatterns = [
    # API endpoints will be added here
    path('api/', views.api_placeholder, name='api_placeholder'),
]
EOF

if [ $? -eq 0 ]; then
    echo "SUCCESS: calendars URLs created"
else
    echo "FAILED: calendars URLs creation failed"
    exit 1
fi

# Create accounts app URLs
echo "Creating accounts app URLs..."
cat > apps/accounts/urls.py << 'EOF'
"""
URL configuration for accounts app.
"""
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # OAuth and authentication URLs will be added here
    path('auth/', views.auth_placeholder, name='auth_placeholder'),
]
EOF

if [ $? -eq 0 ]; then
    echo "SUCCESS: accounts URLs created"
else
    echo "FAILED: accounts URLs creation failed"
    exit 1
fi

# Create dashboard app URLs
echo "Creating dashboard app URLs..."
cat > apps/dashboard/urls.py << 'EOF'
"""
URL configuration for dashboard app.
"""
from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
]
EOF

if [ $? -eq 0 ]; then
    echo "SUCCESS: dashboard URLs created"
else
    echo "FAILED: dashboard URLs creation failed"
    exit 1
fi

# STEP 3: Create placeholder views
echo "Creating placeholder views..."

# Dashboard home view
cat > apps/dashboard/views.py << 'EOF'
"""
Dashboard views for the calendar sync application.
"""
from django.http import HttpResponse

def home(request):
    """
    Placeholder home view for dashboard.
    """
    return HttpResponse("""
    <html>
    <head><title>Calendar Sync - Dashboard</title></head>
    <body>
        <h1>Calendar Sync Dashboard</h1>
        <p>Welcome to the Calendar Sync application!</p>
        <p>This is a placeholder view. The full dashboard will be implemented later.</p>
        <ul>
            <li><a href="/admin/">Admin Interface</a></li>
            <li><a href="/auth/">Authentication (placeholder)</a></li>
            <li><a href="/api/">API (placeholder)</a></li>
        </ul>
    </body>
    </html>
    """)
EOF

# Accounts placeholder view
cat > apps/accounts/views.py << 'EOF'
"""
Accounts views for authentication and OAuth.
"""
from django.http import HttpResponse

def auth_placeholder(request):
    """
    Placeholder view for authentication.
    """
    return HttpResponse("""
    <html>
    <head><title>Calendar Sync - Authentication</title></head>
    <body>
        <h1>Authentication</h1>
        <p>OAuth integration will be implemented here.</p>
        <p><a href="/">Back to Dashboard</a></p>
    </body>
    </html>
    """)
EOF

# Calendars placeholder view  
cat > apps/calendars/views.py << 'EOF'
"""
Calendars views for API endpoints.
"""
from django.http import HttpResponse

def api_placeholder(request):
    """
    Placeholder view for API endpoints.
    """
    return HttpResponse("""
    <html>
    <head><title>Calendar Sync - API</title></head>
    <body>
        <h1>Calendar API</h1>
        <p>Calendar sync API endpoints will be implemented here.</p>
        <p><a href="/">Back to Dashboard</a></p>
    </body>
    </html>
    """)
EOF

echo "SUCCESS: Placeholder views created"

# STEP 4: Update main URLs configuration
echo "Updating main URLs configuration..."
cat > calendar_sync/urls.py << 'EOF'
"""
URL configuration for calendar_sync project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),
    
    # App URLs
    path('', include('apps.dashboard.urls')),
    path('auth/', include('apps.accounts.urls')),
    path('api/', include('apps.calendars.urls')),
]
EOF

if [ $? -eq 0 ]; then
    echo "SUCCESS: Main URLs configuration updated"
else
    echo "FAILED: Main URLs configuration failed"
    exit 1
fi

echo "SUCCESS: TASK-005 completed successfully"
```

### Acceptance Criteria (AI Agent Validation)
**Each criterion must be programmatically verified:**

- [ ] **URL files created for all apps**
  ```bash
  # Validation command:
  cd src/
  ls apps/calendars/urls.py apps/accounts/urls.py apps/dashboard/urls.py
  if [ $? -eq 0 ]; then echo "SUCCESS: All app URL files exist"; else echo "FAILED: Missing URL files"; exit 1; fi
  ```

- [ ] **Main URLs configuration updated**
  ```bash
  # Validation command:
  cd src/
  if grep -q "include.*apps.dashboard" calendar_sync/urls.py; then echo "SUCCESS: Main URLs configured"; else echo "FAILED: Main URLs not configured"; exit 1; fi
  ```

- [ ] **URL routing functional**
  ```bash
  # Validation command:
  cd src/
  uv run python manage.py check
  if [ $? -eq 0 ]; then echo "SUCCESS: URL routing valid"; else echo "FAILED: URL routing issues"; exit 1; fi
  ```

---

## TASK-006: Development Workflow Validation
**Status:** Not Started  
**Estimated Time:** 30 minutes  
**Dependencies:** TASK-005  

### Description
Validate that the complete development workflow is functioning correctly.

### AI Agent Prerequisites Check
**MANDATORY: Verify TASK-005 completion:**
```bash
# Validate TASK-005 completion
echo "Checking TASK-005 completion..."
if [ ! -f "src/apps/dashboard/urls.py" ]; then
    echo "FAILED: TASK-005 incomplete - URL configuration missing"
    exit 1
fi

# Verify we're in correct working directory
if [ "$(pwd)" != "/home/sheraz/src/calendar-bridge-clone" ]; then
    echo "FAILED: Wrong working directory. Expected: /home/sheraz/src/calendar-bridge-clone"
    exit 1
fi

echo "SUCCESS: TASK-005 verified complete"
```

### AI Agent Execution Pattern
**Follow this exact sequence:**
```bash
# STEP 1: Test development server startup
echo "Starting TASK-006: Development Workflow Validation"
cd /home/sheraz/src/calendar-bridge-clone/src/

echo "Testing development server startup..."
timeout 15 uv run python manage.py runserver --noreload 0.0.0.0:8000 > server.log 2>&1 &
SERVER_PID=$!
sleep 8

# Check if server is running
if kill -0 $SERVER_PID 2>/dev/null; then
    echo "SUCCESS: Development server started (PID: $SERVER_PID)"
    
    # Test basic connectivity
    curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ > response_code.txt 2>/dev/null || echo "000" > response_code.txt
    RESPONSE_CODE=$(cat response_code.txt)
    
    if [ "$RESPONSE_CODE" = "200" ]; then
        echo "SUCCESS: Home page accessible (HTTP 200)"
    else
        echo "WARNING: Home page returned HTTP $RESPONSE_CODE (may be expected)"
    fi
    
    # Stop the server
    kill $SERVER_PID 2>/dev/null
    wait $SERVER_PID 2>/dev/null
    echo "SUCCESS: Development server stopped cleanly"
else
    echo "FAILED: Development server failed to start"
    cat server.log
    exit 1
fi

# STEP 2: Test code quality tools
echo "Testing code quality tools..."

# Test ruff check
echo "Running ruff check..."
cd /home/sheraz/src/calendar-bridge-clone/
uv run ruff check .
if [ $? -eq 0 ]; then
    echo "SUCCESS: ruff check passed"
else
    echo "WARNING: ruff check found issues (may need fixes)"
fi

# Test ruff format
echo "Testing ruff format..."
uv run ruff format --check .
if [ $? -eq 0 ]; then
    echo "SUCCESS: Code formatting is correct"
else
    echo "INFO: Code formatting issues detected (can be auto-fixed)"
fi

# STEP 3: Test Django admin interface
echo "Testing Django admin interface..."
cd src/
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/admin/ > admin_response.txt 2>/dev/null || echo "000" > admin_response.txt
# Note: This test may fail if server isn't running, which is OK

# STEP 4: Validate all critical files exist
echo "Validating critical project files..."
CRITICAL_FILES=(
    ".env"
    "src/manage.py"
    "src/calendar_sync/settings.py"
    "src/apps/calendars/models.py"
    "src/apps/accounts/models.py"
    "src/apps/dashboard/views.py"
    "src/db.sqlite3"
)

for file in "${CRITICAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "SUCCESS: $file exists"
    else
        echo "FAILED: $file missing"
        exit 1
    fi
done

echo "SUCCESS: TASK-006 completed successfully"
```

### Acceptance Criteria (AI Agent Validation)
**Each criterion must be programmatically verified:**

- [ ] **Development server starts successfully**
  ```bash
  # Validation command:
  cd src/
  timeout 10 uv run python manage.py runserver --noreload &
  SERVER_PID=$!
  sleep 5
  if kill -0 $SERVER_PID 2>/dev/null; then
      echo "SUCCESS: Development server working"
      kill $SERVER_PID
  else
      echo "FAILED: Development server failed"
      exit 1
  fi
  ```

- [ ] **Code quality tools functional**
  ```bash
  # Validation command:
  uv run ruff --version
  if [ $? -eq 0 ]; then echo "SUCCESS: ruff available"; else echo "FAILED: ruff not working"; exit 1; fi
  ```

- [ ] **All critical files present**
  ```bash
  # Validation command:
  if [ -f ".env" ] && [ -f "src/manage.py" ] && [ -f "src/db.sqlite3" ]; then
      echo "SUCCESS: Critical files present"
  else
      echo "FAILED: Missing critical files"
      exit 1
  fi
  ```

---

## TASK-007: Google Cloud Console Setup (Optional)
**Status:** Not Started  
**Estimated Time:** 60 minutes  
**Dependencies:** None (can be done in parallel)  

### Description
Set up Google Cloud Console project and OAuth credentials. This task can be done in parallel with the Django setup or deferred until needed.

### Acceptance Criteria
- [ ] Google Cloud Console project created
- [ ] Google Calendar API enabled
- [ ] OAuth 2.0 credentials created (Web application type)
- [ ] Authorized redirect URIs configured:
  - [ ] `http://localhost:8000/auth/callback/`
- [ ] Client ID and Client Secret obtained
- [ ] Credentials added to .env file

### Implementation Notes
- This task can be done independently of Django setup
- Save the JSON credentials file securely
- Document the setup process for future reference
- Ensure redirect URI matches exactly

---

## Summary (Updated with Guilfoyle's Fixes)
**Total estimated time:** 4 hours  
**Critical path:** TASK-001 → TASK-002 → TASK-003 → TASK-004 → TASK-005 → TASK-006  
**Optional parallel work:** TASK-007 can be done anytime

### Key Technical Fixes Implemented:
- **Proper Django project structure** (no nested directories)
- **Secure SECRET_KEY generation** using `secrets.token_urlsafe(50)`
- **Correct app registration** with `apps.` prefix in INSTALLED_APPS
- **Docker-compatible database path** using `sqlite:///./db.sqlite3`
- **Explicit working directory management** with validation steps
- **Structured apps/ directory** for better organization

### Task Sequence Rationale (Guilfoyle's Recommendations):
1. **Setup → Project → Apps → Environment → Database → URLs → Validation**
2. This sequence ensures each layer depends on the previous being complete
3. Working directory management is enforced throughout
4. Each task includes comprehensive validation for AI agent execution
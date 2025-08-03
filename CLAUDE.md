# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## AI Agent Quick Start (CRITICAL - READ FIRST)

### Prerequisites Validation for AI Agents
**MANDATORY: Run these commands before any development work:**

```bash
# Validate environment setup
pwd  # Expected: /home/sheraz/src/calendar-bridge-clone
python --version  # Expected: Python 3.11+
uv --version  # Expected: uv version info
ls pyproject.toml CLAUDE.md  # Expected: Both files exist

# Verify project is ready for AI agent work
echo "Environment validated for AI agent development"
```

### AI Agent Safety Protocol
**CRITICAL CONSTRAINTS - DO NOT IGNORE:**
- **NEVER** execute `rm -rf` or destructive commands without explicit user confirmation
- **ALWAYS** run tests before committing: `uv run python manage.py test`
- **MANDATORY** follow test-driven development: Write tests first, then implement
- **REQUIRED** maintain ≥75% test coverage for all new code
- **ESSENTIAL** validate every command with success/failure checking

### Quick Command Reference for AI Agents
```bash
# Setup and validation
uv sync --all-extras                    # Install dependencies
uv run python manage.py test            # Run tests (MANDATORY before commits)
uv run ruff check . && uv run ruff format .  # Code quality checks

# Development workflow
uv run python manage.py runserver       # Start dev server
uv run python manage.py makemigrations  # Create migrations
uv run python manage.py migrate         # Apply migrations

# Coverage and quality
uv run coverage run manage.py test      # Test with coverage
uv run coverage report --fail-under=75  # Check coverage threshold
```

## AI Agent Development Decision Tree

**Before Starting Any Phase:**
1. **Check Prerequisites** → Run validation commands above
2. **Review Task List** → Check [tasks/00-task-overview.md](tasks/00-task-overview.md)
3. **Engage Coverage-Enforcer** → Run `@coverage-enforcer analyze current Django coverage status`
4. **Validate Tests Pass** → Run `uv run python manage.py test`

**Phase 1: Foundation**
- **Focus**: Follow [tasks/01-setup-infrastructure.md](tasks/01-setup-infrastructure.md) and [tasks/02-models-authentication.md](tasks/02-models-authentication.md)
- **Critical Validations**: OAuth working, tests passing, models created
- **Success Criteria**: All Phase 1 tests pass, coverage ≥75%

**Phase 2: Core Sync**  
- **Focus**: Follow [tasks/03-google-calendar-integration.md](tasks/03-google-calendar-integration.md) and [tasks/04-sync-engine-implementation.md](tasks/04-sync-engine-implementation.md)
- **Critical Validations**: Bi-directional sync working, busy blocks tagged correctly
- **Success Criteria**: Manual sync test passes, reset functionality safe

**Phase 3: Enhancement**
- **Focus**: Follow [tasks/05-web-interface.md](tasks/05-web-interface.md) and [tasks/06-testing-deployment.md](tasks/06-testing-deployment.md)
- **Critical Validations**: Web interface functional, Docker deployment works
- **Success Criteria**: Production deployment successful, monitoring active

### Phase Transition Checklist
**MANDATORY before moving to next phase:**
```bash
# Validate current phase completion
echo "Validating phase completion..."
uv run python manage.py test --verbosity=2
uv run coverage report --fail-under=75
uv run ruff check .

# If all pass:
echo "Phase complete - ready for next phase"
# If any fail:
echo "Phase incomplete - fix issues before proceeding"
```

## AI Agent Success Indicators

**Green light to proceed indicators:**
- All prerequisite validation commands pass
- CLAUDE.md safety protocols understood and followed
- Test-driven development workflow established
- Coverage baseline recorded and enforced

**Red flags - STOP and escalate:**
- Any test failures that auto-fix doesn't resolve
- Coverage below 75% threshold
- OAuth or security-related errors
- Destructive operations without proper safeguards

## AI Agent Development Notes

### What's Provided for AI Agents
**Complete implementation guidance:**
- **CLAUDE.md**: Comprehensive command templates and safety guardrails
- **Task Files**: 52 detailed tasks with execution patterns and validation steps
- **Testing Framework**: Mandatory TDD workflow with coverage enforcement
- **Quality Gates**: Automated code quality and security validation
- **Subagent Integration**: Coverage-enforcer and code review integration points

### AI Agent Starting Point
**MANDATORY first steps for AI agents:**
1. **Read CLAUDE.md completely** - Contains critical safety protocols
2. **Run prerequisite validation** - Ensure environment is ready
3. **Start with tasks/01-setup-infrastructure.md** - Follow exact command patterns
4. **Engage @coverage-enforcer** - Establish coverage baseline

### Next Steps for AI Agents
Start with the AI agent validation sequence above, then follow the task implementation order for guaranteed success.

## Memories and Personal Notes

### AI Interaction Guidelines
- Please stop using time estimates to deliver work like humans are doing it. Unless you have new benchmarks for how quickly it takes a coding agent, then please don't offer it

### Code Quality and Best Practices
- Remember to run ruff linting and formatting early and often
- Comprehensive ruff configuration in pyproject.toml includes:
  - Django-specific rules (DJ)
  - Security checks (S - bandit)
  - Code complexity limits (C90 - max complexity 8)
  - Import sorting (I - isort compatible)
  - Per-file rule exceptions for tests, migrations, settings
- Run `uv run ruff check .` for linting
- Run `uv run ruff format .` for code formatting  
- Run `uv run ruff check --fix .` to auto-fix issues
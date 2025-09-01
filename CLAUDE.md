# DjangoCon US Automation Project Guide

## Essential Commands

### Development & Setup
- **Full setup**: `just setup` (bootstrap + migrate for new developers)
- **Bootstrap**: `just bootstrap` (install deps, create .env, build image)  
- **Start server**: `just up` or `just server` (runs on http://localhost:8000)
- **Stop server**: `just down` or `just stop`
- **Console access**: `just console` (bash shell in web container)

### Testing & Quality
- **Run tests**: `just test` (all tests)
- **Single test**: `just test tickets/tests/test_models.py::TestClassName::test_method`
- **System check**: `just check` (Django configuration validation)
- **Lint**: `just lint` (runs pre-commit on all files)

### Database Operations
- **Apply migrations**: `just migrate`
- **Create migrations**: `just makemigrations`
- **Django shell**: `just shell`
- **Create superuser**: `just createsuperuser`
- **Run management command**: `just run <command>`

### Dependencies & Maintenance
- **Update project**: `just update` (upgrade pip, pull/build images)
- **Lock dependencies**: `just lock` (updates uv.lock file)
- **Upgrade deps**: `just upgrade` (update to latest versions)
- **Clean up**: `just clean` (remove docker volumes/images)

### Deployment & Production
- **Deploy**: `just deploy` (to Fly.io production)
- **SSH to prod**: `just ssh`
- **Check status**: `just status`
- **Open prod site**: `just open` (https://dcus-automation-prod.fly.dev)
- **View logs**: `just logs` or `just tail` (follow recent logs)

## Code Style & Standards
- **Python**: 3.12, Django 5.2
- **Formatting**: Black-compatible (120 char line length)
- **Linting**: Ruff with rules 'B', 'E', 'F', 'I', 'W', 'B9'
- **Imports**: Standard library → Django/third-party → Local modules (sorted alphabetically)
- **Naming**: snake_case for variables/functions, PascalCase for classes
- **Testing**: pytest with django_db marker for DB tests, fixtures in conftest.py
- **Error Handling**: Use try/except with specific exceptions, atomic transactions for DB operations
- **Django Patterns**: Class-based views preferred, model fields have descriptive names

## Project Structure & Architecture

### Django Applications

**tickets/** - Email-based ticket distribution system
- Models: `TicketLink` - stores URLs with attendee email assignment tracking
- Views: `/tickets/` (claim form + results), `/tickets/create/` (admin bulk creation), `/tickets/list/` (admin overview)
- Admin: Bulk ticket management with assignment status
- Key Features: Atomic claiming with database locking, email-based assignment

**sendy/** - Email marketing integration
- Models: `Brand`, `List` - Sendy service configuration
- Utils: API client for subscriber management
- Management: `import_brands`, `import_lists` for sync
- Integration: Processes Tito webhook events into email subscriptions

**titowebhooks/** - Tito event platform webhooks
- Models: `TitoWebhookEvent`, `TitoEvent` - webhook payload processing
- Views: `/titowebhook/` - CSRF-exempt webhook endpoint
- Management: `send_to_sendy` - processes events to email subscriptions
- Background: Uses django-q2 for async task processing

### Key Integrations
- **Tito**: Webhook receiver for ticket purchases, triggers email subscriptions
- **Sendy**: Email list management API (requires SENDY_API_KEY, SENDY_ENDPOINT_URL)
- **Slack**: OAuth-based messaging (requires SLACK_OAUTH_TOKEN)
- **GitHub**: OAuth authentication via django-allauth

### Current Features (2025.8.4)
- **Ticket Management**: Create, assign, and track ticket links via email claiming
- **Admin Interface**: Bulk ticket operations, assignment tracking, GitHub OAuth login
- **Email Integration**: Automatic subscriber management via Tito → Sendy pipeline
- **Responsive Design**: Tailwind CSS with dark green theme
- **Background Processing**: django-q2 for webhook processing

### Testing Patterns
- Framework: pytest with django_db marker for database tests
- Fixtures: Define in conftest.py files  
- Test structure: `app/tests/test_models.py`, `app/tests/test_views.py`
- Run single test: `just test path/to/test.py::TestClass::test_method`
- Database: Tests use transactional rollback by default

## Development Environment
- **Docker Compose**: web (Django), db (PostgreSQL), worker (django-q2)
- **Database**: PostgreSQL with auto-upgrade, default `postgres://postgres@postgres/postgres`
- **Static files**: WhiteNoise serving, Tailwind CSS via CDN
- **Environment**: Copy `.env-dist` to `.env`, required vars: DATABASE_URL, DJANGO_DEBUG
- **Version**: CalVer format YYYY.MM.INC1 (current: 2025.8.4)

## Deployment
- **Platform**: Fly.io (app: dcus-automation-prod)
- **Processes**: Gunicorn WSGI (2 workers), Django-Q worker
- **Release**: Auto-migrations on deploy, automatic GitHub Actions deployment
- **Monitoring**: Flyctl for SSH access, status checks, log viewing

## Important Notes
- All imports must be on separate lines
- Never add comments unless explicitly requested
- Use django-test-plus with `tp` fixture for testing
- Email-based ticket assignment (no access tracking)
- GitHub OAuth requires Social App configuration in Django admin
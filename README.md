# DjangoCon US Automation

Django Project to automate tasks for the DjangoCon US.

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- [Just](https://just.systems/) command runner (optional but recommended)

### Quick Setup

1. **Clone and setup environment**:
   ```shell
   just setup
   ```
   This will:
   - Install/upgrade pip and uv
   - Copy `.env-dist` to `.env` if it doesn't exist
   - Build the Docker image
   - Run database migrations

2. **Start the development server**:
   ```shell
   just up
   ```
   Access the application at [http://localhost:8000](http://localhost:8000)

### Manual Setup (without Just)

If you don't have Just installed:

1. **Create environment file**:
   ```shell
   cp .env-dist .env
   ```

2. **Build and start**:
   ```shell
   docker compose build
   docker compose up
   ```

## Development Commands

### Setup & Initialization
- `just setup` - Complete initial setup for new developers (runs bootstrap then migrations)
- `just bootstrap` - Bootstrap the project: install Python tools, create .env file, and build Docker images
- `just update` - Update the project: upgrade pip/uv, pull latest images, and rebuild containers

### Docker & Services
- `just up` / `just server` - Start all services (web, db, worker) in the foreground
- `just start` - Start services in detached/background mode
- `just down` / `just stop` - Stop and remove all running containers (preserves volumes)
- `just restart [service]` - Restart one or more services (e.g., 'just restart web')
- `just build` - Build or rebuild the Docker images without cache
- `just console` - Open an interactive bash shell inside the web container
- `just logs` - View container logs (use -f to follow, --tail N to limit lines)
- `just tail` - Follow the last 100 lines of logs in real-time
- `just clean` - Remove all containers, volumes, and locally built images

### Django Operations
- `just migrate` - Apply all pending database migrations
- `just makemigrations` - Create new migration files for model changes
- `just createsuperuser` - Create a superuser account for Django admin access
- `just shell` - Open Django's interactive Python shell with project context
- `just runserver` - Run Django's built-in development server (bypasses Docker)
- `just run [command]` - Run any Django management command (e.g., 'just run collectstatic')
- `just check` - Validate Django project configuration and settings

### Testing & Code Quality
- `just test [path]` - Run the test suite with pytest (optionally specify test paths)
- `just lint` - Run pre-commit hooks on all files (formatting, linting, type checks)
- `just fmt` - Format this justfile using Just's built-in formatter (requires --unstable flag)

### Dependency Management
- `just lock` - Generate pinned requirements.txt from requirements.in
- `just upgrade` - Update all Python dependencies to their latest compatible versions

### Utilities
- `just bump [--dry]` - Update version number using bumpver (--dry for preview, omit for actual bump)

## Project Structure

### Django Applications

- **tickets/** - Ticket link distribution system for event access
- **sendy/** - Email marketing integration with Sendy API
- **titowebhooks/** - Webhook receiver for Tito event platform

### Key Features

- **Email-based ticket claiming** - Attendees can claim unique ticket links
- **Admin ticket management** - Bulk creation and monitoring of tickets
- **GitHub OAuth authentication** - Staff login via GitHub
- **Email subscription management** - Integration with Sendy for marketing
- **Webhook processing** - Handle Tito purchase events

## Deployment

Deployments happen automatically when changes are pushed to the `main` branch via GitHub Actions.

Production URL: https://automation.defna.org

## Configuration

Edit `.env` file to configure:

- **Database**: `DATABASE_URL` (defaults to local PostgreSQL)
- **Email**: `SENDY_API_KEY`, `SENDY_ENDPOINT_URL` for Sendy integration
- **Slack**: `SLACK_OAUTH_TOKEN` for notifications
- **Debug**: `DJANGO_DEBUG=True` for development

## Architecture

- **Backend**: Django 4.2.11 LTS with Python 3.12
- **Database**: PostgreSQL with atomic transactions
- **Task Queue**: django-q2 for background processing
- **Frontend**: Tailwind CSS with minimal JavaScript
- **Authentication**: django-allauth with GitHub OAuth
- **Deployment**: Gunicorn WSGI server

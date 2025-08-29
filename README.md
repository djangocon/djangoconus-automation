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

### Common Tasks
- `just up` - Start all services
- `just down` - Stop all services  
- `just test` - Run all tests
- `just lint` - Run linting and formatting checks
- `just shell` - Open Django shell
- `just console` - Open bash shell in web container

### Database Operations
- `just migrate` - Apply database migrations
- `just makemigrations` - Create new migrations
- `just createsuperuser` - Create Django admin user

### Testing and Quality
- `just test path/to/test.py::TestClass::test_method` - Run specific test
- `just check` - Run Django system checks
- `just lint` - Run pre-commit hooks on all files

### Dependency Management
- `just lock` - Compile requirements.in to requirements.txt
- `just upgrade` - Upgrade dependencies to latest versions
- `just update` - Update project (pull images, build)

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

### Automatic Deployments

Deployments happen automatically when changes are pushed to the `main` branch via GitHub Actions.

### Manual Deployment

- `just deploy` - Deploy to production (Fly.io)
- `just ssh` - SSH into production server
- `just status` - Check production deployment status
- `just open` - Open production site in browser

Production URL: https://dcus-automation-prod.fly.dev

## Configuration

Edit `.env` file to configure:

- **Database**: `DATABASE_URL` (defaults to local PostgreSQL)
- **Email**: `SENDY_API_KEY`, `SENDY_ENDPOINT_URL` for Sendy integration
- **Slack**: `SLACK_OAUTH_TOKEN` for notifications
- **Debug**: `DJANGO_DEBUG=True` for development

## Architecture

- **Backend**: Django 4.2.11 LTS with Python 3.11
- **Database**: PostgreSQL with atomic transactions
- **Task Queue**: django-q2 for background processing
- **Frontend**: Tailwind CSS with minimal JavaScript
- **Authentication**: django-allauth with GitHub OAuth
- **Deployment**: Fly.io with Gunicorn WSGI server
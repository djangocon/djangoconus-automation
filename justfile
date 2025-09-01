set dotenv-load := false

# Define common command prefixes for docker operations

COMPOSE := "docker compose run --rm --no-deps web"
MANAGE := COMPOSE + " python -m manage"

# List all available commands with groups when running 'just' without arguments
@_default:
    just --list --list-heading $'Available commands:\n'

# Format this justfile using Just's built-in formatter (requires --unstable flag)
@fmt:
    just --fmt --unstable

# Bootstrap the project: install Python tools, create .env file, and build Docker images
[group('setup')]
bootstrap:
    #!/usr/bin/env bash
    set -euo pipefail

    python -m pip install --upgrade pip uv

    if [ ! -f ".env" ]; then
        cp .env-dist .env
        echo ".env created"
    fi

    docker compose build --force-rm

# Complete initial setup for new developers (runs bootstrap then migrations)
[group('setup')]
@setup: bootstrap migrate

# Update the project: upgrade pip/uv, pull latest images, and rebuild containers
[group('setup')]
@update:
    -pip install --upgrade pip uv
    -docker compose pull
    -docker compose build

# Build or rebuild the Docker images without cache
[group('docker')]
@build:
    docker compose build

# Start all services (web, db, worker) in the foreground
[group('docker')]
@up *ARGS:
    docker compose up {{ ARGS }}

# Stop and remove all running containers (preserves volumes)
[group('docker')]
@down:
    docker compose down

# Stop and remove all containers (alias for 'down')
[group('docker')]
@stop:
    docker compose down

# Start the development server (alias for 'up')
[group('docker')]
@server *ARGS:
    just up {{ ARGS }}

# Start services in detached/background mode
[group('docker')]
@start +ARGS="--detach":
    just server {{ ARGS }}

# Restart one or more services (e.g., 'just restart web')
[group('docker')]
@restart *ARGS:
    docker compose restart {{ ARGS }}

# Remove all containers, volumes, and locally built images
[group('docker')]
@clean:
    docker compose down -v --rmi local

# View container logs (use -f to follow, --tail N to limit lines)
[group('docker')]
@logs *ARGS:
    docker compose logs {{ ARGS }}

# Follow the last 100 lines of logs in real-time
[group('docker')]
@tail:
    just logs --follow --tail 100

# Open an interactive bash shell inside the web container
[group('docker')]
@console:
    {{ COMPOSE }} /bin/bash

# Apply all pending database migrations
[group('django')]
@migrate *ARGS:
    {{ MANAGE }} migrate --noinput {{ ARGS }}

# Create new migration files for model changes
[group('django')]
@makemigrations *ARGS:
    {{ MANAGE }} makemigrations --noinput {{ ARGS }}

# Open Django's interactive Python shell with project context
[group('django')]
@shell:
    {{ MANAGE }} shell

# Run Django's built-in development server (bypasses Docker)
[group('django')]
@runserver:
    {{ MANAGE }} runserver

# Create a superuser account for Django admin access
[group('django')]
@createsuperuser:
    {{ MANAGE }} createsuperuser

# Run any Django management command (e.g., 'just run collectstatic')
[group('django')]
@run +ARGS="--help":
    {{ MANAGE }} {{ ARGS }}

# Validate Django project configuration and settings
[group('django')]
@check:
    {{ MANAGE }} check

# Run the test suite with pytest (optionally specify test paths)
[group('quality')]
@test *ARGS:
    {{ COMPOSE }} pytest {{ ARGS }}

# Run pre-commit hooks on all files (formatting, linting, type checks)
[group('quality')]
@lint *ARGS:
    uv --quiet tool run --with pre-commit-uv pre-commit run {{ ARGS }} --all-files

# Generate pinned requirements.txt from requirements.in
[group('deps')]
@lock *ARGS:
    docker compose run \
        --entrypoint= \
        --rm web \
            bash -c "uv pip compile \
                --output-file ./requirements.txt \
                {{ ARGS }} ./requirements.in"

# Update all Python dependencies to their latest compatible versions
[group('deps')]
@upgrade:
    just lock --upgrade

# Deploy the application to Fly.io production environment
[group('deploy')]
@deploy *ARGS:
    # https://dcus-automation-prod.fly.dev/
    flyctl deploy --config fly.toml {{ ARGS }}

# SSH into the production server for debugging or maintenance
[group('deploy')]
@ssh *ARGS:
    flyctl ssh console --config fly.toml {{ ARGS }}

# View the current status and health of production deployment
[group('deploy')]
@status *ARGS:
    flyctl status --config fly.toml {{ ARGS }}

# Open the production website in your default browser
[group('deploy')]
@open:
    open https://dcus-automation-prod.fly.dev/

# Update version number using bumpver (--dry for preview, omit for actual bump)
[group('utils')]
@bump *ARGS="--dry":
    bumpver update {{ ARGS }}

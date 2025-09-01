set dotenv-load := false

# Define common command prefixes for docker operations

COMPOSE := "docker compose run --rm --no-deps web"
MANAGE := COMPOSE + " python -m manage"

# Show all available commands when running 'just' without arguments
@_default:
    just --list --list-heading $'Available commands:\n'

# Format the justfile (for developers maintaining this file)
@fmt:
    just --fmt --unstable

# Install/update all dependencies, create env file if needed, build docker image
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

# Full setup for new developers (bootstrap + database migrations)
[group('setup')]
@setup: bootstrap migrate

# Update existing project: upgrade pip, pull and build latest images
[group('setup')]
@update:
    -pip install --upgrade pip uv
    -docker compose pull
    -docker compose build

# Build the docker image
[group('docker')]
@build:
    docker compose build

# Start all services with docker compose
[group('docker')]
@up *ARGS:
    docker compose up {{ ARGS }}

# Stop all containers without removing them
[group('docker')]
@down:
    docker compose down

# Alias to docker compose down - stop and remove containers
[group('docker')]
@stop:
    docker compose down

# Start the application using docker compose up
[group('docker')]
@server *ARGS:
    just up {{ ARGS }}

# Start the application in detached mode by default
[group('docker')]
@start +ARGS="--detach":
    just server {{ ARGS }}

# Restart containers (optionally specify which service)
[group('docker')]
@restart *ARGS:
    docker compose restart {{ ARGS }}

# Clean up docker resources completely (volumes and images)
[group('docker')]
@clean:
    docker compose down -v --rmi local

# View docker logs with optional arguments
[group('docker')]
@logs *ARGS:
    docker compose logs {{ ARGS }}

# Show recent logs and follow new ones
[group('docker')]
@tail:
    just logs --follow --tail 100

# Open an interactive bash shell in the web container
[group('docker')]
@console:
    {{ COMPOSE }} /bin/bash

# Apply pending database migrations
[group('django')]
@migrate *ARGS:
    {{ MANAGE }} migrate --noinput {{ ARGS }}

# Generate new Django migrations for model changes
[group('django')]
@makemigrations *ARGS:
    {{ MANAGE }} makemigrations --noinput {{ ARGS }}

# Open a Django shell for interactive Python with project context
[group('django')]
@shell:
    {{ MANAGE }} shell

# Run Django's development server directly
[group('django')]
@runserver:
    {{ MANAGE }} runserver

# Create a Django superuser for admin access
[group('django')]
@createsuperuser:
    {{ MANAGE }} createsuperuser

# Run a Django management command (defaults to showing help)
[group('django')]
@run +ARGS="--help":
    {{ MANAGE }} {{ ARGS }}

# Run Django system check to validate project configuration
[group('django')]
@check:
    {{ MANAGE }} check

# Run tests with pytest (can specify path to test file/module/function as args)
[group('quality')]
@test *ARGS:
    {{ COMPOSE }} pytest {{ ARGS }}

# Run pre-commit hooks on all files
[group('quality')]
@lint *ARGS:
    uv --quiet tool run --with pre-commit-uv pre-commit run {{ ARGS }} --all-files

# Compile requirements.in to requirements.txt with version pinning
[group('deps')]
@lock *ARGS:
    docker compose run \
        --entrypoint= \
        --rm web \
            bash -c "uv pip compile \
                --output-file ./requirements.txt \
                {{ ARGS }} ./requirements.in"

# Upgrade existing Python dependencies to their latest versions
[group('deps')]
@upgrade:
    just lock --upgrade

# Deploy the application to production environment
[group('deploy')]
@deploy *ARGS:
    # https://dcus-automation-prod.fly.dev/
    flyctl deploy --config fly.toml {{ ARGS }}

# SSH into the production server for debugging
[group('deploy')]
@ssh *ARGS:
    flyctl ssh console --config fly.toml {{ ARGS }}

# Check status of the production deployment
[group('deploy')]
@status *ARGS:
    flyctl status --config fly.toml {{ ARGS }}

# Open the production site in default browser
[group('deploy')]
@open:
    open https://dcus-automation-prod.fly.dev/

# Bump the version number (use --dry for preview, omit for actual update)
[group('utils')]
@bump *ARGS="--dry":
    bumpver update {{ ARGS }}

set dotenv-load := false

# Define common command prefixes for docker operations
COMPOSE := "docker compose run --rm --no-deps web"
MANAGE := COMPOSE + " python -m manage"

# Show all available commands when running 'just' without arguments
@_default:
    just --list

# Format the justfile (for developers maintaining this file)
@fmt:
    just --fmt --unstable

# Install/update all dependencies, create env file if needed, build docker image
bootstrap:
    #!/usr/bin/env bash
    set -euo pipefail

    python -m pip install --upgrade pip uv

    if [ ! -f ".env" ]; then
        cp .env-dist .env
        echo ".env created"
    fi

    docker compose build --force-rm

# Build the docker image
@build:
    docker compose build

# Bump the version number (use --dry for preview, omit for actual update)
@bump *ARGS="--dry":
    bumpver update {{ ARGS }}

# Run Django system check to validate project configuration
@check:
    {{ MANAGE }} check

# Clean up docker resources completely (volumes and images)
@clean:
    docker compose down -v --rmi local

# Open an interactive bash shell in the web container
@console:
    {{ COMPOSE }} /bin/bash

# Deploy the application to production environment
@deploy *ARGS:
    # https://dcus-automation-prod.fly.dev/
    flyctl deploy --config fly.toml {{ ARGS }}

# Open the production site in default browser
@open:
    open https://dcus-automation-prod.fly.dev/


# Run linting on all files using pre-commit hooks
@lint:
    just pre-commit --all-files

# View docker logs with optional arguments
@logs *ARGS:
    docker compose logs {{ ARGS }}

# Run pre-commit hooks on specified files (or all files with --all-files)
@pre-commit *ARGS:
    pre-commit run {{ ARGS }}

# Start the application using docker compose up
@server *ARGS:
    just up {{ ARGS }}

# Full setup for new developers (bootstrap + database migrations)
@setup: bootstrap migrate

# Open a Django shell for interactive Python with project context
@shell:
    {{ MANAGE }} shell

# SSH into the production server for debugging
@ssh *ARGS:
    flyctl ssh console --config fly.toml {{ ARGS }}

# Check status of the production deployment
@status *ARGS:
    flyctl status --config fly.toml {{ ARGS }}

# Run tests with pytest (can specify path to test file/module/function as args)
@test *ARGS:
    {{ COMPOSE }} pytest {{ ARGS }}

# Update existing project: upgrade pip, pull and build latest images
@update:
    -pip install --upgrade pip uv
    -docker compose pull
    -docker compose build

# Create a Django superuser for admin access
@createsuperuser:
    {{ MANAGE }} createsuperuser

# Stop all containers without removing them
@down:
    docker compose down

# Compile requirements.in to requirements.txt with version pinning
@lock *ARGS:
    docker compose run \
        --entrypoint= \
        --rm web \
            bash -c "uv pip compile \
                --output-file ./requirements.txt \
                {{ ARGS }} ./requirements.in"

# Generate new Django migrations for model changes
@makemigrations *ARGS:
    {{ MANAGE }} makemigrations --noinput {{ ARGS }}

# Apply pending database migrations
@migrate *ARGS:
    {{ MANAGE }} migrate --noinput {{ ARGS }}

# Run a Django management command (defaults to showing help)
@run +ARGS="--help":
    {{ MANAGE }} {{ ARGS }}

# Restart containers (optionally specify which service)
@restart *ARGS:
    docker compose restart {{ ARGS }}

# Run Django's development server directly
@runserver:
    {{ MANAGE }} runserver

# Start the application in detached mode by default
@start +ARGS="--detach":
    just server {{ ARGS }}

# Alias to docker compose down - stop and remove containers
@stop:
    docker compose down

# Show recent logs and follow new ones
@tail:
    just logs --follow --tail 100

# Start all services with docker compose
@up *ARGS:
    docker compose up {{ ARGS }}

# Upgrade existing Python dependencies to their latest versions
@upgrade:
    just lock --upgrade

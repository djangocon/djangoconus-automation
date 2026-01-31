set dotenv-load := false

export JUST_UNSTABLE := "true"

# Display list of available recipes
@_default:
    just --list

# Initialize project with first-time setup
bootstrap *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail

    if [ ! -f ".env" ]; then
        cp .env-dist .env
        echo ".env created"
    fi

    just build {{ ARGS }} --force-rm

# Build Docker containers with optional arguments
@build *ARGS:
    docker compose build {{ ARGS }}

# Open a bash shell in the utility container
@console:
    docker compose run --rm --no-deps utility /bin/bash

# Open interactive bash console in database container
@console-db:
    docker compose run \
        --no-deps \
        --rm \
        db /bin/bash

# Stop and remove Docker containers and networks
@down *ARGS:
    docker compose down {{ ARGS }}

# Format justfile with proper indentation and spacing
@fmt:
    just --fmt

# Run pre-commit hooks on all files
@lint *ARGS:
    uv --quiet tool run prek {{ ARGS }} --all-files

# Update pre-commit hooks to latest versions
@lint-autoupdate:
    uv --quiet tool run prek autoupdate

# Create or update dependency lock file
@lock *ARGS:
    uv lock {{ ARGS }}

# Display logs from Docker containers
@logs *ARGS:
    docker compose logs {{ ARGS }}

# Run Django management commands in the utility container
@manage *ARGS:
    docker compose run --rm --no-deps utility uv run -m manage {{ ARGS }}

# Run Django migrations to apply database schema changes
@migrate *ARGS:
    docker compose run --rm --no-deps utility uv run -m manage migrate {{ ARGS }}

# Generate Django migration files from model changes
@makemigrations *ARGS:
    docker compose run --rm --no-deps utility uv run -m manage makemigrations {{ ARGS }}

# Dump database to file
@pg_dump file='db.dump':
    docker compose run \
        --no-deps \
        --rm \
        db pg_dump \
            --dbname "${DATABASE_URL:=postgres://postgres@db/postgres}" \
            --file /src/{{ file }} \
            --format=c \
            --verbose

# Restore database dump from file
@pg_restore file='db.dump':
    docker compose run \
        --no-deps \
        --rm \
        db pg_restore \
            --dbname "${DATABASE_URL:=postgres://postgres@db/postgres}" \
            --no-owner \
            --verbose \
            /src/{{ file }}

# Pull Docker images
@pull *ARGS:
    docker compose pull {{ ARGS }}

# Restart Docker containers
@restart *ARGS:
    docker compose restart {{ ARGS }}

# Run a one-off command in the utility container
@run *ARGS:
    docker compose run \
        --no-deps \
        --rm \
        utility {{ ARGS }}

# Open Django's interactive Python shell
@shell:
    docker compose run --rm --no-deps utility uv run -m manage shell

# Start the application (alias for 'up')
@start *ARGS="--detach":
    just up {{ ARGS }}

# Stop running containers
@stop *ARGS:
    docker compose stop {{ ARGS }}

# Follow logs from Docker containers
@tail:
    just logs --follow

# Run tests with pytest in the utility container
@test *ARGS:
    docker compose run \
        --no-deps \
        --rm \
        utility uv run pytest {{ ARGS }}

# Start Docker containers with optional arguments
@up *ARGS:
    docker compose up {{ ARGS }}

# Update dependencies and pre-commit hooks
@update:
    just upgrade
    just lint-autoupdate

# Upgrade dependencies in lock file
@upgrade:
    just lock --upgrade

# Watch for file changes and rebuild Docker services
@watch *ARGS:
    docker compose watch {{ ARGS }}

# Update version number using bumpver (--dry for preview, omit for actual bump)
@bump *ARGS="--dry":
    uvx bumpver update {{ ARGS }}

# Create a superuser account for Django admin access
@createsuperuser:
    docker compose run --rm --no-deps utility uv run -m manage createsuperuser

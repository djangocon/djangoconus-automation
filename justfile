set dotenv-load := false

COMPOSE := "docker compose run --rm --no-deps web"
MANAGE := COMPOSE + " python -m manage"

@_default:
    just --list

@fmt:
    just --fmt --unstable

# installs/updates all dependencies
bootstrap:
    #!/usr/bin/env bash
    set -euo pipefail

    python -m pip install --upgrade pip uv

    if [ ! -f ".env" ]; then
        cp .env-dist .env
        echo ".env created"
    fi

    # if [ ! -f "compose.override.yml" ]; then
    #     cp compose.override.yml-dist docker compose.override.yml
    #     echo "compose.override.yml created"
    # fi

    docker compose build --force-rm

@build:
    docker compose build

@bump *ARGS="--dry":
    bumpver update {{ ARGS }}

@check:
    {{ MANAGE }} check

@clean:
    docker compose down -v --rmi local

# opens a console
@console:
    {{ COMPOSE }} /bin/bash

@deploy-to-production *ARGS:
    # https://dcus-automation-prod.fly.dev/
    flyctl deploy --config fly.production.toml {{ ARGS }}

@deploy-to-staging *ARGS:
    # https://dcus-automation.fly.dev/
    flyctl deploy {{ ARGS }}

@open-production:
    open https://dcus-automation-prod.fly.dev/

@open-staging:
    open https://dcus-automation.fly.dev/

@lint:
    just pre-commit --all-files

@logs *ARGS:
    docker compose logs {{ ARGS }}

# Python linting
@pre-commit *ARGS:
    pre-commit run {{ ARGS }}

# starts app
@server *ARGS:
    just up {{ ARGS }}

# sets up a project to be used for the first time
@setup: bootstrap migrate

# opens a console
@shell:
    {{ MANAGE }} shell

@ssh-to-production *ARGS:
    flyctl ssh console --config fly.production.toml {{ ARGS }}

@ssh-to-staging *ARGS:
    flyctl ssh console {{ ARGS }}

# runs tests
@test *ARGS:
    {{ COMPOSE }} pytest {{ ARGS }}

# updates a project to run at its current version
@update:
    -pip install --upgrade pip uv
    -docker compose pull
    -docker compose build

@createsuperuser:
    {{ MANAGE }} createsuperuser

@down:
    docker compose down

# Compile new python dependencies
@lock *ARGS:
    docker compose run \
        --entrypoint= \
        --rm web \
            bash -c "uv pip compile \
                --output-file ./requirements.txt \
                {{ ARGS }} ./requirements.in"

@makemigrations *ARGS:
    {{ MANAGE }} makemigrations --noinput {{ ARGS }}

@migrate *ARGS:
    {{ MANAGE }} migrate --noinput {{ ARGS }}

@run +ARGS="--help":
    {{ MANAGE }} {{ ARGS }}

@restart *ARGS:
    docker compose restart {{ ARGS }}

@runserver:
    {{ MANAGE }} runserver

@start +ARGS="--detach":
    just server {{ ARGS }}

@stop:
    docker compose down

@tail:
    just logs --follow --tail 100

@up *ARGS:
    docker compose up {{ ARGS }}

# Upgrade existing Python dependencies to their latest versions
@upgrade:
    just lock --upgrade

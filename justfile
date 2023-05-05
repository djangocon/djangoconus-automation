set dotenv-load := false

COMPOSE := "docker-compose run --rm --no-deps web"
MANAGE := COMPOSE + " python manage.py"

@_default:
    just --list

@fmt:
    just --fmt --unstable

# installs/updates all dependencies
bootstrap:
    #!/usr/bin/env bash
    set -euo pipefail

    if [ ! -f ".env" ]; then
        cp .env-dist .env
        echo ".env created"
    fi

    # if [ ! -f "docker-compose.override.yml" ]; then
    #     cp docker-compose.override.yml-dist docker-compose.override.yml
    #     echo "docker-compose.override.yml created"
    # fi

    {{ COMPOSE }} build --force-rm

@build:
    docker-compose build

@bump:
    bumpver update

@check:
    {{ MANAGE }} check

@clean:
    docker-compose down -v --rmi local

# opens a console
@console:
    {{ COMPOSE }} /bin/bash

@lint:
    just pre-commit --all-files

@logs *ARGS:
    docker-compose logs {{ ARGS }}

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

# runs tests
@test *ARGS:
    docker-compose run --rm --no-deps web pytest {{ ARGS }}

# updates a project to run at its current version
@update:
    -pip install -U pip
    -docker-compose pull
    -docker-compose build

@createsuperuser:
    {{ MANAGE }} createsuperuser

@down:
    docker-compose down

@loaddata:
    {{ MANAGE }} loaddata \
        ./newsletters/fixtures/newsletters.json \
        ./news/fixtures/news-fixtures.json

@makemigrations:
    {{ MANAGE }} makemigrations --noinput

@migrate *ARGS:
    {{ MANAGE }} migrate --noinput {{ ARGS }}

# Compile new python dependencies
@pip-compile *ARGS:
    docker-compose run \
        --entrypoint= \
        --rm web \
            bash -c "pip-compile {{ ARGS }} ./requirements.in \
                --generate-hashes \
                --resolver=backtracking \
                --output-file ./requirements.txt"

# Upgrade existing Python dependencies to their latest versions
@pip-compile-upgrade:
    just pip-compile --upgrade

@poll_feeds:
    {{ MANAGE }} poll_feeds

@run +ARGS="--help":
    {{ MANAGE }} {{ ARGS }}

@collectstatic:
    {{ MANAGE }} collectstatic --no-input

@restart *ARGS:
    docker-compose restart {{ ARGS }}

@runserver:
    {{ MANAGE }} runserver

@start +ARGS="--detach":
    just server {{ ARGS }}

@stop:
    docker-compose down

@tail:
    just logs --follow --tail 100

@up *ARGS:
    docker-compose up {{ ARGS }}

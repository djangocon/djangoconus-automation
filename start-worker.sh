#!/bin/sh
uv run -m manage migrate --noinput

# sync_schedules is deliberately NOT run here. It creates django-q Schedule rows
# from Q_SCHEDULES on every worker boot, which meant a deploy could quietly add
# or re-add a background job. Schedules already in the database keep running
# untouched; this only stops deploys from registering them behind our backs.
#
# To register a new or missing job, run it by hand:
#     ssh defna-node1
#     docker exec -w /src <web-container> uv run --no-sync manage.py sync_schedules
uv run -m manage qcluster

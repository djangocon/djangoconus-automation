#!/bin/sh
uv run -m manage migrate --noinput
uv run -m manage sync_schedules

uv run -m manage qcluster

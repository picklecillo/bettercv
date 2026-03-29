#!/bin/sh
set -e

uv run python manage.py migrate --noinput

exec uv run gunicorn ats_analyzer.wsgi:application --bind 0.0.0.0:8000 --workers 1

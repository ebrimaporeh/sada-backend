#!/usr/bin/env bash
set -e

echo "==> Installing dependencies"
pip install -r requirements.txt

echo "==> Collecting static files"
python manage.py collectstatic --no-input

echo "==> Running database migrations"
python manage.py migrate

echo "==> Build complete"

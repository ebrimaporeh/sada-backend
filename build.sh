#!/usr/bin/env bash
set -e

echo "==> Installing dependencies"
pip install -r requirements.txt

echo "==> Collecting static files"
python manage.py collectstatic --no-input

echo "==> Running database migrations"
python manage.py migrate

echo "==> Seeding initial data"
python manage.py seed_data

echo "==> Build complete"

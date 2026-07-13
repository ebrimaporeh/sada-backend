import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings.production')

app = Celery('sada')
app.config_from_object('django.conf:settings', namespace='CELERY')
# autodiscover_tasks() with no args only scans INSTALLED_APPS for tasks.py —
# `emails` holds tasks.py but isn't (and doesn't need to be) a registered
# Django app, so it has to be named explicitly here too.
app.autodiscover_tasks()
app.autodiscover_tasks(packages=['emails'])

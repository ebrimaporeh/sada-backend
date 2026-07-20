import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings.production')

app = Celery('sada')
app.config_from_object('django.conf:settings', namespace='CELERY')
# autodiscover_tasks() with no args only scans INSTALLED_APPS for tasks.py —
# `emails` holds tasks.py but isn't (and doesn't need to be) a registered
# Django app, so it has to be named explicitly here too.
app.autodiscover_tasks()
app.autodiscover_tasks(packages=['emails'])

# Reconciliation safety net for donations/payouts stuck PENDING/PROCESSING
# because a gateway webhook was missed or delayed — requires a
# `celery -A config beat` process running alongside the worker.
app.conf.beat_schedule = {
    'sweep-pending-donations': {
        'task': 'apps.donations.tasks.sweep_pending_donations_task',
        'schedule': crontab(minute='*/5'),
    },
    'sweep-processing-payouts': {
        'task': 'apps.payments.tasks.sweep_processing_payouts_task',
        'schedule': crontab(minute='*/5'),
    },
}

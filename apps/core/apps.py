from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    label = 'core'

    def ready(self):
        # Settings live in a top-level `settings` package, not `config.settings`,
        # so nothing implicitly imports `config/__init__.py` (where the Celery
        # app gets built and configured from Django settings) under entry
        # points that don't touch ROOT_URLCONF — `manage.py shell` being the
        # main one. Without this, @shared_task .delay() calls silently fall
        # back to Celery's blank default app (AMQP/localhost), not Redis.
        # AppConfig.ready() runs after settings are fully loaded on every
        # entry point (shell, runserver, migrate, celery worker), so it's a
        # safe, universal place to trigger that import.
        from config.celery import app as celery_app  # noqa: F401

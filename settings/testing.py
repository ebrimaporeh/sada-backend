from .base import *

DEBUG = True

# In-memory sqlite by default -- fast for local `manage.py test` runs, with
# no setup required. CI sets DATABASE_URL to a real, disposable Postgres
# service instead (see .github/workflows/test.yml), so the same test suite
# also runs against the actual production database engine before merge --
# migrations and Postgres-specific behavior get caught in CI even though
# local runs stay on sqlite. dj_database_url is already imported by
# settings/base.py's own `from .base import *` above.
DATABASES = {
    'default': dj_database_url.config(
        default='sqlite:///:memory:',
        conn_max_age=0,
    )
}

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

ACCOUNT_EMAIL_VERIFICATION = 'none'

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

SIMPLE_JWT = {
    **SIMPLE_JWT,
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=5),
}

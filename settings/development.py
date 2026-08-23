from .base import *

DEBUG = True

ALLOWED_HOSTS = ['*']

CORS_ALLOW_ALL_ORIGINS = True

# EMAIL_BACKEND is already forced to Anymail's Resend backend in base.py —
# don't override it here. Local dev sends real emails via Resend, same as
# production; there is no console/SMTP fallback.

# Faster password hashing for tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Disable email verification in development
ACCOUNT_EMAIL_VERIFICATION = 'none'

INSTALLED_APPS += [
    # 'debug_toolbar',  # Uncomment if using django-debug-toolbar
]

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

from .base import *

DEBUG = True

ALLOWED_HOSTS = ['*']

CORS_ALLOW_ALL_ORIGINS = True

# EMAIL_BACKEND is already read from .env in base.py (defaults to console if
# unset there) — don't hardcode it here, or a real SMTP backend configured in
# .env gets silently overridden and "sent" emails just print to the terminal.

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

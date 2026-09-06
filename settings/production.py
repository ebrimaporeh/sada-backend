from .base import *

DEBUG = config('DEBUG', default=False, cast=bool)

# ─── Security ─────────────────────────────────────────────────────────────────

SECURE_SSL_REDIRECT = True
# Railway terminates TLS at its edge and forwards requests over plain HTTP,
# adding X-Forwarded-Proto. Without this, SecurityMiddleware never sees a
# request as secure and redirects every request, causing a redirect loop.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# ─── CORS (production must be explicit) ─────────────────────────────────────

CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', cast=Csv())

# Django only trusts these for cookie-authenticated POST/PUT/DELETE (session
# auth via allauth/admin) -- the SPA's own JWT-authenticated calls aren't
# cookie-based and don't need this, but without it any session-authenticated
# cross-origin request (e.g. the Django admin behind a proxy, or allauth's
# social-login callbacks) is rejected. Defaults to the same origins as CORS
# since in practice that's the one domain that legitimately calls this API.
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default=','.join(CORS_ALLOWED_ORIGINS), cast=Csv())

# ─── Caching ─────────────────────────────────────────────────────────────────

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        # For Redis, replace with:
        # 'BACKEND': 'django_redis.cache.RedisCache',
        # 'LOCATION': config('REDIS_URL'),
    }
}

# ─── Logging ─────────────────────────────────────────────────────────────────

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

# ─── JWT (shorter expiry in production) ─────────────────────────────────────

from datetime import timedelta
SIMPLE_JWT = {
    **SIMPLE_JWT,
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
}

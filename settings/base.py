import os
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost', cast=Csv())

# Bounds the whole request body (including multipart file uploads) Django will
# parse before rejecting with a 400 — a backstop above the per-field
# validate_image_size checks on individual ImageFields.
DATA_UPLOAD_MAX_MEMORY_SIZE = config('DATA_UPLOAD_MAX_MEMORY_SIZE', default=10 * 1024 * 1024, cast=int)
FILE_UPLOAD_MAX_MEMORY_SIZE = config('FILE_UPLOAD_MAX_MEMORY_SIZE', default=10 * 1024 * 1024, cast=int)

# ─── Apps ────────────────────────────────────────────────────────────────────

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'drf_spectacular_sidecar',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'django_rest_passwordreset',
]

LOCAL_APPS = [
    'apps.core',
    'apps.common',
    'apps.authentication',
    'apps.users',
    'apps.campaigns',
    'apps.donations',
    'apps.payments',
    'apps.notifications',
    'apps.analytics',
    'apps.zakat',
    'apps.vision',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─── Middleware ───────────────────────────────────────────────────────────────

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# ─── Database ────────────────────────────────────────────────────────────────

import dj_database_url

DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default=f'sqlite:///{BASE_DIR}/db.sqlite3'),
        conn_max_age=600,
    )
}

# ─── Auth ────────────────────────────────────────────────────────────────────

AUTH_USER_MODEL = 'users.User'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── JWT ─────────────────────────────────────────────────────────────────────

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=config('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', default=60, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=7, cast=int)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
}

# ─── DRF ─────────────────────────────────────────────────────────────────────

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'pagination.base.StandardResultsPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': config('API_RATE_LIMIT_ANON', default='100/hour'),
        'user': config('API_RATE_LIMIT_USER', default='1000/hour'),
    },
    'EXCEPTION_HANDLER': 'utils.exceptions.custom_exception_handler',
}

# ─── API Docs ────────────────────────────────────────────────────────────────

SPECTACULAR_SETTINGS = {
    'TITLE': config('SITE_NAME', default='Dolelma') + ' API',
    'DESCRIPTION': config('SITE_DESCRIPTION', default='API Documentation'),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
}

# ─── Static / Media ──────────────────────────────────────────────────────────

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ─── Media storage (Supabase Storage, S3-compatible) ────────────────────────
# Falls back to local disk (above) when SUPABASE_STORAGE_BUCKET isn't set —
# e.g. running tests, or before a Supabase project exists. Railway's
# filesystem is ephemeral (wiped on every deploy/restart), so anything
# meant to run there needs uploads to live somewhere persistent instead.
SUPABASE_STORAGE_BUCKET = config('SUPABASE_STORAGE_BUCKET', default='')

if SUPABASE_STORAGE_BUCKET:
    DEFAULT_FILE_STORAGE = 'storages.backends.s3.S3Storage'

    # .strip() everything credential/signing-related — a stray trailing
    # space or newline from copy-pasting into an env var UI is invisible
    # but gets included in the SigV4 signature, producing a
    # SignatureDoesNotMatch that looks exactly like a wrong key.
    AWS_STORAGE_BUCKET_NAME = SUPABASE_STORAGE_BUCKET.strip()
    AWS_S3_ENDPOINT_URL = config('SUPABASE_STORAGE_ENDPOINT').strip()
    AWS_S3_REGION_NAME = config('SUPABASE_STORAGE_REGION', default='eu-west-1').strip()
    AWS_ACCESS_KEY_ID = config('SUPABASE_STORAGE_ACCESS_KEY_ID').strip()
    AWS_SECRET_ACCESS_KEY = config('SUPABASE_STORAGE_SECRET_ACCESS_KEY').strip()
    AWS_S3_ADDRESSING_STYLE = config('SUPABASE_STORAGE_ADDRESSING_STYLE', default='path').strip()
    AWS_QUERYSTRING_AUTH = config('SUPABASE_STORAGE_QUERYSTRING_AUTH', default=False, cast=bool)
    AWS_DEFAULT_ACL = None
    # Django's default (False) calls HeadObject before every save to check
    # for a name collision and auto-rename — Supabase's storage access keys
    # aren't granted that permission, so it fails with a 403 before the
    # actual upload ever happens. Not needed anyway: every upload_paths.py
    # function already includes a microsecond timestamp, so collisions
    # can't realistically occur.
    AWS_S3_FILE_OVERWRITE = True

    # Uploads go through the S3-compatible endpoint above, but Supabase serves
    # public reads from a different path on the main project domain — set
    # this as the custom domain so file .url() calls resolve to that instead
    # of the S3 endpoint (which isn't the public-read URL).
    _supabase_url = config('SUPABASE_URL', default='').strip().replace('https://', '').replace('http://', '')
    if _supabase_url:
        AWS_S3_CUSTOM_DOMAIN = f'{_supabase_url}/storage/v1/object/public/{AWS_STORAGE_BUCKET_NAME}'

# ─── Email ───────────────────────────────────────────────────────────────────

EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@yourapp.com')

# Railway (and most PaaS hosts) block outbound SMTP entirely, so production
# sends over Resend's HTTPS API instead — see settings/production.py.
ANYMAIL = {
    'RESEND_API_KEY': config('RESEND_API_KEY', default=''),
}

# ─── Celery ──────────────────────────────────────────────────────────────────
# Emails (and any other background work) run through Celery so a slow SMTP
# server never blocks the request that triggered the send.

REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default=REDIS_URL)
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=False, cast=bool)

# ─── Allauth ─────────────────────────────────────────────────────────────────

SITE_ID = 1
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'

# ─── CORS ────────────────────────────────────────────────────────────────────

CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ['Content-Type', 'X-CSRFToken']
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type',
    'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
]

# ─── Internationalization ────────────────────────────────────────────────────

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ─── Misc ────────────────────────────────────────────────────────────────────

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SITE_NAME = config('SITE_NAME', default='Dolelma')
SITE_DESCRIPTION = config('SITE_DESCRIPTION', default='Crowdfunding for The Gambia')
CONTACT_EMAIL = config('CONTACT_EMAIL', default='support@yourapp.com')
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:5173')
# Used to build the ModemPay webhook callback URL. Falls back to deriving it
# from FRONTEND_URL (see modempay_service._build_webhook_url) if left blank.
BACKEND_URL = config('BACKEND_URL', default='')

# ─── ModemPay ────────────────────────────────────────────────────────────────
# The real ModemPay Python SDK (modempay) reads only the secret key — it talks
# to https://api.modempay.com directly, so there's no API URL to configure.

MODEMPAY_SECRET_KEY = config('MODEMPAY_SECRET_API_KEY', default='')
MODEMPAY_PUBLIC_KEY = config('MODEMPAY_PUBLIC_API_KEY', default='')
MODEMPAY_WEBHOOK_SECRET = config('MODEMPAY_WEBHOOK_SECRET', default='')
MODEMPAY_MERCHANT_ID = config('MODEMPAY_MERCHANT_ID', default='')
DEMO_MODE = config('DEMO_MODE', default=True, cast=bool)

# ─── Stripe ──────────────────────────────────────────────────────────────────
# Donation-only — see services/gateways/stripe_gateway.py. Credentials only;
# whether the gateway is actually offered, and what currency/exchange rate a
# GMD donation gets converted at, are admin-editable DB fields on
# PlatformSettings (stripe_enabled, stripe_settlement_currency,
# gmd_to_settlement_rate) — not env vars, so an admin can change them at
# runtime without a deploy. See apps/payments/models.py::PlatformSettings.
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default='')
STRIPE_PUBLISHABLE_KEY = config('STRIPE_PUBLISHABLE_KEY', default='')
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET', default='')

# ─── Payment gateways ────────────────────────────────────────────────────────
# services/gateways/registry.py looks up a gateway's config here by code for
# credentials — whether a gateway is *enabled* is a DB-backed PlatformSettings
# field (registry._is_enabled), not read from this dict at all. Each
# gateway's own credentials stay in its own *_SECRET_KEY-style vars above,
# read directly by its service module as before; this dict is what the
# registry needs to resolve and construct a gateway instance.
PAYMENT_GATEWAYS = {
    'modempay': {
        'demo_mode': DEMO_MODE,
    },
    'stripe': {
        'secret_key': STRIPE_SECRET_KEY,
        'publishable_key': STRIPE_PUBLISHABLE_KEY,
        'webhook_secret': STRIPE_WEBHOOK_SECRET,
    },
}

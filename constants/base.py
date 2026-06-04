from django.conf import settings

SITE_NAME = getattr(settings, 'SITE_NAME', 'My App')
SITE_DESCRIPTION = getattr(settings, 'SITE_DESCRIPTION', 'A great application')
CONTACT_EMAIL = getattr(settings, 'CONTACT_EMAIL', 'support@yourapp.com')
FRONTEND_URL = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')

PASSWORD_RESET_TIMEOUT_SECONDS = 3600  # 1 hour

MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_AVATAR_TYPES = ['image/jpeg', 'image/png', 'image/webp']

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

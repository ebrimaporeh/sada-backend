from django.db import models
from apps.core.models import BaseModel
from apps.core.validators import validate_image_size
from utils.upload_paths import site_logo_path, site_logo_with_background_path
from .legal_defaults import DEFAULT_HELP_CONTENT, DEFAULT_TRUST_SAFETY_CONTENT, DEFAULT_PRIVACY_CONTENT, DEFAULT_TERMS_CONTENT


class SiteSettings(BaseModel):
    """Singleton row of admin-editable site branding.

    Separate from apps.payments.PlatformSettings, which is fee/payout
    config — this is presentation-only and safe to expose publicly
    (unauthenticated), since the logo/name/description show on the
    landing and auth pages before anyone signs in.
    """
    site_name = models.CharField(max_length=100, default='Dolelma')
    site_description = models.CharField(max_length=255, blank=True, default='Crowdfunding for The Gambia')
    logo = models.ImageField(
        upload_to=site_logo_path, null=True, blank=True, validators=[validate_image_size],
        help_text='Transparent logo, used on light and dark surfaces (nav, footer).',
    )
    logo_with_background = models.ImageField(
        upload_to=site_logo_with_background_path, null=True, blank=True, validators=[validate_image_size],
        help_text='Logo on its own solid background, used where a transparent logo needs backing (e.g. social sharing).',
    )

    class Meta:
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return self.site_name

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj


class LegalContent(BaseModel):
    """Singleton row of admin-editable markdown for the public Help,
    Trust & Safety, Privacy, and Terms pages. Seeded from each page's
    previously-hardcoded copy (see legal_defaults.py) so switching them
    over to admin-editable content doesn't change what's shown until an
    admin actually edits something."""
    help_content = models.TextField(default=DEFAULT_HELP_CONTENT)
    trust_safety_content = models.TextField(default=DEFAULT_TRUST_SAFETY_CONTENT)
    privacy_content = models.TextField(default=DEFAULT_PRIVACY_CONTENT)
    terms_content = models.TextField(default=DEFAULT_TERMS_CONTENT)

    class Meta:
        verbose_name = 'Legal Content'
        verbose_name_plural = 'Legal Content'

    def __str__(self):
        return 'Legal Content'

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj

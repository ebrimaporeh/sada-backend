from django.conf import settings as django_settings
from rest_framework import serializers
from services.logo_processing import process_logo_image
from .models import SiteSettings, LegalContent


class SiteSettingsSerializer(serializers.ModelSerializer):
    # Not a DB field — CONTACT_EMAIL is server-side env config (see
    # settings/base.py) with nowhere else public to read it from. Exposed
    # here (read-only) so the frontend can offer it as a {{contact_email}}
    # variable in the Legal/Help markdown editor without a dedicated
    # endpoint just for one value.
    contact_email = serializers.SerializerMethodField()

    class Meta:
        model = SiteSettings
        fields = ['site_name', 'site_description', 'logo', 'logo_with_background', 'contact_email']

    def get_contact_email(self, obj):
        return getattr(django_settings, 'CONTACT_EMAIL', '')

    def validate_site_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('Site name cannot be blank.')
        return value.strip()

    def validate_logo(self, value):
        return process_logo_image(value, transparent_padding=True)

    def validate_logo_with_background(self, value):
        return process_logo_image(value, transparent_padding=False)


class LegalContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalContent
        fields = ['help_content', 'trust_safety_content', 'privacy_content', 'terms_content']

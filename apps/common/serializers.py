from django.conf import settings as django_settings
from rest_framework import serializers
from services.logo_processing import process_logo_image
from .models import SiteSettings, LegalContent


class SiteSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        fields = ['site_name', 'site_description', 'logo', 'logo_with_background', 'contact_email']

    def to_representation(self, instance):
        # contact_email is admin-editable (Settings -> Branding), but falls
        # back to the CONTACT_EMAIL env var when left blank -- an empty
        # value here should never make support unreachable.
        data = super().to_representation(instance)
        if not data.get('contact_email'):
            data['contact_email'] = getattr(django_settings, 'CONTACT_EMAIL', '')
        return data

    def validate_contact_email(self, value):
        return value.strip()

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

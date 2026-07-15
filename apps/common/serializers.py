from rest_framework import serializers
from services.logo_processing import process_logo_image
from .models import SiteSettings


class SiteSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        fields = ['site_name', 'site_description', 'logo', 'logo_with_background']

    def validate_site_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('Site name cannot be blank.')
        return value.strip()

    def validate_logo(self, value):
        return process_logo_image(value, transparent_padding=True)

    def validate_logo_with_background(self, value):
        return process_logo_image(value, transparent_padding=False)

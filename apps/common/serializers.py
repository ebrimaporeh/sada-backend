from rest_framework import serializers
from .models import SiteSettings


class SiteSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        fields = ['site_name', 'site_description', 'logo', 'logo_with_background']

    def validate_site_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('Site name cannot be blank.')
        return value.strip()

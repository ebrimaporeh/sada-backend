from django.test import override_settings
from rest_framework.test import APITestCase

from apps.common.models import SiteSettings
from apps.common.serializers import SiteSettingsSerializer


class SiteSettingsContactEmailTest(APITestCase):
    """contact_email is admin-editable (Settings -> Branding) but falls back
    to the CONTACT_EMAIL env var when left blank, so support is never
    unreachable just because the field hasn't been set yet."""

    def test_blank_contact_email_falls_back_to_the_env_var(self):
        with override_settings(CONTACT_EMAIL='env-support@example.com'):
            data = SiteSettingsSerializer(SiteSettings.get_solo()).data
        self.assertEqual(data['contact_email'], 'env-support@example.com')

    def test_admin_can_set_a_custom_support_email(self):
        serializer = SiteSettingsSerializer(
            SiteSettings.get_solo(), data={'contact_email': ' custom-support@example.com '}, partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.assertEqual(SiteSettings.get_solo().contact_email, 'custom-support@example.com')

    def test_set_contact_email_overrides_the_env_var_fallback(self):
        settings_obj = SiteSettings.get_solo()
        settings_obj.contact_email = 'custom-support@example.com'
        settings_obj.save(update_fields=['contact_email'])

        with override_settings(CONTACT_EMAIL='env-support@example.com'):
            data = SiteSettingsSerializer(settings_obj).data
        self.assertEqual(data['contact_email'], 'custom-support@example.com')

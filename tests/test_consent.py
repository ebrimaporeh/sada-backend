from unittest.mock import patch
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.common.models import LegalContent
from apps.users.models import User, TermsAcceptance
import services.consent_service as consent_service
from services.google_oauth_service import get_or_create_google_user


class RecordTermsAcceptanceTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='consent@example.com', password='pass')

    def test_creates_a_row_with_a_version_hash_and_ip(self):
        acceptance = consent_service.record_terms_acceptance(self.user, ip_address='41.66.12.1')
        self.assertEqual(acceptance.user, self.user)
        self.assertTrue(acceptance.terms_version)
        self.assertEqual(acceptance.ip_address, '41.66.12.1')

    def test_blank_ip_is_stored_as_null_not_an_empty_string(self):
        acceptance = consent_service.record_terms_acceptance(self.user, ip_address='')
        self.assertIsNone(acceptance.ip_address)

    def test_version_hash_changes_when_terms_text_changes(self):
        first = consent_service.record_terms_acceptance(self.user)

        legal = LegalContent.get_solo()
        legal.terms_content = legal.terms_content + '\n\nA new clause.'
        legal.save()

        second = consent_service.record_terms_acceptance(self.user)
        self.assertNotEqual(first.terms_version, second.terms_version)

    def test_version_hash_is_unaffected_by_edits_to_other_legal_pages(self):
        # terms_content, privacy_content, help_content, and
        # trust_safety_content all live on the same LegalContent row --
        # editing an unrelated page must not look like a Terms change.
        first = consent_service.record_terms_acceptance(self.user)

        legal = LegalContent.get_solo()
        legal.privacy_content = legal.privacy_content + '\n\nSomething unrelated.'
        legal.save()

        second = consent_service.record_terms_acceptance(self.user)
        self.assertEqual(first.terms_version, second.terms_version)


class GetClientIpTest(APITestCase):
    def test_prefers_x_forwarded_for(self):
        request = type('Req', (), {'META': {
            'HTTP_X_FORWARDED_FOR': '41.66.12.1, 10.0.0.1',
            'REMOTE_ADDR': '10.0.0.1',
        }})()
        self.assertEqual(consent_service.get_client_ip(request), '41.66.12.1')

    def test_falls_back_to_remote_addr(self):
        request = type('Req', (), {'META': {'REMOTE_ADDR': '10.0.0.1'}})()
        self.assertEqual(consent_service.get_client_ip(request), '10.0.0.1')


class RegisterViewConsentTest(APITestCase):
    def test_records_ip_from_the_request(self):
        url = reverse('auth-register')
        self.client.post(url, {
            'email': 'ipcheck@example.com', 'password': 'StrongPass@1',
            'password_confirm': 'StrongPass@1', 'terms_accepted': True,
        }, REMOTE_ADDR='197.211.0.1')
        user = User.objects.get(email='ipcheck@example.com')
        acceptance = TermsAcceptance.objects.get(user=user)
        self.assertEqual(acceptance.ip_address, '197.211.0.1')


class GoogleSignupConsentTest(APITestCase):
    """get_or_create_google_user's `created` flag is what GoogleOAuthView
    uses to decide whether to record consent -- only a brand-new account
    counts as a fresh signup, not a returning user logging back in."""

    def test_new_google_user_is_flagged_as_created(self):
        user, created = get_or_create_google_user({
            'email': 'newgoogle@example.com', 'name': 'New User', 'google_sub': 'sub-1',
        })
        self.assertTrue(created)
        self.assertEqual(user.email, 'newgoogle@example.com')

    def test_returning_google_user_is_not_flagged_as_created(self):
        get_or_create_google_user({'email': 'returning@example.com', 'name': 'R U', 'google_sub': 'sub-2'})
        user, created = get_or_create_google_user({'email': 'returning@example.com', 'name': 'R U', 'google_sub': 'sub-2'})
        self.assertFalse(created)

    @patch('apps.authentication.views.verify_google_token')
    def test_view_records_consent_only_for_a_new_signup(self, mock_verify):
        url = reverse('auth-google')
        mock_verify.return_value = {'email': 'viagoogle@example.com', 'name': 'Via Google', 'google_sub': 'sub-3'}

        first_response = self.client.post(url, {'id_token': 'fake-token'})
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        user = User.objects.get(email='viagoogle@example.com')
        self.assertEqual(TermsAcceptance.objects.filter(user=user).count(), 1)

        second_response = self.client.post(url, {'id_token': 'fake-token'})
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        # Logging back in again must not create a second acceptance record.
        self.assertEqual(TermsAcceptance.objects.filter(user=user).count(), 1)

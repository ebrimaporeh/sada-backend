from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User
import services.google_oauth_service as google_oauth_service


def _payload(email='victim@example.com', email_verified=True, sub='google-sub-1', name='Victim'):
    return {'email': email, 'email_verified': email_verified, 'sub': sub, 'name': name}


class VerifyGoogleTokenEmailVerifiedTest(APITestCase):
    """Google's own email_verified claim is the entire trust boundary for
    logging into an *existing* account via get_or_create_google_user() --
    a token presenting someone else's email must be rejected unless Google
    itself vouches that the presenter actually controls it. See
    services/google_oauth_service.py for the full rationale."""

    @patch('services.google_oauth_service.config')
    @patch('services.google_oauth_service.id_token.verify_oauth2_token')
    def test_rejects_a_token_whose_email_google_has_not_verified(self, mock_verify, mock_config):
        mock_config.return_value = 'fake-client-id'
        mock_verify.return_value = _payload(email_verified=False)

        with self.assertRaises(ValidationError):
            google_oauth_service.verify_google_token('fake-token')

    @patch('services.google_oauth_service.config')
    @patch('services.google_oauth_service.id_token.verify_oauth2_token')
    def test_rejects_a_token_missing_the_email_verified_claim_entirely(self, mock_verify, mock_config):
        mock_config.return_value = 'fake-client-id'
        mock_verify.return_value = {'email': 'victim@example.com', 'sub': 'sub-1', 'name': 'Victim'}

        with self.assertRaises(ValidationError):
            google_oauth_service.verify_google_token('fake-token')

    @patch('services.google_oauth_service.config')
    @patch('services.google_oauth_service.id_token.verify_oauth2_token')
    def test_accepts_a_token_with_a_verified_email(self, mock_verify, mock_config):
        mock_config.return_value = 'fake-client-id'
        mock_verify.return_value = _payload(email_verified=True)

        data = google_oauth_service.verify_google_token('fake-token')
        self.assertEqual(data['email'], 'victim@example.com')


class GoogleOAuthViewAccountTakeoverTest(APITestCase):
    """End-to-end: a Google token for an unverified email must not be able
    to log into a pre-existing account that was never linked to Google."""

    def setUp(self):
        self.victim = User.objects.create_user(email='victim@example.com', password='RealPass@123')

    @patch('services.google_oauth_service.config')
    @patch('services.google_oauth_service.id_token.verify_oauth2_token')
    def test_unverified_google_email_cannot_log_into_an_existing_account(self, mock_verify, mock_config):
        mock_config.return_value = 'fake-client-id'
        mock_verify.return_value = _payload(email='victim@example.com', email_verified=False, sub='attacker-sub')

        url = reverse('auth-google')
        response = self.client.post(url, {'id_token': 'fake-token'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.victim.refresh_from_db()
        self.assertIsNone(self.victim.google_sub)

    @patch('services.google_oauth_service.config')
    @patch('services.google_oauth_service.id_token.verify_oauth2_token')
    def test_verified_google_email_can_log_into_the_matching_existing_account(self, mock_verify, mock_config):
        mock_config.return_value = 'fake-client-id'
        mock_verify.return_value = _payload(email='victim@example.com', email_verified=True, sub='real-sub')

        url = reverse('auth-google')
        response = self.client.post(url, {'id_token': 'fake-token'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['user']['email'], 'victim@example.com')

from django.core import mail
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from apps.users.models import User
from services.auth_service import EMAIL_VERIFICATION_SALT


class RegisterViewTest(APITestCase):
    def setUp(self):
        self.url = reverse('auth-register')
        self.valid_data = {
            'email': 'test@example.com',
            'password': 'StrongPass@1',
            'password_confirm': 'StrongPass@1',
            'first_name': 'Test',
            'last_name': 'User',
            'terms_accepted': True,
        }

    def test_register_success(self):
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertNotIn('tokens', response.data['data'])
        self.assertTrue(User.objects.filter(email='test@example.com').exists())

    def test_register_does_not_auto_verify_or_allow_login(self):
        self.client.post(self.url, self.valid_data)
        user = User.objects.get(email='test@example.com')
        self.assertFalse(user.email_verified)
        response = self.client.post(reverse('auth-login'), {
            'email': 'test@example.com',
            'password': 'StrongPass@1',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_records_terms_acceptance(self):
        from apps.users.models import TermsAcceptance
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email='test@example.com')
        self.assertTrue(TermsAcceptance.objects.filter(user=user).exists())

    def test_register_without_accepting_terms_fails(self):
        data = {**self.valid_data, 'terms_accepted': False}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='test@example.com').exists())

    def test_register_duplicate_email(self):
        User.objects.create_user(email='test@example.com', password='pass')
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_register_password_mismatch(self):
        data = {**self.valid_data, 'password_confirm': 'WrongPass@1'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginViewTest(APITestCase):
    def setUp(self):
        self.url = reverse('auth-login')
        self.user = User.objects.create_user(
            email='login@example.com',
            password='StrongPass@1',
            email_verified=True,
        )

    def test_login_success(self):
        response = self.client.post(self.url, {
            'email': 'login@example.com',
            'password': 'StrongPass@1',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('access', response.data['data']['tokens'])

    def test_login_wrong_password(self):
        response = self.client.post(self.url, {
            'email': 'login@example.com',
            'password': 'WrongPass@1',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_login_blocked_when_email_unverified(self):
        User.objects.create_user(
            email='unverified@example.com',
            password='StrongPass@1',
            email_verified=False,
        )
        response = self.client.post(self.url, {
            'email': 'unverified@example.com',
            'password': 'StrongPass@1',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])


class LogoutViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='logout@example.com', password='StrongPass@1', email_verified=True)
        self.refresh = RefreshToken.for_user(self.user)
        self.client.force_authenticate(user=self.user)

    def test_logout_blacklists_the_refresh_token(self):
        response = self.client.post(reverse('auth-logout'), {'refresh': str(self.refresh)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        outstanding = OutstandingToken.objects.get(jti=self.refresh['jti'])
        self.assertTrue(BlacklistedToken.objects.filter(token=outstanding).exists())

    def test_logout_without_a_refresh_token_is_a_400(self):
        response = self.client.post(reverse('auth-logout'), {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_logout_with_an_already_blacklisted_token_does_not_error(self):
        # Blacklisting is idempotent -- a double-click or retry on the
        # client shouldn't turn into a 500.
        self.client.post(reverse('auth-logout'), {'refresh': str(self.refresh)})
        response = self.client.post(reverse('auth-logout'), {'refresh': str(self.refresh)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logout_requires_auth(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(reverse('auth-logout'), {'refresh': str(self.refresh)})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class VerifyEmailViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='verifyme@example.com', password='StrongPass@1', email_verified=False)
        self.url = reverse('auth-verify-email')

    def _token(self):
        from django.core import signing
        return signing.dumps(str(self.user.id), salt=EMAIL_VERIFICATION_SALT)

    def test_valid_token_verifies_the_user_and_then_allows_login(self):
        response = self.client.post(self.url, {'token': self._token()})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

        login = self.client.post(reverse('auth-login'), {'email': 'verifyme@example.com', 'password': 'StrongPass@1'})
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_missing_token_is_a_400(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_garbage_token_is_rejected(self):
        response = self.client.post(self.url, {'token': 'not-a-real-token'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_token_for_a_deleted_user_is_rejected(self):
        token = self._token()
        self.user.delete()
        response = self.client.post(self.url, {'token': token})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_verifying_twice_is_harmless(self):
        token = self._token()
        self.client.post(self.url, {'token': token})
        response = self.client.post(self.url, {'token': token})
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ResendVerificationEmailViewTest(APITestCase):
    def setUp(self):
        self.url = reverse('auth-resend-verification')

    def test_resend_queues_a_new_verification_email(self):
        User.objects.create_user(email='needsverify@example.com', password='StrongPass@1', email_verified=False)
        mail.outbox = []
        response = self.client.post(self.url, {'email': 'needsverify@example.com'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('needsverify@example.com', mail.outbox[0].to)

    def test_already_verified_user_gets_no_email(self):
        User.objects.create_user(email='alreadyverified@example.com', password='StrongPass@1', email_verified=True)
        mail.outbox = []
        response = self.client.post(self.url, {'email': 'alreadyverified@example.com'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_unknown_email_does_not_leak_whether_it_is_registered(self):
        mail.outbox = []
        response = self.client.post(self.url, {'email': 'nobody@example.com'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(len(mail.outbox), 0)

    def test_missing_email_is_a_400(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class RequestPasswordResetViewTest(APITestCase):
    def setUp(self):
        self.url = reverse('auth-password-reset-request')
        self.user = User.objects.create_user(email='resetme@example.com', password='StrongPass@1', email_verified=True)

    def test_valid_email_sends_a_reset_email_to_that_address(self):
        mail.outbox = []
        response = self.client.post(self.url, {'email': 'resetme@example.com'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertIn('resetme@example.com', sent.to)
        self.assertIn('reset', sent.subject.lower())

    def test_unknown_email_returns_an_error_without_sending_anything(self):
        mail.outbox = []
        response = self.client.post(self.url, {'email': 'nobody@example.com'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(mail.outbox), 0)

    def test_deactivated_account_is_not_eligible(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        mail.outbox = []
        response = self.client.post(self.url, {'email': 'resetme@example.com'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(mail.outbox), 0)

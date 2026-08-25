from unittest.mock import patch

from django.core import signing
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User, Organization, OrganizationChangeRequest
import services.organization_change_service as organization_change_service


def make_org_user(**kwargs):
    org_kwargs = kwargs.pop('org', {})
    user = User.objects.create_user(
        email=kwargs.pop('email', f'org{User.objects.count()}@example.com'),
        password='pass',
        account_type=User.AccountType.ORGANIZATION,
        **kwargs,
    )
    org_defaults = {
        'organization_name': 'Test Org', 'organization_type': Organization.OrgType.COMMUNITY,
        'contact_person_name': 'Contact Person', 'phone_2': '7000001',
    }
    org_defaults.update(org_kwargs)
    Organization.objects.create(user=user, **org_defaults)
    return user


class SubmitChangeRequestNotificationTest(APITestCase):
    """A recovery-email change gets an email-confirmation link sent to the
    proposed address; a phone change still notifies admins for review --
    these must never cross over."""

    @patch('services.organization_change_service.generate_recovery_email_confirm_url')
    @patch('emails.tasks.send_recovery_email_confirmation_email_task.delay')
    @patch('emails.tasks.send_new_organization_change_request_notification_task.delay')
    def test_recovery_email_change_sends_confirmation_not_admin_notification(
        self, mock_admin_notify, mock_confirm_email, mock_gen_url,
    ):
        mock_gen_url.return_value = 'https://dolelma.org/confirm-recovery-email?token=abc'
        user = make_org_user()

        request = organization_change_service.submit_change_request(user, 'recovery_email_1', 'new@example.com')

        mock_confirm_email.assert_called_once_with(str(request.id), 'https://dolelma.org/confirm-recovery-email?token=abc')
        mock_admin_notify.assert_not_called()

    @patch('services.organization_change_service.generate_recovery_email_confirm_url')
    @patch('emails.tasks.send_recovery_email_confirmation_email_task.delay')
    @patch('emails.tasks.send_new_organization_change_request_notification_task.delay')
    def test_phone_change_still_notifies_admins_not_a_confirmation_email(
        self, mock_admin_notify, mock_confirm_email, mock_gen_url,
    ):
        user = make_org_user()

        request = organization_change_service.submit_change_request(user, 'phone_2', '7009999')

        mock_admin_notify.assert_called_once_with(str(request.id))
        mock_confirm_email.assert_not_called()


class ConfirmRecoveryEmailChangeTest(APITestCase):
    def setUp(self):
        self.user = make_org_user()
        self.request = OrganizationChangeRequest.objects.create(
            user=self.user, field_name='recovery_email_1',
            current_value='', proposed_value='new-recovery@example.com',
        )

    def _token(self, request_id=None):
        return signing.dumps(
            str(request_id or self.request.id), salt=organization_change_service.RECOVERY_EMAIL_CONFIRM_SALT,
        )

    @patch('emails.tasks.send_organization_change_request_reviewed_email_task.delay')
    def test_confirming_applies_the_change_with_no_admin_reviewer(self, mock_notify):
        result = organization_change_service.confirm_recovery_email_change(self._token())

        self.assertEqual(result.status, OrganizationChangeRequest.Status.APPROVED)
        self.assertIsNone(result.reviewed_by)
        self.assertIsNotNone(result.reviewed_at)
        self.user.organization.refresh_from_db()
        self.assertEqual(self.user.organization.recovery_email_1, 'new-recovery@example.com')
        mock_notify.assert_called_once_with(str(self.request.id))

    def test_invalid_token_is_rejected(self):
        with self.assertRaises(ValidationError):
            organization_change_service.confirm_recovery_email_change('not-a-real-token')

    def test_tampered_token_is_rejected(self):
        token = self._token()
        with self.assertRaises(ValidationError):
            organization_change_service.confirm_recovery_email_change(token + 'x')

    def test_expired_token_is_rejected(self):
        with patch('services.organization_change_service.RECOVERY_EMAIL_CONFIRM_MAX_AGE', -1):
            with self.assertRaises(ValidationError):
                organization_change_service.confirm_recovery_email_change(self._token())

    def test_already_reviewed_request_is_rejected(self):
        self.request.status = OrganizationChangeRequest.Status.APPROVED
        self.request.save(update_fields=['status'])
        with self.assertRaises(ValidationError):
            organization_change_service.confirm_recovery_email_change(self._token())

    def test_a_phone_change_requests_token_is_rejected_by_this_endpoint(self):
        # Defense-in-depth: even if somehow a phone request's id were signed
        # with this salt, the field-type guard must still stop it.
        phone_request = OrganizationChangeRequest.objects.create(
            user=self.user, field_name='phone_2', current_value='', proposed_value='7001234',
        )
        token = self._token(phone_request.id)
        with self.assertRaises(ValidationError):
            organization_change_service.confirm_recovery_email_change(token)
        phone_request.refresh_from_db()
        self.assertEqual(phone_request.status, OrganizationChangeRequest.Status.PENDING)

    def test_api_endpoint_confirms_with_no_auth_required(self):
        response = self.client.post(
            reverse('organization-change-request-confirm-recovery-email'), {'token': self._token()},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.organization.refresh_from_db()
        self.assertEqual(self.user.organization.recovery_email_1, 'new-recovery@example.com')

    def test_api_endpoint_requires_a_token(self):
        response = self.client.post(reverse('organization-change-request-confirm-recovery-email'), {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AdminCannotApproveRecoveryEmailChangesTest(APITestCase):
    """Removing admin approval for these two fields means the admin action
    endpoint must actually refuse to approve them, not just go unused --
    otherwise a compromised/careless admin could still bypass the mailbox
    proof this whole design exists to require."""

    def setUp(self):
        self.admin = User.objects.create_user(email='admin-orgchange@example.com', password='pass', is_staff=True, role=User.Role.ADMIN)
        self.user = make_org_user()
        self.client.force_authenticate(user=self.admin)

    def test_admin_approve_is_rejected_for_a_recovery_email_request(self):
        request = OrganizationChangeRequest.objects.create(
            user=self.user, field_name='recovery_email_2', current_value='', proposed_value='admin-tried@example.com',
        )
        with self.assertRaises(ValidationError):
            organization_change_service.approve_change_request(request.id, self.admin)
        request.refresh_from_db()
        self.assertEqual(request.status, OrganizationChangeRequest.Status.PENDING)
        self.user.organization.refresh_from_db()
        self.assertNotEqual(self.user.organization.recovery_email_2, 'admin-tried@example.com')

    def test_admin_can_still_reject_a_recovery_email_request(self):
        request = OrganizationChangeRequest.objects.create(
            user=self.user, field_name='recovery_email_1', current_value='', proposed_value='suspicious@example.com',
        )
        result = organization_change_service.reject_change_request(request.id, self.admin, reason='Looks suspicious')
        self.assertEqual(result.status, OrganizationChangeRequest.Status.REJECTED)

    def test_admin_can_still_approve_a_phone_request(self):
        request = OrganizationChangeRequest.objects.create(
            user=self.user, field_name='phone_2', current_value='', proposed_value='7005555',
        )
        result = organization_change_service.approve_change_request(request.id, self.admin)
        self.assertEqual(result.status, OrganizationChangeRequest.Status.APPROVED)
        self.user.organization.refresh_from_db()
        self.assertEqual(self.user.organization.phone_2, '7005555')

    def test_api_endpoint_surfaces_the_same_rejection(self):
        request = OrganizationChangeRequest.objects.create(
            user=self.user, field_name='recovery_email_1', current_value='', proposed_value='admin-tried2@example.com',
        )
        response = self.client.post(
            reverse('admin-organization-change-request-action', args=[request.id, 'approve']),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

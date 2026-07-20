from unittest.mock import patch
from django.core import mail
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from apps.users.models import User, IdentityVerification, Organization, OrganizationVerification
import services.verification_service as verification_service


def make_user(**kwargs):
    defaults = {'email': f'user{User.objects.count()}@example.com', 'password': 'pass'}
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def make_org_user(**kwargs):
    org_kwargs = kwargs.pop('org', {})
    user = make_user(account_type=User.AccountType.ORGANIZATION, **kwargs)
    org_defaults = {
        'user': user, 'organization_name': 'Test Org',
        'organization_type': Organization.OrgType.COMMUNITY,
        'contact_person_name': 'Contact Person', 'phone_2': '+2207000001',
    }
    org_defaults.update(org_kwargs)
    Organization.objects.create(**org_defaults)
    return user


# process_image does real image compression -- irrelevant to the
# verification state machine this file tests, and slow/fragile to feed real
# bytes through, so every test here patches it to pass the input straight
# through.
PROCESS_IMAGE_PATCH = patch('services.image_compression.process_image', side_effect=lambda f, profile: f)


class SubmitVerificationTest(APITestCase):
    def setUp(self):
        self.user = make_user()

    @PROCESS_IMAGE_PATCH
    def test_creates_a_pending_request(self, _mock):
        verification = verification_service.submit_verification(self.user, 'national_id', '123456', 'front.jpg')
        self.assertEqual(verification.status, IdentityVerification.Status.PENDING)
        self.assertEqual(verification.user, self.user)

    @PROCESS_IMAGE_PATCH
    def test_rejects_resubmission_if_already_verified(self, _mock):
        self.user.is_verified = True
        self.user.save(update_fields=['is_verified'])
        with self.assertRaises(ValidationError):
            verification_service.submit_verification(self.user, 'national_id', '123456', 'front.jpg')

    @PROCESS_IMAGE_PATCH
    def test_rejects_a_second_submission_while_one_is_pending(self, _mock):
        verification_service.submit_verification(self.user, 'national_id', '123456', 'front.jpg')
        with self.assertRaises(ValidationError):
            verification_service.submit_verification(self.user, 'passport', '789', 'front2.jpg')
        self.assertEqual(IdentityVerification.objects.filter(user=self.user).count(), 1)

    @PROCESS_IMAGE_PATCH
    def test_can_resubmit_after_a_rejection(self, _mock):
        first = verification_service.submit_verification(self.user, 'national_id', '123456', 'front.jpg')
        first.status = IdentityVerification.Status.REJECTED
        first.save(update_fields=['status'])

        second = verification_service.submit_verification(self.user, 'passport', '789', 'front2.jpg')
        self.assertEqual(IdentityVerification.objects.filter(user=self.user).count(), 2)
        self.assertEqual(second.status, IdentityVerification.Status.PENDING)


class GetLatestVerificationTest(APITestCase):
    def test_returns_the_most_recent_request(self):
        user = make_user()
        older = IdentityVerification.objects.create(user=user, id_type='national_id', id_number='1', id_photo_front='x.jpg')
        newer = IdentityVerification.objects.create(user=user, id_type='passport', id_number='2', id_photo_front='y.jpg')
        self.assertEqual(verification_service.get_latest_verification(user), newer)
        self.assertNotEqual(verification_service.get_latest_verification(user), older)

    def test_returns_none_when_no_requests_exist(self):
        user = make_user()
        self.assertIsNone(verification_service.get_latest_verification(user))


class ApproveRejectVerificationTest(APITestCase):
    def setUp(self):
        self.applicant = make_user(email='applicant@example.com')
        self.admin = make_user(email='admin@example.com', role='admin')
        self.verification = IdentityVerification.objects.create(
            user=self.applicant, id_type='national_id', id_number='123', id_photo_front='x.jpg',
        )

    def test_approve_verifies_the_user(self):
        mail.outbox = []
        result = verification_service.approve_verification(self.verification.id, self.admin)
        self.assertEqual(result.status, IdentityVerification.Status.APPROVED)
        self.assertEqual(result.reviewed_by, self.admin)
        self.assertIsNotNone(result.reviewed_at)

        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_verified)
        self.assertEqual(len(mail.outbox), 1)

    def test_reject_does_not_verify_the_user(self):
        result = verification_service.reject_verification(self.verification.id, self.admin, reason='Blurry photo')
        self.assertEqual(result.status, IdentityVerification.Status.REJECTED)
        self.assertEqual(result.rejection_reason, 'Blurry photo')

        self.applicant.refresh_from_db()
        self.assertFalse(self.applicant.is_verified)

    def test_cannot_review_an_already_reviewed_request(self):
        verification_service.approve_verification(self.verification.id, self.admin)
        with self.assertRaises(ValidationError):
            verification_service.reject_verification(self.verification.id, self.admin)

    def test_unknown_verification_id_raises(self):
        with self.assertRaises(ValidationError):
            verification_service.approve_verification('00000000-0000-0000-0000-000000000000', self.admin)


class RevokeVerificationTest(APITestCase):
    def setUp(self):
        self.admin = make_user(email='revoker@example.com', role='admin')

    def test_revokes_an_approved_individual_verification(self):
        user = make_user(email='verified-user@example.com', is_verified=True)
        approved = IdentityVerification.objects.create(
            user=user, id_type='national_id', id_number='1', id_photo_front='x.jpg',
            status=IdentityVerification.Status.APPROVED,
        )
        verification_service.revoke_verification(user, self.admin)
        approved.refresh_from_db()
        self.assertEqual(approved.status, IdentityVerification.Status.REJECTED)
        self.assertEqual(approved.reviewed_by, self.admin)
        self.assertTrue(approved.rejection_reason)

    def test_does_not_touch_a_pending_or_already_rejected_request(self):
        user = make_user(email='mixed-user@example.com')
        pending = IdentityVerification.objects.create(
            user=user, id_type='national_id', id_number='1', id_photo_front='x.jpg',
            status=IdentityVerification.Status.PENDING,
        )
        rejected = IdentityVerification.objects.create(
            user=user, id_type='passport', id_number='2', id_photo_front='y.jpg',
            status=IdentityVerification.Status.REJECTED,
        )
        verification_service.revoke_verification(user, self.admin)
        pending.refresh_from_db()
        rejected.refresh_from_db()
        self.assertEqual(pending.status, IdentityVerification.Status.PENDING)
        self.assertIsNone(pending.reviewed_by)
        self.assertEqual(rejected.status, IdentityVerification.Status.REJECTED)

    def test_revokes_an_approved_organization_verification(self):
        user = make_org_user(email='org-owner@example.com', is_verified=True)
        approved = OrganizationVerification.objects.create(
            user=user, contact_id_type='national_id', contact_id_number='1',
            contact_id_photo_front='x.jpg', registration_document='reg.jpg', organization_photo='org.jpg',
            status=OrganizationVerification.Status.APPROVED,
        )
        verification_service.revoke_verification(user, self.admin)
        approved.refresh_from_db()
        self.assertEqual(approved.status, OrganizationVerification.Status.REJECTED)


class SubmitOrganizationVerificationTest(APITestCase):
    @PROCESS_IMAGE_PATCH
    def test_creates_a_pending_request_for_an_org_account(self, _mock):
        user = make_org_user()
        verification = verification_service.submit_organization_verification(
            user, 'national_id', '123', 'front.jpg', 'reg.jpg', 'org.jpg',
        )
        self.assertEqual(verification.status, OrganizationVerification.Status.PENDING)

    @PROCESS_IMAGE_PATCH
    def test_rejects_individual_accounts(self, _mock):
        individual = make_user()
        with self.assertRaises(ValidationError):
            verification_service.submit_organization_verification(
                individual, 'national_id', '123', 'front.jpg', 'reg.jpg', 'org.jpg',
            )

    @PROCESS_IMAGE_PATCH
    def test_rejects_second_submission_while_pending(self, _mock):
        user = make_org_user()
        verification_service.submit_organization_verification(user, 'national_id', '123', 'front.jpg', 'reg.jpg', 'org.jpg')
        with self.assertRaises(ValidationError):
            verification_service.submit_organization_verification(user, 'passport', '456', 'f2.jpg', 'r2.jpg', 'o2.jpg')


class ApproveOrganizationVerificationTest(APITestCase):
    def test_approve_verifies_user_and_copies_photo_to_org_logo(self):
        user = make_org_user(email='org2@example.com')
        admin = make_user(email='org-admin@example.com', role='admin')
        verification = OrganizationVerification.objects.create(
            user=user, contact_id_type='national_id', contact_id_number='1',
            contact_id_photo_front='x.jpg', registration_document='reg.jpg',
            organization_photo='mosque_event.jpg',
        )

        result = verification_service.approve_organization_verification(verification.id, admin)
        self.assertEqual(result.status, OrganizationVerification.Status.APPROVED)

        user.refresh_from_db()
        self.assertTrue(user.is_verified)
        user.organization.refresh_from_db()
        self.assertEqual(user.organization.logo, 'mosque_event.jpg')

    def test_reject_sets_reason_without_verifying(self):
        user = make_org_user(email='org3@example.com')
        admin = make_user(email='org-admin2@example.com', role='admin')
        verification = OrganizationVerification.objects.create(
            user=user, contact_id_type='national_id', contact_id_number='1',
            contact_id_photo_front='x.jpg', registration_document='reg.jpg', organization_photo='o.jpg',
        )
        result = verification_service.reject_organization_verification(verification.id, admin, reason='Docs unclear')
        self.assertEqual(result.status, OrganizationVerification.Status.REJECTED)
        self.assertEqual(result.rejection_reason, 'Docs unclear')
        user.refresh_from_db()
        self.assertFalse(user.is_verified)

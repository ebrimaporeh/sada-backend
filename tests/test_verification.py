from unittest.mock import patch
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User, IdentityVerification, Organization, OrganizationVerification
from apps.organizations.models import OrganizationType, OrganizationRole, OrganizationMembership
from apps.organizations.permissions import ALL_ORGANIZATION_PERMISSIONS, OrganizationPermission
from utils.storage import VerificationDocumentStorage
import services.verification_service as verification_service


def make_user(**kwargs):
    defaults = {'email': f'user{User.objects.count()}@example.com', 'password': 'pass'}
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def make_org_and_owner(**kwargs):
    """Returns (user, organization) -- user is the org's Owner-role member."""
    org_kwargs = kwargs.pop('org', {})
    user = make_user(**kwargs)
    org_type, _ = OrganizationType.objects.get_or_create(slug='community', defaults={'name': 'Community-Based Organization'})
    org_defaults = {
        'organization_name': 'Test Org', 'organization_type': org_type,
        'phone_2': '+2207000001', 'created_by': user,
    }
    org_defaults.update(org_kwargs)
    org = Organization.objects.create(**org_defaults)
    owner_role = OrganizationRole.objects.create(organization=org, name='Owner', permissions=list(ALL_ORGANIZATION_PERMISSIONS))
    OrganizationMembership.objects.create(user=user, organization=org, role=owner_role, is_contact_person=True)
    return user, org


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

    def test_does_not_touch_organization_verification(self):
        # revoke_verification is individual-identity-only now --
        # Organization.is_verified is a separate flag not tied to any one
        # member's own is_verified, so this must never touch it (see
        # verification_service.revoke_verification's docstring).
        user, org = make_org_and_owner(email='org-owner@example.com')
        org.is_verified = True
        org.save(update_fields=['is_verified'])
        approved = OrganizationVerification.objects.create(
            organization=org, submitted_by=user, registration_number='REG-1',
            registration_document='reg.jpg', organization_photo='org.jpg',
            status=OrganizationVerification.Status.APPROVED,
        )
        verification_service.revoke_verification(user, self.admin)
        approved.refresh_from_db()
        org.refresh_from_db()
        self.assertEqual(approved.status, OrganizationVerification.Status.APPROVED)
        self.assertTrue(org.is_verified)


class SubmitOrganizationVerificationTest(APITestCase):
    @PROCESS_IMAGE_PATCH
    def test_creates_a_pending_request_for_an_org_member(self, _mock):
        user, org = make_org_and_owner()
        verification = verification_service.submit_organization_verification(
            org, user, 'REG-123', 'reg.jpg', 'org.jpg',
        )
        self.assertEqual(verification.status, OrganizationVerification.Status.PENDING)

    @PROCESS_IMAGE_PATCH
    def test_rejects_a_non_member(self, _mock):
        _, org = make_org_and_owner()
        outsider = make_user()
        with self.assertRaises(ValidationError):
            verification_service.submit_organization_verification(
                org, outsider, 'REG-123', 'reg.jpg', 'org.jpg',
            )

    @PROCESS_IMAGE_PATCH
    def test_rejects_second_submission_while_pending(self, _mock):
        user, org = make_org_and_owner()
        verification_service.submit_organization_verification(org, user, 'REG-123', 'reg.jpg', 'org.jpg')
        with self.assertRaises(ValidationError):
            verification_service.submit_organization_verification(org, user, 'REG-456', 'r2.jpg', 'o2.jpg')

    @PROCESS_IMAGE_PATCH
    def test_rejects_when_organization_already_verified(self, _mock):
        user, org = make_org_and_owner()
        org.is_verified = True
        org.save(update_fields=['is_verified'])
        with self.assertRaises(ValidationError):
            verification_service.submit_organization_verification(org, user, 'REG-123', 'reg.jpg', 'org.jpg')


class ApproveOrganizationVerificationTest(APITestCase):
    def test_approve_verifies_org_and_copies_photo_to_org_logo(self):
        # organization_photo needs real bytes behind it here (unlike the
        # bare-string fixtures elsewhere in this file) -- approval now reads
        # the file back out of its (private-bucket-in-production, local-
        # disk-in-tests) storage and re-saves those bytes into org.logo's
        # own storage, rather than just copying the FieldFile's name. A
        # bare string with nothing on disk behind it would 404 on that read.
        from django.core.files.base import ContentFile
        user, org = make_org_and_owner(email='org2@example.com')
        admin = make_user(email='org-admin@example.com', role='admin')
        verification = OrganizationVerification.objects.create(
            organization=org, submitted_by=user, registration_number='REG-1',
            registration_document='reg.jpg',
        )
        verification.organization_photo.save('mosque_event.jpg', ContentFile(b'fake-image-bytes'), save=True)
        self.addCleanup(lambda: verification.organization_photo.delete(save=False))

        result = verification_service.approve_organization_verification(verification.id, admin)
        self.assertEqual(result.status, OrganizationVerification.Status.APPROVED)

        org.refresh_from_db()
        self.assertTrue(org.is_verified)
        # A real copy, not a shared reference -- different storage, so a
        # different (fresh-timestamped) path via organization_logo_path,
        # not an exact-name match with the source.
        self.assertNotEqual(org.logo.name, verification.organization_photo.name)
        self.assertTrue(org.logo.name.startswith(f'organizations/{org.id}/logo_'))
        with org.logo.open('rb') as f:
            self.assertEqual(f.read(), b'fake-image-bytes')
        self.addCleanup(lambda: org.logo.delete(save=False))

    def test_reject_sets_reason_without_verifying(self):
        user, org = make_org_and_owner(email='org3@example.com')
        admin = make_user(email='org-admin2@example.com', role='admin')
        verification = OrganizationVerification.objects.create(
            organization=org, submitted_by=user, registration_number='REG-1',
            registration_document='reg.jpg', organization_photo='o.jpg',
        )
        result = verification_service.reject_organization_verification(verification.id, admin, reason='Docs unclear')
        self.assertEqual(result.status, OrganizationVerification.Status.REJECTED)
        self.assertEqual(result.rejection_reason, 'Docs unclear')
        org.refresh_from_db()
        self.assertFalse(org.is_verified)


class VerificationDocumentStorageTest(APITestCase):
    """Organization verification documents must use the private
    `verification-documents` bucket, never the public `media` bucket, and
    must never resolve to a permanent/public URL. See utils/storage.py.

    apps/users/models.py resolves `storage=get_verification_storage()` once,
    at import time (Django app-loading, i.e. process boot) -- same timing
    as settings/base.py's own DEFAULT_FILE_STORAGE fallback for the public
    bucket. That means a field's already-resolved `.storage` can't be
    changed retroactively by `override_settings` inside a running test
    process, so the "does the field actually pick up
    SUPABASE_VERIFICATION_BUCKET" fact is verified in its own subprocess
    below, booted with the env var already set -- not by poking the
    already-loaded model in *this* test process.
    """

    def test_public_media_bucket_is_not_used_for_verification_documents(self):
        # Organization.logo never passes storage= at all -- it's always the
        # public default, in every environment. Proves the two are wired to
        # genuinely different mechanisms, not just different config values
        # of the same one (the field-level wiring itself is exercised for
        # real, env-var-configured behavior in the subprocess test below).
        logo_storage = Organization._meta.get_field('logo').storage
        self.assertNotIsInstance(logo_storage, VerificationDocumentStorage)

    @override_settings(SUPABASE_VERIFICATION_BUCKET='verification-documents')
    def test_bucket_name_comes_from_the_dedicated_env_setting(self):
        self.assertEqual(VerificationDocumentStorage().bucket_name, 'verification-documents')

    def test_get_verification_storage_falls_back_to_default_when_unconfigured(self):
        with override_settings(SUPABASE_VERIFICATION_BUCKET=''):
            from utils.storage import get_verification_storage
            self.assertIsNone(get_verification_storage())

    def test_get_verification_storage_returns_the_private_backend_when_configured(self):
        with override_settings(SUPABASE_VERIFICATION_BUCKET='verification-documents'):
            from utils.storage import get_verification_storage
            storage = get_verification_storage()
            self.assertIsInstance(storage, VerificationDocumentStorage)
            self.assertEqual(storage.bucket_name, 'verification-documents')

    def test_field_uses_the_private_bucket_when_env_var_is_set_at_boot(self):
        # Real subprocess, booted with SUPABASE_VERIFICATION_BUCKET already
        # in the environment -- the only way to observe the field-level
        # wiring this repo's settings actually use in production, since
        # get_verification_storage() is called once at Django app-loading
        # time, before any in-process override_settings could take effect.
        import os
        import subprocess
        import sys

        script = (
            "import django, os\n"
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings.testing')\n"
            "django.setup()\n"
            "from apps.users.models import OrganizationVerification\n"
            "from utils.storage import VerificationDocumentStorage\n"
            "field = OrganizationVerification._meta.get_field('registration_document')\n"
            "assert isinstance(field.storage, VerificationDocumentStorage), field.storage\n"
            "assert field.storage.bucket_name == 'verification-documents', field.storage.bucket_name\n"
            "print('OK')\n"
        )
        env = {**os.environ, 'SUPABASE_VERIFICATION_BUCKET': 'verification-documents'}
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, env=env, cwd=os.getcwd())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('OK', result.stdout)

    def test_signed_urls_are_temporary_and_never_public(self):
        storage = VerificationDocumentStorage()
        # querystring_auth=True + a custom_domain of None is what makes
        # .url() return a boto3-presigned, expiring S3 URL instead of the
        # public bucket's permanent /storage/v1/object/public/... path (see
        # AWS_S3_CUSTOM_DOMAIN in settings/base.py, which VerificationDocumentStorage
        # deliberately does not inherit).
        self.assertTrue(storage.querystring_auth)
        self.assertIsNone(storage.custom_domain)
        self.assertEqual(storage.querystring_expire, 300)


class OrganizationVerificationAccessTest(APITestCase):
    """Authorization for GET /users/organization-verification/me/ -- reuses
    the existing organization membership/RBAC model rather than a new one
    (see MyOrganizationVerificationView and
    OrganizationVerificationSerializer._can_view_documents)."""

    def setUp(self):
        self.owner, self.org = make_org_and_owner(email='doc-owner@example.com')

        member_role = OrganizationRole.objects.create(
            organization=self.org, name='Member', permissions=[OrganizationPermission.CREATE_CAMPAIGN],
        )
        self.plain_member = make_user(email='plain-member@example.com')
        OrganizationMembership.objects.create(user=self.plain_member, organization=self.org, role=member_role)

        self.outsider = make_user(email='outsider@example.com')
        self.admin = make_user(email='staff-admin@example.com', role='admin')

        self.verification = OrganizationVerification.objects.create(
            organization=self.org, submitted_by=self.owner, registration_number='REG-1',
            registration_document='reg.jpg',
        )
        self.verification.organization_photo.save('org.jpg', ContentFile(b'fake-bytes'), save=True)
        self.addCleanup(lambda: self.verification.organization_photo.delete(save=False))

    def _get(self):
        return self.client.get(reverse('organization-verification-me'), {'organization_id': str(self.org.id)})

    def test_non_member_cannot_access_at_all(self):
        self.client.force_authenticate(user=self.outsider)
        response = self._get()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_member_without_manage_organization_sees_status_but_not_documents(self):
        self.client.force_authenticate(user=self.plain_member)
        response = self._get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        verification = response.data['data']['verification']
        self.assertEqual(verification['registration_number'], 'REG-1')
        self.assertIsNone(verification['registration_document'])
        self.assertIsNone(verification['organization_photo'])

    def test_owner_with_manage_organization_can_see_signed_document_urls(self):
        self.client.force_authenticate(user=self.owner)
        response = self._get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        verification = response.data['data']['verification']
        self.assertIsNotNone(verification['registration_document'])
        self.assertIsNotNone(verification['organization_photo'])

    def test_platform_admin_can_see_documents_regardless_of_membership(self):
        from apps.users.serializers import OrganizationVerificationSerializer
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        request = Request(APIRequestFactory().get('/'))
        request.user = self.admin
        data = OrganizationVerificationSerializer(self.verification, context={'request': request}).data
        self.assertIsNotNone(data['registration_document'])
        self.assertIsNotNone(data['organization_photo'])

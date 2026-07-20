from django.core import mail
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.users.models import User, IdentityVerification, Organization, OrganizationVerification
import services.user_service as user_service


class MeViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='me@example.com',
            password='StrongPass@1',
            first_name='John',
            last_name='Doe',
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse('user-me')

    def test_get_me(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'me@example.com')

    def test_update_me(self):
        response = self.client.patch(self.url, {'first_name': 'Jane'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Jane')

    def test_unauthenticated_access(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserListViewTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@example.com',
            password='Admin@1234',
            is_staff=True,
            role=User.Role.ADMIN,
        )
        self.regular = User.objects.create_user(
            email='regular@example.com',
            password='User@1234',
        )
        self.url = reverse('user-list')

    def test_admin_can_list_users(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_regular_user_cannot_list_users(self):
        self.client.force_authenticate(user=self.regular)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DeleteOwnAccountTest(APITestCase):
    """Self-service account deletion anonymizes rather than hard-deletes --
    Campaign.owner is CASCADE, so an actual delete would destroy every
    campaign (and, via Donation.campaign's own CASCADE, every donation to
    them) a campaign-owning user ever had, which the Privacy Policy's
    financial-record-retention promise rules out."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='deleteme@example.com', password='StrongPass@1',
            first_name='John', last_name='Doe', phone='+2207000000',
        )

    def test_wrong_password_is_rejected(self):
        with self.assertRaises(ValidationError):
            user_service.delete_own_account(self.user, password='wrong')
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_correct_password_anonymizes_and_deactivates(self):
        original_id = self.user.id
        user_service.delete_own_account(self.user, password='StrongPass@1')
        self.user.refresh_from_db()

        self.assertEqual(self.user.id, original_id)  # same row, not a new/hard-deleted one
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.user.has_usable_password())
        self.assertEqual(self.user.first_name, 'Deleted')
        self.assertEqual(self.user.phone, '')
        self.assertNotEqual(self.user.email, 'deleteme@example.com')
        self.assertIn('deleted', self.user.email)

    def test_campaigns_and_donations_survive_deletion(self):
        from tests.test_campaigns import make_campaign
        from apps.donations.models import Donation
        from decimal import Decimal

        campaign = make_campaign(owner=self.user)
        donation = Donation.objects.create(
            campaign=campaign, donor=self.user, amount=Decimal('100.00'), provider='wave',
            phone='+2207000000', gateway='modempay', status=Donation.Status.PAID,
        )

        user_service.delete_own_account(self.user, password='StrongPass@1')

        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(campaign.__class__.objects.filter(pk=campaign.pk).exists())
        self.assertTrue(Donation.objects.filter(pk=donation.pk).exists())

    def test_social_only_account_does_not_need_a_password(self):
        social_user = User.objects.create_user(email='social@example.com', google_sub='abc123')
        social_user.set_unusable_password()
        social_user.save()
        # Should not raise even with no password supplied.
        user_service.delete_own_account(social_user, password='')
        social_user.refresh_from_db()
        self.assertFalse(social_user.is_active)

    def test_deletes_identity_verification_requests(self):
        IdentityVerification.objects.create(
            user=self.user, id_type='national_id', id_number='123', id_photo_front='x.jpg',
        )
        user_service.delete_own_account(self.user, password='StrongPass@1')
        self.assertFalse(IdentityVerification.objects.filter(user=self.user).exists())

    def test_anonymizes_organization_profile(self):
        org_user = User.objects.create_user(
            email='org@example.com', password='StrongPass@1',
            account_type=User.AccountType.ORGANIZATION,
        )
        Organization.objects.create(
            user=org_user, organization_name='Real Org Name', organization_type=Organization.OrgType.COMMUNITY,
            contact_person_name='Real Contact', phone_2='+2207000002',
        )
        OrganizationVerification.objects.create(
            user=org_user, contact_id_type='national_id', contact_id_number='1',
            contact_id_photo_front='x.jpg', registration_document='reg.jpg', organization_photo='o.jpg',
        )

        user_service.delete_own_account(org_user, password='StrongPass@1')

        org_user.organization.refresh_from_db()
        self.assertNotEqual(org_user.organization.organization_name, 'Real Org Name')
        self.assertEqual(org_user.organization.contact_person_name, '')
        self.assertFalse(OrganizationVerification.objects.filter(user=org_user).exists())

    def test_sends_a_confirmation_email_to_the_original_address(self):
        mail.outbox = []
        user_service.delete_own_account(self.user, password='StrongPass@1')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('deleteme@example.com', mail.outbox[0].to)


class DeleteAccountViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='viewdelete@example.com', password='StrongPass@1')
        self.client.force_authenticate(user=self.user)
        self.url = reverse('user-me')

    def test_requires_auth(self):
        self.client.logout()
        response = self.client.delete(self.url, {'password': 'StrongPass@1'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_deletes_with_correct_password(self):
        response = self.client.delete(self.url, {'password': 'StrongPass@1'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_wrong_password_returns_400_and_leaves_account_active(self):
        response = self.client.delete(self.url, {'password': 'wrong'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

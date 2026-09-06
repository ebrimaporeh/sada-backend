from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from apps.users.models import User, Organization
from apps.campaigns.models import Campaign, Category
from apps.donations.models import Donation
from apps.notifications.models import Notification
from apps.ledger.models import Account, LedgerEntry
from apps.organizations.models import OrganizationType, OrganizationRole, OrganizationMembership
from apps.organizations.permissions import OrganizationPermission
import services.donation_service as donation_service
import services.organization_service as organization_service


def make_org_type(**kwargs):
    defaults = {'slug': f'org-type-{OrganizationType.objects.count()}', 'name': 'Community Organization', 'is_visible': True}
    defaults.update(kwargs)
    return OrganizationType.objects.create(**defaults)


def make_org_and_owner(**kwargs):
    org_type = kwargs.pop('org_type', None) or make_org_type()
    user = kwargs.pop('user', None) or User.objects.create_user(
        email=f'owner{User.objects.count()}@example.com', password='pass',
    )
    org = organization_service.create_organization(
        user,
        organization_name=kwargs.pop('organization_name', 'Al-Madina Mosque'),
        organization_type_slug=org_type.slug,
    )
    return user, org


def make_member(org, permissions=None):
    user = User.objects.create_user(email=f'member{User.objects.count()}@example.com', password='pass')
    role = OrganizationRole.objects.create(
        organization=org, name=f'Role {OrganizationRole.objects.count()}', permissions=permissions or [],
    )
    OrganizationMembership.objects.create(user=user, organization=org, role=role)
    return user, role


def make_category(**kwargs):
    defaults = {'name': f'Category {Category.objects.count()}'}
    defaults.update(kwargs)
    return Category.objects.create(**defaults)


def make_campaign(**kwargs):
    owner = kwargs.pop('owner', None) or User.objects.create_user(
        email=f'campowner{User.objects.count()}@example.com', password='pass',
    )
    category = kwargs.pop('category', None) or make_category()
    defaults = {
        'owner': owner,
        'category': category,
        'title': 'Build New Mosque',
        'slug': f'build-new-mosque-{Campaign.objects.count()}',
        'short_description': 'New prayer hall',
        'story': 'Community fundraiser.',
        'goal': Decimal('10000.00'),
        'status': Campaign.Status.ACTIVE,
    }
    defaults.update(kwargs)
    return Campaign.objects.create(**defaults)


class OrganizationModelTest(APITestCase):
    def test_slug_auto_generated_and_unique_on_collision(self):
        _, org1 = make_org_and_owner(organization_name='What\'s On Gambia')
        _, org2 = make_org_and_owner(organization_name='What\'s On Gambia')
        self.assertEqual(org1.slug, 'whats-on-gambia')
        self.assertEqual(org2.slug, 'whats-on-gambia-1')


class DonationModelConstraintTest(APITestCase):
    def test_cannot_save_donation_with_neither_destination(self):
        with self.assertRaises(Exception):
            Donation.objects.create(amount=Decimal('50.00'), payment_reference='SD-NEITHER')

    def test_cannot_save_donation_with_both_destinations(self):
        _, org = make_org_and_owner()
        campaign = make_campaign()
        with self.assertRaises(Exception):
            Donation.objects.create(
                amount=Decimal('50.00'), payment_reference='SD-BOTH',
                campaign=campaign, organization=org,
            )

    def test_destination_helpers(self):
        _, org = make_org_and_owner(organization_name='Donors for Life')
        donation = Donation.objects.create(amount=Decimal('50.00'), payment_reference='SD-ORG1', organization=org)
        self.assertTrue(donation.is_organization_donation)
        self.assertEqual(donation.destination, org)
        self.assertEqual(donation.destination_title, 'Donors for Life')
        self.assertEqual(donation.destination_slug, org.slug)

        campaign = make_campaign(title='Well for Bakau')
        campaign_donation = Donation.objects.create(amount=Decimal('50.00'), payment_reference='SD-CAMP1', campaign=campaign)
        self.assertFalse(campaign_donation.is_organization_donation)
        self.assertEqual(campaign_donation.destination_title, 'Well for Bakau')


class CreateOrganizationDonationTest(APITestCase):
    def setUp(self):
        self.owner, self.org = make_org_and_owner()

    @patch('services.modempay_service.create_payment_intent')
    def test_create_donation_direct_to_organization(self, mock_create):
        mock_create.return_value = {
            'status': True,
            'data': {'payment_link': 'https://pay.modempay.com/org', 'intent_secret': 'sec_org1'},
        }
        donation, payment_link, error_message = donation_service.create_donation(None, {
            'organization_id': self.org.id,
            'amount': Decimal('250.00'),
            'provider': 'wave',
            'phone': '+2207000000',
        })
        self.assertIsNone(error_message)
        self.assertEqual(payment_link, 'https://pay.modempay.com/org')
        self.assertEqual(donation.organization_id, self.org.id)
        self.assertIsNone(donation.campaign_id)
        self.assertEqual(donation.status, Donation.Status.PENDING)

    def test_create_donation_unknown_organization_404s(self):
        import uuid
        from django.http import Http404
        with self.assertRaises(Http404):
            donation_service.create_donation(None, {
                'organization_id': uuid.uuid4(),
                'amount': Decimal('100.00'),
                'provider': 'wave',
                'phone': '+2207000000',
            })

    def test_serializer_rejects_neither_destination(self):
        from apps.donations.serializers import DonationCreateSerializer
        serializer = DonationCreateSerializer(data={'amount': '100.00', 'provider': 'wave', 'phone': '+2207000000'})
        self.assertFalse(serializer.is_valid())

    def test_serializer_rejects_both_destinations(self):
        from apps.donations.serializers import DonationCreateSerializer
        campaign = make_campaign()
        serializer = DonationCreateSerializer(data={
            'amount': '100.00', 'provider': 'wave', 'phone': '+2207000000',
            'campaign_id': str(campaign.id), 'organization_id': str(self.org.id),
        })
        self.assertFalse(serializer.is_valid())

    def test_serializer_accepts_organization_only(self):
        from apps.donations.serializers import DonationCreateSerializer
        serializer = DonationCreateSerializer(data={
            'amount': '100.00', 'provider': 'wave', 'phone': '+2207000000',
            'organization_id': str(self.org.id),
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)


class ConfirmOrganizationDonationTest(APITestCase):
    def setUp(self):
        self.owner, self.org = make_org_and_owner()
        self.donation = Donation.objects.create(
            organization=self.org, amount=Decimal('300.00'), fee=Decimal('0'),
            payment_reference='SD-ORGCONFIRM', provider='wave', phone='+2207000000',
            gateway='modempay', status=Donation.Status.PENDING,
        )

    def test_confirm_posts_ledger_to_organization_account(self):
        donation_service.confirm_donation_by_reference('SD-ORGCONFIRM', provider_reference='tx_1')
        self.donation.refresh_from_db()
        self.assertEqual(self.donation.status, Donation.Status.PAID)

        account = Account.objects.get(type=Account.Type.ORGANIZATION, code=f'organization:{self.org.id}')
        credited = LedgerEntry.objects.filter(account=account, direction=LedgerEntry.Direction.CREDIT).first()
        self.assertIsNotNone(credited)
        self.assertEqual(credited.amount, Decimal('300.00'))

    def test_confirm_notifies_owner_role_members_only(self):
        # A plain member with no manage_organization permission shouldn't
        # be notified -- only Owner-role members (or anyone else explicitly
        # granted manage_organization) should.
        plain_member, _ = make_member(self.org, permissions=[OrganizationPermission.CREATE_CAMPAIGN])
        manager, _ = make_member(self.org, permissions=[OrganizationPermission.MANAGE_ORGANIZATION])

        donation_service.confirm_donation_by_reference('SD-ORGCONFIRM', provider_reference='tx_1')

        self.assertTrue(Notification.objects.filter(user=self.owner, notification_type=Notification.Type.DONATION_RECEIVED).exists())
        self.assertTrue(Notification.objects.filter(user=manager, notification_type=Notification.Type.DONATION_RECEIVED).exists())
        self.assertFalse(Notification.objects.filter(user=plain_member, notification_type=Notification.Type.DONATION_RECEIVED).exists())

    def test_confirm_does_not_touch_any_campaign(self):
        campaign = make_campaign(organization=self.org, raised=Decimal('0'), donors_count=0)
        donation_service.confirm_donation_by_reference('SD-ORGCONFIRM', provider_reference='tx_1')
        campaign.refresh_from_db()
        self.assertEqual(campaign.raised, Decimal('0'))
        self.assertEqual(campaign.donors_count, 0)


class OrganizationTotalsSeparationTest(APITestCase):
    """Direct organization donations must be included in the org's overall
    total, but never leak into a specific campaign's own total -- see
    project.md's donation-totals example."""

    def setUp(self):
        self.owner, self.org = make_org_and_owner()
        self.campaign = make_campaign(organization=self.org, raised=Decimal('0'), donors_count=0)

    def _make_paid(self, reference, **kwargs):
        defaults = {
            'amount': Decimal('100.00'), 'fee': Decimal('0'), 'payment_reference': reference,
            'provider': 'wave', 'phone': '+2207000000', 'gateway': 'modempay',
            'status': Donation.Status.PENDING,
        }
        defaults.update(kwargs)
        donation = Donation.objects.create(**defaults)
        return donation_service.confirm_donation_by_reference(reference, provider_reference='tx')

    def test_organization_total_includes_direct_and_campaign_donations(self):
        self._make_paid('SD-DIRECT1', organization=self.org, amount=Decimal('100.00'))
        self._make_paid('SD-CAMP1', campaign=self.campaign, amount=Decimal('50.00'))

        stats = donation_service.get_organization_donation_stats(self.owner, str(self.org.id))

        self.assertEqual(stats['direct_total'], Decimal('100.00'))
        self.assertEqual(stats['campaign_total'], Decimal('50.00'))
        self.assertEqual(stats['total_raised'], Decimal('150.00'))

    def test_campaign_raised_excludes_direct_organization_donations(self):
        self._make_paid('SD-DIRECT2', organization=self.org, amount=Decimal('999.00'))
        self._make_paid('SD-CAMP2', campaign=self.campaign, amount=Decimal('50.00'))

        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.raised, Decimal('50.00'))

    def test_public_total_raised_is_direct_only(self):
        self._make_paid('SD-DIRECT3', organization=self.org, amount=Decimal('40.00'))
        self._make_paid('SD-CAMP3', campaign=self.campaign, amount=Decimal('999.00'))

        total = donation_service.get_public_organization_total_raised(self.org)
        self.assertEqual(total, Decimal('40.00'))


class RefundOrganizationDonationTest(APITestCase):
    def setUp(self):
        self.owner, self.org = make_org_and_owner()
        self.donor = User.objects.create_user(email='donor@example.com', password='pass')
        self.donation = Donation.objects.create(
            organization=self.org, donor=self.donor, amount=Decimal('200.00'),
            payment_reference='SD-ORGREFUND', provider='wave', phone='+2207000000',
            gateway='modempay', provider_reference='ch_orgpaid', status=Donation.Status.PAID,
        )

    @patch('services.modempay_service.reverse_transaction')
    def test_refund_reverses_ledger_and_notifies(self, mock_reverse):
        mock_reverse.return_value = {'id': 'ch_orgpaid', 'status': 'reversed'}

        result = donation_service.refund_donation(self.donation, reason='Duplicate charge')

        self.assertEqual(result.status, Donation.Status.REFUNDED)
        self.assertTrue(
            Notification.objects.filter(user=self.owner, notification_type=Notification.Type.DONATION_REFUNDED).exists()
        )
        self.assertTrue(
            Notification.objects.filter(user=self.donor, notification_type=Notification.Type.DONATION_REFUNDED).exists()
        )


class OrganizationDonationPermissionsTest(APITestCase):
    def setUp(self):
        self.owner, self.org = make_org_and_owner()
        self.outsider = User.objects.create_user(email='outsider@example.com', password='pass')

    def test_non_member_cannot_view_donation_list(self):
        with self.assertRaises(Exception):
            donation_service.get_organization_donations(self.outsider, str(self.org.id))

    def test_non_member_cannot_view_donation_stats(self):
        with self.assertRaises(Exception):
            donation_service.get_organization_donation_stats(self.outsider, str(self.org.id))

    def test_member_without_manage_organization_cannot_edit_description(self):
        member, _ = make_member(self.org, permissions=[OrganizationPermission.CREATE_CAMPAIGN])
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            organization_service.update_organization(member, self.org, description='New bio')

    def test_owner_can_edit_description(self):
        organization_service.update_organization(self.owner, self.org, description='Serving our community.')
        self.org.refresh_from_db()
        self.assertEqual(self.org.description, 'Serving our community.')


class PublicOrganizationDonateViewTest(APITestCase):
    def setUp(self):
        self.owner, self.org = make_org_and_owner(organization_name='Serrekunda CDA')

    def test_public_donate_page_is_reachable_without_auth(self):
        url = reverse('organization-public-donate', kwargs={'slug': self.org.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']['organization']
        self.assertEqual(data['organization_name'], 'Serrekunda CDA')
        self.assertEqual(data['slug'], self.org.slug)
        self.assertIn('total_raised', data)

    def test_public_donate_page_stays_reachable_with_no_campaigns(self):
        # No campaign ever created for this org -- the whole point of a
        # direct organization donation destination.
        self.assertEqual(Campaign.objects.filter(organization=self.org).count(), 0)
        url = reverse('organization-public-donate', kwargs={'slug': self.org.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unknown_slug_404s(self):
        url = reverse('organization-public-donate', kwargs={'slug': 'does-not-exist'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class DonationCreateViewOrganizationTest(APITestCase):
    """End-to-end through the real POST /donations/ view, not just the
    service function -- regression coverage that the existing campaign
    donation view path still works unchanged alongside the new branch."""

    def setUp(self):
        self.owner, self.org = make_org_and_owner()
        self.campaign = make_campaign()

    @patch('services.modempay_service.create_payment_intent')
    def test_donate_to_organization_via_api(self, mock_create):
        mock_create.return_value = {
            'status': True,
            'data': {'payment_link': 'https://pay.modempay.com/x', 'intent_secret': 'sec_x'},
        }
        response = self.client.post(reverse('donation-create'), {
            'organization_id': str(self.org.id),
            'amount': '150.00',
            'provider': 'wave',
            'phone': '+2207000000',
            'donor_name': 'Ebrima',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        donation_id = response.data['data']['donation']['id']
        donation = Donation.objects.get(pk=donation_id)
        self.assertEqual(donation.organization_id, self.org.id)
        self.assertIsNone(donation.campaign_id)

    @patch('services.modempay_service.create_payment_intent')
    def test_existing_campaign_donation_flow_unaffected(self, mock_create):
        mock_create.return_value = {
            'status': True,
            'data': {'payment_link': 'https://pay.modempay.com/y', 'intent_secret': 'sec_y'},
        }
        response = self.client.post(reverse('donation-create'), {
            'campaign_id': str(self.campaign.id),
            'amount': '150.00',
            'provider': 'wave',
            'phone': '+2207000000',
            'donor_name': 'Ebrima',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        donation_id = response.data['data']['donation']['id']
        donation = Donation.objects.get(pk=donation_id)
        self.assertEqual(donation.campaign_id, self.campaign.id)
        self.assertIsNone(donation.organization_id)

    def test_view_rejects_neither_destination(self):
        response = self.client.post(reverse('donation-create'), {
            'amount': '150.00', 'provider': 'wave', 'phone': '+2207000000',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class OpenEndedCampaignTest(APITestCase):
    """Campaigns with deadline=None -- see architecture-plan.md's
    "no deadline does not mean no goal" note and project.md's campaign
    lifecycle section."""

    def test_campaign_can_be_created_without_a_deadline(self):
        campaign = make_campaign(deadline=None)
        self.assertIsNone(campaign.deadline)
        self.assertEqual(campaign.status, Campaign.Status.ACTIVE)

    def test_campaign_creation_serializer_does_not_require_deadline(self):
        from apps.campaigns.serializers import CampaignCreateSerializer
        serializer = CampaignCreateSerializer(data={
            'title': 'Ongoing relief fund',
            'short_description': 'Helping as needed',
            'story': 'A long-running fund with no fixed end date.',
            'goal': '5000.00',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn('deadline', serializer.validated_data)

    def test_open_ended_campaign_survives_expire_sweep(self):
        import services.campaign_service as campaign_service
        campaign = make_campaign(deadline=None)

        result = campaign_service.expire_overdue_campaigns()

        self.assertEqual(result, {'checked': 0, 'expired': 0})
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.ACTIVE)

    def test_open_ended_campaign_can_still_complete_on_goal(self):
        import services.campaign_service as campaign_service
        campaign = make_campaign(deadline=None, goal=Decimal('1000.00'), raised=Decimal('1000.00'))

        result = campaign_service.close_funded_campaigns()

        self.assertEqual(result, {'checked': 1, 'completed': 1})
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.COMPLETED)

    @patch('services.modempay_service.create_payment_intent')
    def test_donation_to_open_ended_campaign_succeeds(self, mock_create):
        mock_create.return_value = {
            'status': True,
            'data': {'payment_link': 'https://pay.modempay.com/z', 'intent_secret': 'sec_z'},
        }
        campaign = make_campaign(deadline=None)
        donation, payment_link, error_message = donation_service.create_donation(None, {
            'campaign_id': campaign.id,
            'amount': Decimal('100.00'),
            'provider': 'wave',
            'phone': '+2207000000',
        })
        self.assertIsNone(error_message)
        self.assertIsNotNone(payment_link)

    def test_deadlined_campaign_still_expires_as_before(self):
        """Regression guard alongside the open-ended tests above."""
        import services.campaign_service as campaign_service
        from datetime import timedelta
        campaign = make_campaign(deadline=timezone.localdate() - timedelta(days=1))

        result = campaign_service.expire_overdue_campaigns()

        self.assertEqual(result, {'checked': 1, 'expired': 1})
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.EXPIRED)

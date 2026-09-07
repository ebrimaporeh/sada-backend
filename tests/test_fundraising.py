from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.users.models import User, Organization
from apps.campaigns.models import Campaign, Category
from apps.fundraising.models import DestinationType, Embed, Poster
import services.organization_service as organization_service
import services.fundraising_destination as fundraising_destination
from apps.organizations.models import OrganizationType


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


class PosterModelConstraintTest(APITestCase):
    def test_cannot_save_poster_with_neither_destination(self):
        with self.assertRaises(Exception):
            Poster.objects.create(
                destination_type=DestinationType.CAMPAIGN, name='Untitled', template=Poster.Template.SQUARE,
            )

    def test_cannot_save_poster_with_both_destinations(self):
        _, org = make_org_and_owner()
        campaign = make_campaign()
        with self.assertRaises(Exception):
            Poster.objects.create(
                destination_type=DestinationType.CAMPAIGN, campaign=campaign, organization=org,
                name='Untitled', template=Poster.Template.SQUARE,
            )

    def test_can_save_poster_for_campaign_destination(self):
        campaign = make_campaign()
        poster = Poster.objects.create(
            destination_type=DestinationType.CAMPAIGN, campaign=campaign,
            name='Ramadan Poster', template=Poster.Template.SQUARE,
        )
        self.assertEqual(poster.campaign, campaign)
        self.assertIsNone(poster.organization)

    def test_can_save_poster_for_organization_destination(self):
        _, org = make_org_and_owner()
        poster = Poster.objects.create(
            destination_type=DestinationType.ORGANIZATION, organization=org,
            name='Homepage Poster', template=Poster.Template.STORY,
        )
        self.assertEqual(poster.organization, org)
        self.assertIsNone(poster.campaign)


class EmbedModelConstraintTest(APITestCase):
    def test_cannot_save_embed_with_neither_destination(self):
        with self.assertRaises(Exception):
            Embed.objects.create(destination_type=DestinationType.CAMPAIGN, name='Untitled')

    def test_cannot_save_embed_with_both_destinations(self):
        _, org = make_org_and_owner()
        campaign = make_campaign()
        with self.assertRaises(Exception):
            Embed.objects.create(
                destination_type=DestinationType.CAMPAIGN, campaign=campaign, organization=org, name='Untitled',
            )


class FundraisingDestinationResolverTest(APITestCase):
    def test_resolve_campaign_destination(self):
        campaign = make_campaign(
            goal=Decimal('10000.00'), raised=Decimal('2500.00'), donors_count=3,
            deadline=timezone.now().date() + timezone.timedelta(days=30),
        )
        destination = fundraising_destination.resolve_destination(DestinationType.CAMPAIGN, campaign=campaign)
        self.assertEqual(destination.type, DestinationType.CAMPAIGN)
        self.assertEqual(destination.title, campaign.title)
        self.assertEqual(destination.goal, Decimal('10000.00'))
        self.assertEqual(destination.raised, Decimal('2500.00'))
        self.assertEqual(destination.progress_percent, 25)
        self.assertFalse(destination.is_ongoing)
        self.assertIn(f'/campaigns/{campaign.slug}', destination.public_url)
        self.assertIn(f'/donate/{campaign.slug}', destination.donation_url)

    def test_open_ended_campaign_has_no_deadline_and_is_ongoing(self):
        campaign = make_campaign(deadline=None)
        destination = fundraising_destination.resolve_destination(DestinationType.CAMPAIGN, campaign=campaign)
        self.assertIsNone(destination.deadline)
        self.assertTrue(destination.is_ongoing)

    def test_resolve_organization_destination_has_no_progress_fields(self):
        _, org = make_org_and_owner()
        destination = fundraising_destination.resolve_destination(DestinationType.ORGANIZATION, organization=org)
        self.assertEqual(destination.type, DestinationType.ORGANIZATION)
        self.assertEqual(destination.title, org.organization_name)
        self.assertIsNone(destination.goal)
        self.assertIsNone(destination.raised)
        self.assertIsNone(destination.progress_percent)
        self.assertTrue(destination.is_ongoing)
        self.assertIn(f'/give/{org.slug}', destination.public_url)
        self.assertIn(f'/give/{org.slug}', destination.donation_url)

    def test_resolve_campaign_destination_requires_campaign(self):
        with self.assertRaises(ValueError):
            fundraising_destination.resolve_destination(DestinationType.CAMPAIGN)

    def test_resolve_organization_destination_requires_organization(self):
        with self.assertRaises(ValueError):
            fundraising_destination.resolve_destination(DestinationType.ORGANIZATION)

    def test_resolve_unknown_destination_type_raises(self):
        with self.assertRaises(ValueError):
            fundraising_destination.resolve_destination('something-else')

    def test_campaign_belonging_to_organization_surfaces_organization_display_fields(self):
        _, org = make_org_and_owner()
        campaign = make_campaign(organization=org)
        destination = fundraising_destination.resolve_destination(DestinationType.CAMPAIGN, campaign=campaign)
        self.assertEqual(destination.organization_name, org.organization_name)

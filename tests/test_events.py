from decimal import Decimal
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.campaigns.models import Campaign, Category
from apps.events.models import Event
from apps.users.models import User
import services.events_service as events_service


def make_campaign(**kwargs):
    owner = kwargs.pop('owner', None) or User.objects.create_user(
        email=f'events-owner{User.objects.count()}@example.com', password='pass',
    )
    category = kwargs.pop('category', None) or Category.objects.create(name=f'Cat {Category.objects.count()}')
    defaults = {
        'owner': owner, 'category': category, 'title': 'Well for Bakau',
        'slug': f'well-for-bakau-{Campaign.objects.count()}', 'short_description': 'Clean water',
        'story': 'A well for the community.', 'goal': Decimal('10000.00'), 'status': Campaign.Status.ACTIVE,
    }
    defaults.update(kwargs)
    return Campaign.objects.create(**defaults)


class TrackEventViewTest(APITestCase):
    def test_records_a_campaign_viewed_event(self):
        campaign = make_campaign()
        response = self.client.post('/api/v1/events/track/', {
            'type': Event.Type.CAMPAIGN_VIEWED, 'campaign_slug': campaign.slug, 'session_id': 'abc123',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = Event.objects.get(type=Event.Type.CAMPAIGN_VIEWED)
        self.assertEqual(event.campaign, campaign)
        self.assertEqual(event.session_id, 'abc123')

    def test_works_without_authentication(self):
        response = self.client.post('/api/v1/events/track/', {'type': Event.Type.CAMPAIGN_CLICKED}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_unknown_campaign_slug_does_not_error(self):
        response = self.client.post('/api/v1/events/track/', {
            'type': Event.Type.CAMPAIGN_SHARED, 'campaign_slug': 'does-not-exist',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = Event.objects.get(type=Event.Type.CAMPAIGN_SHARED)
        self.assertIsNone(event.campaign)

    def test_invalid_type_is_rejected(self):
        response = self.client.post('/api/v1/events/track/', {'type': 'not_a_real_type'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_metadata_is_stored(self):
        response = self.client.post('/api/v1/events/track/', {
            'type': Event.Type.DONATION_AMOUNT_SELECTED, 'metadata': {'amount': 250},
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = Event.objects.get(type=Event.Type.DONATION_AMOUNT_SELECTED)
        self.assertEqual(event.metadata['amount'], 250)


class CampaignViewIsAnalyticsNotAuditTest(APITestCase):
    """The exact regression this whole redesign was for: a campaign page
    view must show up as a product-engagement Event, never as an AuditLog
    entry."""

    def test_recording_a_view_creates_an_event_and_no_audit_entry(self):
        campaign = make_campaign()
        response = self.client.post(f'/api/v1/campaigns/{campaign.slug}/view/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(Event.objects.filter(type=Event.Type.CAMPAIGN_VIEWED, campaign=campaign).exists())
        self.assertEqual(AuditLog.objects.count(), 0)
        campaign.refresh_from_db()
        self.assertEqual(campaign.views_count, 1)


class EventsServiceTest(APITestCase):
    def test_track_never_raises(self):
        events_service.track('not_a_real_type')  # invalid choice at the DB layer
        # No exception -- that's the assertion.

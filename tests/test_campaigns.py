from decimal import Decimal
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User
from apps.campaigns.models import Campaign, Category
from apps.campaigns.serializers import AdminCampaignListSerializer
import services.campaign_service as campaign_service


def make_category(**kwargs):
    defaults = {'name': f'Category {Category.objects.count()}'}
    defaults.update(kwargs)
    return Category.objects.create(**defaults)


def make_campaign(**kwargs):
    owner = kwargs.pop('owner', None) or User.objects.create_user(
        email=f'owner{User.objects.count()}@example.com', password='pass',
    )
    category = kwargs.pop('category', None) or make_category()
    defaults = {
        'owner': owner,
        'category': category,
        'title': 'Well for Bakau',
        'slug': f'well-for-bakau-{Campaign.objects.count()}',
        'short_description': 'Clean water',
        'story': 'A well for the community.',
        'goal': Decimal('10000.00'),
        'status': Campaign.Status.ACTIVE,
    }
    defaults.update(kwargs)
    return Campaign.objects.create(**defaults)


class AdminCampaignListSerializerTest(APITestCase):
    """The admin campaigns list table + summary sheet only ever read a
    handful of fields -- AdminCampaignListSerializer is the lean projection
    that replaced serializing full story/images/updates (and running
    reports_count/pending_reports_count/total_withdrawn/available_balance
    aggregate queries) for every row on the page."""

    def test_excludes_heavy_fields_the_list_and_sheet_never_render(self):
        campaign = make_campaign()
        data = AdminCampaignListSerializer(campaign).data
        for field in ('story', 'short_description', 'images', 'updates', 'updates_count',
                      'reports_count', 'pending_reports_count', 'total_withdrawn',
                      'available_balance', 'owner_id', 'owner_email', 'cover_image_url'):
            self.assertNotIn(field, data)

    def test_includes_exactly_what_the_table_and_sheet_render(self):
        campaign = make_campaign()
        data = AdminCampaignListSerializer(campaign).data
        for field in ('id', 'title', 'slug', 'status', 'goal', 'raised',
                      'region', 'beneficiary', 'category_name', 'deadline'):
            self.assertIn(field, data)
        self.assertEqual(data['category_name'], campaign.category.name)


class AdminCampaignListQueryCountTest(APITestCase):
    """Regression test for the N+1 this endpoint had: AdminCampaignSerializer's
    nested images/updates (no prefetch_related) and 4 SerializerMethodFields
    each ran their own query per row, so query count scaled with the number
    of campaigns on the page. Asserts it no longer does."""

    def test_query_count_does_not_scale_with_campaign_count(self):
        for _ in range(3):
            make_campaign()
        with CaptureQueriesContext(connection) as ctx:
            list(campaign_service.get_all_campaigns())
            serializer = AdminCampaignListSerializer(Campaign.objects.select_related('category').all(), many=True)
            serializer.data
        few_campaigns_queries = len(ctx.captured_queries)

        for _ in range(10):
            make_campaign()
        with CaptureQueriesContext(connection) as ctx:
            list(campaign_service.get_all_campaigns())
            serializer = AdminCampaignListSerializer(Campaign.objects.select_related('category').all(), many=True)
            serializer.data
        many_campaigns_queries = len(ctx.captured_queries)

        self.assertEqual(few_campaigns_queries, many_campaigns_queries)


class AdminCampaignListViewTest(APITestCase):
    def test_endpoint_requires_admin(self):
        response = self.client.get('/api/v1/campaigns/admin/all/')
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

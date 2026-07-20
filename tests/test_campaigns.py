from decimal import Decimal
from django.core import mail
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User
from apps.campaigns.models import Campaign, CampaignReport, Category
from apps.campaigns.serializers import AdminCampaignListSerializer
from apps.donations.models import Donation
from apps.notifications.models import Notification
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


class CreateUpdateCampaignTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='creator@example.com', password='pass')
        self.category = make_category()

    def test_create_campaign_goes_straight_to_active(self):
        # No draft/pending review step today -- create_campaign approves on
        # creation, matching the product's current "publish immediately" flow.
        campaign = campaign_service.create_campaign(self.owner, {
            'category_id': self.category.id,
            'title': 'New Well',
            'short_description': 'Water for the village',
            'story': 'Long story here.',
            'goal': Decimal('5000.00'),
        })
        self.assertEqual(campaign.status, Campaign.Status.ACTIVE)
        self.assertIsNotNone(campaign.approved_at)
        self.assertEqual(campaign.owner, self.owner)
        self.assertTrue(campaign.slug)

    def test_create_campaign_with_unknown_category_id_leaves_category_null(self):
        campaign = campaign_service.create_campaign(self.owner, {
            'category_id': '00000000-0000-0000-0000-000000000000',
            'title': 'No Category',
            'short_description': 'desc',
            'story': 'story',
            'goal': Decimal('100.00'),
        })
        self.assertIsNone(campaign.category)

    def test_update_campaign_changes_category(self):
        campaign = make_campaign(owner=self.owner, category=self.category)
        new_category = make_category()
        updated = campaign_service.update_campaign(campaign, {
            'category_id': new_category.id, 'title': 'Renamed',
        })
        self.assertEqual(updated.category, new_category)
        self.assertEqual(updated.title, 'Renamed')


class TogglePauseCampaignTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='pauser@example.com', password='pass')

    def test_active_toggles_to_suspended_and_back(self):
        campaign = make_campaign(owner=self.owner, status=Campaign.Status.ACTIVE)
        toggled = campaign_service.toggle_pause_campaign(self.owner, campaign.slug)
        self.assertEqual(toggled.status, Campaign.Status.SUSPENDED)

        toggled_again = campaign_service.toggle_pause_campaign(self.owner, campaign.slug)
        self.assertEqual(toggled_again.status, Campaign.Status.ACTIVE)

    def test_pending_campaign_cannot_be_toggled(self):
        campaign = make_campaign(owner=self.owner, status=Campaign.Status.PENDING)
        with self.assertRaises(ValueError):
            campaign_service.toggle_pause_campaign(self.owner, campaign.slug)


class DeleteCampaignTest(APITestCase):
    def test_draft_campaign_can_be_deleted(self):
        campaign = make_campaign(status=Campaign.Status.DRAFT)
        campaign_service.delete_campaign(campaign)
        self.assertFalse(Campaign.objects.filter(pk=campaign.pk).exists())

    def test_rejected_campaign_can_be_deleted(self):
        campaign = make_campaign(status=Campaign.Status.REJECTED)
        campaign_service.delete_campaign(campaign)
        self.assertFalse(Campaign.objects.filter(pk=campaign.pk).exists())

    def test_active_campaign_cannot_be_deleted(self):
        campaign = make_campaign(status=Campaign.Status.ACTIVE)
        with self.assertRaises(ValueError):
            campaign_service.delete_campaign(campaign)
        self.assertTrue(Campaign.objects.filter(pk=campaign.pk).exists())


class CampaignUpdateNotificationTest(APITestCase):
    """_notify_donors_of_update -- posting an update should reach every
    distinct PAID donor exactly once, and no one else."""

    def setUp(self):
        self.campaign = make_campaign()
        self.owner = self.campaign.owner

    def make_donation(self, donor=None, status=Donation.Status.PAID, **kwargs):
        defaults = {
            'campaign': self.campaign, 'donor': donor, 'amount': Decimal('50.00'),
            'provider': 'wave', 'phone': '+2207000000', 'gateway': 'modempay',
            'status': status,
        }
        defaults.update(kwargs)
        return Donation.objects.create(**defaults)

    def test_notifies_each_distinct_paid_donor_once(self):
        donor1 = User.objects.create_user(email='donor1@example.com', password='pass')
        donor2 = User.objects.create_user(email='donor2@example.com', password='pass')
        self.make_donation(donor=donor1)
        self.make_donation(donor=donor1)  # same donor donated twice -- one notification, not two
        self.make_donation(donor=donor2)

        campaign_service.add_campaign_update(self.campaign, self.owner, 'Progress!', 'We built the well.')

        self.assertEqual(Notification.objects.filter(user=donor1, notification_type=Notification.Type.CAMPAIGN_UPDATE).count(), 1)
        self.assertEqual(Notification.objects.filter(user=donor2, notification_type=Notification.Type.CAMPAIGN_UPDATE).count(), 1)

    def test_does_not_notify_pending_or_failed_donors(self):
        donor = User.objects.create_user(email='pending-donor@example.com', password='pass')
        self.make_donation(donor=donor, status=Donation.Status.PENDING)
        self.make_donation(donor=donor, status=Donation.Status.FAILED)

        campaign_service.add_campaign_update(self.campaign, self.owner, 'Progress!', 'Update body.')

        self.assertFalse(Notification.objects.filter(user=donor).exists())

    def test_does_not_notify_anonymous_guest_donations(self):
        self.make_donation(donor=None, donor_name='Guest')
        campaign_service.add_campaign_update(self.campaign, self.owner, 'Progress!', 'Update body.')
        self.assertEqual(Notification.objects.count(), 0)


class CampaignReportTest(APITestCase):
    def setUp(self):
        self.campaign = make_campaign()

    def test_logged_in_user_report_dedupes_on_resubmit(self):
        reporter = User.objects.create_user(email='reporter@example.com', password='pass')
        first = campaign_service.create_campaign_report(self.campaign, reporter, 'spam', 'Looks fake')
        second = campaign_service.create_campaign_report(self.campaign, reporter, 'fraudulent', 'Actually fraud')

        self.assertEqual(first.id, second.id)
        self.assertEqual(CampaignReport.objects.filter(campaign=self.campaign, reported_by=reporter).count(), 1)
        second.refresh_from_db()
        self.assertEqual(second.reason, 'fraudulent')

    def test_anonymous_reports_each_create_a_new_row(self):
        campaign_service.create_campaign_report(self.campaign, None, 'spam', 'desc', reporter_name='Guest A')
        campaign_service.create_campaign_report(self.campaign, None, 'spam', 'desc', reporter_name='Guest B')
        self.assertEqual(CampaignReport.objects.filter(campaign=self.campaign).count(), 2)

    def test_different_users_reporting_the_same_campaign_both_persist(self):
        reporter1 = User.objects.create_user(email='r1@example.com', password='pass')
        reporter2 = User.objects.create_user(email='r2@example.com', password='pass')
        campaign_service.create_campaign_report(self.campaign, reporter1, 'spam', 'desc')
        campaign_service.create_campaign_report(self.campaign, reporter2, 'spam', 'desc')
        self.assertEqual(CampaignReport.objects.filter(campaign=self.campaign).count(), 2)


class AdminActionTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email='mod@example.com', password='pass', role='admin')
        self.campaign = make_campaign(status=Campaign.Status.PENDING)

    def test_approve_activates_and_notifies_owner(self):
        result = campaign_service.admin_action(self.campaign.id, 'approve', '', self.admin)
        self.assertEqual(result.status, Campaign.Status.ACTIVE)
        self.assertIsNotNone(result.approved_at)
        self.assertTrue(Notification.objects.filter(
            user=self.campaign.owner, notification_type=Notification.Type.CAMPAIGN_APPROVED,
        ).exists())

    def test_approve_clears_a_previous_rejection_reason(self):
        self.campaign.rejection_reason = 'Previously rejected for X'
        self.campaign.save(update_fields=['rejection_reason'])
        result = campaign_service.admin_action(self.campaign.id, 'approve', '', self.admin)
        self.assertEqual(result.rejection_reason, '')

    def test_reject_stores_reason_and_notifies_owner(self):
        result = campaign_service.admin_action(self.campaign.id, 'reject', 'Incomplete story', self.admin)
        self.assertEqual(result.status, Campaign.Status.REJECTED)
        self.assertEqual(result.rejection_reason, 'Incomplete story')
        self.assertTrue(Notification.objects.filter(
            user=self.campaign.owner, notification_type=Notification.Type.CAMPAIGN_REJECTED,
        ).exists())

    def test_suspend_sets_status_without_notification(self):
        active = make_campaign(status=Campaign.Status.ACTIVE)
        result = campaign_service.admin_action(active.id, 'suspend', '', self.admin)
        self.assertEqual(result.status, Campaign.Status.SUSPENDED)

    def test_unknown_action_raises(self):
        with self.assertRaises(ValueError):
            campaign_service.admin_action(self.campaign.id, 'nonsense', '', self.admin)


class ChangeCampaignStatusTest(APITestCase):
    def setUp(self):
        self.campaign = make_campaign(status=Campaign.Status.PENDING)

    def test_setting_active_stamps_approved_at_and_emails_owner(self):
        mail.outbox = []
        result = campaign_service.change_campaign_status(self.campaign.id, Campaign.Status.ACTIVE)
        self.assertEqual(result.status, Campaign.Status.ACTIVE)
        self.assertIsNotNone(result.approved_at)
        self.assertTrue(Notification.objects.filter(user=self.campaign.owner).exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.campaign.owner.email, mail.outbox[0].to)

    def test_setting_rejected_stores_reason(self):
        result = campaign_service.change_campaign_status(self.campaign.id, Campaign.Status.REJECTED, reason='Not eligible')
        self.assertEqual(result.rejection_reason, 'Not eligible')


class PublicCampaignQueryTest(APITestCase):
    def setUp(self):
        self.category = make_category(name='Water')

    def test_filters_by_category_region_and_urgency(self):
        match = make_campaign(category=self.category, region=Campaign.Region.BANJUL, is_urgent=True)
        make_campaign(category=make_category(), region=Campaign.Region.BANJUL)
        make_campaign(category=self.category, region=Campaign.Region.KANIFING)

        results = campaign_service.get_public_campaigns({
            'category': self.category.slug, 'region': Campaign.Region.BANJUL, 'urgent': True,
        })
        self.assertEqual(list(results), [match])

    def test_anonymous_campaign_is_excluded_from_owner_filter(self):
        # The whole point of a campaign's is_anonymous flag is that it must
        # never be reachable via its owner's public profile -- confirms
        # get_public_campaigns() actually enforces that, not just the
        # frontend choosing not to show it.
        owner = User.objects.create_user(email='anon-owner@example.com', password='pass')
        anon_campaign = make_campaign(owner=owner, is_anonymous=True)
        visible_campaign = make_campaign(owner=owner, is_anonymous=False)

        results = list(campaign_service.get_public_campaigns({'owner': str(owner.id)}))
        self.assertNotIn(anon_campaign, results)
        self.assertIn(visible_campaign, results)

    def test_only_active_and_approved_statuses_are_public(self):
        make_campaign(status=Campaign.Status.DRAFT)
        make_campaign(status=Campaign.Status.PENDING)
        make_campaign(status=Campaign.Status.REJECTED)
        visible = make_campaign(status=Campaign.Status.ACTIVE)

        results = list(campaign_service.get_public_campaigns())
        self.assertEqual(results, [visible])


class FeaturedCampaignsTest(APITestCase):
    def test_prefers_featured_then_urgent_then_anything_else_capped_at_four(self):
        featured = [make_campaign(is_featured=True) for _ in range(2)]
        urgent = [make_campaign(is_urgent=True) for _ in range(1)]
        filler = [make_campaign() for _ in range(3)]

        results = campaign_service.get_featured_campaigns()

        self.assertEqual(len(results), 4)
        for c in featured:
            self.assertIn(c, results)
        for c in urgent:
            self.assertIn(c, results)
        # No duplicates even though a campaign could in principle satisfy
        # more than one tier.
        self.assertEqual(len({c.pk for c in results}), 4)


class CampaignStatsTest(APITestCase):
    def test_get_campaign_stats_counts_by_status(self):
        make_campaign(status=Campaign.Status.ACTIVE)
        make_campaign(status=Campaign.Status.ACTIVE)
        make_campaign(status=Campaign.Status.PENDING)
        make_campaign(status=Campaign.Status.COMPLETED)

        stats = campaign_service.get_campaign_stats()
        self.assertEqual(stats['total_campaigns'], 4)
        self.assertEqual(stats['active_campaigns'], 2)
        self.assertEqual(stats['pending_campaigns'], 1)
        self.assertEqual(stats['completed_campaigns'], 1)

    def test_get_campaign_report_stats_counts_by_status(self):
        campaign = make_campaign()
        CampaignReport.objects.create(campaign=campaign, reason='spam', description='d', status=CampaignReport.Status.PENDING)
        CampaignReport.objects.create(campaign=campaign, reason='spam', description='d', status=CampaignReport.Status.RESOLVED)
        CampaignReport.objects.create(campaign=campaign, reason='spam', description='d', status=CampaignReport.Status.RESOLVED)

        stats = campaign_service.get_campaign_report_stats()
        self.assertEqual(stats['total_reports'], 3)
        self.assertEqual(stats['pending_reports'], 1)
        self.assertEqual(stats['resolved_reports'], 2)


class PublicPlatformStatsTest(APITestCase):
    """Regression test for a real bug this test file's setup uncovered:
    known_donors used .values('donor').distinct().count(), which silently
    inflates the count for any donor with more than one paid donation (see
    the fix in get_public_platform_stats -- same root cause as
    _notify_donors_of_update's double-notification bug)."""

    def test_a_repeat_donor_is_only_counted_once(self):
        campaign = make_campaign(status=Campaign.Status.ACTIVE)
        donor = User.objects.create_user(email='repeat-donor@example.com', password='pass')
        for _ in range(3):
            Donation.objects.create(
                campaign=campaign, donor=donor, amount=Decimal('50.00'), provider='wave',
                phone='+2207000000', gateway='modempay', status=Donation.Status.PAID,
            )
        # One guest (no donor account) donation too, counted separately.
        Donation.objects.create(
            campaign=campaign, donor=None, donor_name='Guest', amount=Decimal('20.00'),
            provider='wave', phone='+2207000001', gateway='modempay', status=Donation.Status.PAID,
        )

        stats = campaign_service.get_public_platform_stats()
        self.assertEqual(stats['donors_count'], 2)  # 1 known donor + 1 guest donation

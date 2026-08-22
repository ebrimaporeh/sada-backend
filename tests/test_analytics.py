from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.users.models import User
from apps.campaigns.models import Campaign
from apps.donations.models import Donation
import services.analytics_service as analytics_service


def make_campaign(**kwargs):
    owner = kwargs.pop('owner', None) or User.objects.create_user(
        email=f'owner{User.objects.count()}@example.com', password='pass',
    )
    defaults = {
        'owner': owner,
        'title': 'Well for Bakau',
        'short_description': 'Clean water',
        'story': 'A well for the community.',
        'goal': Decimal('10000.00'),
        'status': Campaign.Status.ACTIVE,
    }
    defaults.update(kwargs)
    return Campaign.objects.create(**defaults)


def make_donation_on(campaign, amount, days_ago, reference):
    donation = Donation.objects.create(
        campaign=campaign, amount=Decimal(str(amount)), provider='wave', phone='+2207000000',
        payment_reference=reference, gateway='modempay', status=Donation.Status.PAID,
    )
    Donation.objects.filter(pk=donation.pk).update(
        created_at=timezone.now() - timedelta(days=days_ago),
    )
    return donation


class DonationsByDayTrendTest(APITestCase):
    """get_donations_by_day() / _bucketed_daily_trend() -- backs the
    Dashboard's "Donations Over Time" and Finance's "Donations Trend"
    charts. Every day in range gets a point (zero-filled if no donation),
    but the number of points is capped so a wide range doesn't render as an
    unreadable wall of daily ticks."""

    def setUp(self):
        self.campaign = make_campaign()

    def test_short_range_gets_one_point_per_day_with_zero_fill(self):
        make_donation_on(self.campaign, '100.00', days_ago=0, reference='SD-TREND1')
        start = (timezone.now().date() - timedelta(days=7)).isoformat()
        end = timezone.now().date().isoformat()

        result = analytics_service.get_donations_by_day(start, end)

        self.assertEqual(len(result), 8)  # inclusive of both endpoints
        self.assertEqual(sum(1 for r in result if r['amount'] == 0.0), 7)
        self.assertEqual(sum(r['amount'] for r in result), 100.0)

    def test_wide_range_is_capped_at_max_trend_points(self):
        make_donation_on(self.campaign, '50.00', days_ago=10, reference='SD-TREND2')
        start = (timezone.now().date() - timedelta(days=89)).isoformat()
        end = timezone.now().date().isoformat()

        result = analytics_service.get_donations_by_day(start, end)

        self.assertLessEqual(len(result), analytics_service.MAX_TREND_POINTS)
        # Nothing gets dropped just because it's bucketed -- the donation's
        # amount still shows up somewhere in the trend.
        self.assertEqual(sum(r['amount'] for r in result), 50.0)

    def test_bucket_sums_every_donation_that_falls_within_it(self):
        # 20-day range with MAX_TREND_POINTS=15 buckets 2 days at a time,
        # so days 0 and 1 (days_ago 19 and 18 from a 19-day-ago start) land
        # in the same first bucket.
        make_donation_on(self.campaign, '50.00', days_ago=19, reference='SD-TREND3')
        make_donation_on(self.campaign, '30.00', days_ago=18, reference='SD-TREND4')
        start = (timezone.now().date() - timedelta(days=19)).isoformat()
        end = timezone.now().date().isoformat()

        result = analytics_service.get_donations_by_day(start, end)

        self.assertEqual(result[0]['amount'], 80.0)
        self.assertEqual(result[0]['count'], 2)

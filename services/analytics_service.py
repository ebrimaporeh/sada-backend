from datetime import datetime, timedelta, date
from decimal import Decimal
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import TruncDate
from django.utils import timezone
from apps.donations.models import Donation
from apps.campaigns.models import Campaign
from apps.payments.models import Payout


def parse_date(date_str):
    """Parse date string (YYYY-MM-DD) to datetime"""
    if not date_str:
        return None
    return datetime.strptime(date_str, '%Y-%m-%d').date()


def get_date_range(start_date_str=None, end_date_str=None):
    """Get date range, handling None values"""
    end_date = parse_date(end_date_str) if end_date_str else timezone.now().date()

    if start_date_str:
        start_date = parse_date(start_date_str)
    else:
        # Default to last 7 days
        start_date = end_date - timedelta(days=7)

    return start_date, end_date


def get_dashboard_stats(start_date_str=None, end_date_str=None):
    """Get all dashboard stats for a date range"""
    start_date, end_date = get_date_range(start_date_str, end_date_str)

    # Date filters
    date_filter = Q(created_at__date__gte=start_date, created_at__date__lte=end_date)

    # Get donations stats
    donations = Donation.objects.filter(date_filter)
    donations_count = donations.count()
    total_raised = donations.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    # Get campaigns stats
    campaigns = Campaign.objects.filter(date_filter)
    campaigns_count = campaigns.count()

    # Get users count (not date filtered as it's cumulative)
    from apps.users.models import User
    users_count = User.objects.filter(is_active=True).count()

    return {
        'campaigns_count': campaigns_count,
        'total_raised': float(total_raised),
        'users_count': users_count,
        'donations_count': donations_count,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
    }


def get_donations_by_day(start_date_str=None, end_date_str=None):
    """Get donations aggregated by day for chart"""
    start_date, end_date = get_date_range(start_date_str, end_date_str)

    donations = Donation.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).annotate(
        date=TruncDate('created_at')
    ).values('date').annotate(
        amount=Sum('amount'),
        count=Count('id')
    ).order_by('date')

    return [
        {
            'date': d['date'].strftime('%b %d') if d['date'] else 'Unknown',
            'amount': float(d['amount'] or 0),
            'count': d['count'],
        }
        for d in donations
    ]


def get_campaign_status_distribution(start_date_str=None, end_date_str=None):
    """Get campaign distribution by status"""
    start_date, end_date = get_date_range(start_date_str, end_date_str)

    campaigns = Campaign.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).values('status').annotate(
        count=Count('id')
    ).order_by('status')

    return [
        {
            'status': c['status'],
            'count': c['count'],
        }
        for c in campaigns
    ]


def get_top_campaigns(start_date_str=None, end_date_str=None, limit=5):
    """Get top campaigns by amount raised"""
    start_date, end_date = get_date_range(start_date_str, end_date_str)

    campaigns = Campaign.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).order_by('-raised')[:limit]

    return [
        {
            'id': str(c.id),
            'title': c.title,
            'category': c.category.name if c.category else 'N/A',
            'raised': float(c.raised or 0),
            'goal': float(c.goal or 0),
            'percentage': int((c.raised / c.goal * 100) if c.goal else 0),
            'status': c.status,
        }
        for c in campaigns
    ]


def get_top_donors(start_date_str=None, end_date_str=None, limit=5):
    """Get top donors by total amount"""
    start_date, end_date = get_date_range(start_date_str, end_date_str)

    donors = Donation.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).values('donor_name').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')[:limit]

    return [
        {
            'donor': d['donor_name'] or 'Anonymous',
            'amount': float(d['total'] or 0),
            'count': d['count'],
        }
        for d in donors
    ]


FINANCE_PERIODS = ('week', 'month', 'year', 'custom')


def get_finance_period_range(period=None, start_date_str=None, end_date_str=None):
    """Resolve a named period (week/month/year/custom) to a concrete date range"""
    if period not in FINANCE_PERIODS:
        period = 'week'

    end_date = timezone.now().date()

    if period == 'month':
        start_date = end_date - timedelta(days=30)
    elif period == 'year':
        start_date = end_date - timedelta(days=365)
    elif period == 'custom':
        start_date, end_date = get_date_range(start_date_str, end_date_str)
    else:
        period = 'week'
        start_date = end_date - timedelta(days=7)

    return period, start_date, end_date


def get_finance_summary(period=None, start_date_str=None, end_date_str=None, top_campaigns_limit=10):
    """Aggregate all figures needed by the admin Finances page for a given period.

    All amounts/counts/rates are computed here so the frontend only renders
    the response, it never sums or derives rates from raw model data.
    """
    period, start_date, end_date = get_finance_period_range(period, start_date_str, end_date_str)
    date_filter = Q(created_at__date__gte=start_date, created_at__date__lte=end_date)

    donations_qs = Donation.objects.filter(date_filter)
    paid_donations = donations_qs.filter(status=Donation.Status.PAID)

    donations_total = paid_donations.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    donations_count = paid_donations.count()
    average_donation = (donations_total / donations_count) if donations_count else Decimal('0')

    payouts_qs = Payout.objects.filter(date_filter)
    completed_payouts = payouts_qs.filter(status=Payout.Status.COMPLETED)
    pending_payouts = payouts_qs.filter(status__in=[Payout.Status.PENDING, Payout.Status.PROCESSING])
    completed_payouts_amount = completed_payouts.aggregate(total=Sum('net_amount'))['total'] or Decimal('0')
    pending_payouts_amount = pending_payouts.aggregate(total=Sum('net_amount'))['total'] or Decimal('0')

    status_counts = {row['status']: row['count'] for row in donations_qs.values('status').annotate(count=Count('id'))}
    total_transactions = donations_qs.count()
    paid_count = status_counts.get(Donation.Status.PAID, 0)
    success_rate = round((paid_count / total_transactions * 100), 1) if total_transactions else 0.0

    donations_trend = (
        paid_donations
        .annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(amount=Sum('amount'), count=Count('id'))
        .order_by('date')
    )

    provider_breakdown = (
        paid_donations
        .values('provider')
        .annotate(amount=Sum('amount'), count=Count('id'))
        .order_by('-amount')
    )

    top_campaigns = Campaign.objects.filter(date_filter).order_by('-raised')[:top_campaigns_limit]

    return {
        'period': period,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'donations': {
            'total_amount': float(donations_total),
            'count': donations_count,
            'average_amount': float(average_donation),
        },
        'payouts': {
            'completed_amount': float(completed_payouts_amount),
            'completed_count': completed_payouts.count(),
            'pending_amount': float(pending_payouts_amount),
            'pending_count': pending_payouts.count(),
        },
        'transactions': {
            'paid': paid_count,
            'failed': status_counts.get(Donation.Status.FAILED, 0),
            'pending': status_counts.get(Donation.Status.PENDING, 0),
            'refunded': status_counts.get(Donation.Status.REFUNDED, 0),
            'total': total_transactions,
            'success_rate': success_rate,
        },
        'donations_trend': [
            {
                'date': row['date'].strftime('%b %d') if row['date'] else 'Unknown',
                'amount': float(row['amount'] or 0),
                'count': row['count'],
            }
            for row in donations_trend
        ],
        'provider_breakdown': [
            {
                'provider': row['provider'],
                'amount': float(row['amount'] or 0),
                'count': row['count'],
            }
            for row in provider_breakdown
        ],
        'top_campaigns': [
            {
                'id': str(c.id),
                'title': c.title,
                'raised': float(c.raised or 0),
                'goal': float(c.goal or 0),
                'percentage': int((c.raised / c.goal * 100) if c.goal else 0),
                'status': c.status,
            }
            for c in top_campaigns
        ],
    }


def get_recent_donations(start_date_str=None, end_date_str=None, limit=10):
    """Get recent donations"""
    start_date, end_date = get_date_range(start_date_str, end_date_str)

    donations = Donation.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    ).select_related('campaign').order_by('-created_at')[:limit]

    return [
        {
            'id': str(d.id),
            'donor_name': d.donor_name or 'Anonymous',
            'campaign_title': d.campaign.title if d.campaign else 'Unknown',
            'amount': float(d.amount),
            'created_at': d.created_at.isoformat(),
        }
        for d in donations
    ]

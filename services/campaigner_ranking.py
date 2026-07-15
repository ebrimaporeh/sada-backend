"""Ranks public campaigner profiles by how active their campaigns
currently are, so the directory surfaces people with campaigns
currently gaining momentum first rather than just whoever raised the
most all-time.

"Active" is measured as donation frequency: how many completed
donations have landed on the campaigner's public campaigns within the
last ACTIVITY_WINDOW_DAYS days. A campaigner whose campaign is
receiving frequent recent donations ranks above one who raised a lot
once, long ago, and has since gone quiet.
"""
from datetime import timedelta

from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

ACTIVITY_WINDOW_DAYS = 30


def annotate_activity(queryset, public_campaign_statuses):
    """Adds `recent_donation_count` to `queryset` (a User queryset) — the
    number of paid donations across the user's public campaigns within
    the last ACTIVITY_WINDOW_DAYS days.

    Uses a correlated subquery rather than a second `Count` in the same
    `.annotate()` call as `campaign_count`/`total_raised`: those already
    join through `campaigns`, and joining through `campaigns__donations`
    too in the same query would fan out and inflate every aggregate.
    """
    from apps.donations.models import Donation

    since = timezone.now() - timedelta(days=ACTIVITY_WINDOW_DAYS)
    recent_donation_counts = (
        Donation.objects
        .filter(
            campaign__owner_id=OuterRef('pk'),
            campaign__status__in=public_campaign_statuses,
            campaign__is_anonymous=False,
            status=Donation.Status.PAID,
            created_at__gte=since,
        )
        .order_by()
        .values('campaign__owner_id')
        .annotate(count=Count('id'))
        .values('count')
    )
    return queryset.annotate(
        recent_donation_count=Coalesce(
            Subquery(recent_donation_counts, output_field=IntegerField()), 0,
        ),
    )


def order_by_activity(queryset):
    """Most active campaigners first. Ties broken by total public campaign
    count, then lifetime raised, then newest — same stable tiebreakers the
    directory used before activity ranking existed."""
    return queryset.order_by('-recent_donation_count', '-campaign_count', '-total_raised', '-created_at')

import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404
from django.http import Http404
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)


def success_response(data, message='Success.', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'message': message, 'data': data}, status=status_code)


def error_response(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': message, 'errors': errors or {}}, status=status_code)


def create_donation(donor, validated_data):
    """Create a PENDING donation and start a payment intent for it with
    whichever gateway validated_data['gateway'] names (modempay by default).

    Returns (donation, payment_link). payment_link is the gateway's hosted
    checkout URL the frontend must redirect the donor to — None if the
    intent could not be created (donation is left FAILED in that case).

    The campaign row lock only covers the deadline/status check + donation
    creation; it's released before the gateway's HTTP call so one donor's
    request to a provider can't block every other donor to the same campaign.
    Confirmation (and the actual Campaign.raised/donors_count increment)
    happens later, asynchronously, via the webhook -> _confirm_donation.
    """
    from apps.donations.models import Donation
    from apps.campaigns.models import Campaign
    from services.gateways.registry import get_gateway

    campaign_id = validated_data.pop('campaign_id')
    # Raises ValidationError here (before any lock/DB write) for an unknown
    # or disabled gateway, rather than creating an orphaned PENDING donation
    # that _initiate_payment would only discover was unpayable afterward.
    gateway = get_gateway(validated_data.get('gateway') or 'modempay')

    with transaction.atomic():
        # Lock the row so concurrent donations can't both pass the goal check
        campaign = Campaign.objects.select_for_update().filter(
            pk=campaign_id,
            status__in=[Campaign.Status.ACTIVE, Campaign.Status.APPROVED],
        ).first()

        if campaign is None:
            raise Http404('Campaign not found or not accepting donations.')

        # Deadline check
        if campaign.deadline and campaign.deadline < timezone.now().date():
            raise ValidationError('This campaign has ended and is no longer accepting donations.')

        # Campaigns can be overfunded — reaching (or passing) the goal doesn't
        # close donations, it just pushes progress past 100%. Only an active
        # deadline/status gates whether a campaign can still receive funds.

        # No platform fee on donations — donors only pay whatever ModemPay
        # itself charges them directly; the full amount is credited to the
        # campaign. (The platform fee is taken on payout, not donation.)
        amount = Decimal(str(validated_data['amount']))

        donation = Donation.objects.create(
            campaign=campaign,
            donor=donor,
            fee=Decimal('0'),
            # Server-resolved, not client-controlled — Stripe doesn't settle
            # in GMD at all, so its donations are charged in whatever
            # PlatformSettings.stripe_settlement_currency an admin has set.
            currency=gateway.default_currency,
            payment_reference=f'SD-{uuid.uuid4().hex[:12].upper()}',
            **validated_data,
        )

    payment_link = _initiate_payment(donation)
    return donation, payment_link


def _initiate_payment(donation):
    """Create the payment intent for a donation via its gateway. Returns the
    hosted payment_link, or None (and marks the donation FAILED) if it
    couldn't be created."""
    from django.conf import settings
    from services.gateways.registry import get_gateway

    frontend_url = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
    slug = donation.campaign.slug
    return_url = f'{frontend_url}/donate/{slug}/success?ref={donation.payment_reference}&amount={donation.amount}'
    cancel_url = f'{frontend_url}/donate/{slug}'

    gateway = get_gateway(donation.gateway)
    intent = gateway.create_payment_intent(donation, return_url=return_url, cancel_url=cancel_url)

    if intent is None:
        donation.status = donation.Status.FAILED
        donation.save(update_fields=['status'])
        return None

    donation.provider_reference = intent.provider_reference
    donation.save(update_fields=['provider_reference'])
    return intent.payment_link


@transaction.atomic
def _confirm_donation(donation):
    from apps.campaigns.models import Campaign
    from apps.notifications.models import Notification
    from emails.tasks import send_donation_received_email_task

    donation.status = donation.Status.PAID
    donation.paid_at = timezone.now()
    donation.save(update_fields=['status', 'paid_at'])

    Campaign.objects.filter(pk=donation.campaign_id).update(
        raised=F('raised') + donation.net_amount,
        donors_count=F('donors_count') + 1,
    )
    donation.campaign.refresh_from_db()

    Notification.objects.create(
        user=donation.campaign.owner,
        notification_type=Notification.Type.DONATION_RECEIVED,
        title='New Donation!',
        message=f'{donation.donor_display} donated D{donation.amount} to "{donation.campaign.title}".',
        link=f'/my-campaigns/{donation.campaign.slug}',
    )

    # Deferred to on_commit — enqueueing before the transaction lands would
    # let a worker pick this up and query a donation row that isn't there yet
    # (or worse, email out a confirmation for a donation that later rolled back).
    transaction.on_commit(lambda: send_donation_received_email_task.delay(str(donation.id)))

    if donation.campaign.is_funded:
        Notification.objects.create(
            user=donation.campaign.owner,
            notification_type=Notification.Type.GOAL_REACHED,
            title='Goal Reached!',
            message=f'Your campaign "{donation.campaign.title}" has reached its goal!',
            link=f'/my-campaigns/{donation.campaign.slug}',
        )

    return donation


@transaction.atomic
def admin_update_donation(donation, validated_data):
    """Apply an admin edit to a donation, keeping Campaign.raised/donors_count in sync.

    A plain serializer.save() here would let amount/status changes silently
    desync the campaign's ledger from what was actually paid — this recomputes
    the campaign delta the same way _confirm_donation() does.
    """
    from apps.campaigns.models import Campaign

    old_status = donation.status
    old_net = donation.net_amount if old_status == donation.Status.PAID else Decimal('0')

    for field, value in validated_data.items():
        setattr(donation, field, value)

    new_status = donation.status
    new_net = donation.net_amount if new_status == donation.Status.PAID else Decimal('0')

    campaign = Campaign.objects.select_for_update().get(pk=donation.campaign_id)

    delta_raised = new_net - old_net
    delta_donors = 0
    if old_status != donation.Status.PAID and new_status == donation.Status.PAID:
        delta_donors = 1
        if not donation.paid_at:
            donation.paid_at = timezone.now()
    elif old_status == donation.Status.PAID and new_status != donation.Status.PAID:
        delta_donors = -1

    if delta_raised != 0 or delta_donors != 0:
        Campaign.objects.filter(pk=campaign.pk).update(
            raised=F('raised') + delta_raised,
            donors_count=F('donors_count') + delta_donors,
        )

    donation.save()
    donation.refresh_from_db()
    return donation


@transaction.atomic
def refund_donation(donation, reason=''):
    """Refund a PAID donation via its own gateway and unwind its
    contribution to the campaign's totals — the reverse of _confirm_donation().

    Re-fetches the donation with a row lock so two concurrent refund
    attempts on the same donation can't both pass the PAID check before
    either commits. Raises ValidationError if the donation isn't PAID or
    the gateway declines the refund (real money reversing — surfaced to the
    admin, not silently swallowed).
    """
    from apps.campaigns.models import Campaign
    from apps.notifications.models import Notification
    from services.gateways.registry import get_gateway
    from emails.tasks import send_donation_refunded_email_task

    donation = donation.__class__.objects.select_for_update().get(pk=donation.pk)
    if donation.status != donation.Status.PAID:
        raise ValidationError(f'Only paid donations can be refunded (current status: {donation.status}).')

    gateway = get_gateway(donation.gateway)
    result = gateway.refund_donation(donation)
    if result is None:
        raise ValidationError('Refund could not be processed by the payment provider. Please try again shortly.')

    Campaign.objects.filter(pk=donation.campaign_id).update(
        raised=F('raised') - donation.net_amount,
        donors_count=F('donors_count') - 1,
    )

    donation.status = donation.Status.REFUNDED
    donation.refunded_at = timezone.now()
    donation.refund_reason = reason
    donation.save(update_fields=['status', 'refunded_at', 'refund_reason'])
    donation.campaign.refresh_from_db()

    Notification.objects.create(
        user=donation.campaign.owner,
        notification_type=Notification.Type.DONATION_REFUNDED,
        title='Donation Refunded',
        message=f'A donation of D{donation.amount} to "{donation.campaign.title}" was refunded. '
                f'Your campaign total has been adjusted.',
        link=f'/my-campaigns/{donation.campaign.slug}',
    )

    if donation.donor:
        Notification.objects.create(
            user=donation.donor,
            notification_type=Notification.Type.DONATION_REFUNDED,
            title='Donation Refunded',
            message=f'Your donation of D{donation.amount} to "{donation.campaign.title}" has been refunded.',
            link=f'/campaigns/{donation.campaign.slug}',
        )
        transaction.on_commit(lambda: send_donation_refunded_email_task.delay(str(donation.id)))

    return donation


def confirm_donation_by_reference(reference, provider_reference=''):
    from apps.donations.models import Donation
    try:
        donation = Donation.objects.get(payment_reference=reference, status=Donation.Status.PENDING)
    except Donation.DoesNotExist:
        return None
    donation.provider_reference = provider_reference
    donation.save(update_fields=['provider_reference'])
    return _confirm_donation(donation)


def fail_donation_by_reference(reference):
    """Mark a still-pending donation as failed/cancelled from a webhook event.
    No campaign totals to unwind — a PENDING donation was never credited."""
    from apps.donations.models import Donation
    updated = Donation.objects.filter(
        payment_reference=reference, status=Donation.Status.PENDING
    ).update(status=Donation.Status.FAILED)
    return updated > 0


def reconcile_donation_by_reference(reference):
    """Check the donation's own gateway directly for its real status and
    confirm/fail it if needed.

    The webhook is the primary confirmation path, but it can't reach a
    localhost backend at all in dev, and could in principle be missed/delayed
    even in production — this is the fallback. Safe to call repeatedly: a
    no-op once the donation is no longer PENDING. Returns the (possibly
    updated) donation, or None if the reference doesn't exist.
    """
    from apps.donations.models import Donation
    from services.gateways.registry import get_gateway

    try:
        donation = Donation.objects.get(payment_reference=reference)
    except Donation.DoesNotExist:
        return None

    if donation.status != Donation.Status.PENDING or not donation.provider_reference:
        return donation

    gateway = get_gateway(donation.gateway)
    intent = gateway.retrieve_payment_intent(donation.provider_reference)
    if not intent:
        return donation

    resolved = gateway.intent_status(intent)
    if resolved == 'successful':
        real_reference = gateway.resolve_confirmed_reference(reference, intent.get('id', ''))
        return confirm_donation_by_reference(reference, real_reference)
    if resolved == 'failed':
        fail_donation_by_reference(reference)
        donation.refresh_from_db()

    return donation


def sweep_pending_donations(older_than_minutes=15, limit=50):
    """Reconcile PENDING donations old enough that their webhook should have
    already arrived. Runs on a periodic schedule (see apps/donations/tasks.py)
    as the safety net for missed/delayed webhooks — the same fallback
    reconcile_donation_by_reference() provides on-demand, just self-triggered
    instead of waiting for a donor to check their status.

    `limit` caps how many donations one sweep run touches, so a large backlog
    is worked off over several runs rather than one run making `limit`
    synchronous gateway calls back-to-back.
    """
    from apps.donations.models import Donation

    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    references = list(
        Donation.objects.filter(
            status=Donation.Status.PENDING,
            created_at__lt=cutoff,
        ).order_by('created_at').values_list('payment_reference', flat=True)[:limit]
    )

    resolved = 0
    for reference in references:
        donation = reconcile_donation_by_reference(reference)
        if donation and donation.status != Donation.Status.PENDING:
            resolved += 1

    if references:
        logger.info(
            'sweep_pending_donations: checked %d, resolved %d, still pending %d',
            len(references), resolved, len(references) - resolved,
        )
    return {'checked': len(references), 'resolved': resolved}


def get_user_donations(user):
    from apps.donations.models import Donation
    return Donation.objects.filter(donor=user).select_related('campaign').order_by('-created_at')


def get_campaign_donors(user, slug):
    from apps.donations.models import Donation
    from apps.campaigns.models import Campaign
    campaign = get_object_or_404(Campaign, owner=user, slug=slug)
    return Donation.objects.filter(
        campaign=campaign,
        status=Donation.Status.PAID,
    ).select_related('donor').order_by('-paid_at')


def get_public_campaign_donors(slug):
    """Donor list for the public campaign page — any visible campaign, not owner-scoped."""
    from apps.donations.models import Donation
    from apps.campaigns.models import Campaign
    campaign = get_object_or_404(
        Campaign,
        slug=slug,
        status__in=[
            Campaign.Status.ACTIVE,
            Campaign.Status.APPROVED,
            Campaign.Status.COMPLETED,
            Campaign.Status.PENDING,
        ],
    )
    return Donation.objects.filter(
        campaign=campaign,
        status=Donation.Status.PAID,
    ).select_related('donor').order_by('-paid_at')


def get_all_donations(params=None):
    from apps.donations.models import Donation
    from django.db.models import Q
    qs = Donation.objects.select_related('campaign', 'donor').order_by('-created_at')
    if params:
        s = params.get('status')
        if s:
            qs = qs.filter(status=s)
        q = params.get('search')
        if q:
            qs = qs.filter(
                Q(payment_reference__icontains=q)
                | Q(campaign__title__icontains=q)
                | Q(donor__email__icontains=q)
                | Q(donor_name__icontains=q)
                | Q(donor__first_name__icontains=q)
                | Q(donor__last_name__icontains=q)
            )
    return qs


def get_donation_stats():
    from apps.donations.models import Donation
    from django.db.models import Sum, Count

    total_donations = Donation.objects.count()
    anonymous_count = Donation.objects.filter(is_anonymous=True).count()
    paid = Donation.objects.filter(status=Donation.Status.PAID).aggregate(
        total=Sum('amount'), count=Count('id'),
    )
    total_raised = paid['total'] or Decimal('0')
    paid_count = paid['count'] or 0
    average_donation = (total_raised / paid_count) if paid_count else Decimal('0')

    return {
        'total_donations': total_donations,
        'total_raised': float(total_raised),
        'average_donation': float(average_donation),
        'anonymous_count': anonymous_count,
    }

import uuid
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404
from django.http import Http404
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError


def success_response(data, message='Success.', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'message': message, 'data': data}, status=status_code)


def error_response(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': message, 'errors': errors or {}}, status=status_code)


def create_donation(donor, validated_data):
    """Create a PENDING donation and start a ModemPay payment intent for it.

    Returns (donation, payment_link). payment_link is the ModemPay-hosted
    checkout URL the frontend must redirect the donor to — None if the intent
    could not be created (donation is left FAILED in that case).

    The campaign row lock only covers the deadline/status check + donation
    creation; it's released before the ModemPay HTTP call so one donor's
    request to a provider can't block every other donor to the same campaign.
    Confirmation (and the actual Campaign.raised/donors_count increment)
    happens later, asynchronously, via the webhook -> _confirm_donation.
    """
    from apps.donations.models import Donation
    from apps.campaigns.models import Campaign

    campaign_id = validated_data.pop('campaign_id')

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
            payment_reference=f'SD-{uuid.uuid4().hex[:12].upper()}',
            **validated_data,
        )

    payment_link = _initiate_payment(donation)
    return donation, payment_link


def _initiate_payment(donation):
    """Create the ModemPay payment intent for a donation. Returns the hosted
    payment_link, or None (and marks the donation FAILED) if it couldn't be created."""
    from django.conf import settings
    from services import modempay_service

    frontend_url = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
    slug = donation.campaign.slug
    return_url = f'{frontend_url}/donate/{slug}/success?ref={donation.payment_reference}&amount={donation.amount}'
    cancel_url = f'{frontend_url}/donate/{slug}'

    result = modempay_service.create_payment_intent(donation, return_url=return_url, cancel_url=cancel_url)

    if not result or not result.get('status'):
        donation.status = donation.Status.FAILED
        donation.save(update_fields=['status'])
        return None

    data = result.get('data', {})
    donation.provider_reference = data.get('intent_secret', '')
    donation.save(update_fields=['provider_reference'])
    return data.get('payment_link')


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
    """Check ModemPay directly for a donation's real status and confirm/fail it if needed.

    The webhook is the primary confirmation path, but it can't reach a
    localhost backend at all in dev, and could in principle be missed/delayed
    even in production — this is the fallback. Safe to call repeatedly: a
    no-op once the donation is no longer PENDING. Returns the (possibly
    updated) donation, or None if the reference doesn't exist.
    """
    from apps.donations.models import Donation
    from services import modempay_service

    try:
        donation = Donation.objects.get(payment_reference=reference)
    except Donation.DoesNotExist:
        return None

    if donation.status != Donation.Status.PENDING or not donation.provider_reference:
        return donation

    intent = modempay_service.retrieve_payment_intent(donation.provider_reference)
    if not intent:
        return donation

    intent_status = intent.get('status')
    if intent_status == 'successful':
        return confirm_donation_by_reference(reference, intent.get('id', ''))
    if intent_status in ('failed', 'cancelled'):
        fail_donation_by_reference(reference)
        donation.refresh_from_db()

    return donation


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

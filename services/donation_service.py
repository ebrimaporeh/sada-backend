import uuid
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.http import Http404
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError


TRANSACTION_FEE_RATE = Decimal('0.015')  # 1.5%


def success_response(data, message='Success.', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'message': message, 'data': data}, status=status_code)


def error_response(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': message, 'errors': errors or {}}, status=status_code)


def create_donation(donor, validated_data):
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

        # Goal check — prevent raised from exceeding goal
        remaining = (campaign.goal - campaign.raised).quantize(Decimal('0.01'))
        if remaining <= 0:
            raise ValidationError('This campaign has already reached its funding goal.')

        amount = Decimal(str(validated_data['amount']))
        fee = (amount * TRANSACTION_FEE_RATE).quantize(Decimal('0.01'))
        net = (amount - fee).quantize(Decimal('0.01'))

        if net > remaining:
            max_gross = (remaining / (1 - TRANSACTION_FEE_RATE)).quantize(Decimal('0.01'))
            raise ValidationError(
                f'Donation of D{amount} would exceed the campaign goal. '
                f'Maximum you can donate is D{max_gross}.'
            )

        donation = Donation.objects.create(
            campaign=campaign,
            donor=donor,
            fee=fee,
            payment_reference=f'SD-{uuid.uuid4().hex[:12].upper()}',
            **validated_data,
        )
        _initiate_payment(donation)
        donation.refresh_from_db()

    return donation


def _initiate_payment(donation):
    """Confirm donation immediately. Replace with real provider call when payment is integrated."""
    _confirm_donation(donation)


@transaction.atomic
def _confirm_donation(donation):
    from apps.campaigns.models import Campaign
    from apps.notifications.models import Notification

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

    if donation.campaign.is_funded:
        Notification.objects.create(
            user=donation.campaign.owner,
            notification_type=Notification.Type.GOAL_REACHED,
            title='Goal Reached!',
            message=f'Your campaign "{donation.campaign.title}" has reached its goal!',
            link=f'/my-campaigns/{donation.campaign.slug}',
        )

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
            )
    return qs

import uuid
import json
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from services import modempay_service


PAYOUT_FEE_RATE = Decimal('0.01')  # 1%


def success_response(data, message='Success.', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'message': message, 'data': data}, status=status_code)


def error_response(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': message, 'errors': errors or {}}, status=status_code)


@transaction.atomic
def request_payout(user, validated_data):
    from apps.campaigns.models import Campaign
    from apps.payments.models import Payout
    from apps.notifications.models import Notification

    campaign_id = validated_data.pop('campaign_id')

    # Lock the campaign row to prevent concurrent over-withdrawals
    campaign = Campaign.objects.select_for_update().filter(
        pk=campaign_id, owner=user
    ).first()
    if campaign is None:
        from django.http import Http404
        raise Http404('Campaign not found.')

    # Sum all active (non-failed, non-cancelled) payouts against this campaign
    active_statuses = [Payout.Status.PENDING, Payout.Status.PROCESSING, Payout.Status.COMPLETED]
    already_requested = campaign.payouts.filter(
        status__in=active_statuses
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    available = (campaign.raised - already_requested).quantize(Decimal('0.01'))
    amount = Decimal(str(validated_data['amount']))

    if available <= 0:
        raise ValidationError('No funds are available for withdrawal.')
    if amount > available:
        raise ValidationError(
            f'Requested amount D{amount} exceeds available balance D{available}.'
        )

    fee = (amount * PAYOUT_FEE_RATE).quantize(Decimal('0.01'))
    net = (amount - fee).quantize(Decimal('0.01'))
    reference = f'PO-{uuid.uuid4().hex[:12].upper()}'

    payout = Payout.objects.create(
        campaign=campaign,
        requested_by=user,
        amount=amount,
        fee=fee,
        net_amount=net,
        reference=reference,
        status=Payout.Status.PROCESSING,
        **validated_data,
    )

    # Trigger disbursement
    result, _ = modempay_service.request_disbursement(
        reference=reference,
        amount=amount,
        phone=validated_data.get('phone', ''),
        provider=validated_data.get('provider', 'modempay'),
    )

    if result:
        payout.provider_reference = result.get('transaction_id', '')
        payout.status = Payout.Status.COMPLETED
        payout.processed_at = timezone.now()
    else:
        payout.status = Payout.Status.PENDING

    payout.save()

    Notification.objects.create(
        user=user,
        notification_type=Notification.Type.PAYOUT_PROCESSED,
        title='Payout Requested',
        message=f'Your payout of D{net} from "{campaign.title}" is being processed.',
        link=f'/my-campaigns/{campaign.slug}',
    )

    return payout


def get_campaign_payouts(user, slug):
    from apps.campaigns.models import Campaign
    from apps.payments.models import Payout
    campaign = get_object_or_404(Campaign, owner=user, slug=slug)
    return Payout.objects.filter(campaign=campaign).order_by('-created_at')


def handle_modempay_webhook(data, headers):
    """Process incoming ModemPay webhook: confirm payment or payout."""
    from apps.donations.models import Donation

    event_type = data.get('event')
    reference = data.get('reference') or data.get('data', {}).get('reference')

    if not reference:
        return False

    if event_type == 'charge.success':
        from services.donation_service import confirm_donation_by_reference
        provider_ref = data.get('data', {}).get('transaction_id', '')
        donation = confirm_donation_by_reference(reference, provider_ref)
        return donation is not None

    if event_type == 'disbursement.success':
        from apps.payments.models import Payout
        try:
            payout = Payout.objects.get(reference=reference)
            payout.status = Payout.Status.COMPLETED
            payout.provider_reference = data.get('data', {}).get('transaction_id', '')
            payout.processed_at = timezone.now()
            payout.save()
            return True
        except Payout.DoesNotExist:
            return False

    return False

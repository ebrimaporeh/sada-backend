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
from services.gateways.registry import get_gateway
from services.gateways.base import GatewayEventType


def success_response(data, message='Success.', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'message': message, 'data': data}, status=status_code)


def error_response(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': message, 'errors': errors or {}}, status=status_code)


def _compute_payout_fees(amount, provider):
    """Shared by request_payout and the fee-preview endpoint, so the preview
    a campaign owner sees always matches what actually gets charged.

    Two distinct fees, deducted in order: SADA's own platform_fee_percent
    first, then ModemPay's real transfer fee (network/amount-dependent,
    queried live) on what's left. Returns (platform_fee, provider_fee,
    pre_provider_net, net) or (None, None, None, None) if the provider fee
    couldn't be determined right now (real money -- don't guess).
    """
    from apps.payments.models import PlatformSettings

    fee_rate = PlatformSettings.get_fee_rate()
    platform_fee = (amount * fee_rate).quantize(Decimal('0.01'))
    pre_provider_net = (amount - platform_fee).quantize(Decimal('0.01'))

    # Payouts are modempay-only for now — Stripe (card donations) has no
    # payout API to a Gambian mobile-money wallet, so there's nothing to
    # select here yet.
    provider_fee = get_gateway('modempay').check_transfer_fee(pre_provider_net, provider)
    if provider_fee is None:
        return None, None, None, None

    net = (pre_provider_net - provider_fee).quantize(Decimal('0.01'))
    return platform_fee, provider_fee, pre_provider_net, net


def preview_payout_fees(amount, provider):
    """For the withdrawal form's live fee preview, before the owner submits."""
    platform_fee, provider_fee, _, net = _compute_payout_fees(amount, provider)
    if platform_fee is None:
        return None
    return {
        'amount': amount,
        'platform_fee': platform_fee,
        'provider_fee': provider_fee,
        'net_amount': net,
    }


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
    amount = Decimal(str(validated_data.pop('amount')))

    if available <= 0:
        raise ValidationError('No funds are available for withdrawal.')
    if amount > available:
        raise ValidationError(
            f'Requested amount D{amount} exceeds available balance D{available}.'
        )

    provider = validated_data.get('provider', 'wave')
    fee, provider_fee, pre_provider_net, net = _compute_payout_fees(amount, provider)
    if fee is None:
        raise ValidationError('Could not verify the payout network fee right now. Please try again shortly.')
    if net <= 0:
        raise ValidationError('Withdrawal amount is too small to cover fees.')

    # Our own ledger (campaign.raised) can show funds as available before
    # ModemPay has actually settled them into the pooled payout_balance
    # wallet real disbursements draw from — check that directly so a
    # shortfall fails cleanly here instead of after creating a Payout row.
    # ModemPay charges its transfer fee ON TOP of the transfer amount, out
    # of this same pooled balance (confirmed against real transfer
    # responses: balance_before - balance_after == amount + fee, the
    # beneficiary receives the full transfer amount) — so what actually
    # leaves payout_balance is net + provider_fee, i.e. pre_provider_net.
    balance = get_gateway('modempay').get_balance()
    if balance is None:
        raise ValidationError('Could not verify payout balance right now. Please try again shortly.')
    payout_balance = Decimal(str(balance.get('payout_balance', 0)))
    if pre_provider_net > payout_balance:
        raise ValidationError(
            'Withdrawal is on hold — funds are still settling with our payment provider. '
            'Please try again shortly or contact support if this persists.'
        )

    reference = f'PO-{uuid.uuid4().hex[:12].upper()}'

    payout = Payout.objects.create(
        campaign=campaign,
        requested_by=user,
        amount=amount,
        fee=fee,
        provider_fee=provider_fee,
        net_amount=net,
        reference=reference,
        status=Payout.Status.PROCESSING,
        **validated_data,
    )

    # Trigger disbursement — this is async in practice; a "completed" result
    # here (or from DEMO_MODE) is a real terminal state, otherwise ModemPay
    # confirms for real later via the transfer.succeeded/failed webhook.
    result = get_gateway('modempay').request_disbursement(
        reference=reference,
        net_amount=net,
        phone=validated_data.get('phone', ''),
        method=validated_data.get('provider', 'wave'),
        beneficiary_name=user.full_name,
    )

    if result is None:
        # request_disbursement() returned None only when no transfer was
        # ever created at ModemPay (rejected outright, or the call errored) —
        # there's no transfer to wait on, so this is a real terminal failure,
        # not something a webhook will ever resolve.
        payout.status = Payout.Status.FAILED
    elif result.get('status') == 'completed':
        payout.provider_reference = result.get('id', '')
        payout.status = Payout.Status.COMPLETED
        payout.processed_at = timezone.now()
    elif result.get('status') in ('failed', 'cancelled'):
        payout.provider_reference = result.get('id', '')
        payout.status = Payout.Status.FAILED
    else:
        # ModemPay accepted the transfer but it's still processing —
        # transfer.succeeded/transfer.failed webhook resolves it for real.
        payout.provider_reference = result.get('id', '')
        payout.status = Payout.Status.PROCESSING

    payout.save()

    Notification.objects.create(
        user=user,
        notification_type=Notification.Type.PAYOUT_PROCESSED,
        title='Payout Requested',
        message=f'Your payout of D{net} from "{campaign.title}" is being processed.',
        link=f'/my-campaigns/{campaign.slug}',
    )

    from emails.tasks import send_payout_update_email_task
    transaction.on_commit(lambda: send_payout_update_email_task.delay(str(payout.id)))

    return payout


def get_campaign_payouts(user, slug):
    from apps.campaigns.models import Campaign
    from apps.payments.models import Payout
    campaign = get_object_or_404(Campaign, owner=user, slug=slug)
    return Payout.objects.filter(campaign=campaign).order_by('-created_at')


def handle_webhook(gateway_code, payload, headers):
    """Verify and process an incoming webhook from any gateway: confirm/fail
    a donation or payout. Gateway-agnostic — dispatches on the normalized
    GatewayEvent each gateway's own verify_webhook() produces, never on that
    gateway's raw event-name vocabulary, so adding a gateway here means
    adding a class in services/gateways/, not a new branch in this function.

    `payload` is the raw parsed request body (dict); `headers` is the
    request's header mapping — this function reads whichever header the
    resolved gateway's signature actually arrives in. Returns True if the
    signature was valid and the event was handled or safely ignored (unknown
    event types are acknowledged, not treated as errors) — False for an
    unknown/disabled gateway code, an invalid signature, or a referenced
    donation/payout we can't find.
    """
    try:
        gateway = get_gateway(gateway_code)
    except ValidationError:
        return False

    signature = headers.get(gateway.signature_header, '') if gateway.signature_header else ''
    event = gateway.verify_webhook(payload, signature)
    if event is None:
        return False

    if event.type == GatewayEventType.DONATION_SUCCEEDED:
        from services.donation_service import confirm_donation_by_reference
        if not event.donation_reference:
            return False
        donation = confirm_donation_by_reference(event.donation_reference, event.provider_reference)
        return donation is not None

    if event.type == GatewayEventType.DONATION_FAILED:
        from services.donation_service import fail_donation_by_reference
        return bool(event.donation_reference) and fail_donation_by_reference(event.donation_reference)

    if event.type == GatewayEventType.PAYOUT_SUCCEEDED:
        from apps.payments.models import Payout
        from emails.tasks import send_payout_update_email_task
        try:
            payout = Payout.objects.get(reference=event.payout_reference)
        except Payout.DoesNotExist:
            return False
        was_already_completed = payout.status == Payout.Status.COMPLETED
        payout.status = Payout.Status.COMPLETED
        payout.provider_reference = event.provider_reference
        payout.processed_at = timezone.now()
        payout.save()
        # Only email on the transition — the initial request already sent one
        # if ModemPay resolved it synchronously; this covers the case where
        # it was left PROCESSING and only resolves later via this webhook.
        if not was_already_completed:
            send_payout_update_email_task.delay(str(payout.id))
        return True

    if event.type == GatewayEventType.PAYOUT_FAILED:
        from apps.payments.models import Payout
        from emails.tasks import send_payout_update_email_task
        try:
            payout = Payout.objects.get(reference=event.payout_reference)
        except Payout.DoesNotExist:
            return False
        was_already_failed = payout.status == Payout.Status.FAILED
        payout.status = Payout.Status.FAILED
        payout.save(update_fields=['status'])
        if not was_already_failed:
            send_payout_update_email_task.delay(str(payout.id))
        return True

    # GatewayEventType.UNHANDLED (customer.*, payment_intent.*, charge.created,
    # ...) — acknowledge receipt, nothing for us to do.
    return True

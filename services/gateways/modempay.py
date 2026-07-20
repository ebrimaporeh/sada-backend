"""ModemPay adapter — a thin wrapper around services/modempay_service.py.

Deliberately delegates every call straight through to the existing
module rather than reimplementing anything: this adapter is a pure
refactor of *how callers reach* modempay_service, not a rewrite of what
it does. ModemPay's own behavior (DEMO_MODE short-circuits, GMD
whole-integer amounts, the +220 phone stripping, ...) is unchanged.
"""
from services import modempay_service
from .base import PaymentGateway, GatewayIntent, GatewayEvent, GatewayEventType


class ModemPayGateway(PaymentGateway):
    code = 'modempay'
    supports_payouts = True
    signature_header = 'x-modem-signature'

    def create_payment_intent(self, donation, return_url='', cancel_url=''):
        result = modempay_service.create_payment_intent(donation, return_url=return_url, cancel_url=cancel_url)
        if not result or not result.get('status'):
            return None
        data = result.get('data', {})
        payment_link = data.get('payment_link')
        if not payment_link:
            return None
        return GatewayIntent(
            payment_link=payment_link,
            provider_reference=data.get('intent_secret', ''),
            raw=result,
        )

    def retrieve_payment_intent(self, provider_reference):
        return modempay_service.retrieve_payment_intent(provider_reference)

    def intent_status(self, intent):
        # Raw values: initialized/processing/requires_payment_method/
        # successful/failed/cancelled.
        raw = (intent or {}).get('status')
        if raw == 'successful':
            return 'successful'
        if raw in ('failed', 'cancelled'):
            return 'failed'
        return 'pending'

    def verify_webhook(self, payload, signature):
        # payload is the raw request body (bytes) — pass it through as a
        # string rather than a re-serialized dict, so the HMAC modempay
        # computes matches the exact bytes it originally signed.
        if isinstance(payload, bytes):
            payload = payload.decode('utf-8')
        event = modempay_service.verify_and_parse_webhook(payload, signature)
        if event is None:
            return None
        return _normalize_event(event)

    @property
    def supported_donation_methods(self):
        # wave/aps are the only two Donation.Provider choices ModemPay's
        # checkout actually offers — card isn't in this set (that's Stripe's).
        return {'wave', 'aps'}

    @property
    def supported_payout_methods(self):
        return modempay_service.SUPPORTED_PAYOUT_NETWORKS

    def get_balance(self):
        return modempay_service.get_balance()

    def check_transfer_fee(self, amount, method, currency='GMD'):
        return modempay_service.check_transfer_fee(amount, method, currency=currency)

    def request_disbursement(self, reference, net_amount, phone, method, beneficiary_name, currency='GMD'):
        return modempay_service.request_disbursement(
            reference=reference,
            net_amount=net_amount,
            phone=phone,
            provider=method,
            beneficiary_name=beneficiary_name,
            currency=currency,
        )

    def retrieve_transfer(self, provider_reference):
        return modempay_service.retrieve_transfer(provider_reference)

    def transfer_status(self, transfer):
        # Transfer.status is Literal['pending', 'completed', 'failed', 'cancelled'].
        raw = (transfer or {}).get('status')
        if raw == 'completed':
            return 'successful'
        if raw in ('failed', 'cancelled'):
            return 'failed'
        return 'pending'


def _normalize_event(event) -> GatewayEvent:
    event_type = event.get('event')
    data = event.get('payload') or {}
    metadata = data.get('metadata') or {}
    provider_ref = data.get('id', '')

    if event_type == 'charge.succeeded':
        return GatewayEvent(
            type=GatewayEventType.DONATION_SUCCEEDED,
            donation_reference=metadata.get('donation_reference', ''),
            provider_reference=provider_ref,
            raw=event,
        )
    if event_type in ('charge.failed', 'charge.cancelled'):
        return GatewayEvent(
            type=GatewayEventType.DONATION_FAILED,
            donation_reference=metadata.get('donation_reference', ''),
            provider_reference=provider_ref,
            raw=event,
        )
    if event_type == 'transfer.succeeded':
        return GatewayEvent(
            type=GatewayEventType.PAYOUT_SUCCEEDED,
            payout_reference=metadata.get('payout_reference', ''),
            provider_reference=provider_ref,
            raw=event,
        )
    if event_type in ('transfer.failed', 'transfer.reversed'):
        return GatewayEvent(
            type=GatewayEventType.PAYOUT_FAILED,
            payout_reference=metadata.get('payout_reference', ''),
            provider_reference=provider_ref,
            raw=event,
        )
    # Unhandled event types (customer.*, payment_intent.*, charge.created, ...)
    # — acknowledge receipt, nothing for us to do.
    return GatewayEvent(type=GatewayEventType.UNHANDLED, raw=event)

"""Stripe adapter — a thin wrapper around services/stripe_service.py.

Named stripe_gateway.py (not stripe.py) so this module never shadows the
real `stripe` SDK package that services/stripe_service.py imports.

Donation-only: supports_payouts stays False (the base class default) since
a card charge has no path to disburse to a Gambian mobile-money wallet —
payouts remain modempay-only, full stop.
"""
from services import stripe_service
from .base import PaymentGateway, GatewayIntent, GatewayEvent, GatewayEventType


class StripeGateway(PaymentGateway):
    code = 'stripe'
    signature_header = 'Stripe-Signature'
    requires_phone = False
    default_method = 'card'

    @property
    def default_currency(self):
        return self.config.get('currency', 'usd')

    def create_payment_intent(self, donation, return_url='', cancel_url=''):
        session = stripe_service.create_checkout_session(
            donation, self.default_currency, success_url=return_url, cancel_url=cancel_url,
        )
        if session is None:
            return None
        checkout_url = session.get('url')
        if not checkout_url:
            return None
        return GatewayIntent(
            payment_link=checkout_url,
            provider_reference=session.get('id', ''),
            raw=session,
        )

    def retrieve_payment_intent(self, provider_reference):
        return stripe_service.retrieve_checkout_session(provider_reference)

    def intent_status(self, intent):
        # Checkout Session has two fields: `status` (open/complete/expired)
        # and `payment_status` (paid/unpaid/no_payment_required) — a session
        # can be 'complete' via a $0 line item without ever being paid, so
        # both matter for "successful".
        if not intent:
            return 'pending'
        if intent.get('payment_status') == 'paid':
            return 'successful'
        if intent.get('status') == 'expired':
            return 'failed'
        return 'pending'

    def verify_webhook(self, payload, signature):
        # Stripe signs the exact raw bytes it sent — never pass a
        # re-parsed/re-serialized version of the body here.
        event = stripe_service.verify_and_parse_webhook(payload, signature)
        if event is None:
            return None
        return _normalize_event(event)


def _normalize_event(event) -> GatewayEvent:
    event_type = event['type']
    data = event['data']['object']
    metadata = data.get('metadata') or {}
    donation_reference = metadata.get('donation_reference', '')
    provider_ref = data.get('id', '')

    if event_type == 'checkout.session.completed' and data.get('payment_status') == 'paid':
        return GatewayEvent(
            type=GatewayEventType.DONATION_SUCCEEDED,
            donation_reference=donation_reference,
            provider_reference=provider_ref,
            raw=event,
        )
    if event_type in ('checkout.session.async_payment_failed', 'checkout.session.expired'):
        return GatewayEvent(
            type=GatewayEventType.DONATION_FAILED,
            donation_reference=donation_reference,
            provider_reference=provider_ref,
            raw=event,
        )
    # Unhandled event types (payment_intent.*, charge.*, customer.*, ...) —
    # acknowledge receipt, nothing for us to do. Stripe never sends a
    # payout-side event here since this gateway never initiates a transfer.
    return GatewayEvent(type=GatewayEventType.UNHANDLED, raw=event)

"""Stripe adapter — a thin wrapper around services/stripe_service.py.

Named stripe_gateway.py (not stripe.py) so this module never shadows the
real `stripe` SDK package that services/stripe_service.py imports.

Donation-only: supports_payouts stays False (the base class default) since
a card charge has no path to disburse to a Gambian mobile-money wallet —
payouts remain modempay-only, full stop.

Confirmed inline via a Stripe Elements card field mounted directly on the
donation page (stripe.confirmCardPayment() client-side), not a redirect to
Stripe's own hosted Checkout page — see create_payment_intent().
"""
from decimal import Decimal
from services import stripe_service
from .base import PaymentGateway, GatewayIntent, GatewayEvent, GatewayEventType


class StripeGateway(PaymentGateway):
    code = 'stripe'
    signature_header = 'Stripe-Signature'
    requires_phone = False
    default_method = 'card'

    def _platform_settings(self):
        from apps.payments.models import PlatformSettings
        return PlatformSettings.get_solo()

    @property
    def default_currency(self):
        # Admin-editable, not env-config — see PlatformSettings docstring.
        return self._platform_settings().stripe_settlement_currency

    @property
    def gmd_to_settlement_rate(self):
        return self._platform_settings().gmd_to_settlement_rate

    @property
    def publishable_key(self):
        return self.config.get('publishable_key', '')

    def convert_gmd_to_minor_units(self, gmd_amount):
        """GMD -> settlement currency -> that currency's smallest unit
        (cents for usd) — using the admin-configured exchange rate, not a
        hardcoded/implicit 1:1 assumption. This is the fix for donations
        being charged as if GMD figures were already the settlement
        currency (D100 silently becoming $100 instead of ~$1.43)."""
        rate = self.gmd_to_settlement_rate
        settlement_amount = Decimal(str(gmd_amount)) / rate
        return int((settlement_amount * Decimal('100')).to_integral_value(rounding='ROUND_HALF_UP'))

    def create_payment_intent(self, donation, return_url='', cancel_url=''):
        amount_minor = self.convert_gmd_to_minor_units(donation.amount)
        intent = stripe_service.create_payment_intent(donation, self.default_currency, amount_minor)
        if intent is None:
            return None
        client_secret = intent.get('client_secret')
        if not client_secret:
            return None
        return GatewayIntent(
            client_secret=client_secret,
            provider_reference=intent.get('id', ''),
            raw=intent,
        )

    def retrieve_payment_intent(self, provider_reference):
        return stripe_service.retrieve_payment_intent(provider_reference)

    def intent_status(self, intent):
        # PaymentIntent's own status vocabulary: requires_payment_method/
        # requires_confirmation/requires_action/processing/succeeded/
        # canceled. 'processing' is genuinely pending (e.g. some bank debits
        # take days) — not a failure — so it falls through to 'pending' too.
        raw = (intent or {}).get('status')
        if raw == 'succeeded':
            return 'successful'
        if raw == 'canceled':
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

    if event_type == 'payment_intent.succeeded':
        return GatewayEvent(
            type=GatewayEventType.DONATION_SUCCEEDED,
            donation_reference=donation_reference,
            provider_reference=provider_ref,
            raw=event,
        )
    if event_type in ('payment_intent.payment_failed', 'payment_intent.canceled'):
        return GatewayEvent(
            type=GatewayEventType.DONATION_FAILED,
            donation_reference=donation_reference,
            provider_reference=provider_ref,
            raw=event,
        )
    # Unhandled event types (payment_method.*, charge.*, customer.*, ...) —
    # acknowledge receipt, nothing for us to do. Stripe never sends a
    # payout-side event here since this gateway never initiates a transfer.
    return GatewayEvent(type=GatewayEventType.UNHANDLED, raw=event)

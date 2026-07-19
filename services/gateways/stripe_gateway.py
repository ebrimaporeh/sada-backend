"""Stripe adapter — a thin wrapper around services/stripe_service.py.

Named stripe_gateway.py (not stripe.py) so this module never shadows the
real `stripe` SDK package that services/stripe_service.py imports.

Donation-only: supports_payouts stays False (the base class default) since
a card charge has no path to disburse to a Gambian mobile-money wallet —
payouts remain modempay-only, full stop.

Uses Stripe's hosted Checkout page (a redirect, same shape as ModemPay's
payment_link) rather than an inline card field — see create_payment_intent().
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
        session = stripe_service.create_checkout_session(
            donation, self.default_currency, amount_minor,
            success_url=return_url, cancel_url=cancel_url,
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

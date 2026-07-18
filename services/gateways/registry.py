"""The single place that knows which PaymentGateway class backs which code.

services/serializers/views ask for a gateway by code via get_gateway() —
none of them import ModemPayGateway/StripeGateway directly. Adding a new
gateway later means writing one class and adding one line to GATEWAYS;
nothing at any call site changes.
"""
from django.conf import settings
from rest_framework.exceptions import ValidationError
from .modempay import ModemPayGateway
from .stripe_gateway import StripeGateway

GATEWAYS = {
    'modempay': ModemPayGateway,
    'stripe': StripeGateway,
}

_instances = {}


def get_gateway(code):
    """Return the configured PaymentGateway instance for `code`.

    Raises ValidationError (not KeyError) for an unknown or disabled code —
    every caller reaches this from request/DB-driven data (a donation's
    stored gateway, a serializer-validated field), so a bad value is a
    client/data problem, not a programming error.
    """
    gateway_cls = GATEWAYS.get(code)
    cfg = settings.PAYMENT_GATEWAYS.get(code)
    if gateway_cls is None or cfg is None or not cfg.get('enabled', False):
        raise ValidationError(f'Payment gateway "{code}" is not available.')

    if code not in _instances:
        _instances[code] = gateway_cls(cfg)
    return _instances[code]


def payout_capable_gateways():
    """Codes of enabled gateways that can disburse payouts. Just modempay
    today — a donation-only gateway (Stripe) never appears here."""
    return [
        code for code, cfg in settings.PAYMENT_GATEWAYS.items()
        if cfg.get('enabled', False) and GATEWAYS.get(code) and GATEWAYS[code].supports_payouts
    ]

import logging
import stripe
from django.conf import settings

logger = logging.getLogger(__name__)


def _secret_key():
    return settings.PAYMENT_GATEWAYS['stripe']['secret_key']


def _as_dict(stripe_object):
    """Stripe's SDK objects (StripeObject/Event/Session) support []
    indexing but NOT dict's .get() — converting once here means every
    caller (stripe_gateway.py, tests) can treat every Stripe response as a
    plain dict, same as modempay_service's responses already are."""
    return stripe_object.to_dict() if hasattr(stripe_object, 'to_dict') else stripe_object


def create_payment_intent(donation, currency, amount_minor):
    """Create a Stripe PaymentIntent for a donation.

    Unlike Checkout Sessions (a hosted, full-page redirect), a PaymentIntent
    is confirmed inline — the frontend mounts a Stripe Elements card field
    directly in the donation page and calls stripe.confirmCardPayment() with
    the client_secret this returns, so the donor never leaves the site.

    `amount_minor` is the already-converted, already-minor-unit amount (e.g.
    cents for usd) — conversion from the donor's GMD amount happens once, in
    services/gateways/stripe_gateway.py, using the admin-configured
    PlatformSettings.gmd_to_settlement_rate, not here, so this function has
    no currency-math opinion of its own to get wrong twice.

    Returns the SDK's PaymentIntent as a plain dict on success (has
    `client_secret`, `id`, `status`), or None on failure — never raises.
    """
    try:
        intent = stripe.PaymentIntent.create(
            api_key=_secret_key(),
            amount=amount_minor,
            currency=currency,
            payment_method_types=['card'],
            description=f'Donation to {donation.campaign.title}',
            receipt_email=donation.donor.email if donation.donor and donation.donor.email else None,
            # How the async webhook matches this event back to our donation —
            # authoritative, same pattern as ModemPay's donation_reference.
            metadata={'donation_reference': donation.payment_reference},
        )
        return _as_dict(intent)
    except stripe.error.StripeError as e:
        logger.error(
            'Stripe create_payment_intent failed for donation %s: %s',
            donation.payment_reference, e,
        )
        return None


def retrieve_payment_intent(intent_id):
    """Fetch a PaymentIntent's current status directly from Stripe — used to
    reconcile a donation when a webhook is missed. Returns the raw
    PaymentIntent dict (status: requires_payment_method/requires_action/
    processing/succeeded/canceled/...), or None on failure."""
    if not intent_id:
        return None
    try:
        intent = stripe.PaymentIntent.retrieve(intent_id, api_key=_secret_key())
        return _as_dict(intent)
    except stripe.error.StripeError as e:
        logger.error('Stripe retrieve_payment_intent failed: %s', e)
        return None


def verify_and_parse_webhook(payload, signature, secret=None):
    """Validate an incoming webhook signature and return the parsed Stripe
    Event, or None if invalid. `payload` must be the raw request body
    (str/bytes) — Stripe signs the exact bytes sent, not a re-serialized
    version of them."""
    key = secret or settings.PAYMENT_GATEWAYS['stripe']['webhook_secret']
    if not signature or not key:
        return None
    try:
        event = stripe.Webhook.construct_event(payload, signature, key)
        return _as_dict(event)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.warning('Stripe webhook signature/payload rejected: %s', e)
        return None

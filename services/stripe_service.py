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


def create_checkout_session(donation, currency, amount_minor, success_url, cancel_url):
    """Create a Stripe Checkout Session for a donation — a hosted, full-page
    redirect, same shape as ModemPay's payment_link: the frontend sends the
    donor to `url`, Stripe collects card details on its own page, and the
    donor lands back on `success_url`/`cancel_url`.

    `amount_minor` is the already-converted, already-minor-unit amount (e.g.
    cents for usd) — conversion from the donor's GMD amount happens once, in
    services/gateways/stripe_gateway.py, using the admin-configured
    PlatformSettings.gmd_to_settlement_rate, not here, so this function has
    no currency-math opinion of its own to get wrong twice.

    Returns the SDK's Session as a plain dict on success (has `id`, `url`),
    or None on failure — never raises.
    """
    try:
        session = stripe.checkout.Session.create(
            api_key=_secret_key(),
            mode='payment',
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': currency,
                    'unit_amount': amount_minor,
                    'product_data': {'name': f'Donation to {donation.campaign.title}'},
                },
                'quantity': 1,
            }],
            # How the async webhook matches this event back to our donation —
            # authoritative, same pattern as ModemPay's donation_reference.
            metadata={'donation_reference': donation.payment_reference},
            customer_email=donation.donor.email if donation.donor and donation.donor.email else None,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return _as_dict(session)
    except stripe.error.StripeError as e:
        logger.error(
            'Stripe create_checkout_session failed for donation %s: %s',
            donation.payment_reference, e,
        )
        return None


def retrieve_checkout_session(session_id):
    """Fetch a Checkout Session's current status directly from Stripe —
    used to reconcile a donation when a webhook is missed. Returns the raw
    Session dict (has payment_status: 'paid'/'unpaid'/'no_payment_required'),
    or None on failure."""
    if not session_id:
        return None
    try:
        session = stripe.checkout.Session.retrieve(session_id, api_key=_secret_key())
        return _as_dict(session)
    except stripe.error.StripeError as e:
        logger.error('Stripe retrieve_checkout_session failed: %s', e)
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

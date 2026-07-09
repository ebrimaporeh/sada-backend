import logging
from functools import lru_cache
from django.conf import settings
from modempay import ModemPay
from modempay.error import ModemPayError

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_client():
    return ModemPay(api_key=settings.MODEMPAY_SECRET_KEY)


def create_payment_intent(donation, return_url='', cancel_url=''):
    """Create a ModemPay Payment Intent for a donation.

    Returns the SDK's parsed response dict (`{status, message, data: {...}}`)
    on success, or None on failure — never raises.
    """
    params = {
        # ModemPay's amount field is an integer (whole GMD) — fractional
        # amounts aren't representable in a single charge.
        'amount': int(donation.amount),
        'currency': donation.currency or 'GMD',
        'title': f'Donation to {donation.campaign.title}',
        'customer_name': donation.donor_display,
        'customer_phone': donation.phone,
        # This is how we match the async webhook back to this donation —
        # authoritative, unlike guessing from the provider's own id fields.
        'metadata': {'donation_reference': donation.payment_reference},
    }
    # ModemPay rejects non-public callback_urls outright ("Must be a valid
    # URL"), so localhost would break every donation attempt in local dev.
    # Only override it when a real public BACKEND_URL is configured; leave it
    # unset otherwise so ModemPay falls back to the dashboard-level webhook
    # URL (Developers > Webhooks).
    webhook_url = _build_webhook_url()
    if webhook_url:
        params['callback_url'] = webhook_url
    if return_url:
        params['return_url'] = return_url
    if cancel_url:
        params['cancel_url'] = cancel_url
    if donation.donor and donation.donor.email:
        params['customer_email'] = donation.donor.email

    try:
        return get_client().payment_intents.create(params=params)
    except ModemPayError as e:
        logger.error(
            'ModemPay create_payment_intent failed for donation %s: %s (status_code=%s)',
            donation.payment_reference, e, getattr(e, 'status_code', None),
        )
        return None


def retrieve_payment_intent(intent_secret):
    """Fetch a payment intent's current status directly from ModemPay.

    Used to reconcile a donation when the webhook hasn't arrived — e.g. local
    dev where ModemPay can't reach localhost at all, or as a safety net if a
    webhook is ever missed/delayed in production. Returns the raw PaymentIntent
    dict (has a top-level 'status': initialized/processing/requires_payment_method/
    successful/failed/cancelled), or None on failure.
    """
    if not intent_secret:
        return None
    try:
        return get_client().payment_intents.retrieve(intent_secret)
    except ModemPayError as e:
        logger.error('ModemPay retrieve_payment_intent failed: %s (status_code=%s)', e, getattr(e, 'status_code', None))
        return None


def get_balance():
    """Fetch current ModemPay balances. `payout_balance` is what actually
    funds real disbursements — Campaign.raised in our own DB can show funds
    as available before ModemPay has settled them into this pooled wallet.

    Returns {'available_balance': ..., 'payout_balance': ...} — an
    effectively-infinite payout_balance in DEMO_MODE since there's no real
    wallet to check — or None if the check itself failed.
    """
    if getattr(settings, 'DEMO_MODE', False):
        return {'available_balance': float('inf'), 'payout_balance': float('inf')}
    try:
        return get_client().balances.retrieve()
    except ModemPayError as e:
        logger.error('ModemPay get_balance failed: %s (status_code=%s)', e, getattr(e, 'status_code', None))
        return None


def verify_and_parse_webhook(payload, signature, secret=None):
    """Validate an incoming webhook signature and return {'event', 'payload'}, or None if invalid."""
    key = secret or settings.MODEMPAY_WEBHOOK_SECRET
    if not signature or not key:
        return None
    try:
        return get_client().webhooks.compose_event_details(payload, signature, key)
    except (ValueError, KeyError, TypeError) as e:
        logger.warning('ModemPay webhook signature/payload rejected: %s', e)
        return None


# ModemPay's own payout docs list wave/afrimoney as valid transfer networks,
# but we only actually use wave — aps isn't confirmed to work for payouts
# (only verified as a donation/charge method so far). Revisit this once
# aps-for-payouts is confirmed with ModemPay.
SUPPORTED_PAYOUT_NETWORKS = {'wave'}


def request_disbursement(reference, net_amount, phone, provider, beneficiary_name, currency='GMD'):
    """Trigger a payout transfer of `net_amount` to a mobile money number.

    `net_amount` is the platform-fee-already-deducted amount the caller
    computed (via PlatformSettings.get_fee_rate()) — this function doesn't
    recompute the fee itself, so there's one source of truth for the rate.

    Returns None on failure/error (including an unsupported network — caller
    should really validate this before creating the Payout row, but we guard
    here too since this is where real money would move), or a dict with a
    real ModemPay `status` (pending/completed/...) when the transfer was
    accepted. Caller decides COMPLETED vs PROCESSING from `result['status']`
    — transfers are asynchronous and confirmed for real via the
    `transfer.succeeded` webhook, this call only starts them.
    """
    if getattr(settings, 'DEMO_MODE', False):
        return {'id': f'DEMO-{reference}', 'status': 'completed'}

    if provider not in SUPPORTED_PAYOUT_NETWORKS:
        logger.error(
            'ModemPay request_disbursement rejected for payout %s: unsupported network %r (must be one of %s)',
            reference, provider, SUPPORTED_PAYOUT_NETWORKS,
        )
        return None

    params = {
        'amount': int(net_amount),
        'currency': currency,
        'network': provider,
        # ModemPay wants the bare local number ("Must be 7 digits"), not our
        # stored +220-prefixed format.
        'account_number': _local_phone(phone),
        'beneficiary_name': beneficiary_name,
        'narration': f'SADA payout {reference}',
        'metadata': {'payout_reference': reference},
    }
    try:
        return get_client().transfers.initiate(params=params, idempotency_key=reference)
    except ModemPayError as e:
        logger.error(
            'ModemPay request_disbursement failed for payout %s: %s (status_code=%s)',
            reference, e, getattr(e, 'status_code', None),
        )
        return None


def _local_phone(phone):
    """Strip the +220 country code (and any non-digits) down to the bare
    7-digit local number ModemPay's payout account_number field expects."""
    digits = ''.join(c for c in phone if c.isdigit())
    if digits.startswith('220') and len(digits) > 7:
        digits = digits[3:]
    return digits[-7:]


def _build_webhook_url():
    """Returns the webhook callback URL, or '' if none is configured for a
    public backend (BACKEND_URL unset — the common case in local dev)."""
    backend_url = getattr(settings, 'BACKEND_URL', '')
    if not backend_url:
        return ''
    return f'{backend_url.rstrip("/")}/api/v1/payments/webhook/modempay/'

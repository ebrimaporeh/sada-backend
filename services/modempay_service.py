import hmac
import hashlib
import requests
from decimal import Decimal
from django.conf import settings


MODEMPAY_API_URL = getattr(settings, 'MODEMPAY_API_URL', 'https://api.modempay.com/v1')
MODEMPAY_SECRET_KEY = getattr(settings, 'MODEMPAY_SECRET_KEY', '')
MODEMPAY_PUBLIC_KEY = getattr(settings, 'MODEMPAY_PUBLIC_KEY', '')
PAYOUT_FEE_RATE = Decimal('0.01')  # 1%


def initiate_payment(reference, amount, phone, provider, currency='GMD', callback_url=''):
    """Initiate a mobile money payment charge."""
    payload = {
        'reference': reference,
        'amount': str(amount),
        'currency': currency,
        'phone': phone,
        'provider': provider,
        'callback_url': callback_url or _build_webhook_url(),
    }
    try:
        resp = requests.post(
            f'{MODEMPAY_API_URL}/charges',
            json=payload,
            headers=_auth_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def verify_webhook_signature(payload_body, signature, secret=None):
    """Verify incoming webhook HMAC-SHA256 signature from ModemPay."""
    key = (secret or MODEMPAY_SECRET_KEY).encode('utf-8')
    expected = hmac.new(key, payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or '')


def request_disbursement(reference, amount, phone, provider, currency='GMD'):
    """Trigger a payout disbursement to a mobile money number."""
    net = amount - (amount * PAYOUT_FEE_RATE)
    payload = {
        'reference': reference,
        'amount': str(net),
        'currency': currency,
        'phone': phone,
        'provider': provider,
    }
    try:
        resp = requests.post(
            f'{MODEMPAY_API_URL}/disbursements',
            json=payload,
            headers=_auth_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json(), net
    except requests.RequestException:
        return None, net


def _auth_headers():
    return {
        'Authorization': f'Bearer {MODEMPAY_SECRET_KEY}',
        'Content-Type': 'application/json',
    }


def _build_webhook_url():
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:8000')
    base = frontend_url.replace('localhost:5173', 'localhost:8000')
    return f'{base}/api/v1/payments/webhook/modempay/'

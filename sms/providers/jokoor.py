"""Jokoor (https://docs.jokoor.com) SMS provider adapter.

Wraps the `jokoor` PyPI SDK's `client.sms.send(...)`, which itself never
raises for an ordinary send failure - it returns a (data, error) tuple where
`error` is a plain string (see jokoor/http_client.py: every branch, including
a bare `except Exception`, resolves to that tuple). The try/except here is
just a defensive backstop for something the SDK didn't anticipate (e.g. a
config problem), same posture as EmailService._send().

IMPORTANT, from Jokoor's own docs (docs.jokoor.com/sending-sms-messages):
SMS endpoints require a LIVE secret key (`sk_live_...`) - a test key
(`sk_test_...`) is accepted for other Jokoor products (payments) but
rejected here. If JOKOOR_API_KEY in settings is a test key, sends will fail
with an auth error until it's swapped for a live one - that's a credentials
problem, not a bug in this adapter.
"""
from .base import SmsProvider, SmsResult


class JokoorProvider(SmsProvider):
    code = 'jokoor'

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        # Built lazily, not in __init__ - registry.get_provider() constructs
        # this once at import/first-use time, and importing the `jokoor`
        # package shouldn't be a hard requirement just to import this module
        # (e.g. during tests that never actually send).
        if self._client is None:
            from jokoor import Jokoor
            self._client = Jokoor(self.config.get('api_key', ''))
        return self._client

    def send(self, to: str, message: str, sender_id: str = '') -> SmsResult:
        if not self.config.get('api_key'):
            return SmsResult(ok=False, error='JOKOOR_API_KEY is not configured.')
        try:
            sms, error = self.client.sms.send(
                recipient_phone=to,
                message_body=message,
                sender_id=sender_id or self.config.get('sender_id') or None,
            )
        except Exception as e:  # noqa: BLE001 - backstop, see module docstring
            return SmsResult(ok=False, error=str(e))
        if error:
            return SmsResult(ok=False, error=error)
        # `sms` is a TypedDict (plain dict at runtime), not an object -
        # dict access, not attribute access.
        return SmsResult(ok=True, message_id=sms.get('id', '') if sms else '')

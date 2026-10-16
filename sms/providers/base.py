"""Common interface every SMS provider adapter implements.

Mirrors services/gateways/base.py's PaymentGateway pattern: nothing outside
this package (and sms/registry.py, the one place allowed to import a
concrete adapter by name) should ever import JokoorProvider directly -
sms/service.py goes through registry.get_provider() instead, so switching or
adding a provider is a settings + registry change, not a call-site change.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SmsResult:
    """Result of a single send attempt. `ok=False` covers both a provider
    error (bad key, insufficient credits, invalid number...) and the
    provider being unreachable - either way there's nothing further to do
    with `message_id`, so callers only need to branch on `ok`."""
    ok: bool
    message_id: str = ''
    error: str = ''


class SmsProvider(ABC):
    """Base class for an SMS provider adapter (Jokoor, ...)."""
    code = ''

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def send(self, to: str, message: str, sender_id: str = '') -> SmsResult:
        """Send a single SMS. Must never raise for an ordinary send failure
        (bad number, no credit, provider outage) - return SmsResult(ok=False,
        error=...) instead, same contract as EmailService._send() returning
        False rather than raising. A raised exception here is reserved for a
        genuine programming error (e.g. missing config)."""

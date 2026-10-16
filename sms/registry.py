"""The single place that knows which SmsProvider class backs settings.SMS_PROVIDER.

Same shape as services/gateways/registry.py: sms/service.py asks for the
active provider via get_provider() - it never imports JokoorProvider (or
any future provider) directly. Adding a provider later means writing one
class, adding one line to PROVIDERS, and adding its credentials to
settings.SMS_PROVIDERS - no call-site change anywhere else.
"""
from django.conf import settings
from .providers.jokoor import JokoorProvider

PROVIDERS = {
    'jokoor': JokoorProvider,
}

_instance = None
_instance_code = None


def get_provider():
    """Return the configured SmsProvider instance for settings.SMS_PROVIDER.
    Cached (like services/gateways/registry.py's _instances) so each worker
    builds its underlying SDK client once, not per send."""
    global _instance, _instance_code

    code = settings.SMS_PROVIDER
    if _instance is not None and _instance_code == code:
        return _instance

    provider_cls = PROVIDERS.get(code)
    if provider_cls is None:
        raise ValueError(f'Unknown SMS_PROVIDER "{code}" - add it to sms/registry.py\'s PROVIDERS.')

    config = settings.SMS_PROVIDERS.get(code, {})
    _instance = provider_cls(config)
    _instance_code = code
    return _instance

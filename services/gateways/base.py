"""Common interface every payment gateway adapter implements.

Nothing outside this package (and registry.py, which is the one place
allowed to import a concrete adapter by name) should ever import
ModemPayGateway/StripeGateway/etc directly — services/serializers/views all
go through registry.get_gateway(code) instead, so switching or adding a
gateway is a settings + registry change, not a call-site change.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class GatewayIntent:
    """Result of successfully creating a payment intent with a gateway."""
    payment_link: str
    provider_reference: str = ''
    raw: dict = field(default_factory=dict)


class GatewayEventType:
    # The vocabulary payment_service.handle_*_webhook() dispatches on —
    # every gateway's verify_webhook() translates its own event names
    # (ModemPay's "charge.succeeded", Stripe's "checkout.session.completed",
    # ...) into these, so the dispatch logic never has to know which
    # gateway produced the event.
    DONATION_SUCCEEDED = 'donation_succeeded'
    DONATION_FAILED = 'donation_failed'
    PAYOUT_SUCCEEDED = 'payout_succeeded'
    PAYOUT_FAILED = 'payout_failed'
    UNHANDLED = 'unhandled'


@dataclass
class GatewayEvent:
    """A webhook event, normalized to GatewayEventType."""
    type: str
    donation_reference: str = ''
    payout_reference: str = ''
    provider_reference: str = ''
    raw: dict = field(default_factory=dict)


class PaymentGateway(ABC):
    """Base class for a payment gateway adapter (ModemPay, Stripe, ...).

    Donation-side methods are required of every gateway. Payout-side methods
    (get_balance/check_transfer_fee/request_disbursement) only need real
    implementations from gateways with supports_payouts=True — the default
    implementations here raise, so a donation-only gateway (Stripe: card
    payments can't disburse to a Gambian mobile-money wallet) never has to
    fake a payout API it doesn't have.
    """
    code = ''
    supports_payouts = False

    def __init__(self, config):
        self.config = config

    @abstractmethod
    def create_payment_intent(self, donation, return_url='', cancel_url='') -> GatewayIntent | None:
        """Start a payment for `donation`. Returns None (donation should be
        marked FAILED by the caller) if the intent could not be created."""

    @abstractmethod
    def retrieve_payment_intent(self, provider_reference) -> dict | None:
        """Fetch a payment intent's current status directly from the
        gateway — used to reconcile a donation when a webhook is missed."""

    @abstractmethod
    def verify_webhook(self, payload, signature) -> GatewayEvent | None:
        """Verify an incoming webhook's signature and return a normalized
        GatewayEvent, or None if the signature/payload is invalid."""

    @property
    def supported_payout_methods(self) -> set:
        return set()

    def get_balance(self) -> dict | None:
        raise NotImplementedError(f'{self.code} does not support payouts.')

    def check_transfer_fee(self, amount, method, currency='GMD'):
        raise NotImplementedError(f'{self.code} does not support payouts.')

    def request_disbursement(self, reference, net_amount, phone, method, beneficiary_name, currency='GMD'):
        raise NotImplementedError(f'{self.code} does not support payouts.')

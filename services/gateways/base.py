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
    # The HTTP header a webhook's signature arrives in — gateways don't
    # agree on a name (ModemPay: x-modem-signature, Stripe: Stripe-Signature),
    # so the generic webhook view reads this rather than hardcoding one.
    signature_header = ''
    # Whether this gateway needs a phone number to charge (ModemPay's mobile-
    # money networks do; Stripe's card checkout doesn't) — read by
    # DonationCreateSerializer so "phone required" isn't hardcoded to one
    # gateway there either.
    requires_phone = True
    # The currency this gateway actually settles in, server-side — not
    # client-controlled. GMD for ModemPay; Stripe doesn't support GMD as a
    # settlement currency at all, so a Stripe donation is charged in
    # whatever PAYMENT_GATEWAYS['stripe']['currency'] is configured to.
    default_currency = 'GMD'
    # If a gateway only ever offers one payment method (Stripe: card),
    # DonationCreateSerializer fills `provider` in with this automatically
    # instead of trusting the client to pair gateway+provider correctly.
    # None for gateways with more than one method (ModemPay: wave or aps),
    # where the donor's choice is meaningful and required.
    default_method = None

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
    def intent_status(self, intent) -> str:
        """Normalize a retrieve_payment_intent() result to one of
        'successful' / 'failed' / 'pending' — each gateway has its own raw
        status vocabulary (ModemPay: successful/failed/cancelled/...;
        Stripe: a status + a separate payment_status), so callers doing
        reconciliation dispatch on this instead of a gateway-specific string."""

    @abstractmethod
    def verify_webhook(self, payload, signature) -> GatewayEvent | None:
        """Verify an incoming webhook's signature and return a normalized
        GatewayEvent, or None if the signature/payload is invalid."""

    @property
    def supported_donation_methods(self) -> set:
        """Payment methods this gateway can charge a donation through
        (ModemPay: wave/aps; Stripe: card) — read by GatewayListView so the
        frontend can build its provider picker from actual server config
        instead of a hand-maintained constant. Defaults to {default_method}
        for a single-method gateway; override for a multi-method one."""
        return {self.default_method} if self.default_method else set()

    @property
    def supported_payout_methods(self) -> set:
        return set()

    def get_balance(self) -> dict | None:
        raise NotImplementedError(f'{self.code} does not support payouts.')

    def check_transfer_fee(self, amount, method, currency='GMD'):
        raise NotImplementedError(f'{self.code} does not support payouts.')

    def request_disbursement(self, reference, net_amount, phone, method, beneficiary_name, currency='GMD'):
        raise NotImplementedError(f'{self.code} does not support payouts.')

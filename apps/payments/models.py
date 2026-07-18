from decimal import Decimal
from django.db import models
from django.conf import settings
from apps.core.models import BaseModel


class Payment(BaseModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    class Provider(models.TextChoices):
        # ModemPay is the payment gateway, not itself a provider — these are
        # the underlying networks it processes payments through. Visa/
        # Mastercard/ModemPay Bank are planned but not live yet.
        WAVE = 'wave', 'Wave'
        APS = 'aps', 'APS Wallet'

    donation = models.OneToOneField(
        'donations.Donation',
        on_delete=models.CASCADE,
        related_name='payment',
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='GMD')
    reference = models.CharField(max_length=200, unique=True)
    provider_reference = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    raw_response = models.JSONField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} - {self.status}'


class Payout(BaseModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    class Provider(models.TextChoices):
        # Model-level choices mirror what ModemPay processes generally;
        # which of these are actually payable-out right now is enforced
        # separately by get_gateway('modempay').supported_payout_methods
        # (wave-only today — ModemPay's payout docs don't list aps as a
        # transfer network). Payouts are modempay-only, full stop — no other
        # gateway can disburse to a Gambian mobile-money wallet.
        WAVE = 'wave', 'Wave'
        APS = 'aps', 'APS Wallet'

    campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.CASCADE,
        related_name='payouts',
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='payouts',
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Two distinct fees, deliberately kept separate: `fee` is SADA's own cut
    # (PlatformSettings.platform_fee_percent, admin-configurable revenue),
    # `provider_fee` is ModemPay/the mobile money network's real transfer
    # cost (queried per-payout via get_gateway('modempay').check_transfer_fee
    # since it varies by network/amount). net_amount = amount - fee - provider_fee.
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    provider_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='GMD')
    provider = models.CharField(max_length=20, choices=Provider.choices)
    phone = models.CharField(max_length=20)
    reference = models.CharField(max_length=200, unique=True, null=True, blank=True)
    provider_reference = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Payout {self.amount} GMD - {self.campaign.title}'


class PlatformSettings(BaseModel):
    """Singleton row of admin-editable platform config.

    Donations carry no platform-side fee — donors only pay whatever the
    payment provider (ModemPay) itself charges them directly. This fee is
    taken only when a campaign owner withdraws (Payout), not on donation.

    Gateway on/off switches live here (not env vars) so an admin can flip
    them at runtime — services/gateways/registry.py reads `<code>_enabled`
    off this row via getattr(), so adding a new gateway later just means
    adding one more `<code>_enabled` field here, no registry code change.
    Credentials (API keys/webhook secrets) stay in env vars regardless —
    those are secrets, not something that belongs in an admin-editable DB row.
    """
    platform_fee_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('1.00'),
        help_text='Percentage the platform takes from each campaign payout.',
    )
    modempay_enabled = models.BooleanField(
        default=True,
        help_text='Whether donors/campaign owners can use ModemPay (Wave/APS mobile money).',
    )
    stripe_enabled = models.BooleanField(
        default=False,
        help_text='Whether donors can pay by card via Stripe. Requires Stripe API keys to '
                   'already be configured in the environment — this switch only controls '
                   'whether the (already-configured) gateway is offered.',
    )
    # Stripe doesn't support GMD as a settlement currency, so a card donation
    # is actually charged in this currency instead — converted from the
    # donor's GMD amount using gmd_to_settlement_rate below.
    stripe_settlement_currency = models.CharField(
        max_length=3, default='usd',
        help_text='Currency Stripe actually charges the card in (Stripe does not support GMD).',
    )
    gmd_to_settlement_rate = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal('70.0000'),
        help_text='How many GMD equal 1 unit of the Stripe settlement currency above — '
                   'e.g. 70 means D70 = 1 unit. Update this to match the real exchange rate; '
                   'a stale rate over/undercharges every card donation.',
    )

    class Meta:
        verbose_name = 'Platform Settings'
        verbose_name_plural = 'Platform Settings'

    def __str__(self):
        return f'Platform fee: {self.platform_fee_percent}%'

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj

    @classmethod
    def get_fee_rate(cls):
        """Returns the payout fee as a 0-1 Decimal ready for multiplication (e.g. 0.01 for 1%)."""
        return cls.get_solo().platform_fee_percent / Decimal('100')

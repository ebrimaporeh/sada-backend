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
        # separately by modempay_service.SUPPORTED_PAYOUT_NETWORKS (wave-only
        # today — ModemPay's payout docs don't list aps as a transfer network).
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
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
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
    """
    platform_fee_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('1.00'),
        help_text='Percentage the platform takes from each campaign payout.',
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

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
        MODEMPAY = 'modempay', 'ModemPay'
        WAVE = 'wave', 'Wave'
        ORANGE_MONEY = 'orange_money', 'Orange Money'
        AFRIMONEY = 'afrimoney', 'Afrimoney'

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
        MODEMPAY = 'modempay', 'ModemPay'
        WAVE = 'wave', 'Wave'
        ORANGE_MONEY = 'orange_money', 'Orange Money'
        AFRIMONEY = 'afrimoney', 'Afrimoney'

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

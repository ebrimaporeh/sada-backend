from django.db import models
from django.conf import settings
from apps.core.models import BaseModel


class Donation(BaseModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    class Provider(models.TextChoices):
        # ModemPay is the payment gateway, not itself a provider — these are
        # the underlying networks/methods it processes payments through.
        WAVE = 'wave', 'Wave'
        APS = 'aps', 'APS Wallet'
        # Gated behind PlatformSettings.card_payments_enabled — see the note
        # on that field for why it defaults off.
        CARD = 'card', 'Card'

    campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.CASCADE,
        related_name='donations',
    )
    donor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='donations',
    )
    donor_name = models.CharField(max_length=300, blank=True, help_text='Name for unauthenticated donors')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='GMD')
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.WAVE)
    phone = models.CharField(max_length=20, blank=True, help_text='Not required for card payments.')
    payment_reference = models.CharField(max_length=200, unique=True, null=True, blank=True)
    provider_reference = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    is_anonymous = models.BooleanField(default=False)
    message = models.TextField(blank=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Donation'
        verbose_name_plural = 'Donations'

    def __str__(self):
        return f'{self.amount} GMD to {self.campaign.title}'

    @property
    def net_amount(self):
        return self.amount - self.fee

    @property
    def donor_display(self):
        if self.is_anonymous:
            return 'Anonymous'
        if self.donor:
            return self.donor.full_name
        if self.donor_name:
            return self.donor_name
        return 'Anonymous'

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
        MODEMPAY = 'modempay', 'ModemPay'
        WAVE = 'wave', 'Wave'
        ORANGE_MONEY = 'orange_money', 'Orange Money'
        AFRIMONEY = 'afrimoney', 'Afrimoney'

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
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='GMD')
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.MODEMPAY)
    phone = models.CharField(max_length=20)
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
        if self.is_anonymous or not self.donor:
            return 'Anonymous'
        return self.donor.full_name

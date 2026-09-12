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
        # The payment *method* within whichever gateway processed this
        # donation (see `gateway` below) - wave/aps/afrimoney are ModemPay's
        # mobile-money networks; card is Stripe's. ModemPay itself doesn't
        # support card (confirmed 2026-07-14) - ModemPay donations are always
        # wave/aps/afrimoney, Stripe donations are always card.
        WAVE = 'wave', 'Wave'
        APS = 'aps', 'APS Wallet'
        AFRIMONEY = 'afrimoney', 'Afrimoney'
        CARD = 'card', 'Card'

    # Exactly one of campaign/organization is ever set -- a campaign donation
    # or a direct organization donation, never both, never neither (enforced
    # by the CheckConstraint below). campaign was the only destination before
    # direct organization donations existed; it's nullable now purely to make
    # room for organization-only rows, not because a campaign donation can
    # ever legitimately omit one.
    campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='donations',
    )
    # A direct donation to an organization itself, independent of any
    # campaign -- see project.md's "direct organization donations" notes.
    organization = models.ForeignKey(
        'users.Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='direct_donations',
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
    # Which gateway processed this donation (modempay, stripe, ...) - separate
    # from `provider`, which is the payment *method* within that gateway
    # (wave/aps for modempay, card for stripe). No `choices=` here deliberately:
    # gateways are registered in services/gateways/registry.py, not as a fixed
    # enum, so adding one shouldn't require a migration on this field.
    gateway = models.CharField(max_length=20, default='modempay')
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.WAVE)
    # Blank for card/Stripe donations - only ModemPay's mobile-money methods
    # need a phone number to charge (see PaymentGateway.requires_phone).
    phone = models.CharField(max_length=20, blank=True)
    payment_reference = models.CharField(max_length=200, unique=True, null=True, blank=True)
    provider_reference = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    is_anonymous = models.BooleanField(default=False)
    message = models.TextField(blank=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Set only for donations made through an embedded widget with a
    # configured Embed.return_url -- a frozen copy taken at creation time
    # (see donation_service.create_donation), not a live reference, so a
    # later edit to the embed doesn't retroactively change where this
    # donor's success page sends them. Blank for every other donation.
    source_url = models.URLField(max_length=2000, blank=True, default='')
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    refund_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Donation'
        verbose_name_plural = 'Donations'
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(campaign__isnull=False, organization__isnull=True)
                    | models.Q(campaign__isnull=True, organization__isnull=False)
                ),
                name='donation_exactly_one_destination',
            ),
        ]

    def __str__(self):
        return f'{self.amount} {self.currency} to {self.destination_title}'

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

    @property
    def is_organization_donation(self):
        return self.organization_id is not None

    @property
    def destination(self):
        """The Campaign or Organization this donation was made to -- exactly
        one is ever set, see the CheckConstraint above."""
        return self.campaign if self.campaign_id else self.organization

    @property
    def destination_title(self):
        return self.campaign.title if self.campaign_id else self.organization.organization_name

    @property
    def destination_slug(self):
        return self.campaign.slug if self.campaign_id else self.organization.slug

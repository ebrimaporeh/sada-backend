"""Append-only double-entry ledger - the authoritative record of every
money movement (donations received, refunds, payouts, admin corrections).

`Campaign.raised` (apps/campaigns/models.py) stays exactly as it is today -
a denormalized, F()-updated read-model for cheap access. This app doesn't
replace it; it's the durable, immutable record that read-model is
conceptually derived from. See services/ledger_service.py for the only
supported way to write to these tables.

Nothing here imports apps.donations/apps.payments/apps.campaigns - a
Transaction points at its originating Donation/Payout the same
denormalized way apps.audit.AuditLog points at its target (`source_type`/
`source_id`, not a real FK), so this app has zero dependency on them.
"""
from django.db import models
from apps.core.models import BaseModel


class Account(BaseModel):
    """A named bucket money can be debited/credited against.

    `type` is deliberately broader than what this first pass actually
    posts to (only PLATFORM_CLEARING/PLATFORM_FEES/CAMPAIGN/SUSPENSE are
    ever created by services/ledger_service.py today) - ORGANIZATION/USER
    exist so a future organization- or investor-balance account is a new
    `get_or_create_account()` call with a new `type`, not a schema change.

    `code` is the deterministic identity of an account (e.g.
    'campaign:<uuid>', 'platform_clearing:modempay') - always resolved via
    services/ledger_service.py's helpers, never constructed ad hoc, so the
    same logical account is never accidentally split across two rows.
    """
    class Type(models.TextChoices):
        PLATFORM_CLEARING = 'platform_clearing', 'Platform Clearing (Payment Provider)'
        PLATFORM_FEES = 'platform_fees', 'Platform Fees Revenue'
        CAMPAIGN = 'campaign', 'Campaign Balance'
        ORGANIZATION = 'organization', 'Organization Balance'
        USER = 'user', 'User / Investor Balance'
        SUSPENSE = 'suspense', 'Suspense / Manual Adjustments'

    type = models.CharField(max_length=30, choices=Type.choices)
    code = models.SlugField(max_length=150, unique=True)
    # Which domain object this account belongs to -- blank for
    # platform-singleton accounts (platform_clearing:*, platform_fees,
    # suspense). Indexed so "get this campaign's account" doesn't need to
    # know the code format.
    owner_type = models.CharField(max_length=50, blank=True)
    owner_id = models.CharField(max_length=64, blank=True)
    currency = models.CharField(max_length=3, default='GMD')
    name = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['code']
        indexes = [
            models.Index(fields=['owner_type', 'owner_id']),
            models.Index(fields=['type']),
        ]

    def __str__(self):
        return self.code


class ImmutableModel(models.Model):
    """Shared append-only enforcement for Transaction/LedgerEntry: once a
    row exists in the DB, it can never be updated or deleted. Corrections
    are new, separate rows (see services/ledger_service.py::reverse_transaction),
    never an edit to history."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.__class__.objects.filter(pk=self.pk).exists():
            raise ValueError(
                f'{self.__class__.__name__} rows are append-only and cannot be modified '
                f'(pk={self.pk}). Post a new compensating entry instead.'
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(
            f'{self.__class__.__name__} rows are append-only and cannot be deleted '
            f'(pk={self.pk}).'
        )


class Transaction(BaseModel, ImmutableModel):
    """One balanced financial event -- a group of LedgerEntry lines whose
    debits equal its credits. Always created via
    services/ledger_service.py::post_transaction(), never .objects.create()
    directly, so the balance invariant is enforced in one place."""

    class EntryType(models.TextChoices):
        DONATION_RECEIVED = 'donation_received', 'Donation Received'
        DONATION_REFUNDED = 'donation_refunded', 'Donation Refunded'
        PAYOUT_COMPLETED = 'payout_completed', 'Payout Completed'
        ADMIN_ADJUSTMENT = 'admin_adjustment', 'Admin Adjustment'

    entry_type = models.CharField(max_length=30, choices=EntryType.choices)
    description = models.CharField(max_length=500)

    # Denormalized pointer to whichever Donation/Payout/etc. caused this --
    # same pattern as apps.audit.AuditLog.target_type/target_id. Not a real
    # FK: this app has no import dependency on apps.donations/apps.payments.
    source_type = models.CharField(max_length=50, blank=True)
    source_id = models.CharField(max_length=64, blank=True)

    # Set when this transaction is a compensating reversal of an earlier
    # one (e.g. a refund reversing the original donation-received
    # transaction) -- PROTECT so the transaction being reversed can never
    # be deleted out from under its reversal (moot in practice since
    # ImmutableModel.delete() already always raises, but documents intent).
    reverses = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='reversed_by',
    )

    metadata = models.JSONField(null=True, blank=True)

    # Guards against double-posting the same logical event -- e.g. a
    # donation confirmed twice would otherwise happily post two balanced
    # (individually valid) transactions. Nullable: not every caller needs
    # one (defense-in-depth under the primary idempotency mechanism, which
    # for webhooks is apps.payments.models.WebhookEvent).
    idempotency_key = models.CharField(max_length=200, unique=True, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['source_type', 'source_id']),
            models.Index(fields=['entry_type']),
        ]

    def __str__(self):
        return f'{self.get_entry_type_display()} - {self.description}'


class LedgerEntry(BaseModel, ImmutableModel):
    """One debit or credit line within a Transaction. `amount` is always
    positive -- which side it's on is `direction`, never the sign."""

    class Direction(models.TextChoices):
        DEBIT = 'debit', 'Debit'
        CREDIT = 'credit', 'Credit'

    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, related_name='entries')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='entries')
    direction = models.CharField(max_length=10, choices=Direction.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='GMD')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['account', '-created_at']),
        ]

    def __str__(self):
        sign = '+' if self.direction == self.Direction.CREDIT else '-'
        return f'{self.account.code} {sign}{self.amount}'

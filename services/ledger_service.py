"""The only supported way to write to apps.ledger's tables.

Every real money movement in the app (donation confirmed, donation
refunded, payout completed, admin correction) goes through
`post_transaction()` or one of the `record_*` wrappers below -- never
`Transaction.objects.create()`/`LedgerEntry.objects.create()` directly,
so the double-entry balance invariant (sum(debits) == sum(credits)) is
enforced in exactly one place.

See apps/ledger/models.py for the schema and .claude/backend/services.md
for the money-flow conventions this mirrors (donation_service.py,
payment_service.py).
"""
from decimal import Decimal
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError

from apps.ledger.models import Account, Transaction as LedgerTransaction, LedgerEntry


def get_or_create_account(type, code, owner_type='', owner_id='', currency='GMD', name=''):
    account, _ = Account.objects.get_or_create(
        code=code,
        defaults={
            'type': type,
            'owner_type': owner_type,
            'owner_id': owner_id,
            'currency': currency,
            'name': name,
        },
    )
    return account


def platform_clearing_account(gateway_code):
    """The pooled cash balance held at a payment gateway (e.g. ModemPay's
    payout_balance) -- one per gateway, since each gateway's balance is a
    genuinely separate pool of real money."""
    return get_or_create_account(
        Account.Type.PLATFORM_CLEARING,
        code=f'platform_clearing:{gateway_code}',
        name=f'Platform Clearing — {gateway_code}',
    )


def platform_fees_account():
    """Platform's own revenue from payout fees -- a single account, not
    per-campaign or per-gateway, since it's the platform's money once
    recognized."""
    return get_or_create_account(Account.Type.PLATFORM_FEES, code='platform_fees', name='Platform Fees Revenue')


def campaign_account(campaign):
    """What the platform currently owes a campaign -- credited on a
    donation, debited on a refund or payout."""
    return get_or_create_account(
        Account.Type.CAMPAIGN,
        code=f'campaign:{campaign.id}',
        owner_type='campaign',
        owner_id=str(campaign.id),
        name=f'Campaign — {campaign.title}',
    )


def organization_account(organization):
    """What the platform currently owes an organization directly -- the
    organization analog of campaign_account, credited on a direct donation
    and debited on its refund. Uses Account.Type.ORGANIZATION, reserved for
    exactly this since apps.ledger.Account was first built (see this
    module's docstring / architecture-plan.md)."""
    return get_or_create_account(
        Account.Type.ORGANIZATION,
        code=f'organization:{organization.id}',
        owner_type='organization',
        owner_id=str(organization.id),
        name=f'Organization — {organization.organization_name}',
    )


def beneficiary_account(donation):
    """The campaign_account or organization_account a donation's money
    moves in/out of, depending on which destination it was made to (see
    Donation.destination) -- the one place that branch is resolved so
    record_donation_received/refunded/admin_adjustment don't each
    reimplement it."""
    if donation.campaign_id:
        return campaign_account(donation.campaign)
    return organization_account(donation.organization)


def suspense_account():
    """Where a manual/admin correction lands when there's no real gateway
    cash movement behind it -- its balance is meant to trend toward zero;
    a nonzero balance is a legible signal that something needs review."""
    return get_or_create_account(Account.Type.SUSPENSE, code='suspense', name='Suspense — Manual Adjustments')


def post_transaction(entry_type, description, lines, *, source=None, reverses=None,
                      idempotency_key=None, metadata=None):
    """Post one balanced transaction. `lines` is a list of
    `(account, direction, amount)` tuples, direction one of
    LedgerEntry.Direction. `source` is the Donation/Payout/etc. this
    transaction records, used to fill `source_type`/`source_id`
    (`source_type` defaults to the source object's class name, lowercased).

    Raises ValidationError if the lines don't balance or any amount isn't
    strictly positive -- a bug in the caller, not a condition any caller
    should ever need to catch (every call site here passes a fixed,
    known-balanced shape).

    If `idempotency_key` collides with an existing transaction, returns
    that existing transaction instead of posting a duplicate -- defense in
    depth under whatever caller-level idempotency already applies (for
    webhooks, apps.payments.models.WebhookEvent is the primary guard).
    """
    if not lines:
        raise ValidationError('A transaction must have at least one entry line.')

    debit_total = Decimal('0')
    credit_total = Decimal('0')
    for account, direction, amount in lines:
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValidationError(f'Ledger entry amount must be positive, got {amount}.')
        if direction == LedgerEntry.Direction.DEBIT:
            debit_total += amount
        elif direction == LedgerEntry.Direction.CREDIT:
            credit_total += amount
        else:
            raise ValidationError(f'Unknown ledger entry direction: {direction!r}')

    if debit_total != credit_total:
        raise ValidationError(
            f'Unbalanced transaction: debits={debit_total} != credits={credit_total} ({description}).'
        )

    source_type = source.__class__.__name__.lower() if source is not None else ''
    source_id = str(source.pk) if source is not None else ''

    try:
        with transaction.atomic():
            txn = LedgerTransaction.objects.create(
                entry_type=entry_type,
                description=description,
                source_type=source_type,
                source_id=source_id,
                reverses=reverses,
                metadata=metadata,
                idempotency_key=idempotency_key,
            )
            LedgerEntry.objects.bulk_create([
                LedgerEntry(
                    transaction=txn,
                    account=account,
                    direction=direction,
                    amount=Decimal(str(amount)),
                    currency=account.currency,
                )
                for account, direction, amount in lines
            ])
    except IntegrityError:
        if idempotency_key:
            existing = LedgerTransaction.objects.filter(idempotency_key=idempotency_key).first()
            if existing is not None:
                return existing
        raise

    return txn


def reverse_transaction(original, description, *, entry_type=None, source=None,
                         idempotency_key=None, metadata=None):
    """Post a new transaction that exactly mirrors `original` with every
    line's direction flipped -- the general "compensating transaction"
    primitive corrections/reversals/refunds all share. Never edits or
    deletes `original` (can't -- see ImmutableModel).

    `entry_type` defaults to `original.entry_type` and `source` is left
    unset (blank source_type/source_id) if not given -- callers that want
    the reversal tagged with its own entry type and pointed at its own
    source object (e.g. record_donation_refunded below, tagging as
    DONATION_REFUNDED against the Donation, not DONATION_RECEIVED) must
    pass both explicitly.
    """
    flip = {
        LedgerEntry.Direction.DEBIT: LedgerEntry.Direction.CREDIT,
        LedgerEntry.Direction.CREDIT: LedgerEntry.Direction.DEBIT,
    }
    lines = [
        (entry.account, flip[entry.direction], entry.amount)
        for entry in original.entries.all()
    ]
    return post_transaction(
        entry_type or original.entry_type,
        description,
        lines,
        source=source,
        reverses=original,
        idempotency_key=idempotency_key,
        metadata=metadata,
    )


def record_donation_received(donation):
    """Donations carry no platform fee (donation_service.create_donation
    always sets fee=0) -- the full net_amount moves from the gateway's
    clearing account into what the platform owes the campaign or
    organization this donation was made to (see Donation.destination)."""
    clearing = platform_clearing_account(donation.gateway)
    beneficiary = beneficiary_account(donation)
    return post_transaction(
        LedgerTransaction.EntryType.DONATION_RECEIVED,
        f'Donation {donation.payment_reference} to "{donation.destination_title}"',
        [
            (clearing, LedgerEntry.Direction.DEBIT, donation.net_amount),
            (beneficiary, LedgerEntry.Direction.CREDIT, donation.net_amount),
        ],
        source=donation,
        idempotency_key=f'donation_received:{donation.id}',
    )


def record_donation_refunded(donation):
    """Reverses the DONATION_RECEIVED transaction for this donation. Looks
    that transaction up by source pointer rather than requiring the caller
    to pass it -- refund_donation() only has the Donation."""
    original = LedgerTransaction.objects.filter(
        entry_type=LedgerTransaction.EntryType.DONATION_RECEIVED,
        source_type='donation',
        source_id=str(donation.id),
    ).first()
    if original is None:
        # Donation was confirmed before this ledger existed, or the
        # DONATION_RECEIVED post somehow never landed -- post a standalone
        # reversal-shaped transaction instead of raising, since the refund
        # itself (real gateway money movement) must not be blocked by a
        # missing historical ledger row.
        clearing = platform_clearing_account(donation.gateway)
        beneficiary = beneficiary_account(donation)
        return post_transaction(
            LedgerTransaction.EntryType.DONATION_REFUNDED,
            f'Refund of donation {donation.payment_reference} (no original ledger entry found)',
            [
                (beneficiary, LedgerEntry.Direction.DEBIT, donation.net_amount),
                (clearing, LedgerEntry.Direction.CREDIT, donation.net_amount),
            ],
            source=donation,
            idempotency_key=f'donation_refunded:{donation.id}',
        )
    return reverse_transaction(
        original,
        f'Refund of donation {donation.payment_reference} from "{donation.destination_title}"',
        entry_type=LedgerTransaction.EntryType.DONATION_REFUNDED,
        source=donation,
        idempotency_key=f'donation_refunded:{donation.id}',
    )


def record_payout_completed(payout):
    """See services.md/this module's docstring for the derivation: the
    platform's fee cut never actually leaves the gateway's clearing
    balance (it's simply recognized as revenue in place), so this balances
    to exactly `payout.amount` with 3 lines. provider_fee/net_amount are
    recorded in metadata rather than a dedicated account -- there's no
    ongoing balance/claim to track, it's a point-in-time cost already
    fully absorbed in the campaign debit."""
    campaign_acct = campaign_account(payout.campaign)
    fees_acct = platform_fees_account()
    clearing = platform_clearing_account('modempay')  # payouts are modempay-only, see services.md
    net_clearing_decrease = payout.amount - payout.fee

    lines = [(campaign_acct, LedgerEntry.Direction.DEBIT, payout.amount)]
    if payout.fee > 0:
        lines.append((fees_acct, LedgerEntry.Direction.CREDIT, payout.fee))
    lines.append((clearing, LedgerEntry.Direction.CREDIT, net_clearing_decrease))

    return post_transaction(
        LedgerTransaction.EntryType.PAYOUT_COMPLETED,
        f'Payout {payout.reference} from "{payout.campaign.title}"',
        lines,
        source=payout,
        idempotency_key=f'payout_completed:{payout.id}',
        metadata={
            'amount': str(payout.amount),
            'platform_fee': str(payout.fee),
            'provider_fee': str(payout.provider_fee),
            'net_amount': str(payout.net_amount),
        },
    )


def record_donation_admin_adjustment(donation, delta):
    """Posted only when an admin edit to a PAID donation
    (donation_service.admin_update_donation) changes the amount credited
    to a campaign with no real gateway cash movement behind it -- the
    suspense account is the offsetting leg precisely because there's
    nothing else to point at."""
    if delta == 0:
        return None
    beneficiary = beneficiary_account(donation)
    suspense = suspense_account()
    amount = abs(Decimal(str(delta)))
    if delta > 0:
        lines = [
            (suspense, LedgerEntry.Direction.DEBIT, amount),
            (beneficiary, LedgerEntry.Direction.CREDIT, amount),
        ]
    else:
        lines = [
            (beneficiary, LedgerEntry.Direction.DEBIT, amount),
            (suspense, LedgerEntry.Direction.CREDIT, amount),
        ]
    return post_transaction(
        LedgerTransaction.EntryType.ADMIN_ADJUSTMENT,
        f'Admin adjustment to donation {donation.payment_reference} ({delta:+})',
        lines,
        source=donation,
    )

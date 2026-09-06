from decimal import Decimal
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from apps.users.models import User
from apps.campaigns.models import Campaign
from apps.donations.models import Donation
from apps.payments.models import Payout
from apps.ledger.models import Account, Transaction, LedgerEntry
import services.ledger_service as ledger_service
import services.donation_service as donation_service
from services import payment_service


def make_campaign(**kwargs):
    owner = kwargs.pop('owner', None) or User.objects.create_user(
        email=f'owner{User.objects.count()}@example.com', password='pass',
    )
    defaults = {
        'owner': owner,
        'title': 'Well for Bakau',
        'short_description': 'Clean water',
        'story': 'A well for the community.',
        'goal': Decimal('10000.00'),
        'status': Campaign.Status.ACTIVE,
    }
    defaults.update(kwargs)
    return Campaign.objects.create(**defaults)


class PostTransactionTest(APITestCase):
    def setUp(self):
        self.a = ledger_service.get_or_create_account(Account.Type.SUSPENSE, code='test:a')
        self.b = ledger_service.get_or_create_account(Account.Type.SUSPENSE, code='test:b')

    def test_balanced_lines_post_successfully(self):
        txn = ledger_service.post_transaction(
            Transaction.EntryType.ADMIN_ADJUSTMENT, 'test',
            [
                (self.a, LedgerEntry.Direction.DEBIT, Decimal('50.00')),
                (self.b, LedgerEntry.Direction.CREDIT, Decimal('50.00')),
            ],
        )
        self.assertEqual(txn.entries.count(), 2)

    def test_unbalanced_lines_raise_and_commit_nothing(self):
        with self.assertRaises(ValidationError):
            ledger_service.post_transaction(
                Transaction.EntryType.ADMIN_ADJUSTMENT, 'test',
                [
                    (self.a, LedgerEntry.Direction.DEBIT, Decimal('50.00')),
                    (self.b, LedgerEntry.Direction.CREDIT, Decimal('40.00')),
                ],
            )
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(LedgerEntry.objects.count(), 0)

    def test_zero_amount_line_rejected(self):
        with self.assertRaises(ValidationError):
            ledger_service.post_transaction(
                Transaction.EntryType.ADMIN_ADJUSTMENT, 'test',
                [
                    (self.a, LedgerEntry.Direction.DEBIT, Decimal('0.00')),
                    (self.b, LedgerEntry.Direction.CREDIT, Decimal('0.00')),
                ],
            )
        self.assertEqual(Transaction.objects.count(), 0)

    def test_negative_amount_line_rejected(self):
        with self.assertRaises(ValidationError):
            ledger_service.post_transaction(
                Transaction.EntryType.ADMIN_ADJUSTMENT, 'test',
                [
                    (self.a, LedgerEntry.Direction.DEBIT, Decimal('-10.00')),
                    (self.b, LedgerEntry.Direction.CREDIT, Decimal('-10.00')),
                ],
            )
        self.assertEqual(Transaction.objects.count(), 0)

    def test_idempotency_key_collision_returns_existing_transaction(self):
        first = ledger_service.post_transaction(
            Transaction.EntryType.ADMIN_ADJUSTMENT, 'first',
            [
                (self.a, LedgerEntry.Direction.DEBIT, Decimal('10.00')),
                (self.b, LedgerEntry.Direction.CREDIT, Decimal('10.00')),
            ],
            idempotency_key='dedupe-key-1',
        )
        second = ledger_service.post_transaction(
            Transaction.EntryType.ADMIN_ADJUSTMENT, 'second (should not post)',
            [
                (self.a, LedgerEntry.Direction.DEBIT, Decimal('10.00')),
                (self.b, LedgerEntry.Direction.CREDIT, Decimal('10.00')),
            ],
            idempotency_key='dedupe-key-1',
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(Transaction.objects.filter(idempotency_key='dedupe-key-1').count(), 1)


class ImmutabilityTest(APITestCase):
    def setUp(self):
        self.a = ledger_service.get_or_create_account(Account.Type.SUSPENSE, code='test:a')
        self.b = ledger_service.get_or_create_account(Account.Type.SUSPENSE, code='test:b')
        self.txn = ledger_service.post_transaction(
            Transaction.EntryType.ADMIN_ADJUSTMENT, 'test',
            [
                (self.a, LedgerEntry.Direction.DEBIT, Decimal('10.00')),
                (self.b, LedgerEntry.Direction.CREDIT, Decimal('10.00')),
            ],
        )

    def test_transaction_cannot_be_resaved(self):
        txn = Transaction.objects.get(pk=self.txn.pk)
        txn.description = 'edited'
        with self.assertRaises(ValueError):
            txn.save()

    def test_transaction_cannot_be_deleted(self):
        with self.assertRaises(ValueError):
            self.txn.delete()

    def test_ledger_entry_cannot_be_resaved(self):
        entry = self.txn.entries.first()
        entry = LedgerEntry.objects.get(pk=entry.pk)
        entry.amount = Decimal('999.00')
        with self.assertRaises(ValueError):
            entry.save()

    def test_ledger_entry_cannot_be_deleted(self):
        entry = self.txn.entries.first()
        with self.assertRaises(ValueError):
            entry.delete()


class DonationLedgerTest(APITestCase):
    """Confirming a donation must post a balanced transaction whose net
    effect on the campaign's ledger account matches Campaign.raised --
    the whole point of the ledger existing alongside that read-model."""

    def setUp(self):
        self.campaign = make_campaign()

    def _account_balance(self, account):
        """credit - debit for a credit-normal account (CAMPAIGN/SUSPENSE/
        PLATFORM_FEES -- a liability/revenue whose balance rises on
        credit), debit - credit for a debit-normal one (PLATFORM_CLEARING --
        an asset whose balance rises on debit)."""
        entries = LedgerEntry.objects.filter(account=account)
        credits = sum(e.amount for e in entries if e.direction == LedgerEntry.Direction.CREDIT)
        debits = sum(e.amount for e in entries if e.direction == LedgerEntry.Direction.DEBIT)
        if account.type == Account.Type.PLATFORM_CLEARING:
            return debits - credits
        return credits - debits

    def test_donation_received_posts_balanced_two_line_transaction(self):
        donation = Donation.objects.create(
            campaign=self.campaign, amount=Decimal('300.00'), provider='wave',
            phone='+2207000000', payment_reference='SD-LEDGER1', gateway='modempay',
            status=Donation.Status.PENDING,
        )
        donation_service._confirm_donation(donation)

        self.campaign.refresh_from_db()
        campaign_acct = ledger_service.campaign_account(self.campaign)
        clearing_acct = ledger_service.platform_clearing_account('modempay')

        entries = LedgerEntry.objects.filter(transaction__source_type='donation', transaction__source_id=str(donation.id))
        self.assertEqual(entries.count(), 2)
        self.assertEqual(
            sum(e.amount for e in entries.filter(direction=LedgerEntry.Direction.DEBIT)),
            sum(e.amount for e in entries.filter(direction=LedgerEntry.Direction.CREDIT)),
        )
        self.assertEqual(self._account_balance(campaign_acct), self.campaign.raised)
        self.assertEqual(self._account_balance(clearing_acct), self.campaign.raised)

    def test_confirming_twice_does_not_double_post(self):
        donation = Donation.objects.create(
            campaign=self.campaign, amount=Decimal('100.00'), provider='wave',
            phone='+2207000000', payment_reference='SD-LEDGER2', gateway='modempay',
            status=Donation.Status.PENDING,
        )
        donation_service.confirm_donation_by_reference('SD-LEDGER2')
        # A second confirmation attempt is a no-op (status is no longer
        # PENDING) -- mirrors what a redelivered webhook would trigger.
        result = donation_service.confirm_donation_by_reference('SD-LEDGER2')
        self.assertIsNone(result)

        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.raised, Decimal('100.00'))
        entries = LedgerEntry.objects.filter(transaction__source_type='donation', transaction__source_id=str(donation.id))
        self.assertEqual(entries.count(), 2)

    def test_refund_reverses_the_original_transaction(self):
        from unittest.mock import patch

        donation = Donation.objects.create(
            campaign=self.campaign, amount=Decimal('150.00'), provider='wave',
            phone='+2207000000', payment_reference='SD-LEDGER3', gateway='modempay',
            provider_reference='ch_refundme', status=Donation.Status.PENDING,
        )
        donation_service._confirm_donation(donation)
        donation.refresh_from_db()

        with patch('services.modempay_service.reverse_transaction', return_value={'id': 'rv_1', 'status': 'success'}):
            donation_service.refund_donation(donation)

        original = Transaction.objects.get(
            entry_type=Transaction.EntryType.DONATION_RECEIVED,
            source_type='donation', source_id=str(donation.id),
        )
        reversal = Transaction.objects.get(
            entry_type=Transaction.EntryType.DONATION_REFUNDED,
            source_type='donation', source_id=str(donation.id),
        )
        self.assertEqual(reversal.reverses_id, original.id)

        original_lines = {(e.account_id, e.direction) for e in original.entries.all()}
        reversal_lines = {(e.account_id, e.direction) for e in reversal.entries.all()}
        flipped = {
            (account_id, LedgerEntry.Direction.CREDIT if direction == LedgerEntry.Direction.DEBIT else LedgerEntry.Direction.DEBIT)
            for account_id, direction in original_lines
        }
        self.assertEqual(reversal_lines, flipped)

        self.campaign.refresh_from_db()
        campaign_acct = ledger_service.campaign_account(self.campaign)
        self.assertEqual(self._account_balance(campaign_acct), self.campaign.raised)
        self.assertEqual(self.campaign.raised, Decimal('0.00'))


class PayoutLedgerTest(APITestCase):
    def test_payout_completed_posts_balanced_three_line_transaction(self):
        campaign = make_campaign(raised=Decimal('1000.00'))
        payout = Payout.objects.create(
            campaign=campaign, requested_by=campaign.owner,
            amount=Decimal('500.00'), fee=Decimal('5.00'), provider_fee=Decimal('12.00'),
            net_amount=Decimal('483.00'), provider='wave', phone='+2207000000',
            reference='PO-LEDGER1', status=Payout.Status.PROCESSING,
        )
        payment_service._mark_payout_completed(payout, provider_reference='tr_ledger1')

        txn = Transaction.objects.get(
            entry_type=Transaction.EntryType.PAYOUT_COMPLETED,
            source_type='payout', source_id=str(payout.id),
        )
        entries = list(txn.entries.all())
        self.assertEqual(len(entries), 3)
        debit_total = sum(e.amount for e in entries if e.direction == LedgerEntry.Direction.DEBIT)
        credit_total = sum(e.amount for e in entries if e.direction == LedgerEntry.Direction.CREDIT)
        self.assertEqual(debit_total, credit_total)
        self.assertEqual(debit_total, payout.amount)

        fees_acct = ledger_service.platform_fees_account()
        fee_entry = [e for e in entries if e.account_id == fees_acct.id][0]
        self.assertEqual(fee_entry.amount, Decimal('5.00'))
        self.assertEqual(fee_entry.direction, LedgerEntry.Direction.CREDIT)

    def test_completing_twice_does_not_double_post(self):
        campaign = make_campaign()
        payout = Payout.objects.create(
            campaign=campaign, requested_by=campaign.owner,
            amount=Decimal('200.00'), fee=Decimal('2.00'), provider_fee=Decimal('3.00'),
            net_amount=Decimal('195.00'), provider='wave', phone='+2207000000',
            reference='PO-LEDGER2', status=Payout.Status.PROCESSING,
        )
        payment_service._mark_payout_completed(payout)
        payment_service._mark_payout_completed(payout)

        count = Transaction.objects.filter(
            entry_type=Transaction.EntryType.PAYOUT_COMPLETED,
            source_type='payout', source_id=str(payout.id),
        ).count()
        self.assertEqual(count, 1)


class AdminAdjustmentLedgerTest(APITestCase):
    def test_admin_amount_increase_posts_against_suspense(self):
        campaign = make_campaign()
        donation = Donation.objects.create(
            campaign=campaign, amount=Decimal('100.00'), provider='wave',
            phone='+2207000000', payment_reference='SD-ADMIN1', gateway='modempay',
            status=Donation.Status.PAID,
        )
        Campaign.objects.filter(pk=campaign.pk).update(raised=Decimal('100.00'), donors_count=1)

        donation_service.admin_update_donation(donation, {'amount': Decimal('120.00')})

        txn = Transaction.objects.get(
            entry_type=Transaction.EntryType.ADMIN_ADJUSTMENT,
            source_type='donation', source_id=str(donation.id),
        )
        entries = list(txn.entries.all())
        debit_total = sum(e.amount for e in entries if e.direction == LedgerEntry.Direction.DEBIT)
        credit_total = sum(e.amount for e in entries if e.direction == LedgerEntry.Direction.CREDIT)
        self.assertEqual(debit_total, credit_total)
        self.assertEqual(debit_total, Decimal('20.00'))

    def test_no_amount_change_posts_nothing(self):
        campaign = make_campaign()
        donation = Donation.objects.create(
            campaign=campaign, amount=Decimal('100.00'), provider='wave',
            phone='+2207000000', payment_reference='SD-ADMIN2', gateway='modempay',
            status=Donation.Status.PAID,
        )
        Campaign.objects.filter(pk=campaign.pk).update(raised=Decimal('100.00'), donors_count=1)

        donation_service.admin_update_donation(donation, {'message': 'edited message only'})

        self.assertFalse(Transaction.objects.filter(
            entry_type=Transaction.EntryType.ADMIN_ADJUSTMENT,
            source_type='donation', source_id=str(donation.id),
        ).exists())

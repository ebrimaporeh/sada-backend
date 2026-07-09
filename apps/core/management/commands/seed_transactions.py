import random
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum, Count
from django.utils import timezone

from apps.campaigns.models import Campaign
from apps.donations.models import Donation
from apps.payments.models import Payout, PlatformSettings
from apps.users.models import User


# Guest (unauthenticated) donor names — realistic Gambian names, distinct from
# the seeded user accounts so guest-checkout donations look authentic.
GUEST_DONORS = [
    ('Ebrima', 'Sanneh'), ('Fatoumatta', 'Jallow'), ('Momodou', 'Ceesay'),
    ('Awa', 'Bah'), ('Sheriff', 'Jammeh'), ('Binta', 'Sowe'), ('Yankuba', 'Darboe'),
    ('Mam', 'Jobe'), ('Musa', 'Colley'), ('Haddy', 'Faal'), ('Ebou', 'Manneh'),
    ('Sainabou', 'Bojang'), ('Pa Modou', 'Cham'), ('Jainaba', 'Sowe'), ('Lamin', 'Sanyang'),
    ('Fatima', 'Jatta'), ('Bakary', 'Trawally'), ('Adama', 'Barrow'), ('Kumba', 'Suso'),
    ('Ousainou', 'Darboe'), ('Nyima', 'Sarr'), ('Karafa', 'Kanteh'), ('Ramou', 'Jagne'),
    ('Alagie', 'Touray'), ('Mariam', 'Jaiteh'), ('Buba', 'Sanno'), ('Sarjo', 'Camara'),
    ('Njundu', 'Drammeh'), ('Assan', 'Jallow'), ('Yassin', 'Sillah'),
]

DONATION_MESSAGES = [
    'Praying for you.', 'Keep strong, we are with you.', 'Small contribution, big love.',
    'From the diaspora with love.', 'God bless this cause.', 'Happy to help however I can.',
    'This touched my heart. Sending support.', 'Sharing with my family and friends too.',
    'Alhamdulillah, glad to give back.', 'Stay strong!', 'For a better Gambia.',
    'Wishing you a speedy recovery.', 'Every little bit helps.', 'Proud to support this.',
    'From our family to yours.', 'May Allah ease your journey.', 'Sending love from London.',
    'Sending love from the US.', 'Investing in our community.', 'Together we can do this.',
    '', '', '', '', '', '',  # blank messages should be common, not the exception
]

DONOR_PHONE_PREFIXES = ['70', '71', '73', '74', '76', '77', '78', '79']


def make_donation_ref():
    return f'GF-{uuid.uuid4().hex[:12].upper()}'


def make_payout_ref():
    return f'PO-{uuid.uuid4().hex[:12].upper()}'


def random_local_phone():
    prefix = random.choice(DONOR_PHONE_PREFIXES)
    return f'+220 {prefix}{random.randint(10000, 99999)}'


def weighted_days_ago():
    """Recency-biased day offset over the last 365 days so week/month/year
    admin-Finance filters all have real data, with more activity recently."""
    bucket = random.choices(
        ['week', 'month', 'quarter', 'year'],
        weights=[35, 30, 20, 15],
        k=1,
    )[0]
    if bucket == 'week':
        return random.randint(0, 7)
    if bucket == 'month':
        return random.randint(8, 30)
    if bucket == 'quarter':
        return random.randint(31, 90)
    return random.randint(91, 365)


def weighted_amount():
    bucket = random.choices(
        ['small', 'medium', 'large', 'very_large'],
        weights=[45, 35, 15, 5],
        k=1,
    )[0]
    if bucket == 'small':
        value = random.uniform(50, 500)
    elif bucket == 'medium':
        value = random.uniform(500, 3000)
    elif bucket == 'large':
        value = random.uniform(3000, 10000)
    else:
        value = random.uniform(10000, 50000)
    return Decimal(str(round(value, 2)))


def quantize(amount):
    return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = (
        'Seed many realistic donations and payouts/withdrawals of every status, '
        'spread across the last year, linked to existing campaigns and users — '
        'for exercising the admin Finances dashboard and charts.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--donations-per-campaign', type=int, default=55,
                             help='Approximate number of donations to create per campaign (default: 55)')
        parser.add_argument('--payouts-per-campaign', type=int, default=5,
                             help='Approximate number of payouts to create per campaign (default: 5)')
        parser.add_argument('--seed', type=int, default=None, help='Random seed for reproducible output')

    def handle(self, *args, **options):
        if options['seed'] is not None:
            random.seed(options['seed'])

        campaigns = list(Campaign.objects.select_related('owner').all())
        if not campaigns:
            self.stdout.write(self.style.ERROR('No campaigns found — run `seed_data` first.'))
            return

        donor_pool = list(User.objects.filter(role=User.Role.USER))
        fee_rate = PlatformSettings.get_fee_rate()

        total_donations = 0
        total_payouts = 0

        now = timezone.now()

        with transaction.atomic():
            for campaign in campaigns:
                max_age_days = self._align_campaign_age(campaign, now)

                n_donations = max(10, options['donations_per_campaign'] + random.randint(-15, 20))
                n_donations = self._seed_donations(campaign, donor_pool, n_donations, max_age_days)
                total_donations += n_donations

                self._recompute_campaign_totals(campaign)

                n_payouts = max(1, options['payouts_per_campaign'] + random.randint(-2, 3))
                n_payouts = self._seed_payouts(campaign, fee_rate, n_payouts, max_age_days)
                total_payouts += n_payouts

                self.stdout.write(f'  {campaign.title[:45]:<45} +{n_donations:>3} donations, +{n_payouts:>2} payouts')

        self.stdout.write(self.style.SUCCESS(
            f'\nCreated {total_donations} donations and {total_payouts} payouts '
            f'across {len(campaigns)} campaigns.'
        ))
        self._print_status_breakdown()

    def _align_campaign_age(self, campaign, now):
        """Backdate created_at to match the campaign's approved_at (set relative
        to 'now' by seed_data), capped at 365 days, so seeded transaction dates
        never predate the campaign's own row. Returns the resulting max age in days."""
        if campaign.approved_at:
            new_created = campaign.approved_at - timedelta(days=random.randint(2, 7))
        else:
            new_created = campaign.created_at
        max_age = min(365, max(1, (now - new_created).days))
        new_created = now - timedelta(days=max_age)
        Campaign.objects.filter(pk=campaign.pk).update(created_at=new_created)
        campaign.created_at = new_created
        return max_age

    # ─── Donations ───────────────────────────────────────────────────────────

    def _seed_donations(self, campaign, donor_pool, count, max_age_days):
        now = timezone.now()
        eligible_donors = [u for u in donor_pool if u.id != campaign.owner_id]

        instances = []
        for _ in range(count):
            status = random.choices(
                [Donation.Status.PAID, Donation.Status.PENDING, Donation.Status.FAILED, Donation.Status.REFUNDED],
                weights=[80, 7, 9, 4],
                k=1,
            )[0]

            roll = random.random()
            if roll < 0.55 and eligible_donors:
                donor = random.choice(eligible_donors)
                donor_name = ''
                phone = donor.phone or random_local_phone()
            elif roll < 0.85:
                donor = None
                first, last = random.choice(GUEST_DONORS)
                donor_name = f'{first} {last}'
                phone = random_local_phone()
            else:
                donor = random.choice(eligible_donors) if eligible_donors and random.random() < 0.5 else None
                if donor:
                    donor_name = ''
                else:
                    first, last = random.choice(GUEST_DONORS)
                    donor_name = f'{first} {last}'
                phone = donor.phone if donor else random_local_phone()

            is_anonymous = random.random() < 0.18

            days_ago = min(weighted_days_ago(), max_age_days)
            created_dt = now - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))
            amount = quantize(weighted_amount())

            donation = Donation(
                campaign=campaign,
                donor=donor,
                donor_name=donor_name,
                amount=amount,
                currency='GMD',
                provider=random.choices(['wave', 'aps'], weights=[70, 30], k=1)[0],
                phone=phone,
                payment_reference=make_donation_ref(),
                status=status,
                is_anonymous=is_anonymous,
                message=random.choice(DONATION_MESSAGES),
                fee=Decimal('0'),
                paid_at=created_dt if status in (Donation.Status.PAID, Donation.Status.REFUNDED) else None,
            )
            donation.created_at = created_dt
            donation.updated_at = created_dt
            instances.append(donation)

        # bulk_create's insert path runs each field's pre_save(), and
        # DateTimeField.pre_save() for auto_now/auto_now_add fields does a
        # setattr(instance, ...) side effect that clobbers our backdated
        # values back to "now" — reapply them before the bulk_update fix-up.
        target_timestamps = [(inst, inst.created_at) for inst in instances]
        Donation.objects.bulk_create(instances)
        for inst, dt in target_timestamps:
            inst.created_at = dt
            inst.updated_at = dt
        Donation.objects.bulk_update(instances, ['created_at', 'updated_at'])
        return len(instances)

    def _recompute_campaign_totals(self, campaign):
        paid = campaign.donations.filter(status=Donation.Status.PAID)
        agg = paid.aggregate(total=Sum('amount'), donors=Count('donor', distinct=True))
        total_amount = agg['total'] or Decimal('0')
        # Distinct donors undercounts guest checkouts (donor is null); approximate
        # a realistic donor count as distinct known donors + guest donation rows.
        guest_count = paid.filter(donor__isnull=True).count()
        campaign.raised = total_amount
        campaign.donors_count = (agg['donors'] or 0) + guest_count
        campaign.save(update_fields=['raised', 'donors_count'])

    # ─── Payouts / withdrawals ───────────────────────────────────────────────

    def _seed_payouts(self, campaign, fee_rate, count, max_age_days):
        now = timezone.now()
        already_withdrawn = campaign.payouts.filter(
            status=Payout.Status.COMPLETED
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        headroom = max(campaign.raised - already_withdrawn, Decimal('0'))
        available = headroom * Decimal('0.7')  # leave a realistic buffer as available_balance
        if available <= 0:
            return 0

        statuses = random.choices(
            [Payout.Status.COMPLETED, Payout.Status.PENDING, Payout.Status.PROCESSING,
             Payout.Status.FAILED, Payout.Status.CANCELLED],
            weights=[60, 12, 8, 12, 8],
            k=count,
        )

        remaining = available
        instances = []
        for status in statuses:
            if status == Payout.Status.COMPLETED:
                if remaining <= 100:
                    continue
                amount = quantize(min(remaining, Decimal(str(random.uniform(float(remaining) * 0.1, float(remaining) * 0.4)))))
                remaining -= amount
            else:
                # Failed/cancelled/pending/processing requests don't actually withdraw funds
                ceiling = float(max(campaign.raised * Decimal('0.3'), Decimal('500')))
                amount = quantize(Decimal(str(random.uniform(200, max(500, ceiling)))))

            fee = quantize(amount * fee_rate)
            net = amount - fee

            payout_max_age = min(max_age_days, random.randint(0, 3)) if status == Payout.Status.PENDING else max_age_days
            days_ago = min(weighted_days_ago(), payout_max_age)
            created_dt = now - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))
            processed_dt = created_dt + timedelta(hours=random.randint(1, 48)) if status in (
                Payout.Status.COMPLETED, Payout.Status.FAILED, Payout.Status.CANCELLED
            ) else None
            if processed_dt and processed_dt > now:
                processed_dt = now

            payout = Payout(
                campaign=campaign,
                requested_by=campaign.owner,
                amount=amount,
                fee=fee,
                net_amount=net,
                currency='GMD',
                provider='wave',
                phone=campaign.owner.phone or random_local_phone(),
                reference=make_payout_ref(),
                status=status,
                notes=self._payout_note(status),
                processed_at=processed_dt,
            )
            payout.created_at = created_dt
            payout.updated_at = processed_dt or created_dt
            instances.append(payout)

        if not instances:
            return 0

        target_timestamps = [(inst, inst.created_at, inst.updated_at) for inst in instances]
        Payout.objects.bulk_create(instances)
        for inst, created_dt, updated_dt in target_timestamps:
            inst.created_at = created_dt
            inst.updated_at = updated_dt
        Payout.objects.bulk_update(instances, ['created_at', 'updated_at'])
        return len(instances)

    def _payout_note(self, status):
        if status == Payout.Status.FAILED:
            return random.choice([
                'Disbursement failed — insufficient payout balance at ModemPay.',
                'Transfer failed — network timeout, please retry.',
                'Disbursement rejected by provider.',
            ])
        if status == Payout.Status.CANCELLED:
            return 'Cancelled by campaign owner.'
        return ''

    # ─── Summary ─────────────────────────────────────────────────────────────

    def _print_status_breakdown(self):
        self.stdout.write('\n' + '─' * 55)
        self.stdout.write(self.style.SUCCESS('Donation status breakdown'))
        for row in Donation.objects.values('status').annotate(n=Count('id'), total=Sum('amount')).order_by('status'):
            self.stdout.write(f"  {row['status']:<12} {row['n']:>5}  (D {row['total'] or 0:,.2f})")

        self.stdout.write(self.style.SUCCESS('\nPayout status breakdown'))
        for row in Payout.objects.values('status').annotate(n=Count('id'), total=Sum('net_amount')).order_by('status'):
            self.stdout.write(f"  {row['status']:<12} {row['n']:>5}  (D {row['total'] or 0:,.2f})")
        self.stdout.write('─' * 55)

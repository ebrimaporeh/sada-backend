from django.core.management.base import BaseCommand
from django.db import transaction

from apps.campaigns.models import CampaignReport
from apps.payments.models import Payout
from apps.donations.models import Donation
from apps.users.models import Organization, User
from utils.validators import migrate_legacy_gambia_phone, normalize_gambia_phone

# Every (model, field) pair that holds a Gambian phone number -- see
# utils/validators.py's own docstring for the numbering reform this
# backfills, and .claude/backend/ for where each of these is normally
# validated going forward (this command only touches what's *already
# stored*; validate_gambia_phone is what enforces the rule on new input).
PHONE_FIELDS = [
    (User, 'phone'),
    (User, 'default_payment_phone'),
    (Organization, 'phone'),
    (Organization, 'phone_2'),
    (Donation, 'phone'),
    (Payout, 'phone'),
    (CampaignReport, 'reporter_phone'),
]


class Command(BaseCommand):
    help = (
        "One-time backfill: converts every already-stored legacy 7-digit Gambian "
        "phone number to the new 9-digit format (see utils/validators.py's "
        "migrate_legacy_gambia_phone), and reformats any already-9-digit number to "
        "the canonical +220XXXXXXXXX shape. Safe to re-run -- already-converted "
        "rows are left alone the second time. Numbers that don't match either "
        "shape (wrong length, unmapped leading digit) are reported but never "
        "guessed at or touched."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would change without writing anything.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        total_converted = 0
        total_reformatted = 0
        total_unrecognized = []

        for model, field in PHONE_FIELDS:
            converted = reformatted = 0
            queryset = model.objects.exclude(**{field: ''}).only('id', field)
            with transaction.atomic():
                for obj in queryset:
                    raw = getattr(obj, field)
                    new_value = migrate_legacy_gambia_phone(raw)
                    if new_value is not None:
                        converted += 1
                    else:
                        # Not a legacy 7-digit number -- either already the
                        # new 9-digit shape (just needs reformatting to the
                        # canonical +220XXXXXXXXX string), or something this
                        # command doesn't know how to safely convert.
                        digits = normalize_gambia_phone(raw)
                        if len(digits) == 9 and digits.startswith('8'):
                            canonical = f'+220{digits}'
                            if canonical != raw:
                                reformatted += 1
                            new_value = canonical  # already-canonical case: equals `raw`, so the save below is a no-op
                        else:
                            total_unrecognized.append(f'{model.__name__}.{field}#{obj.id}: {raw!r}')
                            continue

                    if new_value != raw:
                        setattr(obj, field, new_value)
                        if not dry_run:
                            obj.save(update_fields=[field])

                if dry_run:
                    transaction.set_rollback(True)

            total_converted += converted
            total_reformatted += reformatted
            if converted or reformatted:
                self.stdout.write(f'{model.__name__}.{field}: converted {converted}, reformatted {reformatted}')

        verb = 'Would convert' if dry_run else 'Converted'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} {total_converted} legacy number(s), reformatted {total_reformatted} already-new-format number(s).'
        ))
        if total_unrecognized:
            self.stdout.write(self.style.WARNING(
                f'{len(total_unrecognized)} number(s) left untouched (not a recognized legacy or new format):',
            ))
            for line in total_unrecognized:
                self.stdout.write(f'  {line}')

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count


class Command(BaseCommand):
    """One-off pre-launch cleanup: wipes exactly the model categories named
    in the ops request this was written for -- users, campaigns, donations,
    activity logs, verifications, notifications, staff, organizations,
    reports -- and nothing else. Written for a production database
    confirmed (by the person who asked for this) to still hold only seed
    data, not real users -- it does NOT try to distinguish seed rows from
    real ones. Do not run this against a database that has any real
    donor/campaign-owner/organization activity; there is no way back from a
    completed run on a database this blunt.

    "Staff" isn't a separate table -- it's the is_staff=True User rows,
    which the users wipe already includes. The one carve-out is
    is_superuser=True accounts (e.g. the seeded admin@sada.gm), kept on
    purpose so there's still an admin login immediately after this runs.

    Tables outside the named list get touched anyway, for two different
    reasons:
    - apps.payments.Payment is a OneToOneField on Donation with
      on_delete=CASCADE, and apps.payments.Payout is a ForeignKey on
      Campaign with on_delete=CASCADE -- deleting the donation/campaign
      rows deletes these with them at the database level; Django has no
      way to detach a CASCADE child before deleting its parent.
    - apps.design_studio.Poster and .Embed both hold a PROTECT (not
      CASCADE) ForeignKey to Organization -- Django refuses to delete an
      Organization that either still points to, full stop, no cascade.
      Confirmed blocking this command outright on a real run. This command
      deletes Poster/PosterImage/ShareLink/Embed first so Organization
      deletion can go through -- ask before reusing this command if that's
      no longer the right call for whatever is in the DB at the time.
    Nothing else cascades in: apps.ledger (Transaction/Account/LedgerEntry)
    has no FK to any of this -- confirmed in ledger/models.py's own
    comments, it resolves everything through a string reference_code -- so
    it's left exactly as is, including any ledger rows that referenced a
    now-deleted campaign or donation by that code.

    Defaults to a dry run that only counts what would be deleted. Pass
    --confirm to actually run it.
    """

    help = (
        'Deletes all rows from the seed-data categories this was written for '
        '(users, campaigns, donations, activity logs, verifications, '
        'notifications, organizations, reports). Dry-run unless --confirm is '
        'passed. Do not run against a database that holds any real data.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm', action='store_true',
            help='Actually delete. Without this flag, only prints counts.',
        )

    def handle(self, *args, **options):
        from apps.users.models import (
            User, IdentityVerification, Organization, OrganizationVerification, OrganizationChangeRequest,
        )
        from apps.organizations.models import OrganizationRole, OrganizationMembership, OrganizationInvitation
        from apps.campaigns.models import Campaign, CampaignReport
        from apps.donations.models import Donation
        from apps.notifications.models import Notification
        from apps.audit.models import AuditLog
        from apps.design_studio.models import Poster, PosterImage, ShareLink, Embed

        # Deliberately NOT apps.payments.{Payment,Payout} or apps.ledger.* --
        # see the class docstring. Deliberately NOT apps.campaigns.Category,
        # apps.payments.PlatformSettings, or any other app -- not in the
        # list this was asked for.
        targets = [
            ('Notification', Notification.objects.all()),
            ('AuditLog (activity logs)', AuditLog.objects.all()),
            ('IdentityVerification', IdentityVerification.objects.all()),
            ('OrganizationChangeRequest', OrganizationChangeRequest.objects.all()),
            ('OrganizationVerification', OrganizationVerification.objects.all()),
            ('CampaignReport (reports)', CampaignReport.objects.all()),
            ('Donation', Donation.objects.all()),
            ('OrganizationInvitation', OrganizationInvitation.objects.all()),
            ('OrganizationMembership', OrganizationMembership.objects.all()),
            ('OrganizationRole', OrganizationRole.objects.all()),
            # Poster/Embed (+ their cascade children) deleted before Campaign/
            # Organization -- see class docstring, PROTECT FK blocker.
            ('ShareLink', ShareLink.objects.all()),
            ('PosterImage', PosterImage.objects.all()),
            ('Poster', Poster.objects.all()),
            ('Embed', Embed.objects.all()),
            ('Campaign', Campaign.objects.all()),
            ('Organization', Organization.objects.all()),
            ('User (is_superuser=False, includes staff)', User.objects.filter(is_superuser=False)),
        ]
        kept_superusers = User.objects.filter(is_superuser=True)

        self.stdout.write(self.style.WARNING(
            '\nDRY RUN' if not options['confirm'] else '\nCONFIRMED -- deleting for real'
        ))
        self.stdout.write('-' * 60)
        for label, qs in targets:
            self.stdout.write(f'{label:45} {qs.count():>10}')
        self.stdout.write('-' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'{"Kept (is_superuser=True)":45} {kept_superusers.count():>10}'
        ))
        if kept_superusers.exists():
            for u in kept_superusers:
                self.stdout.write(f'  - {u.email}')

        if not options['confirm']:
            self.stdout.write(self.style.WARNING(
                '\nNothing deleted. Re-run with --confirm to actually delete the rows counted above.'
            ))
            return

        with transaction.atomic():
            for label, qs in targets:
                deleted_count, _ = qs.delete()
                self.stdout.write(f'Deleted {deleted_count} from {label}')

        self.stdout.write(self.style.SUCCESS('\nDone.'))

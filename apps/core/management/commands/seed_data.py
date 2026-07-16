from django.core.management.base import BaseCommand
from django.db import transaction
from apps.core.seeders import clear, users, organizations, categories, campaigns, updates, donations, payouts, summary


class Command(BaseCommand):
    help = 'Seed the database with realistic Sada data'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Clear all data before seeding')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['clear']:
            clear.clear_all(self.stdout)

        from apps.campaigns.models import Category
        if not options['clear'] and Category.objects.exists():
            self.stdout.write(self.style.WARNING('Database already seeded — skipping. Use --clear to reseed.'))
            return

        self.stdout.write('Seeding users...')
        all_users = users.seed_users(self.stdout)

        self.stdout.write('Seeding organizations...')
        all_users.update(organizations.seed_organizations(self.stdout))

        self.stdout.write('Seeding categories...')
        cats = categories.seed_categories(self.stdout)

        self.stdout.write('Seeding campaigns...')
        all_campaigns = campaigns.seed_campaigns(self.stdout, all_users, cats)

        self.stdout.write('Seeding campaign updates...')
        updates.seed_updates(self.stdout, all_campaigns, all_users)

        self.stdout.write('Seeding donations...')
        donations.seed_donations(self.stdout, all_campaigns, all_users)

        self.stdout.write('Seeding payouts...')
        payouts.seed_payouts(self.stdout, all_campaigns, all_users)

        self.stdout.write(self.style.SUCCESS('\nDatabase seeded successfully.'))
        summary.print_summary(self.stdout, self.style, all_users, cats, all_campaigns)

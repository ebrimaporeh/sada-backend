from django.core.management.base import BaseCommand
from django.db import transaction
from apps.users.models import User


class Command(BaseCommand):
    help = 'Seed the database with initial data for development'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Clear existing data before seeding')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            User.objects.filter(is_superuser=False).delete()

        self.stdout.write('Seeding users...')
        self._seed_users()
        self.stdout.write(self.style.SUCCESS('Database seeded successfully.'))

    def _seed_users(self):
        users = [
            {
                'email': 'admin@example.com',
                'password': 'Admin@1234',
                'first_name': 'Admin',
                'last_name': 'User',
                'role': User.Role.ADMIN,
                'is_staff': True,
                'is_superuser': True,
                'email_verified': True,
            },
            {
                'email': 'premium@example.com',
                'password': 'Premium@1234',
                'first_name': 'Premium',
                'last_name': 'User',
                'role': User.Role.PREMIUM,
                'email_verified': True,
            },
            {
                'email': 'user@example.com',
                'password': 'User@1234',
                'first_name': 'Regular',
                'last_name': 'User',
                'role': User.Role.USER,
                'email_verified': True,
            },
        ]

        for data in users:
            password = data.pop('password')
            user, created = User.objects.get_or_create(email=data['email'], defaults=data)
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(f'  Created: {user.email}')
            else:
                self.stdout.write(f'  Already exists: {user.email}')

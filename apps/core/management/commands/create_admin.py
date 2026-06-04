from django.core.management.base import BaseCommand
from django.db import transaction
from apps.users.models import User


class Command(BaseCommand):
    help = 'Create a superuser/admin account interactively'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str)
        parser.add_argument('--password', type=str)
        parser.add_argument('--first-name', type=str, default='Admin')
        parser.add_argument('--last-name', type=str, default='')

    @transaction.atomic
    def handle(self, *args, **options):
        email = options.get('email') or input('Email: ')
        password = options.get('password') or input('Password: ')
        first_name = options.get('first_name', 'Admin')
        last_name = options.get('last_name', '')

        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(f'User with email {email} already exists.'))
            return

        user = User.objects.create_superuser(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        self.stdout.write(self.style.SUCCESS(f'Superuser created: {user.email}'))

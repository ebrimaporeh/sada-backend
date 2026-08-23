from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from emails.service import email_service


class Command(BaseCommand):
    help = 'Send a test email through the configured Resend backend to verify email delivery is working.'

    def add_arguments(self, parser):
        parser.add_argument('recipient', type=str, help='Email address to send the test email to')

    def handle(self, *args, **options):
        recipient = options['recipient']

        if not settings.ANYMAIL.get('RESEND_API_KEY'):
            raise CommandError(
                'RESEND_API_KEY is not set. Configure it in your environment before sending test email.'
            )

        self.stdout.write(f'Sending test email to {recipient} via Resend...')
        self.stdout.write(f'  From:     {settings.DEFAULT_FROM_EMAIL}')
        self.stdout.write(f'  Reply-To: {settings.EMAIL_REPLY_TO or "(not set)"}')

        sent = email_service.send_plain_email(
            to=recipient,
            subject=f'{settings.SITE_NAME} — Resend test email',
            message=(
                'This is a test email confirming that Resend is configured correctly '
                f'for {settings.SITE_NAME}.\n\n'
                'If you received this, email delivery via Resend is working.'
            ),
        )

        if sent:
            self.stdout.write(self.style.SUCCESS(f'Test email sent successfully to {recipient}.'))
        else:
            raise CommandError(
                f'Failed to send test email to {recipient}. Check the logs for the underlying Resend/Anymail error.'
            )

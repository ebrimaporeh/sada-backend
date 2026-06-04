from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class EmailService:
    def _send(self, to: str, subject: str, template: str, context: dict) -> bool:
        try:
            html_content = render_to_string(template, context)
            text_content = render_to_string(template.replace('.html', '.txt'), context) if False else ''
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content or subject,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[to],
            )
            msg.attach_alternative(html_content, 'text/html')
            msg.send()
            return True
        except Exception as e:
            logger.error(f'Failed to send email to {to}: {e}')
            return False

    def send_welcome_email(self, user) -> bool:
        return self._send(
            to=user.email,
            subject=f'Welcome to {settings.SITE_NAME}!',
            template='emails/welcome.html',
            context={'user': user, 'site_name': settings.SITE_NAME, 'frontend_url': settings.FRONTEND_URL},
        )

    def send_password_reset_email(self, user, reset_url: str) -> bool:
        return self._send(
            to=user.email,
            subject=f'Reset your {settings.SITE_NAME} password',
            template='emails/password_reset.html',
            context={
                'user': user,
                'reset_url': reset_url,
                'site_name': settings.SITE_NAME,
                'frontend_url': settings.FRONTEND_URL,
            },
        )

    def send_verification_email(self, user, verification_url: str) -> bool:
        return self._send(
            to=user.email,
            subject=f'Verify your {settings.SITE_NAME} email',
            template='emails/verification.html',
            context={
                'user': user,
                'verification_url': verification_url,
                'site_name': settings.SITE_NAME,
            },
        )

    def send_plain_email(self, to: str, subject: str, message: str) -> bool:
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to],
            )
            return True
        except Exception as e:
            logger.error(f'Failed to send email to {to}: {e}')
            return False


email_service = EmailService()

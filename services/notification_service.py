from apps.users.models import User
from emails.service import email_service


def notify_user(user: User, subject: str, message: str) -> None:
    email_service.send_plain_email(
        to=user.email,
        subject=subject,
        message=message,
    )


def notify_admin(subject: str, message: str) -> None:
    from django.conf import settings
    email_service.send_plain_email(
        to=settings.CONTACT_EMAIL,
        subject=f'[Admin] {subject}',
        message=message,
    )

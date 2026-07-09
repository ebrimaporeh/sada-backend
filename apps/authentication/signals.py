from django.dispatch import receiver
from django.conf import settings
from django_rest_passwordreset.signals import reset_password_token_created


@receiver(reset_password_token_created)
def handle_password_reset_token_created(sender, instance, reset_password_token, **kwargs):
    """django-rest-passwordreset deliberately sends no email itself — this is
    the "whoever receives this signal handles sending the email" hook."""
    from emails.tasks import send_password_reset_email_task

    reset_url = f'{settings.FRONTEND_URL.rstrip("/")}/reset-password?token={reset_password_token.key}'
    send_password_reset_email_task.delay(str(reset_password_token.user.id), reset_url)

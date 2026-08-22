from django.dispatch import receiver
from django.conf import settings
from django_rest_passwordreset.signals import reset_password_token_created, post_password_reset


@receiver(reset_password_token_created)
def handle_password_reset_token_created(sender, instance, reset_password_token, **kwargs):
    """django-rest-passwordreset deliberately sends no email itself — this is
    the "whoever receives this signal handles sending the email" hook."""
    from emails.tasks import send_password_reset_email_task

    reset_url = f'{settings.FRONTEND_URL.rstrip("/")}/reset-password?token={reset_password_token.key}'
    send_password_reset_email_task.delay(str(reset_password_token.user.id), reset_url)


@receiver(post_password_reset)
def handle_password_reset_completed(sender, user, **kwargs):
    """Fired by django-rest-passwordreset's own confirm view once the new
    password is actually set -- the meaningful, audit-worthy moment (unlike
    the request step above, which anyone can trigger for any email without
    proving they control it)."""
    import services.audit_service as audit_service
    from apps.audit.models import AuditLog

    audit_service.log(user, AuditLog.Action.USER_PASSWORD_RESET, None, f'{user.full_name} reset their password')

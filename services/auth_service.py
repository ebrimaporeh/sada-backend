from django.contrib.auth import authenticate
from django.core import signing
from django.core.exceptions import ValidationError, PermissionDenied
from django.conf import settings
from django.db.models import Q
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User
from . import user_service

EMAIL_VERIFICATION_SALT = 'email-verification'
EMAIL_VERIFICATION_MAX_AGE = 60 * 60 * 24  # 24 hours, matches the email copy


def _get_tokens_for_user(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }


def generate_email_verification_url(user: User) -> str:
    token = signing.dumps(str(user.id), salt=EMAIL_VERIFICATION_SALT)
    return f'{settings.FRONTEND_URL}/verify-email?token={token}'


def register_user(email: str, password: str, **kwargs) -> tuple[User, dict]:
    from emails.tasks import send_welcome_email_task, send_verification_email_task

    user = user_service.create_user(email=email, password=password, **kwargs)
    tokens = _get_tokens_for_user(user)
    send_welcome_email_task.delay(str(user.id))
    send_verification_email_task.delay(str(user.id), generate_email_verification_url(user))
    return user, tokens


def login_user(email: str, password: str) -> tuple[User, dict]:
    user = authenticate(email=email, password=password)
    if user is None:
        raise ValidationError('Invalid email or password.')
    if not user.is_active:
        raise ValidationError('Your account has been deactivated.')
    if not user.email_verified:
        raise ValidationError('Please verify your email before logging in. Check your inbox for the verification link.')
    tokens = _get_tokens_for_user(user)
    return user, tokens


def change_password(user: User, old_password: str, new_password: str) -> None:
    from emails.tasks import send_password_changed_email_task

    if not user.check_password(old_password):
        raise ValidationError('Old password is incorrect.')
    user.set_password(new_password)
    user.save(update_fields=['password'])
    send_password_changed_email_task.delay(str(user.id))


def set_password(user: User, new_password: str) -> None:
    """For accounts with no usable password yet (Google-only signups) —
    unlike change_password, doesn't require an old password to check."""
    from emails.tasks import send_password_changed_email_task

    if user.has_usable_password():
        raise ValidationError('Your account already has a password. Use change password instead.')
    user.set_password(new_password)
    user.save(update_fields=['password'])
    send_password_changed_email_task.delay(str(user.id))


def verify_email(token: str) -> User:
    try:
        user_id = signing.loads(token, salt=EMAIL_VERIFICATION_SALT, max_age=EMAIL_VERIFICATION_MAX_AGE)
    except signing.SignatureExpired:
        raise ValidationError('This verification link has expired. Please request a new one.')
    except signing.BadSignature:
        raise ValidationError('Invalid verification token.')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        raise ValidationError('Invalid verification token.')

    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=['email_verified'])
    return user


def resend_verification_email(email: str) -> None:
    from emails.tasks import send_verification_email_task

    try:
        user = User.objects.get(email=email.lower())
    except User.DoesNotExist:
        return  # don't leak whether an email is registered
    if user.email_verified:
        return
    send_verification_email_task.delay(str(user.id), generate_email_verification_url(user))


def request_password_reset(email: str) -> None:
    """Drop-in replacement for django-rest-passwordreset's own
    ResetPasswordRequestToken view (see apps/authentication/urls.py for how
    this shadows it at the same URL) — resolves `email` against the
    account's own login email OR, for an organization, either recovery
    email, and sends the reset link to whichever address was actually
    submitted. That's the whole point of a recovery email: it has to work
    even when the primary inbox is inaccessible, so the link can't always
    go to user.email.

    Raises the same "couldn't find an account" error as the package default
    (DJANGO_REST_PASSWORDRESET_NO_INFORMATION_LEAKAGE is unset) to keep
    existing behavior/UX identical for individual accounts.
    """
    from django_rest_passwordreset.models import ResetPasswordToken
    from emails.tasks import send_password_reset_email_task

    email = email.strip().lower()
    not_found_message = "We couldn't find an account associated with that email. Please try a different e-mail address."

    try:
        user = User.objects.get(email__iexact=email)
        send_to = user.email
    except User.DoesNotExist:
        from apps.users.models import Organization
        org = Organization.objects.filter(
            Q(recovery_email_1__iexact=email) | Q(recovery_email_2__iexact=email)
        ).select_related('user').first()
        if org is None:
            raise ValidationError(not_found_message)
        user = org.user
        send_to = email

    if not user.eligible_for_reset():
        raise ValidationError(not_found_message)

    token = user.password_reset_tokens.first() or ResetPasswordToken.objects.create(user=user)
    reset_url = f'{settings.FRONTEND_URL.rstrip("/")}/reset-password?token={token.key}'
    send_password_reset_email_task.delay(str(user.id), reset_url, send_to)

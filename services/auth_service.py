from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError, PermissionDenied
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User
from . import user_service
from emails.service import email_service


def _get_tokens_for_user(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }


def register_user(email: str, password: str, **kwargs) -> tuple[User, dict]:
    user = user_service.create_user(email=email, password=password, **kwargs)
    tokens = _get_tokens_for_user(user)
    email_service.send_welcome_email(user)
    return user, tokens


def login_user(email: str, password: str) -> tuple[User, dict]:
    user = authenticate(email=email, password=password)
    if user is None:
        raise ValidationError('Invalid email or password.')
    if not user.is_active:
        raise ValidationError('Your account has been deactivated.')
    tokens = _get_tokens_for_user(user)
    return user, tokens


def change_password(user: User, old_password: str, new_password: str) -> None:
    if not user.check_password(old_password):
        raise ValidationError('Old password is incorrect.')
    user.set_password(new_password)
    user.save(update_fields=['password'])


def verify_email(token: str) -> None:
    from allauth.account.models import EmailConfirmationHMAC
    try:
        confirmation = EmailConfirmationHMAC.from_key(token)
        confirmation.confirm(request=None)
    except Exception:
        raise ValidationError('Invalid or expired verification token.')

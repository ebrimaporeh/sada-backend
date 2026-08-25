import logging
import requests
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from django.core.exceptions import ValidationError
from decouple import config

from apps.users.models import User

logger = logging.getLogger(__name__)


def verify_google_token(id_token_str: str) -> dict:
    """
    Verify Google ID token and extract user information.

    Uses GOOGLE_OAUTH_CLIENT_ID for verification.
    Does NOT use client secret (it's never transmitted to frontend).

    Args:
        id_token_str: Google ID token from frontend

    Returns:
        dict with 'email', 'name', 'google_sub', 'picture' keys

    Raises:
        ValidationError: If token is invalid, verification fails, or Google
            itself hasn't verified the token's email address (see below —
            this is a real account-takeover vector, not a theoretical one).
    """
    client_id = config('GOOGLE_OAUTH_CLIENT_ID', default=None)
    if not client_id:
        raise ValidationError('Google OAuth is not configured.')

    try:
        # Verify token signature using Google's public certificates
        payload = id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            audience=client_id
        )

        # Verify token hasn't expired (verify_oauth2_token checks this)

        # get_or_create_google_user() logs the caller straight into an
        # *existing* account matching this email with no further
        # confirmation — so this claim is the entire trust boundary for
        # every already-registered account on the platform. Google includes
        # email_verified=False for some accounts (e.g. legacy/Workspace
        # accounts with an admin-added, never-confirmed address); without
        # this check, presenting such a token for someone else's email is a
        # full account takeover requiring no knowledge of their password.
        # Fail closed if the claim is missing entirely.
        if not payload.get('email_verified'):
            raise ValidationError(
                "This Google account's email isn't verified with Google, so it "
                "can't be used to sign in here. Verify it with Google, or sign "
                "in with your password instead."
            )

        # Extract user information
        return {
            'email': payload.get('email'),
            'name': payload.get('name', ''),
            'google_sub': payload.get('sub'),
            'picture': payload.get('picture'),
        }
    except ValueError as e:
        raise ValidationError(f'Invalid Google token: {str(e)}')
    except Exception as e:
        raise ValidationError(f'Token verification failed: {str(e)}')


def _set_avatar_from_google(user: User, picture_url: str) -> None:
    """Best-effort only -- a failed fetch/process must never block the
    signup itself, so any error here is swallowed (and logged) rather than
    raised. Only called for brand-new accounts (see `created` below), so
    this never overwrites an avatar a returning user has since uploaded."""
    if not picture_url:
        return
    try:
        from django.core.files.base import ContentFile
        from services.image_compression import process_image
        response = requests.get(picture_url, timeout=10)
        response.raise_for_status()
        raw = ContentFile(response.content, name='google_avatar.jpg')
        user.avatar = process_image(raw, profile='avatar')
        user.save(update_fields=['avatar'])
    except Exception:
        logger.warning('Failed to fetch Google profile picture for %s', user.email, exc_info=True)


def get_or_create_google_user(google_data: dict) -> tuple[User, bool]:
    """
    Get or create a user from Google OAuth data. Every account this
    creates is an individual (see User.AccountType docstring) -- there is
    no account-type toggle on the signup path anymore.

    Args:
        google_data: dict with 'email', 'name', 'google_sub' keys

    Returns:
        (User instance, created) -- `created` is True only when this call
        made a brand-new account, so callers can tell a first-time Google
        signup apart from a returning user just logging back in (e.g. to
        record Terms acceptance once, not on every login).

    Raises:
        ValidationError: If email is missing
    """
    email = google_data.get('email')
    if not email:
        raise ValidationError('Email not provided by Google.')

    google_sub = google_data.get('google_sub')
    name_parts = google_data.get('name', '').split()

    from django.db import transaction
    with transaction.atomic():
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'first_name': name_parts[0] if name_parts else '',
                'last_name': ' '.join(name_parts[1:]),
                'email_verified': True,  # Google verifies emails
                # is_verified is identity (government ID) verification — a
                # separate manual process regardless of signup method. Google
                # proves email ownership only, not who someone actually is.
                'google_sub': google_sub,
                'account_type': User.AccountType.INDIVIDUAL,
            }
        )

        if created:
            # Otherwise this is left as '', which has_usable_password() treats
            # as a usable (empty) password rather than "no password set".
            user.set_unusable_password()
            user.save(update_fields=['password'])

            _set_avatar_from_google(user, google_data.get('picture'))
        elif google_sub and user.google_sub != google_sub:
            # An existing email/password account signing in via Google for the
            # first time — link it the same way an explicit "Connect Google"
            # action would.
            user.google_sub = google_sub
            user.save(update_fields=['google_sub'])

    # Update last login
    from django.utils import timezone
    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])

    return user, created


def link_google_account(user: User, id_token_str: str) -> User:
    """
    Attach a Google account to an already-authenticated user, e.g. from a
    "Connect Google" button in account settings.

    Raises:
        ValidationError: If the token's email doesn't match the user's own
            email, or if that Google account is already linked elsewhere.
    """
    google_data = verify_google_token(id_token_str)
    google_email = (google_data.get('email') or '').lower()
    if google_email != user.email.lower():
        raise ValidationError("That Google account's email doesn't match your account email.")

    google_sub = google_data.get('google_sub')
    if User.objects.filter(google_sub=google_sub).exclude(pk=user.pk).exists():
        raise ValidationError('That Google account is already linked to another user.')

    user.google_sub = google_sub
    user.save(update_fields=['google_sub'])
    return user

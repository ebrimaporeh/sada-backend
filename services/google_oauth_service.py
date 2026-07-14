from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from django.core.exceptions import ValidationError
from decouple import config

from apps.users.models import User


def verify_google_token(id_token_str: str) -> dict:
    """
    Verify Google ID token and extract user information.

    Uses GOOGLE_OAUTH_CLIENT_ID for verification.
    Does NOT use client secret (it's never transmitted to frontend).

    Args:
        id_token_str: Google ID token from frontend

    Returns:
        dict with 'email', 'name', 'google_sub' keys

    Raises:
        ValidationError: If token is invalid or verification fails
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


def get_or_create_google_user(google_data: dict) -> User:
    """
    Get or create a user from Google OAuth data.

    Args:
        google_data: dict with 'email', 'name', 'google_sub' keys

    Returns:
        User instance

    Raises:
        ValidationError: If email is missing
    """
    email = google_data.get('email')
    if not email:
        raise ValidationError('Email not provided by Google.')

    google_sub = google_data.get('google_sub')

    # Get or create user
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            'first_name': google_data.get('name', '').split()[0],
            'last_name': ' '.join(google_data.get('name', '').split()[1:]),
            'email_verified': True,  # Google verifies emails
            # is_verified is identity (government ID) verification — a
            # separate manual process regardless of signup method. Google
            # proves email ownership only, not who someone actually is.
            'google_sub': google_sub,
        }
    )

    if created:
        # Otherwise this is left as '', which has_usable_password() treats
        # as a usable (empty) password rather than "no password set".
        user.set_unusable_password()
        user.save(update_fields=['password'])
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

    return user


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

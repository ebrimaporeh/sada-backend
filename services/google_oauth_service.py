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
        }
    )

    # Update last login
    from django.utils import timezone
    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])

    return user

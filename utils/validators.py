import re
from django.core.exceptions import ValidationError


def validate_phone_number(value: str) -> None:
    pattern = r'^\+?[1-9]\d{1,14}$'
    if not re.match(pattern, value):
        raise ValidationError('Enter a valid phone number (E.164 format, e.g. +1234567890).')


def validate_image_file(file) -> None:
    from constants.base import MAX_AVATAR_SIZE_BYTES, ALLOWED_AVATAR_TYPES
    if file.size > MAX_AVATAR_SIZE_BYTES:
        raise ValidationError(f'File size must not exceed {MAX_AVATAR_SIZE_BYTES // (1024*1024)} MB.')
    if file.content_type not in ALLOWED_AVATAR_TYPES:
        raise ValidationError(f'Unsupported file type. Allowed: {", ".join(ALLOWED_AVATAR_TYPES)}.')


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise ValidationError('Password must be at least 8 characters.')
    if not re.search(r'[A-Z]', password):
        raise ValidationError('Password must contain at least one uppercase letter.')
    if not re.search(r'[a-z]', password):
        raise ValidationError('Password must contain at least one lowercase letter.')
    if not re.search(r'\d', password):
        raise ValidationError('Password must contain at least one digit.')

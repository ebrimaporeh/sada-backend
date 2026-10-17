import re
from django.core.exceptions import ValidationError


def validate_phone_number(value: str) -> None:
    pattern = r'^\+?[1-9]\d{1,14}$'
    if not re.match(pattern, value):
        raise ValidationError('Enter a valid phone number (E.164 format, e.g. +1234567890).')


# Gambia-only for now (the platform's only supported country) -- not a
# general E.164 rule like validate_phone_number above. PURA's numbering
# reform is complete: every Gambian mobile number is now exactly 9 digits,
# always starting with 8. The old 7-digit format is no longer accepted as
# input anywhere (see migrate_legacy_gambia_phone below for converting
# what's already stored, which is a one-time data migration, not an
# ongoing input-acceptance rule).
GAMBIA_DIAL_CODE = '220'


def normalize_gambia_phone(value: str) -> str:
    """Strips everything but digits, and a leading country code if
    present. Returns the bare local-number digits (not E.164) -- callers
    decide whether/how to re-attach +220."""
    digits = re.sub(r'\D', '', value or '')
    if digits.startswith(GAMBIA_DIAL_CODE):
        digits = digits[len(GAMBIA_DIAL_CODE):]
    return digits


def validate_gambia_phone(value: str) -> str:
    """Validates *and* normalizes to E.164 (+220XXXXXXXXX) -- use as a
    serializer `validate_<field>` method (which can transform the value),
    not as a passive entry in a field's `validators=[...]` list. Blank is
    allowed through unchanged -- every field this backs is optional at the
    model level; pair with `required=True` on the serializer field itself
    if a caller needs to actually require one."""
    if not value:
        return value
    digits = normalize_gambia_phone(value)
    if len(digits) != 9 or not digits.startswith('8'):
        raise ValidationError('Enter a valid Gambian phone number -- 9 digits, starting with 8, after +220.')
    return f'+{GAMBIA_DIAL_CODE}{digits}'


# Old first digit -> new 2-digit prefix, per the numbering reform. Chosen
# so the *last 7 digits* of every converted number are exactly the
# original 7-digit number -- services/modempay_service.py's own
# _local_phone() already extracts an account number by taking the last 7
# digits of whatever it's given, so this conversion needs no matching
# change there; it keeps working unmodified.
_LEGACY_PREFIX_MAP = {
    '7': '87', '2': '87', '4': '87',
    '3': '83', '5': '83',
    '6': '86',
}


def migrate_legacy_gambia_phone(value: str) -> str | None:
    """One-time conversion for an *old*, 7-digit-format stored number to
    the new 9-digit scheme (see apps/users/migrations for where this
    actually runs against existing rows). Returns the converted E.164
    value, or None if `value` isn't a recognizable legacy 7-digit number --
    already-new-format numbers, blanks, and anything with an unmapped
    leading digit are left untouched rather than guessed at."""
    digits = normalize_gambia_phone(value)
    if len(digits) != 7:
        return None
    new_prefix = _LEGACY_PREFIX_MAP.get(digits[0])
    if not new_prefix:
        return None
    return f'+{GAMBIA_DIAL_CODE}{new_prefix}{digits}'


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

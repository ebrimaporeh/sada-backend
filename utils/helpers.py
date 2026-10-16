import uuid
import re
from datetime import datetime


def generate_uuid() -> str:
    return str(uuid.uuid4())


def is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return re.sub(r'^-+|-+$', '', text)


def truncate(text: str, length: int = 100, suffix: str = '...') -> str:
    if len(text) <= length:
        return text
    return text[:length].rstrip() + suffix


def format_date(dt: datetime, fmt: str = '%Y-%m-%d') -> str:
    if dt is None:
        return ''
    return dt.strftime(fmt)


def to_e164_gambia(raw: str) -> str:
    """Normalize a stored phone number (e.g. '+220 7612345', the format
    apps.users.models.User.phone/seeders use) to the E.164 Jokoor's SMS API
    requires ('+2207612345' - no spaces/dashes). Assumes Gambia (+220) when
    no country code is present, since that's the only country this platform
    operates in today. Returns '' for anything that isn't a plausible
    number, so callers can treat an empty result as "don't send" rather than
    pass a bad value to the provider."""
    if not raw:
        return ''
    digits = re.sub(r'[\s()-]', '', raw)
    if not digits.startswith('+'):
        digits = '+220' + digits.lstrip('0')
    if not re.fullmatch(r'\+\d{8,15}', digits):
        return ''
    return digits

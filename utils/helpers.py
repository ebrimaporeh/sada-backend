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

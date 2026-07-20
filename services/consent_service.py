import hashlib


def _current_terms_version() -> str:
    from apps.common.models import LegalContent
    terms_content = LegalContent.get_solo().terms_content
    return hashlib.sha256(terms_content.encode()).hexdigest()[:16]


def record_terms_acceptance(user, ip_address: str = '') -> 'TermsAcceptance':
    from apps.users.models import TermsAcceptance
    return TermsAcceptance.objects.create(
        user=user,
        terms_version=_current_terms_version(),
        ip_address=ip_address or None,
    )


def get_client_ip(request) -> str:
    """The app runs behind Railway's reverse proxy, so REMOTE_ADDR alone is
    the proxy's own address -- X-Forwarded-For (when present) carries the
    real client IP first, with any intermediate proxies after it."""
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')

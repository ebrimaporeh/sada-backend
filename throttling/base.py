from django.conf import settings
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from decouple import config


class CustomAnonThrottle(AnonRateThrottle):
    rate = config('API_RATE_LIMIT_ANON', default='100/hour')


class CustomUserThrottle(UserRateThrottle):
    rate = config('API_RATE_LIMIT_USER', default='1000/hour')


class _DevBypassAnonThrottle(AnonRateThrottle):
    """Anon throttle that no-ops when DEBUG is on, so local dev/testing never gets locked out.

    Tight windows (10 requests/15min) are correct for production brute-force
    protection but trip immediately during normal interactive dev testing.
    """

    def allow_request(self, request, view):
        if settings.DEBUG:
            return True
        return super().allow_request(request, view)


class LoginThrottle(_DevBypassAnonThrottle):
    scope = 'login'
    rate = '10/15min'  # not a valid DRF rate string — parse_rate is overridden below to honor it

    def parse_rate(self, rate):
        return (10, 15 * 60)


class RegisterThrottle(_DevBypassAnonThrottle):
    scope = 'register'
    rate = '10/hour'


class DonationCreateThrottle(_DevBypassAnonThrottle):
    scope = 'donation_create'
    rate = '20/hour'


class ReportCreateThrottle(_DevBypassAnonThrottle):
    scope = 'report_create'
    rate = '10/hour'


class ResendVerificationThrottle(_DevBypassAnonThrottle):
    scope = 'resend_verification'
    rate = '5/hour'

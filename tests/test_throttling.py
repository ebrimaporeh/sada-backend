"""Regression coverage for throttling/base.py::_DevBypassAnonThrottle --
found uncovered during a security audit. security.md flags this as its
#0 priority item: every anti-abuse rate limit in the app (login,
register, donation-create, report-create, resend-verification,
password-reset-request) silently disables itself whenever settings.DEBUG
is True, *regardless of which settings module is active*. That behavior
had no test at all, so a refactor could break either half (the dev
bypass, or the production-mode throttle it's bypassing) with nothing to
catch it.
"""
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User


class LoginThrottleTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email='throttle-test@example.com', password='wrong-is-fine')

    def _attempt(self):
        return self.client.post('/api/v1/auth/login/', {
            'email': 'throttle-test@example.com', 'password': 'definitely-wrong',
        }, format='json')

    @override_settings(DEBUG=True)
    def test_debug_true_never_throttles(self):
        # 15 > LoginThrottle's 10/15min limit -- none of these should 429
        # if DEBUG is actually bypassing it as documented.
        for _ in range(15):
            response = self._attempt()
            self.assertNotEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @override_settings(DEBUG=False)
    def test_debug_false_throttles_after_ten_attempts(self):
        for _ in range(10):
            response = self._attempt()
            self.assertNotEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        response = self._attempt()
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from decouple import config


class CustomAnonThrottle(AnonRateThrottle):
    rate = config('API_RATE_LIMIT_ANON', default='100/hour')


class CustomUserThrottle(UserRateThrottle):
    rate = config('API_RATE_LIMIT_USER', default='1000/hour')


class LoginThrottle(AnonRateThrottle):
    scope = 'login'
    rate = '10/15min'


class RegisterThrottle(AnonRateThrottle):
    scope = 'register'
    rate = '10/hour'

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='auth-register'),
    path('login/', views.LoginView.as_view(), name='auth-login'),
    path('logout/', views.LogoutView.as_view(), name='auth-logout'),
    path('refresh/', TokenRefreshView.as_view(), name='auth-token-refresh'),
    path('change-password/', views.ChangePasswordView.as_view(), name='auth-change-password'),
    path('set-password/', views.SetPasswordView.as_view(), name='auth-set-password'),
    # Shadows django_rest_passwordreset's own request-token view at the exact
    # same URL (config/urls.py includes that package's urls at
    # api/v1/auth/password-reset/) so organizations' recovery emails work
    # too. This resolves first because config/urls.py includes
    # apps.authentication.urls (this file) BEFORE the package's own include —
    # Django tries urlpatterns in list order, so an exact-path match here
    # wins and the request never reaches the package's "" route. The
    # package's confirm/ and validate_token/ sub-paths are untouched and
    # still handled by its own include, since this pattern has no wildcard
    # and only matches the bare password-reset/ path.
    path('password-reset/', views.RequestPasswordResetView.as_view(), name='auth-password-reset-request'),
    path('verify-email/', views.VerifyEmailView.as_view(), name='auth-verify-email'),
    path('resend-verification/', views.ResendVerificationEmailView.as_view(), name='auth-resend-verification'),
    path('google/', views.GoogleOAuthView.as_view(), name='auth-google'),
    path('google/link/', views.GoogleLinkView.as_view(), name='auth-google-link'),
]

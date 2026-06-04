from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='auth-register'),
    path('login/', views.LoginView.as_view(), name='auth-login'),
    path('logout/', views.LogoutView.as_view(), name='auth-logout'),
    path('refresh/', TokenRefreshView.as_view(), name='auth-token-refresh'),
    path('change-password/', views.ChangePasswordView.as_view(), name='auth-change-password'),
    path('verify-email/', views.VerifyEmailView.as_view(), name='auth-verify-email'),
]

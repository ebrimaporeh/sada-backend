from django.urls import path
from . import views

urlpatterns = [
    path('me/', views.MeView.as_view(), name='user-me'),
    path('stats/', views.UserStatsView.as_view(), name='user-stats'),
    path('verification/', views.IdentityVerificationSubmitView.as_view(), name='verification-submit'),
    path('verification/me/', views.MyVerificationView.as_view(), name='verification-me'),
    path('admin/verifications/', views.AdminVerificationListView.as_view(), name='admin-verification-list'),
    path('admin/verifications/<uuid:pk>/<str:action>/', views.AdminVerificationActionView.as_view(), name='admin-verification-action'),
    path('', views.UserListView.as_view(), name='user-list'),
    path('<uuid:pk>/', views.UserDetailView.as_view(), name='user-detail'),
]

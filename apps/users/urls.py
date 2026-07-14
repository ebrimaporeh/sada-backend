from django.urls import path
from . import views

urlpatterns = [
    path('me/', views.MeView.as_view(), name='user-me'),
    path('stats/', views.UserStatsView.as_view(), name='user-stats'),
    # Public routes — must come before the generic <uuid:pk>/ catch-all below.
    path('campaigners/', views.PublicCampaignerListView.as_view(), name='public-campaigner-list'),
    path('campaigners/<uuid:id>/', views.PublicCampaignerDetailView.as_view(), name='public-campaigner-detail'),
    path('verification/', views.IdentityVerificationSubmitView.as_view(), name='verification-submit'),
    path('verification/me/', views.MyVerificationView.as_view(), name='verification-me'),
    path('organization-verification/', views.OrganizationVerificationSubmitView.as_view(), name='organization-verification-submit'),
    path('organization-verification/me/', views.MyOrganizationVerificationView.as_view(), name='organization-verification-me'),
    path('admin/verifications/', views.AdminVerificationListView.as_view(), name='admin-verification-list'),
    path('admin/verifications/<uuid:pk>/<str:action>/', views.AdminVerificationActionView.as_view(), name='admin-verification-action'),
    path('admin/organization-verifications/', views.AdminOrganizationVerificationListView.as_view(), name='admin-organization-verification-list'),
    path('admin/organization-verifications/<uuid:pk>/<str:action>/', views.AdminOrganizationVerificationActionView.as_view(), name='admin-organization-verification-action'),
    path('admin/create/', views.AdminUserCreateView.as_view(), name='admin-user-create'),
    path('admin/staff/', views.AdminStaffListView.as_view(), name='admin-staff-list'),
    path('admin/staff/<uuid:pk>/role/', views.AdminStaffRoleChangeView.as_view(), name='admin-staff-role-change'),
    path('', views.UserListView.as_view(), name='user-list'),
    path('<uuid:pk>/', views.UserDetailView.as_view(), name='user-detail'),
]

from django.urls import path
from . import views

urlpatterns = [
    path('me/', views.MeView.as_view(), name='user-me'),
    path('me/avatar/', views.MyAvatarUploadView.as_view(), name='user-me-avatar'),
    path('stats/', views.UserStatsView.as_view(), name='user-stats'),
    # Public routes — must come before the generic <uuid:pk>/ catch-all below.
    path('campaigners/', views.PublicCampaignerListView.as_view(), name='public-campaigner-list'),
    path('campaigners/<uuid:id>/', views.PublicCampaignerDetailView.as_view(), name='public-campaigner-detail'),
    path('verification/', views.IdentityVerificationSubmitView.as_view(), name='verification-submit'),
    path('verification/me/', views.MyVerificationView.as_view(), name='verification-me'),
    path('organization-verification/', views.OrganizationVerificationSubmitView.as_view(), name='organization-verification-submit'),
    path('organization-verification/me/', views.MyOrganizationVerificationView.as_view(), name='organization-verification-me'),
    path('organization-change-requests/', views.OrganizationChangeRequestSubmitView.as_view(), name='organization-change-request-submit'),
    path('organization-change-requests/mine/', views.MyOrganizationChangeRequestsView.as_view(), name='organization-change-request-mine'),
    path('admin/verifications/', views.AdminVerificationListView.as_view(), name='admin-verification-list'),
    path('admin/verifications/<uuid:pk>/<str:action>/', views.AdminVerificationActionView.as_view(), name='admin-verification-action'),
    path('admin/organization-verifications/', views.AdminOrganizationVerificationListView.as_view(), name='admin-organization-verification-list'),
    path('admin/organization-verifications/<uuid:pk>/<str:action>/', views.AdminOrganizationVerificationActionView.as_view(), name='admin-organization-verification-action'),
    path('admin/organization-change-requests/', views.AdminOrganizationChangeRequestListView.as_view(), name='admin-organization-change-request-list'),
    path('admin/organization-change-requests/<uuid:pk>/<str:action>/', views.AdminOrganizationChangeRequestActionView.as_view(), name='admin-organization-change-request-action'),
    path('admin/create/', views.AdminUserCreateView.as_view(), name='admin-user-create'),
    path('admin/<uuid:pk>/avatar/', views.AdminUserAvatarUploadView.as_view(), name='admin-user-avatar'),
    path('admin/<uuid:pk>/organization-logo/', views.AdminOrganizationLogoUploadView.as_view(), name='admin-organization-logo'),
    path('admin/staff/', views.AdminStaffListView.as_view(), name='admin-staff-list'),
    path('admin/staff/<uuid:pk>/role/', views.AdminStaffRoleChangeView.as_view(), name='admin-staff-role-change'),
    path('', views.UserListView.as_view(), name='user-list'),
    path('<uuid:pk>/', views.UserDetailView.as_view(), name='user-detail'),
]

from django.urls import path
from . import views

urlpatterns = [
    # Specific fixed paths first -- must come before the <uuid:pk>/ catch-alls.
    path('types/', views.OrganizationTypeListView.as_view(), name='organization-type-list'),
    path('mine/', views.MyOrganizationsView.as_view(), name='organization-mine'),
    path('invitations/mine/', views.MyInvitationsView.as_view(), name='organization-invitation-mine'),
    path('invitations/preview/', views.InvitationPreviewView.as_view(), name='organization-invitation-preview'),
    path('invitations/accept/', views.InvitationAcceptView.as_view(), name='organization-invitation-accept'),
    path('invitations/reject/', views.InvitationRejectView.as_view(), name='organization-invitation-reject'),
    path('admin/all/', views.AdminOrganizationListView.as_view(), name='admin-organization-list'),
    path('admin/<uuid:pk>/', views.AdminOrganizationDetailView.as_view(), name='admin-organization-detail'),
    path('admin/<uuid:pk>/members/', views.AdminOrganizationMemberListView.as_view(), name='admin-organization-member-list'),

    path('', views.OrganizationCreateView.as_view(), name='organization-create'),
    path('<uuid:pk>/', views.OrganizationDetailView.as_view(), name='organization-detail'),
    path('<uuid:pk>/transfer-ownership/', views.TransferOwnershipView.as_view(), name='organization-transfer-ownership'),
    path('<uuid:pk>/roles/', views.OrganizationRoleListCreateView.as_view(), name='organization-role-list'),
    path('<uuid:pk>/roles/<uuid:role_id>/', views.OrganizationRoleDetailView.as_view(), name='organization-role-detail'),
    path('<uuid:pk>/members/', views.OrganizationMemberListView.as_view(), name='organization-member-list'),
    path('<uuid:pk>/members/<uuid:user_id>/', views.OrganizationMemberDetailView.as_view(), name='organization-member-detail'),
    path('<uuid:pk>/invitations/', views.OrganizationInvitationListCreateView.as_view(), name='organization-invitation-list'),
    path('<uuid:pk>/invitations/<uuid:invitation_id>/<str:action>/', views.OrganizationInvitationActionView.as_view(), name='organization-invitation-action'),
]

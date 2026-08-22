from django.urls import path
from . import views

urlpatterns = [
    path('roles/', views.AdminRolePermissionsListView.as_view(), name='admin-role-permissions-list'),
    path('roles/<str:role>/', views.AdminRolePermissionsUpdateView.as_view(), name='admin-role-permissions-update'),
]

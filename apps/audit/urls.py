from django.urls import path
from . import views

urlpatterns = [
    path('admin/', views.AdminAuditLogListView.as_view(), name='admin-audit-log-list'),
    path('admin/actions/', views.AuditActionChoicesView.as_view(), name='admin-audit-log-actions'),
    path('admin/actors/', views.AuditActorsListView.as_view(), name='admin-audit-log-actors'),
]

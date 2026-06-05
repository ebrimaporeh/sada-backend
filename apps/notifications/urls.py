from django.urls import path
from . import views

urlpatterns = [
    path('', views.NotificationListView.as_view(), name='notification-list'),
    path('unread-count/', views.UnreadCountView.as_view(), name='notification-unread-count'),
    path('<uuid:pk>/read/', views.NotificationMarkReadView.as_view(), name='notification-read'),
    path('mark-all-read/', views.NotificationMarkAllReadView.as_view(), name='notification-mark-all-read'),
]

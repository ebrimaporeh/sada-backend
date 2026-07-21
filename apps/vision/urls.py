from django.urls import path
from . import views

urlpatterns = [
    path('', views.VisionTopicListView.as_view(), name='vision-topic-list'),
    path('admin/', views.AdminVisionTopicListView.as_view(), name='admin-vision-topic-list'),
    path('admin/<slug:slug>/', views.AdminVisionTopicDetailView.as_view(), name='admin-vision-topic-detail'),
    path('<slug:slug>/', views.VisionTopicDetailView.as_view(), name='vision-topic-detail'),
]

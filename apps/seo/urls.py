from django.urls import path
from . import views

urlpatterns = [
    path('sitemap.xml', views.SitemapView.as_view(), name='sitemap'),
    path('robots.txt', views.robots_txt, name='robots-txt'),
    path('share/campaigns/<slug:slug>/', views.CampaignSharePreviewView.as_view(), name='share-campaign'),
    path('share/campaigners/<uuid:id>/', views.CampaignerSharePreviewView.as_view(), name='share-campaigner'),
    path('share/vision/<slug:slug>/', views.VisionTopicSharePreviewView.as_view(), name='share-vision-topic'),
]

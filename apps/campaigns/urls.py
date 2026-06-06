from django.urls import path
from . import views

urlpatterns = [
    # Specific fixed paths MUST come before the generic <slug> catch-all
    path('', views.CampaignListView.as_view(), name='campaign-list'),
    path('featured/', views.FeaturedCampaignsView.as_view(), name='campaign-featured'),
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('create/', views.CampaignCreateView.as_view(), name='campaign-create'),

    # Owner routes
    path('my/', views.MyCampaignListView.as_view(), name='my-campaign-list'),
    path('my/<slug:slug>/pause/', views.MyCampaignTogglePauseView.as_view(), name='my-campaign-pause'),
    path('my/<slug:slug>/cover/', views.MyCampaignUploadCoverView.as_view(), name='my-campaign-cover'),
    path('my/<slug:slug>/media/', views.CampaignMediaView.as_view(), name='campaign-media'),
    path('my/<slug:slug>/media/<uuid:image_id>/', views.CampaignGalleryImageDeleteView.as_view(), name='campaign-media-delete'),
    path('my/<slug:slug>/updates/', views.CampaignUpdateListCreateView.as_view(), name='campaign-update-create'),
    path('my/<slug:slug>/', views.MyCampaignDetailView.as_view(), name='my-campaign-detail'),

    # Admin routes
    path('admin/all/', views.AdminCampaignListView.as_view(), name='admin-campaign-list'),
    path('admin/<uuid:pk>/action/<str:action>/', views.AdminCampaignActionView.as_view(), name='admin-campaign-action'),

    # Generic slug LAST — catches /campaigns/{slug}/
    path('<slug:slug>/', views.CampaignDetailView.as_view(), name='campaign-detail'),
]

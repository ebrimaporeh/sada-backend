from django.urls import path
from . import views

urlpatterns = [
    # Specific fixed paths MUST come before the generic <slug> catch-all
    path('', views.CampaignListView.as_view(), name='campaign-list'),
    path('featured/', views.FeaturedCampaignsView.as_view(), name='campaign-featured'),
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('categories/<uuid:pk>/', views.AdminCategoryDetailView.as_view(), name='admin-category-detail'),
    path('categories/<uuid:pk>/upload-image/', views.AdminCategoryImageUploadView.as_view(), name='admin-category-image-upload'),
    path('create/', views.CampaignCreateView.as_view(), name='campaign-create'),

    # Owner routes
    path('my/', views.MyCampaignListView.as_view(), name='my-campaign-list'),
    path('my/<slug:slug>/pause/', views.MyCampaignTogglePauseView.as_view(), name='my-campaign-pause'),
    path('my/<slug:slug>/cover/', views.MyCampaignUploadCoverView.as_view(), name='my-campaign-cover'),
    path('my/<slug:slug>/media/', views.CampaignMediaView.as_view(), name='campaign-media'),
    path('my/<slug:slug>/media/<uuid:image_id>/', views.CampaignGalleryImageDeleteView.as_view(), name='campaign-media-delete'),
    path('my/<slug:slug>/updates/', views.CampaignUpdateListCreateView.as_view(), name='campaign-update-create'),
    path('my/<slug:slug>/updates/<uuid:update_id>/', views.CampaignUpdateDetailView.as_view(), name='campaign-update-detail'),
    path('my/<slug:slug>/', views.MyCampaignDetailView.as_view(), name='my-campaign-detail'),

    # Admin routes
    path('admin/all/', views.AdminCampaignListView.as_view(), name='admin-campaign-list'),
    path('admin/stats/', views.AdminCampaignStatsView.as_view(), name='admin-campaign-stats'),
    path('admin/reports/stats/', views.AdminCampaignReportStatsView.as_view(), name='admin-campaign-report-stats'),
    path('admin/reports/', views.AdminCampaignReportsView.as_view(), name='admin-campaign-reports'),
    path('admin/<uuid:pk>/action/<str:action>/', views.AdminCampaignActionView.as_view(), name='admin-campaign-action'),
    path('admin/<uuid:pk>/update/', views.AdminCampaignUpdateView.as_view(), name='admin-campaign-update'),
    path('admin/<uuid:pk>/', views.AdminCampaignDetailView.as_view(), name='admin-campaign-detail'),
    path('admin/<uuid:pk>/status-change/', views.AdminCampaignStatusChangeView.as_view(), name='admin-campaign-status-change'),
    path('admin/<uuid:pk>/media/', views.AdminCampaignMediaView.as_view(), name='admin-campaign-media'),
    path('admin/reports/<uuid:pk>/update/', views.AdminCampaignReportUpdateView.as_view(), name='admin-campaign-report-update'),

    # Report a campaign
    path('<slug:slug>/report/', views.CampaignReportView.as_view(), name='campaign-report'),

    # Generic slug LAST — catches /campaigns/{slug}/
    path('<slug:slug>/', views.CampaignDetailView.as_view(), name='campaign-detail'),
]

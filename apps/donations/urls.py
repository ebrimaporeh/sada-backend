from django.urls import path
from . import views

urlpatterns = [
    path('', views.DonationCreateView.as_view(), name='donation-create'),
    path('my/', views.MyDonationListView.as_view(), name='my-donations'),
    path('verify/<str:reference>/', views.DonationVerifyView.as_view(), name='donation-verify'),
    path('campaign/<slug:slug>/', views.CampaignDonorListView.as_view(), name='campaign-donors'),
    path('campaign/<slug:slug>/public/', views.PublicCampaignDonorListView.as_view(), name='public-campaign-donors'),
    path('admin/all/', views.AdminDonationListView.as_view(), name='admin-donations'),
    path('admin/stats/', views.AdminDonationStatsView.as_view(), name='admin-donation-stats'),
    path('admin/<uuid:pk>/update/', views.AdminDonationUpdateView.as_view(), name='admin-donation-update'),
]

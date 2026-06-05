from django.urls import path
from . import views

urlpatterns = [
    path('', views.DonationCreateView.as_view(), name='donation-create'),
    path('my/', views.MyDonationListView.as_view(), name='my-donations'),
    path('campaign/<slug:slug>/', views.CampaignDonorListView.as_view(), name='campaign-donors'),
    path('admin/all/', views.AdminDonationListView.as_view(), name='admin-donations'),
]

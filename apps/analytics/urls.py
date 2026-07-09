from django.urls import path
from . import views

urlpatterns = [
    path('stats/', views.DashboardStatsView.as_view(), name='dashboard-stats'),
    path('donations-by-day/', views.DonationsByDayView.as_view(), name='donations-by-day'),
    path('campaign-status/', views.CampaignStatusDistributionView.as_view(), name='campaign-status'),
    path('top-campaigns/', views.TopCampaignsView.as_view(), name='top-campaigns'),
    path('top-donors/', views.TopDonorsView.as_view(), name='top-donors'),
    path('recent-donations/', views.RecentDonationsView.as_view(), name='recent-donations'),
    path('finance-summary/', views.FinanceSummaryView.as_view(), name='finance-summary'),
]

from django.urls import path
from . import views

urlpatterns = [
    path('settings/', views.ZakatSettingsView.as_view(), name='zakat-settings'),
    path('calculate/', views.ZakatCalculateView.as_view(), name='zakat-calculate'),
    path('recommended-campaigns/', views.ZakatRecommendedCampaignsView.as_view(), name='zakat-recommended-campaigns'),
]

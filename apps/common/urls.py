from django.urls import path
from . import views

urlpatterns = [
    path('', views.SiteSettingsView.as_view(), name='site-settings'),
    path('legal/', views.LegalContentView.as_view(), name='legal-content'),
]

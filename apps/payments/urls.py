from django.urls import path
from . import views

urlpatterns = [
    path('payouts/', views.PayoutRequestView.as_view(), name='payout-request'),
    # Must come before the <slug:slug>/ catch-all below, or it'd swallow this.
    path('payouts/fee-preview/', views.PayoutFeePreviewView.as_view(), name='payout-fee-preview'),
    path('payouts/<slug:slug>/', views.MyCampaignPayoutListView.as_view(), name='campaign-payouts'),
    path('settings/', views.PlatformSettingsView.as_view(), name='platform-settings'),
    path('webhook/modempay/', views.ModemPayWebhookView.as_view(), name='modempay-webhook'),
]

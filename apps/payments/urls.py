from django.urls import path
from . import views

urlpatterns = [
    path('gateways/', views.GatewayListView.as_view(), name='gateway-list'),
    path('payouts/', views.PayoutRequestView.as_view(), name='payout-request'),
    # Must come before the <slug:slug>/ catch-all below, or it'd swallow this.
    path('payouts/fee-preview/', views.PayoutFeePreviewView.as_view(), name='payout-fee-preview'),
    path('payouts/<slug:slug>/', views.MyCampaignPayoutListView.as_view(), name='campaign-payouts'),
    path('settings/', views.PlatformSettingsView.as_view(), name='platform-settings'),
    # Matches the existing /payments/webhook/modempay/ path unchanged (no
    # dashboard config to update) and resolves any future gateway's webhook
    # (e.g. /payments/webhook/stripe/) at the same route with no URL change.
    path('webhook/<str:gateway_code>/', views.GatewayWebhookView.as_view(), name='gateway-webhook'),
]

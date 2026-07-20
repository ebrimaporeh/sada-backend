from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from permissions.base import HasResourceAccess
from permissions.roles import Resource
from .models import PlatformSettings
from .serializers import (
    PayoutCreateSerializer, PayoutSerializer, PayoutFeePreviewSerializer, PlatformSettingsSerializer,
)
import services.payment_service as payment_service


class GatewayListView(APIView):
    """Which payment gateways/methods are currently enabled — the donation
    and withdrawal forms build their provider picker from this instead of a
    hardcoded frontend constant, so enabling Stripe (or disabling it) is a
    backend settings change, not a frontend deploy."""
    permission_classes = [AllowAny]

    @extend_schema(summary='List enabled payment gateways', responses={200: None})
    def get(self, request):
        return payment_service.success_response({'gateways': payment_service.list_enabled_gateways()})


class PayoutRequestView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Request a payout for a campaign', request=PayoutCreateSerializer, responses={201: PayoutSerializer})
    def post(self, request):
        serializer = PayoutCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payout = payment_service.request_payout(request.user, serializer.validated_data)
        out = PayoutSerializer(payout)
        return payment_service.success_response({'payout': out.data}, status_code=status.HTTP_201_CREATED)


class PayoutFeePreviewView(APIView):
    """Live fee breakdown for the withdrawal form, before the owner
    submits — uses the exact same calculation request_payout does, so the
    preview never drifts from what's actually charged."""
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Preview payout fees for an amount/provider', responses={200: None})
    def get(self, request):
        serializer = PayoutFeePreviewSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        preview = payment_service.preview_payout_fees(
            serializer.validated_data['amount'], serializer.validated_data['provider'],
        )
        if preview is None:
            return payment_service.error_response('Could not calculate fees right now. Please try again shortly.')
        return payment_service.success_response(preview)


class MyCampaignPayoutListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='List payouts for my campaign', responses={200: PayoutSerializer(many=True)})
    def get(self, request, slug):
        payouts = payment_service.get_campaign_payouts(request.user, slug)
        serializer = PayoutSerializer(payouts, many=True)
        return payment_service.success_response({'payouts': serializer.data})


class AdminCampaignPayoutListView(APIView):
    """Admin view of a specific campaign's payout history -- unlike
    MyCampaignPayoutListView, not restricted to the campaign's own owner."""
    permission_classes = [HasResourceAccess]
    required_resource = Resource.FINANCES

    @extend_schema(summary='[Admin] List payouts for a campaign', responses={200: PayoutSerializer(many=True)})
    def get(self, request, campaign_id):
        payouts = payment_service.get_admin_campaign_payouts(campaign_id)
        serializer = PayoutSerializer(payouts, many=True)
        return payment_service.success_response({'payouts': serializer.data})


class PlatformSettingsView(APIView):
    """Public read — the platform fee is already shown to anonymous
    visitors on the public Terms/Help pages (via the {{platform_fee_percent}}
    legal-content variable) and to campaign owners previewing a payout, so
    there's nothing sensitive here worth gating behind login. Only admins
    can change it."""

    required_resource = Resource.SETTINGS

    def get_permissions(self):
        if self.request.method == 'PATCH':
            return [HasResourceAccess()]
        return [AllowAny()]

    @extend_schema(summary='Get current platform settings', responses={200: PlatformSettingsSerializer})
    def get(self, request):
        settings_obj = PlatformSettings.get_solo()
        return payment_service.success_response(PlatformSettingsSerializer(settings_obj).data)

    @extend_schema(summary='[Admin] Update platform settings', request=PlatformSettingsSerializer)
    def patch(self, request):
        settings_obj = PlatformSettings.get_solo()
        serializer = PlatformSettingsSerializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return payment_service.success_response(serializer.data, message='Platform settings updated.')


class GatewayWebhookView(APIView):
    """Generic payment-gateway webhook receiver — /payments/webhook/<gateway_code>/.
    One view for every gateway; which one is resolved from the URL and
    handed to payment_service.handle_webhook(), which looks up that
    gateway's own signature header and event vocabulary via the registry."""
    permission_classes = [AllowAny]
    # Server-to-server traffic authenticated by signature, not by IP-based
    # anon throttling meant for public users — a busy day of donations
    # shouldn't risk a gateway's callbacks getting 429'd.
    throttle_classes = []

    @extend_schema(summary='Payment gateway webhook', exclude=True)
    def post(self, request, gateway_code):
        # The raw body, not the DRF-parsed request.data — signature
        # verification (Stripe's especially) is computed over the exact
        # bytes sent, which a re-serialized dict isn't guaranteed to match.
        result = payment_service.handle_webhook(gateway_code, request.body, request.headers)
        if result:
            return payment_service.success_response({}, message='Webhook processed.')
        return Response({'error': 'Invalid webhook'}, status=status.HTTP_400_BAD_REQUEST)
